"""Dataset grants exercised against SQLite, without external services."""

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from peewee import SqliteDatabase

from api.db.db_models import Knowledgebase, KnowledgebaseTeam, SystemSettings, Tenant, User, UserTenant
from api.db import FileType
from api.db.services.knowledgebase_service import KnowledgebaseService
from api.db.services.user_service import TenantService
import api.db.db_models as models
import api.db.services.knowledgebase_service as kb_services


@pytest.fixture
def database(monkeypatch):
    db = SqliteDatabase(":memory:")
    tables = [Knowledgebase, KnowledgebaseTeam, Tenant, UserTenant, User, SystemSettings]
    # Connection decorators are bound to the production DB at import time.
    # Exercise their SQL bodies with all models bound to the same test DB.
    for service, names in [
        (
            KnowledgebaseService,
            [
                "accessible",
                "writable",
                "validate_sharing",
                "save",
                "update_by_id",
                "with_access",
                "delete_by_id",
                "get_by_id",
                "get_or_none",
                "get_list",
                "get_owner_filter",
                "get_accessible_ids",
                "get_kb_by_id",
                "get_kb_by_name",
            ],
        ),
        (TenantService, ["get_by_id"]),
    ]:
        for name in names:
            method = getattr(service, name)
            monkeypatch.setattr(service, name, classmethod(method.__func__.__wrapped__))
    monkeypatch.setattr(kb_services, "DB", db)
    monkeypatch.setattr(models, "DB", db)
    with db.bind_ctx(tables), db:
        db.create_tables(tables)
        for owner in ["a", "b", "c", "d", "outsider", "invited"]:
            Tenant.create(id=owner, name=owner, embd_id="", llm_id="", asr_id="", img2txt_id="", rerank_id="", parser_ids="naive")
            User.create(id=owner, email=owner + "@test.local", nickname=owner, password="")
            UserTenant.create(id=owner, tenant_id=owner, user_id=owner, role="owner", invited_by=owner)
        for team, member, role in [("a", "b", "normal"), ("a", "c", "normal"), ("d", "b", "normal"), ("a", "invited", "invite")]:
            UserTenant.create(id=team + member, tenant_id=team, user_id=member, role=role, invited_by=team)
        yield db
        db.drop_tables(tables)
    db.close()


def dataset(owner="b", teams=None, kb_id="kb"):
    return KnowledgebaseService.save(id=kb_id, tenant_id=owner, created_by=owner, name=kb_id, embd_id="", shared_team_ids=teams or [])


@pytest.mark.parametrize("reader,expected", [("a", True), ("b", True), ("c", True), ("d", False), ("invited", False), ("outsider", False)])
def test_member_dataset_shared_to_selected_team(database, reader, expected):
    dataset(teams=["a"])
    assert KnowledgebaseService.accessible("kb", reader) is expected
    assert KnowledgebaseService.writable("kb", reader) is (reader == "b")


def test_private_and_multiple_teams(database):
    dataset(kb_id="private")
    dataset(teams=["a", "d"], kb_id="shared")
    assert not KnowledgebaseService.accessible("private", "a")
    assert KnowledgebaseService.accessible("shared", "d")
    assert not KnowledgebaseService.accessible("shared", "outsider")


def test_no_transitive_sharing(database):
    dataset(teams=["d"])
    assert not KnowledgebaseService.accessible("kb", "c")
    assert KnowledgebaseService.accessible("kb", "d")


def test_revocation_and_inactive_membership(database):
    dataset(teams=["a", "d"])
    UserTenant.update(status="0").where(UserTenant.tenant_id == "a", UserTenant.user_id == "c").execute()
    assert not KnowledgebaseService.accessible("kb", "c")
    UserTenant.delete().where(UserTenant.tenant_id == "a", UserTenant.user_id == "c").execute()
    assert not KnowledgebaseService.accessible("kb", "c")
    KnowledgebaseService.update_by_id("kb", {"shared_team_ids": ["d"], "permission": "team"})
    assert not KnowledgebaseService.accessible("kb", "a")
    assert KnowledgebaseService.accessible("kb", "d")
    Tenant.update(status="0").where(Tenant.id == "d").execute()
    assert not KnowledgebaseService.accessible("kb", "d")
    assert KnowledgebaseService.accessible("kb", "b")


