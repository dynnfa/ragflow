#
#  Copyright 2024 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
from datetime import datetime

from peewee import JOIN, fn

from api.constants import DATASET_NAME_LIMIT
from api.db import UserTenantRole
from api.db.db_models import DB, Document, Knowledgebase, KnowledgebaseTeam, Tenant, User, UserCanvas, UserTenant
from api.db.joint_services.tenant_model_service import get_composite_model_name_by_ids
from api.db.services import duplicate_name
from api.db.services.common_service import CommonService, retry_db_operation
from api.db.services.user_service import TenantService
from api.utils.api_utils import get_data_error_result, get_parser_config
from common.constants import StatusEnum
from common.misc_utils import get_uuid
from common.time_utils import current_timestamp, datetime_format


def _base_model_name(embd_id: str) -> str:
    """Return the base model name by stripping provider/instance suffix from an embd_id."""
    parts = embd_id.rsplit("@", 2)
    return parts[0]


def _kb_embedding_base_name(kb, resolved_names) -> str:
    """Resolve a dataset's embedding reference to its base model name.

    ``tenant_embd_id`` — or ``embd_id`` itself when it stores a raw
    tenant_model id — is resolved through ``resolved_names`` (id to
    ``model@instance@provider``). An id that no longer resolves falls back to
    the composite base name when ``embd_id`` holds one, otherwise to the id
    itself so only exact matches group together.
    """
    embd_id = (kb.embd_id or "").strip()
    ref = (getattr(kb, "tenant_embd_id", None) or "").strip()
    if not ref and "@" not in embd_id:
        ref = embd_id
    if not ref:
        return _base_model_name(embd_id)
    composite = resolved_names.get(ref)
    if composite:
        return _base_model_name(composite)
    if embd_id and embd_id != ref:
        return _base_model_name(embd_id)
    return ref


def validate_dataset_embedding_models(kbs):
    """Validate that all given datasets use the same embedding model (or all use none).

    Embedding references are resolved through tenant_model first, so datasets
    storing a raw tenant_model id and datasets storing a legacy
    ``model@instance@provider`` composite compare equal when they point at the
    same model.

    Returns an error message string on failure, or ``None`` on success.
    """
    # Either all datasets have an embedding model, or none do. Mixing is not allowed.
    embd_ids = [kb.embd_id for kb in kbs if kb.embd_id]
    has_embd = len(embd_ids) > 0
    if has_embd and len(embd_ids) != len(kbs):
        return "Cannot search across datasets where some have embedding models and others do not."
    if has_embd:
        candidates = []
        for kb in kbs:
            if not kb.embd_id:
                continue
            ref = (getattr(kb, "tenant_embd_id", None) or "").strip()
            if not ref and "@" not in kb.embd_id:
                ref = kb.embd_id.strip()
            if ref:
                candidates.append(ref)
        try:
            resolved_names = get_composite_model_name_by_ids(candidates)
        except Exception:  # noqa: BLE001 - resolution is best-effort; unresolvable ids keep their raw value
            resolved_names = {}
        embd_nms = {_kb_embedding_base_name(kb, resolved_names) for kb in kbs if kb.embd_id}
        if len(embd_nms) > 1:
            return f"Datasets use different embedding models: {[kb.embd_id for kb in kbs]}"
    return None


