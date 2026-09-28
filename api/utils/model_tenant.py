"""Team scope and permissions for model configuration endpoints."""

import inspect
from functools import wraps

from quart import request

from api.apps import current_user
from api.db.services.user_service import UserTenantService
from api.utils.api_utils import get_result
from common.constants import RetCode


def model_tenant_scope(*, manage=False):
    def decorate(func):
        @wraps(func)
        async def wrapper(**kwargs):
            tenant_id = request.headers.get("X-Model-Tenant", "").strip() or current_user.id
            # Own resources use the selected team; shared resources keep their owner scope.
            if request.method == "GET" and request.path.rstrip("/").endswith("/models"):
                owner_id = request.args.get("owner_tenant_id")
                if owner_id and owner_id != current_user.id:
                    tenant_id = owner_id
            membership = UserTenantService.filter_by_tenant_and_user_id(tenant_id, current_user.id)
            if membership is None or membership.role not in ("owner", "normal") or (manage and membership.role != "owner"):
                return get_result(code=RetCode.FORBIDDEN, message="Only team owners can manage model configuration; accepted members can use team models"), 403
            kwargs["tenant_id"] = tenant_id
            if inspect.iscoroutinefunction(func):
                return await func(**kwargs)
            return func(**kwargs)

        return wrapper

    return decorate
