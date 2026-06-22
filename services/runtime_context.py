from typing import Any, Dict, Optional

from services import cache_service
from utils.config_service import get_runtime_config
from utils.logger import debug


def get_cached_runtime_config(key: str, default: Any = None, page_config: Optional[Dict] = None) -> Any:
    return get_runtime_config(key, default, page_config)


def get_cached_page(page_id: Optional[str]) -> Dict:
    if not page_id:
        return {}
    from services.runtime_store import runtime_store
    return runtime_store.get_page(str(page_id)) or {}


def get_cached_app_secrets() -> list:
    from services.runtime_store import runtime_store

    secrets, seen = [], set()
    with runtime_store.lock:
        pages = list(runtime_store.pages_by_id.values())
    for page in pages:
        secret = (page.get("app_secret") or "").strip()
        if secret and secret not in seen:
            secrets.append(secret)
            seen.add(secret)
    return secrets


def get_cached_expertise(expertise_key: Optional[str]) -> Dict:
    if not expertise_key:
        return {}
    from services.runtime_store import runtime_store
    return runtime_store.get_expertise(expertise_key) or {}


def get_cached_skill(skill_name: Optional[str]) -> Dict:
    return get_cached_expertise(skill_name)


def get_cached_skill_fields(skill_name: Optional[str]) -> list:
    expertise = get_cached_expertise(skill_name)
    return list(expertise.get("data_fields") or [])


def build_runtime_context(
    page: Optional[Dict] = None,
    page_id: Optional[str] = None,
    sender_psid: Optional[str] = None,
) -> Dict:
    from services.runtime_store import runtime_store

    page_id = str(page_id or (page or {}).get("page_id") or "default_page")
    context = runtime_store.get_context(page_id)
    if not context and page_id != "default_page":
        context = runtime_store.reload_page(page_id)
    context = dict(context or {})
    if not context:
        return {}
    context["sender_psid"] = sender_psid
    expertise = context.get("expertise") or {}
    debug(
        f"[RUNTIME_CONTEXT] source=memory page_id={page_id} "
        f"expertise={expertise.get('id')} domain={context.get('domain')} "
        f"rows={len(context.get('data_rows') or [])}"
    )
    return context


def clear_page_context(page_id: Optional[str] = None) -> None:
    from services.runtime_store import runtime_store

    if page_id:
        runtime_store.reload_page(page_id)
    else:
        runtime_store.reload_all()
    cache_service.delete_prefix("page:")
    cache_service.delete_prefix("runtime_context:")
    debug(f"[CACHE_INVALIDATE] page_id={page_id or '*'} keys=page,runtime_context")


def clear_skill_context(skill_name: Optional[str] = None) -> None:
    from services.runtime_store import runtime_store

    if skill_name:
        runtime_store.reload_expertise(skill_name)
    else:
        runtime_store.reload_all()
    for prefix in (
        "expertise:", "rag_records:", "runtime_context:", "catalog_summary:",
        "table_schema:", "data_table:",
    ):
        cache_service.delete_prefix(prefix)
    debug(f"[CACHE_INVALIDATE] expertise_id={skill_name or '*'}")


def clear_runtime_config_context(key: Optional[str] = None) -> None:
    from services.runtime_store import runtime_store

    runtime_store.reload_all()
    cache_service.delete_prefix("runtime_config:")
    debug(f"[CACHE_INVALIDATE] runtime_config={key or '*'}")


def clear_inventory_context(expertise_id: Optional[int] = None) -> None:
    from services.runtime_store import runtime_store

    if expertise_id is not None:
        runtime_store.reload_data_table(expertise_id)
    else:
        runtime_store.reload_all()
    for prefix in ("inventory:", "data_table:", "catalog_summary:", "table_schema:"):
        cache_service.delete_prefix(prefix)


def clear_app_secret_context() -> None:
    cache_service.delete("app_secret:list")