class KnowledgebaseService(CommonService):
    """Service class for managing dataset operations.

    This class extends CommonService to provide specialized functionality for dataset
    management, including document parsing status tracking, access control, and configuration
    management. It handles operations such as listing, creating, updating, and deleting
    knowledge bases, as well as managing their associated documents and permissions.

    The class implements a comprehensive set of methods for:
    - Document parsing status verification
    - Knowledge base access control
    - Parser configuration management
    - Tenant-based dataset organization

    Attributes:
        model: The Knowledgebase model class for database operations.
    """

    model = Knowledgebase

    @classmethod
    def _team_ids_for_user(cls, user_id):
        return (
            Tenant.select(Tenant.id)
            .join(UserTenant, on=(UserTenant.tenant_id == Tenant.id))
            .where(
                UserTenant.user_id == user_id,
                UserTenant.status == StatusEnum.VALID.value,
                UserTenant.role.in_([UserTenantRole.OWNER, UserTenantRole.NORMAL]),
                Tenant.status == StatusEnum.VALID.value,
            )
        )

    @classmethod
    def _visibility_and_status_filter(cls, user_id):
        grants = KnowledgebaseTeam.select(KnowledgebaseTeam.kb_id).where(KnowledgebaseTeam.team_id.in_(cls._team_ids_for_user(user_id)))
        return ((cls.model.tenant_id == user_id) | cls.model.id.in_(grants)) & (cls.model.status == StatusEnum.VALID.value)

    @classmethod
    @DB.connection_context()
    def writable(cls, kb_id, user_id):
        return (
            cls.model.select()
            .where(
                cls.model.id == kb_id,
                cls.model.created_by == user_id,
                cls.model.status == StatusEnum.VALID.value,
            )
            .exists()
        )

    @classmethod
    @DB.connection_context()
    def validate_sharing(cls, user_id, data, kb_id=None):
        """Normalize the API scope; explicit team grants own visibility."""
        if "shared_team_ids" not in data and "permission" not in data:
            return
        permission = data.get("permission")
        if permission is not None and permission not in ("me", "team"):
            raise ValueError("permission must be 'me' or 'team'")
        if permission == "me":
            if data.get("shared_team_ids"):
                raise ValueError("Private datasets cannot have shared teams")
            team_ids = []
        else:
            team_ids = data.get("shared_team_ids")
            if team_ids is None:
                if kb_id:
                    team_ids = [g.team_id for g in KnowledgebaseTeam.select().where(KnowledgebaseTeam.kb_id == kb_id)]
                else:
                    team_ids = []
            if not isinstance(team_ids, list) or any(not isinstance(team, str) or not team for team in team_ids):
                raise ValueError("shared_team_ids must be a list of team IDs")
            team_ids = sorted(set(team_ids))
            if permission == "team" and not team_ids:
                raise ValueError("Select at least one team to share the dataset")
        allowed = {team.id for team in cls._team_ids_for_user(user_id)}
        if not set(team_ids).issubset(allowed):
            raise ValueError("You can only share with teams you own or have joined")
        data["shared_team_ids"] = team_ids
        data["permission"] = "team" if team_ids else "me"

    @classmethod
    def _replace_team_grants(cls, kb_id, team_ids):
        KnowledgebaseTeam.delete().where(KnowledgebaseTeam.kb_id == kb_id).execute()
        for team_id in team_ids:
            KnowledgebaseTeam.create(kb_id=kb_id, team_id=team_id)

    @classmethod
    @DB.connection_context()
    def save(cls, **kwargs):
        cls.validate_sharing(kwargs["created_by"], kwargs)
        team_ids = kwargs.pop("shared_team_ids", [])
        kwargs["permission"] = "me"
        with DB.atomic():
            result = cls.model(**kwargs).save(force_insert=True)
            cls._replace_team_grants(kwargs["id"], team_ids)
        return result

    @classmethod
    @DB.connection_context()
    @retry_db_operation
    def update_by_id(cls, pid, data):
        data = dict(data)
        team_ids = data.pop("shared_team_ids", None)
        if team_ids is not None:
            # Grant targets belong to knowledgebase_team. The owner-team flag
            # in the shared table must not expose content to unselected teams.
            data["permission"] = "me"
        with DB.atomic():
            result = cls._update_by_id(pid, data)
            if result and team_ids is not None:
                cls._replace_team_grants(pid, team_ids)
        return result

    @classmethod
    @DB.connection_context()
    def delete_by_id(cls, pid):
        with DB.atomic():
            result = cls.model.delete().where(cls.model.id == pid).execute()
            if result:
                KnowledgebaseTeam.delete().where(KnowledgebaseTeam.kb_id == pid).execute()
        return result

    @classmethod
    @DB.connection_context()
    def with_access(cls, datasets, user_id):
        grants = {}
        for grant in KnowledgebaseTeam.select().where(KnowledgebaseTeam.kb_id.in_([kb["id"] for kb in datasets])):
            grants.setdefault(grant.kb_id, []).append(grant.team_id)
        for kb in datasets:
            kb["shared_team_ids"] = sorted(grants.get(kb["id"], []))
            kb["permission"] = "team" if kb["shared_team_ids"] else "me"
            kb["can_write"] = kb["created_by"] == user_id
        return datasets

    @classmethod
    @DB.connection_context()
    def is_parsed_done(cls, kb_id):
        # Check if all documents in the dataset have completed parsing
        #
        # Args:
        #     kb_id: Knowledge base ID
        #
        # Returns:
        #     If all documents are parsed successfully, returns (True, None)
        #     If any document is not fully parsed, returns (False, error_message)
        from api.db.services.document_service import DocumentService
        from common.constants import TaskStatus

        # Get dataset information
        kbs = cls.query(id=kb_id)
        if not kbs:
            return False, "Knowledge base not found"
        kb = kbs[0]

        # Get all documents in the dataset
        docs, _ = DocumentService.get_by_kb_id(kb_id, 1, 1000, "create_time", True, "", [], [])

        # Check parsing status of each document
        for doc in docs:
            # If document is being parsed, don't allow chat creation
            if doc["run"] == TaskStatus.RUNNING.value or doc["run"] == TaskStatus.CANCEL.value or doc["run"] == TaskStatus.FAIL.value:
                return False, f"Document '{doc['name']}' in dataset '{kb.name}' is still being parsed. Please wait until all documents are parsed before starting a chat."
            # If document is not yet parsed and has no chunks, don't allow chat creation
            if doc["run"] == TaskStatus.UNSTART.value and doc["chunk_num"] == 0:
                return False, f"Document '{doc['name']}' in dataset '{kb.name}' has not been parsed yet. Please parse all documents before starting a chat."

        return True, None

    @classmethod
    @DB.connection_context()
    def list_documents_by_ids(cls, kb_ids):
        # Get document IDs associated with given dataset IDs
        # Args:
        #     kb_ids: List of dataset IDs
        # Returns:
        #     List of document IDs
        doc_ids = cls.model.select(Document.id.alias("document_id")).join(Document, on=(cls.model.id == Document.kb_id)).where(cls.model.id.in_(kb_ids))
        doc_ids = list(doc_ids.dicts())
        doc_ids = [doc["document_id"] for doc in doc_ids]
        return doc_ids

    @classmethod
    @DB.connection_context()
    def get_kb_ids(cls, tenant_id):
        # Get all dataset IDs for a tenant
        # Args:
        #     tenant_id: Tenant ID
        # Returns:
        #     List of dataset IDs
        fields = [
            cls.model.id,
        ]
        kbs = cls.model.select(*fields).where(cls.model.tenant_id == tenant_id)
        kb_ids = [kb.id for kb in kbs]
        return kb_ids

    @classmethod
    @DB.connection_context()
    def get_detail(cls, kb_id):
        # Get detailed information about a dataset
        # Args:
        #     kb_id: Knowledge base ID
        # Returns:
        #     Dictionary containing dataset details
        fields = [
            cls.model.id,
            cls.model.embd_id,
            cls.model.avatar,
            cls.model.name,
            cls.model.language,
            cls.model.description,
            cls.model.permission,
            cls.model.doc_num,
            cls.model.token_num,
            cls.model.chunk_num,
            cls.model.parser_id,
            cls.model.pipeline_id,
            UserCanvas.title.alias("pipeline_name"),
            UserCanvas.avatar.alias("pipeline_avatar"),
            cls.model.parser_config,
            cls.model.pagerank,
            cls.model.graphrag_task_id,
            cls.model.graphrag_task_finish_at,
            cls.model.raptor_task_id,
            cls.model.raptor_task_finish_at,
            cls.model.mindmap_task_id,
            cls.model.mindmap_task_finish_at,
            cls.model.wiki_task_id,
            cls.model.wiki_task_finish_at,
            cls.model.skill_task_id,
            cls.model.skill_task_finish_at,
            cls.model.structure_graph_task_id,
            cls.model.structure_graph_task_finish_at,
            cls.model.structure_mindmap_task_id,
            cls.model.structure_mindmap_task_finish_at,
            cls.model.timeline_task_id,
            cls.model.timeline_task_finish_at,
            cls.model.session_graph_task_id,
            cls.model.session_graph_task_finish_at,
            cls.model.session_essence_task_id,
            cls.model.session_essence_task_finish_at,
            cls.model.structure_task_id,
            cls.model.structure_task_finish_at,
            cls.model.create_time,
            cls.model.update_time,
        ]
        kbs = (
            cls.model.select(*fields)
            .join(UserCanvas, on=(cls.model.pipeline_id == UserCanvas.id), join_type=JOIN.LEFT_OUTER)
            .where((cls.model.id == kb_id), (cls.model.status == StatusEnum.VALID.value))
            .dicts()
        )
        if not kbs:
            return None
        return kbs[0]

    @classmethod
    @DB.connection_context()
    def update_parser_config(cls, id, config):
        # Update parser configuration for a dataset
        # Args:
        #     id: Knowledge base ID
        #     config: New parser configuration
        e, m = cls.get_by_id(id)
        if not e:
            raise LookupError(f"dataset({id}) not found.")

        def dfs_update(old, new):
            # Deep update of nested configuration
            for k, v in new.items():
                if k not in old:
                    old[k] = v
                    continue
                if isinstance(v, dict) and isinstance(old[k], dict):
                    dfs_update(old[k], v)
                elif isinstance(v, list) and isinstance(old[k], list):
                    old[k] = list(set(old[k] + v))
                else:
                    old[k] = v

        dfs_update(m.parser_config, config)
        cls.update_by_id(id, {"parser_config": m.parser_config})

    @classmethod
    @DB.connection_context()
    def delete_field_map(cls, id):
        e, m = cls.get_by_id(id)
        if not e:
            raise LookupError(f"dataset({id}) not found.")

        m.parser_config.pop("field_map", None)
        cls.update_by_id(id, {"parser_config": m.parser_config})

    @classmethod
    @DB.connection_context()
    def get_field_map(cls, ids):
        # Get field mappings for knowledge bases
        # Args:
        #     ids: List of dataset IDs
        # Returns:
        #     Dictionary of field mappings
        conf = {}
        for k in cls.get_by_ids(ids):
            if k.parser_config and "field_map" in k.parser_config:
                conf.update(k.parser_config["field_map"])
        return conf

    @classmethod
    @DB.connection_context()
    def get_by_name(cls, kb_name, tenant_id):
        # Get dataset by name and tenant ID
        # Args:
        #     kb_name: Knowledge base name
        #     tenant_id: Tenant ID
        # Returns:
        #     Tuple of (exists, knowledge_base)
        kb = cls.model.select().where((cls.model.name == kb_name) & (cls.model.tenant_id == tenant_id) & (cls.model.status == StatusEnum.VALID.value))
        if kb:
            return True, kb[0]
        return False, None

    @classmethod
    @DB.connection_context()
    def get_all_ids(cls):
        # Get all dataset IDs
        # Returns:
        #     List of all dataset IDs
        return [m["id"] for m in cls.model.select(cls.model.id).dicts()]

    @classmethod
    @DB.connection_context()
    def create_with_name(cls, *, name: str, tenant_id: str, parser_id: str | None = None, **kwargs):
        """Create a dataset (knowledgebase) by name with kb_app defaults.

        This encapsulates the creation logic used in kb_app.create so other callers
        (including RESTFul endpoints) can reuse the same behavior.

        Returns:
            (ok: bool, model_or_msg): On success, returns (True, Knowledgebase model instance);
                                      on failure, returns (False, error_message).
        """
        # Validate name
        if not isinstance(name, str):
            return False, get_data_error_result(message="Dataset name must be string.")
        dataset_name = name.strip()
        if dataset_name == "":
            return False, get_data_error_result(message="dataset name can't be empty")
        if len(dataset_name.encode("utf-8")) > DATASET_NAME_LIMIT:
            return False, get_data_error_result(message=f"Dataset name length is {len(dataset_name)} which is large than {DATASET_NAME_LIMIT}")

        # Deduplicate name within tenant
        dataset_name = duplicate_name(
            cls.query,
            name=dataset_name,
            tenant_id=tenant_id,
            status=StatusEnum.VALID.value,
        )

        # Verify tenant exists
        ok, _t = TenantService.get_by_id(tenant_id)
        if not ok:
            return False, get_data_error_result(message="Tenant not found.")

        try:
            cls.validate_sharing(tenant_id, kwargs)
        except ValueError as exc:
            return False, str(exc)

        # Build payload
        kb_id = get_uuid()
        payload = {
            "id": kb_id,
            "name": dataset_name,
            "tenant_id": tenant_id,
            "created_by": tenant_id,
            "parser_id": (parser_id or "naive"),
            **kwargs,  # Includes optional fields such as description, language, permission, avatar, parser_config, etc.
        }

        # Update parser_config (always override with validated default/merged config)
        payload["parser_config"] = get_parser_config(parser_id, kwargs.get("parser_config"))
        payload["parser_config"]["llm_id"] = _t.llm_id

        return True, payload

    @classmethod
    @DB.connection_context()
    def get_list(cls, user_id, page_number, items_per_page, orderby, desc, id, name, keywords, parser_id=None, ids=None, owner_ids=None):
        # Get list of knowledge bases with filtering and pagination
        # Args:
        #     user_id: Current user ID
        #     page_number: Page number for pagination
        #     items_per_page: Number of items per page
        #     orderby: Field to order by
        #     desc: Boolean indicating descending order
        #     id: Optional ID filter
        #     name: Optional name filter
        #     keywords: Optional keywords filter
        #     parser_id: Optional parser ID filter
        # Returns:
        #     List of knowledge bases
        #     Total count of knowledge bases
        kbs = cls.model.select()
        if id:
            kbs = kbs.where(cls.model.id == id)
        if ids:
            kbs = kbs.where(cls.model.id.in_(ids))
        if name:
            kbs = kbs.where(cls.model.name == name)
        if keywords:
            kbs = kbs.where(fn.LOWER(cls.model.name).contains(keywords.lower()))
        if parser_id:
            kbs = kbs.where(cls.model.parser_id == parser_id)

        kbs = kbs.where(cls._visibility_and_status_filter(user_id))
        if owner_ids:
            kbs = kbs.where(cls.model.tenant_id.in_(owner_ids))

        if desc:
            kbs = kbs.order_by(cls.model.getter_by(orderby).desc())
        else:
            kbs = kbs.order_by(cls.model.getter_by(orderby).asc())

        total = kbs.count()
        kbs = kbs.paginate(page_number, items_per_page)

        return list(kbs.dicts()), total

    @classmethod
    @DB.connection_context()
    def get_accessible_ids(cls, user_id, ids):
        kbs = cls.model.select(cls.model.id).where(cls.model.id.in_(ids), cls._visibility_and_status_filter(user_id))
        return {kb.id for kb in kbs}

    @classmethod
    @DB.connection_context()
    def get_owner_filter(cls, user_id):
        owners = (
            cls.model.select(
                cls.model.tenant_id.alias("id"),
                User.nickname.alias("label"),
                fn.COUNT(cls.model.id).alias("count"),
            )
            .join(User, on=(cls.model.tenant_id == User.id))
            .where(cls._visibility_and_status_filter(user_id))
            .group_by(cls.model.tenant_id, User.nickname)
        )
        return list(owners.dicts())

    @classmethod
    @DB.connection_context()
    def accessible(cls, kb_id, user_id):
        return (
            cls.model.select()
            .where(
                cls.model.id == kb_id,
                cls._visibility_and_status_filter(user_id),
            )
            .exists()
        )

    @classmethod
    def require_access(cls, kb_ids, user_id):
        """Recheck configured datasets when retrieval executes."""
        if not kb_ids:
            return
        denied = set(kb_ids) - cls.get_accessible_ids(user_id, kb_ids)
        if denied:
            raise PermissionError("No authorization for selected datasets")

    @classmethod
    @DB.connection_context()
    def get_kb_by_id(cls, kb_id, user_id):
        # Get dataset by ID and user ID
        # Args:
        #     kb_id: Knowledge base ID
        #     user_id: User ID
        # Returns:
        #     List containing dataset information
        e, kb = cls.get_by_id(kb_id)
        if not e or not cls.accessible(kb_id, user_id):
            return []
        return cls.with_access([kb.to_dict()], user_id)

    @classmethod
    @DB.connection_context()
    def get_kb_by_name(cls, kb_name, user_id):
        # Get dataset by name and user ID
        # Args:
        #     kb_name: Knowledge base name
        #     user_id: User ID
        # Returns:
        #     List containing dataset information
        kbs = cls.query(name=kb_name, status=StatusEnum.VALID.value)
        for kb in kbs:
            if cls.accessible(kb.id, user_id):
                return cls.with_access([kb.to_dict()], user_id)
        return []

    @classmethod
    @DB.connection_context()
    def atomic_increase_doc_num_by_id(cls, kb_id):
        data = {}
        data["update_time"] = current_timestamp()
        data["update_date"] = datetime_format(datetime.now())
        data["doc_num"] = cls.model.doc_num + 1
        num = cls.model.update(data).where(cls.model.id == kb_id).execute()
        return num

    @classmethod
    @DB.connection_context()
    def update_document_number_in_init(cls, kb_id, doc_num):
        """
        Only use this function when init system
        """
        ok, kb = cls.get_by_id(kb_id)
        if not ok:
            return
        kb.doc_num = doc_num

        dirty_fields = kb.dirty_fields
        if cls.model._meta.combined.get("update_time") in dirty_fields:
            dirty_fields.remove(cls.model._meta.combined["update_time"])

        if cls.model._meta.combined.get("update_date") in dirty_fields:
            dirty_fields.remove(cls.model._meta.combined["update_date"])

        try:
            kb.save(only=dirty_fields)
        except ValueError as e:
            if str(e) == "no data to save!":
                pass  # that's OK
            else:
                raise e

    @classmethod
    @DB.connection_context()
    def decrease_document_num_in_delete(cls, kb_id, doc_num_info: dict):
        kb_row = cls.model.get_by_id(kb_id)
        if not kb_row:
            raise RuntimeError(f"kb_id {kb_id} does not exist")
        update_dict = {
            "doc_num": kb_row.doc_num - doc_num_info["doc_num"],
            "chunk_num": kb_row.chunk_num - doc_num_info["chunk_num"],
            "token_num": kb_row.token_num - doc_num_info["token_num"],
            "update_time": current_timestamp(),
            "update_date": datetime_format(datetime.now()),
        }
        return cls.model.update(update_dict).where(cls.model.id == kb_id).execute()

    @classmethod
    @DB.connection_context()
    def get_null_tenant_embd_id_row(cls):
        fields = [cls.model.id, cls.model.tenant_id, cls.model.embd_id]
        objs = cls.model.select(*fields).where(cls.model.tenant_embd_id.is_null())
        return list(objs)