@pytest.mark.parametrize(
    "payload",
    [
        {"permission": "team"},
        {"permission": "team", "shared_team_ids": []},
        {"permission": "me", "shared_team_ids": ["a"]},
        {"shared_team_ids": ["outsider"]},
        {"shared_team_ids": "a"},
        {"shared_team_ids": [None]},
        {"permission": "public"},
    ],
)
def test_invalid_sharing_is_rejected(database, payload):
    with pytest.raises(ValueError):
        KnowledgebaseService.validate_sharing("b", payload)


def test_invited_user_cannot_share_to_team(database):
    with pytest.raises(ValueError):
        KnowledgebaseService.validate_sharing("invited", {"shared_team_ids": ["a"]})


def test_grant_normalization_private_reset_and_partial_update(database):
    dataset(teams=["a", "a", "d"])
    assert KnowledgebaseTeam.select().count() == 2
    assert Knowledgebase.get_by_id("kb").permission == "me"
    values = {"name": "renamed"}
    KnowledgebaseService.validate_sharing("b", values, "kb")
    KnowledgebaseService.update_by_id("kb", values)
    assert KnowledgebaseService.accessible("kb", "c")
    values = {"permission": "me"}
    KnowledgebaseService.validate_sharing("b", values, "kb")
    KnowledgebaseService.update_by_id("kb", values)
    assert KnowledgebaseTeam.select().count() == 0
    assert not KnowledgebaseService.accessible("kb", "c")


def test_list_filters_and_details_use_same_grants(database):
    dataset(teams=["a", "d"])
    dataset(owner="c", teams=["a"], kb_id="peer")
    dataset(kb_id="private")
    rows, count = KnowledgebaseService.get_list("a", 1, 20, "name", False, None, None, "")
    assert count == 2
    assert {r["id"] for r in rows} == {"kb", "peer"}
    rows, count = KnowledgebaseService.get_list("a", 1, 20, "name", False, None, None, "", owner_ids=["b"])
    assert count == 1 and rows[0]["id"] == "kb"
    assert {r["id"] for r in KnowledgebaseService.get_owner_filter("a")} == {"b", "c"}
    assert KnowledgebaseService.get_accessible_ids("a", ["kb", "private"]) == {"kb"}
    detail = KnowledgebaseService.get_kb_by_id("kb", "a")[0]
    assert detail["shared_team_ids"] == ["a", "d"]
    assert detail["can_write"] is False
    assert KnowledgebaseService.get_kb_by_id("kb", "b")[0]["can_write"] is True


def test_existing_team_visibility_migrates_once(database):
    Knowledgebase.create(id="old", name="old", tenant_id="a", created_by="a", permission="team", embd_id="")
    models.migrate_knowledgebase_team_sharing()
    assert KnowledgebaseService.accessible("old", "b")
    assert not KnowledgebaseService.accessible("old", "d")
    assert KnowledgebaseTeam.select().get().team_id == "a"
    KnowledgebaseTeam.delete().execute()
    models.migrate_knowledgebase_team_sharing()
    assert KnowledgebaseTeam.select().count() == 0


def test_sharing_update_is_atomic(database, monkeypatch):
    dataset(teams=["a"])

    def fail(*args):
        KnowledgebaseTeam.delete().execute()
        raise RuntimeError("failed insert")

    monkeypatch.setattr(KnowledgebaseService, "_replace_team_grants", fail)
    with pytest.raises(RuntimeError):
        KnowledgebaseService.update_by_id("kb", {"name": "changed", "shared_team_ids": ["d"]})
    assert Knowledgebase.get_by_id("kb").name == "kb"
    assert KnowledgebaseService.accessible("kb", "c")


