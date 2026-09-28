"""Model team permissions, tested without external services."""

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch


def load_scope(request, membership):
    modules = {}
    for name, attrs in {
        "quart": {"request": request},
        "api.apps": {"current_user": SimpleNamespace(id="member")},
        "api.db.services.user_service": {"UserTenantService": SimpleNamespace(filter_by_tenant_and_user_id=membership)},
        "api.utils.api_utils": {"get_result": lambda **kwargs: kwargs},
        "common.constants": {"RetCode": SimpleNamespace(FORBIDDEN=403)},
    }.items():
        module = ModuleType(name)
        module.__dict__.update(attrs)
        modules[name] = module
    path = Path(__file__).resolve().parents[4] / "api/utils/model_tenant.py"
    spec = importlib.util.spec_from_file_location("model_tenant_under_test", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module.model_tenant_scope


class ModelTenantScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_member_reads_owner_scope_without_changing_actor(self):
        membership = Mock(return_value=SimpleNamespace(role="normal"))
        request = SimpleNamespace(headers={"X-Model-Tenant": "owner"}, args={}, method="GET", path="/api/v1/models/default")
        scope = load_scope(request, membership)

        @scope()
        def list_models(tenant_id):
            return tenant_id

        self.assertEqual(await list_models(), "owner")
        membership.assert_called_once_with("owner", "member")

    async def test_only_owner_can_change_configuration_or_read_credentials(self):
        for role in ("owner", "normal", "invite", None):
            with self.subTest(role=role):
                membership = Mock(return_value=SimpleNamespace(role=role) if role else None)
                request = SimpleNamespace(headers={"X-Model-Tenant": "owner"}, args={}, method="PATCH", path="/api/v1/models/default")
                scope = load_scope(request, membership)
                action = Mock(return_value="saved")
                result = await scope(manage=True)(action)()
                if role == "owner":
                    self.assertEqual(result, "saved")
                    action.assert_called_once_with(tenant_id="owner")
                else:
                    self.assertEqual(result[1], 403)
                    action.assert_not_called()

    async def test_pending_removed_and_unrelated_users_cannot_read_team_models(self):
        for role in ("invite", None):
            with self.subTest(role=role):
                membership = Mock(return_value=SimpleNamespace(role=role) if role else None)
                request = SimpleNamespace(headers={"X-Model-Tenant": "owner"}, args={}, method="GET", path="/api/v1/models")
                action = Mock()
                result = await load_scope(request, membership)()(action)()
                self.assertEqual(result[1], 403)
                action.assert_not_called()

    async def test_resource_owner_overrides_selected_team_with_membership_check(self):
        membership = Mock(return_value=SimpleNamespace(role="normal"))
        request = SimpleNamespace(headers={"X-Model-Tenant": "selected-team"}, args={"owner_tenant_id": "resource-owner"}, method="GET", path="/api/v1/models")
        action = Mock(return_value="models")
        await load_scope(request, membership)()(action)()
        membership.assert_called_once_with("resource-owner", "member")
        action.assert_called_once_with(tenant_id="resource-owner")

    async def test_own_resources_use_selected_team_models(self):
        membership = Mock(return_value=SimpleNamespace(role="normal"))
        request = SimpleNamespace(headers={"X-Model-Tenant": "selected-team"}, args={"owner_tenant_id": "member"}, method="GET", path="/api/v1/models")
        action = Mock()
        await load_scope(request, membership)()(action)()
        membership.assert_called_once_with("selected-team", "member")
        action.assert_called_once_with(tenant_id="selected-team")

    async def test_missing_header_keeps_own_team_and_supports_async_routes(self):
        membership = Mock(return_value=SimpleNamespace(role="owner"))
        request = SimpleNamespace(headers={}, args={}, method="PATCH", path="/api/v1/models/default")
        scope = load_scope(request, membership)

        @scope(manage=True)
        async def save(tenant_id):
            return tenant_id

        self.assertEqual(await save(), "member")
        membership.assert_called_once_with("member", "member")


if __name__ == "__main__":
    unittest.main()