def _functions(path, names, **scope):
    source = Path(path).read_text()
    nodes = [n for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    for node in nodes:
        node.decorator_list = []
    scope["KnowledgebaseService"] = KnowledgebaseService
    exec(compile(ast.Module(body=nodes, type_ignores=[]), path, "exec"), scope)
    return scope


@pytest.mark.asyncio
async def test_shared_reader_cannot_update_dataset(database):
    dataset(teams=["a"])
    update_dataset = _functions("api/apps/services/dataset_api_service.py", ["update_dataset"])["update_dataset"]
    ok, message = await update_dataset("a", "kb", {"name": "hijacked", "shared_team_ids": ["d"]})
    assert not ok and "lacks permission" in message
    assert Knowledgebase.get_by_id("kb").name == "kb"


def test_deleting_dataset_removes_grants(database):
    dataset(teams=["a", "d"])
    assert KnowledgebaseService.delete_by_id("kb") == 1
    assert KnowledgebaseTeam.select().count() == 0
    assert not KnowledgebaseService.accessible("kb", "a")


def test_runtime_access_is_rechecked_after_revocation(database):
    dataset(teams=["a"])
    KnowledgebaseService.require_access(["kb"], "c")
    KnowledgebaseService.update_by_id("kb", {"shared_team_ids": []})
    with pytest.raises(PermissionError):
        KnowledgebaseService.require_access(["kb"], "c")
    KnowledgebaseService.require_access(["kb"], "b")


def test_member_with_two_grants_gets_one_list_row(database):
    dataset(teams=["a", "d"])
    UserTenant.create(id="dc", tenant_id="d", user_id="c", role="normal", invited_by="d")
    rows, count = KnowledgebaseService.get_list("c", 1, 20, "name", False, None, None, "")
    assert count == 1 and len(rows) == 1


def test_request_scope_is_derived_from_explicit_teams(database):
    from api.utils.validation_utils import CreateDatasetReq

    request = CreateDatasetReq(name="Dataset", shared_team_ids=["a" * 32])
    assert request.permission == "team"


@pytest.mark.asyncio
async def test_leaving_team_removes_own_grants_only(database):
    dataset(teams=["a", "d"])
    dataset(owner="c", teams=["a"], kb_id="peer")
    scope = _functions(
        "api/apps/restful_apis/tenant_api.py",
        ["rm"],
        DB=database,
        Knowledgebase=Knowledgebase,
        KnowledgebaseTeam=KnowledgebaseTeam,
        UserTenant=UserTenant,
        current_user=SimpleNamespace(id="b"),
        get_request_json=AsyncMock(return_value={"user_id": "b"}),
        get_json_result=lambda **kw: kw,
    )
    assert await scope["rm"]("a") == {"data": True}
    assert not KnowledgebaseService.accessible("kb", "c")
    assert KnowledgebaseService.accessible("kb", "d")
    assert KnowledgebaseService.accessible("peer", "a")
    assert not KnowledgebaseService.accessible("peer", "b")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,name,args",
    [
        ("api/apps/restful_apis/chunk_api.py", "parse", ("a", "kb")),
        ("api/apps/restful_apis/document_api.py", "metadata_batch_update", ("kb", "a")),
    ],
)
async def test_shared_reader_cannot_mutate_documents(database, path, name, args):
    dataset(teams=["a"])
    request = AsyncMock()
    scope = _functions(path, [name], get_error_data_result=lambda **kw: kw, get_request_json=request)
    assert "don't own" in (await scope[name](*args))["message"]
    request.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["async_chat", "async_ask", "gen_mindmap", "rag_agent"])
async def test_runtime_entries_deny_revoked_dataset(database, name):
    dataset(teams=["a"])
    KnowledgebaseService.update_by_id("kb", {"shared_team_ids": []})
    scope = _functions("api/db/services/dialog_service.py", [name], logging=Mock())
    with pytest.raises(PermissionError):
        if name in ("async_chat", "rag_agent"):
            await anext(scope[name](SimpleNamespace(kb_ids=["kb"], tenant_id="c"), [], False))
        elif name == "async_ask":
            await anext(scope[name]("Question", ["kb"], "c"))
        else:
            await scope[name]("Question", ["kb"], "c")


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["delete_files", "move_files"])
async def test_file_mutations_preflight_linked_document_permissions(operation):
    file = SimpleNamespace(id="file", created_by="reader", tenant_id="reader", parent_id="root", type="doc", source_type="file", location="object", name="file.txt")
    files = SimpleNamespace(get_by_id=Mock(return_value=(True, file)), get_by_ids=Mock(return_value=[file]), update_by_id=Mock(), delete=Mock())
    storage = SimpleNamespace(rm=Mock(), move=Mock())

    async def run(fn):
        return fn()

    scope = _functions(
        "api/apps/services/file_api_service.py",
        ["_file_writable", operation],
        FileType=FileType,
        FileService=files,
        FileSource=SimpleNamespace(KNOWLEDGEBASE="knowledgebase"),
        File2DocumentService=SimpleNamespace(get_by_file_id=lambda _: [SimpleNamespace(document_id="doc")]),
        DocumentService=SimpleNamespace(writable=lambda *_: False),
        settings=SimpleNamespace(STORAGE_IMPL=storage),
        thread_pool_exec=run,
    )
    if operation == "delete_files":
        ok, result = await scope[operation]("reader", ["file"])
        assert result["success_count"] == 0
    else:
        ok, _ = await scope[operation]("reader", ["file"], new_name="rename.txt")
    assert not ok
    storage.rm.assert_not_called()
    storage.move.assert_not_called()
    files.update_by_id.assert_not_called()
    files.delete.assert_not_called()
