import json
import threading
import time
from datetime import datetime
from typing import Dict, Optional

from brain.knowledge_retriever import parse_training_records
from services.search_index import SearchIndex, normalize_text
from utils.config_service import get_runtime_int, load_config_cache
from utils.logger import debug


def _json_dict(value) -> Dict:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def _json_value(value, default):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return default


def _expertise_key(expertise: Dict, persona: Dict) -> str:
    return str(
        expertise.get("key")
        or persona.get("legacy_skill_id")
        or persona.get("skill_id")
        or expertise.get("id")
        or ""
    ).strip()


def _domain_from_text(value: str) -> str:
    text = normalize_text(value)
    if any(token in text for token in ("bien so", "bien xe", "license plate", "plate sales")):
        return "license_plate"
    if any(token in text for token in ("quan ao", "thoi trang", "fashion", "clothes")):
        return "fashion"
    return ""


def resolve_domain(expertise: Dict, persona: Dict) -> str:
    for value in (
        expertise.get("domain"),
        persona.get("domain"),
        persona.get("legacy_skill_id"),
        expertise.get("key"),
        expertise.get("name"),
        expertise.get("job_title"),
    ):
        explicit = str(value or "").strip().lower()
        if explicit in {"fashion", "license_plate", "generic_commerce"}:
            return explicit
        inferred = _domain_from_text(value)
        if inferred:
            return inferred
    return "generic_commerce"


def resolve_domain_label(expertise: Dict, persona: Dict, domain: str) -> str:
    if domain == "fashion":
        return "quần áo"
    if domain == "license_plate":
        return "biển số"
    info = persona.get("thong_tin") if isinstance(persona.get("thong_tin"), dict) else {}
    return str(
        info.get("vai_tro")
        or info.get("mo_ta")
        or expertise.get("name")
        or expertise.get("job_title")
        or "sản phẩm"
    ).strip()


class RuntimeStore:
    def __init__(self):
        self.pages_by_id = {}
        self.expertises_by_id = {}
        self.expertises_by_key = {}
        self.contexts_by_page_id = {}
        self.data_by_expertise_id = {}
        self.indexes_by_expertise_id = {}
        self.loaded_at = None
        self.version = 0
        self.lock = threading.RLock()

    def _load_rows(self, data_table: str):
        if not data_table:
            return []
        from database.dynamic_table_manager import list_dynamic_rows

        max_rows = get_runtime_int("MAX_PRELOAD_ROWS", 0)
        limit = max_rows if max_rows > 0 else 1_000_000_000
        return list_dynamic_rows(data_table, limit=limit)

    def _build_expertise(self, expertise: Dict, load_rows=True) -> Dict:
        persona = _json_dict(expertise.get("persona_json"))
        domain = resolve_domain(expertise, persona)
        domain_label = resolve_domain_label(expertise, persona, domain)
        rows = self._load_rows(expertise.get("data_table") or "") if load_rows else []
        fields = _json_value(expertise.get("data_fields_json"), [])
        field_map = {
            str(field.get("key") or field.get("field_key")): str(field.get("label") or field.get("field_label") or "")
            for field in fields if isinstance(field, dict) and (field.get("key") or field.get("field_key"))
        }
        index = SearchIndex(
            rows,
            field_map=field_map,
            domain=domain,
            data_fields_json=expertise.get("data_fields_json"),
        )
        records = parse_training_records(expertise.get("training_content") or "")
        item = dict(expertise)
        item.update({
            "expertise_id": expertise.get("id"),
            "expertise_key": _expertise_key(expertise, persona),
            "expertise_name": expertise.get("name") or "",
            "domain": domain,
            "domain_label": domain_label,
            "domain_plugin": domain,
            "persona": persona,
            "knowledge_records": records,
            "parsed_knowledge_records": records,
            "data_fields": fields,
            "field_map": field_map,
            "format": persona.get("format") or {},
            "skill_config": dict(expertise),
            "data_rows": rows,
            "search_index": index,
        })
        return item

    @staticmethod
    def _page_runtime(page: Dict, expertise: Optional[Dict]) -> Dict:
        item = dict(page)
        item["expertise_id"] = expertise.get("id") if expertise else None
        return item

    @staticmethod
    def _context(page: Dict, expertise: Dict) -> Dict:
        return {
            "page": page,
            "page_id": page.get("page_id"),
            "page_name": page.get("page_name") or "Unknown",
            "page_access_token": page.get("page_access_token") or "",
            "ai_skill": page.get("ai_skill") or "",
            "skill": page.get("ai_skill") or "",
            "expertise_id": expertise.get("id"),
            "expertise": expertise,
            "skill_config": expertise.get("skill_config") or expertise,
            "persona_json": expertise.get("persona_json") or "{}",
            "training_content": expertise.get("training_content") or "",
            "data_table": expertise.get("data_table") or "",
            "data_fields_json": expertise.get("data_fields_json") or "[]",
            "domain": expertise.get("domain"),
            "domain_label": expertise.get("domain_label"),
            "domain_plugin": expertise.get("domain_plugin"),
            "knowledge_records": expertise.get("knowledge_records") or [],
            "data_rows": expertise.get("data_rows") or [],
            "search_index": expertise.get("search_index"),
            "ai_provider": page.get("ai_provider") or "ollama",
            "ai_model": page.get("ai_model") or "",
            "ai_provider_token": page.get("ai_provider_token") or "",
            "intent_parser_provider": page.get("intent_parser_provider") or "",
            "intent_parser_model": page.get("intent_parser_model") or "",
            "intent_parser_token": page.get("intent_parser_token") or "",
            "use_llm_intent_parser": page.get("use_llm_intent_parser") or "",
        }

    @staticmethod
    def _find_expertise(expertises_by_id, expertises_by_key, key):
        text = str(key or "").strip()
        if not text:
            return None
        try:
            found = expertises_by_id.get(int(text))
            if found:
                return found
        except ValueError:
            pass
        return expertises_by_key.get(text) or expertises_by_key.get(text.lower())

    def load_all(self):
        started = time.perf_counter()
        debug("[RUNTIME_STORE] load_all start")
        load_config_cache(force=True)
        from database.expertise_manager import list_expertises
        from database.page_manager import get_all_pages

        expertises_by_id = {}
        expertises_by_key = {}
        data_by_expertise_id = {}
        indexes_by_expertise_id = {}
        for raw in list_expertises():
            expertise = self._build_expertise(raw)
            expertise_id = int(expertise["id"])
            expertises_by_id[expertise_id] = expertise
            keys = {
                str(expertise_id),
                expertise.get("expertise_key") or "",
                expertise.get("name") or "",
                expertise.get("job_title") or "",
            }
            for key in keys:
                if key:
                    expertises_by_key[str(key)] = expertise
                    expertises_by_key[str(key).lower()] = expertise
            data_by_expertise_id[expertise_id] = expertise["data_rows"]
            indexes_by_expertise_id[expertise_id] = expertise["search_index"]
            debug(
                f"[RUNTIME_STORE] expertise_id={expertise_id} "
                f"key={expertise.get('expertise_key')} domain={expertise.get('domain')} "
                f"rows={len(expertise['data_rows'])}"
            )

        pages_by_id = {}
        contexts_by_page_id = {}
        for raw_page in get_all_pages():
            if not raw_page.get("is_active"):
                continue
            expertise = self._find_expertise(expertises_by_id, expertises_by_key, raw_page.get("ai_skill"))
            page = self._page_runtime(raw_page, expertise)
            page_id = str(page.get("page_id") or "")
            if not page_id:
                continue
            pages_by_id[page_id] = page
            if expertise:
                contexts_by_page_id[page_id] = self._context(page, expertise)

        with self.lock:
            self.pages_by_id = pages_by_id
            self.expertises_by_id = expertises_by_id
            self.expertises_by_key = expertises_by_key
            self.contexts_by_page_id = contexts_by_page_id
            self.data_by_expertise_id = data_by_expertise_id
            self.indexes_by_expertise_id = indexes_by_expertise_id
            self.loaded_at = datetime.utcnow()
            self.version += 1
        duration_ms = int((time.perf_counter() - started) * 1000)
        debug(
            f"[RUNTIME_STORE] loaded pages={len(pages_by_id)} "
            f"expertises={len(expertises_by_id)} rows_total="
            f"{sum(len(rows) for rows in data_by_expertise_id.values())} duration_ms={duration_ms}"
        )
        return self

    def get_page(self, page_id) -> Dict:
        with self.lock:
            return self.pages_by_id.get(str(page_id), {})

    def get_expertise(self, key) -> Dict:
        with self.lock:
            return self._find_expertise(self.expertises_by_id, self.expertises_by_key, key) or {}

    def get_context(self, page_id) -> Dict:
        with self.lock:
            return self.contexts_by_page_id.get(str(page_id), {})

    def reload_all(self):
        debug("[RUNTIME_RELOAD] type=all")
        return self.load_all()

    def reload_expertise(self, expertise_id):
        from database.expertise_manager import get_expertise

        raw = get_expertise(expertise_id)
        if not raw:
            return self.reload_all()
        expertise = self._build_expertise(raw)
        with self.lock:
            old = self.expertises_by_id.get(int(expertise["id"]))
            pages = [dict(page) for page in self.pages_by_id.values()]
            if old:
                old_keys = [key for key, value in self.expertises_by_key.items() if value is old]
                for key in old_keys:
                    self.expertises_by_key.pop(key, None)
            self.expertises_by_id[int(expertise["id"])] = expertise
            for key in {
                str(expertise["id"]), expertise.get("expertise_key"), expertise.get("name"), expertise.get("job_title")
            }:
                if key:
                    self.expertises_by_key[str(key)] = expertise
                    self.expertises_by_key[str(key).lower()] = expertise
            self.data_by_expertise_id[int(expertise["id"])] = expertise["data_rows"]
            self.indexes_by_expertise_id[int(expertise["id"])] = expertise["search_index"]
            for page in pages:
                if page.get("expertise_id") == expertise["id"] or str(page.get("ai_skill")) in {
                    str(expertise["id"]), expertise.get("expertise_key"), expertise.get("name")
                }:
                    page["expertise_id"] = expertise["id"]
                    self.pages_by_id[str(page["page_id"])] = page
                    self.contexts_by_page_id[str(page["page_id"])] = self._context(page, expertise)
            self.version += 1
        debug(
            f"[RUNTIME_RELOAD] type=expertise expertise_id={expertise['id']} "
            f"domain={expertise['domain']} rows={len(expertise['data_rows'])}"
        )
        return expertise

    def reload_page(self, page_id):
        from database.page_manager import get_page

        raw_page = get_page(str(page_id))
        with self.lock:
            if not raw_page:
                self.pages_by_id.pop(str(page_id), None)
                self.contexts_by_page_id.pop(str(page_id), None)
                self.version += 1
                return {}
            expertise = self._find_expertise(
                self.expertises_by_id, self.expertises_by_key, raw_page.get("ai_skill")
            )
            page = self._page_runtime(raw_page, expertise)
            self.pages_by_id[str(page_id)] = page
            if expertise:
                self.contexts_by_page_id[str(page_id)] = self._context(page, expertise)
            else:
                self.contexts_by_page_id.pop(str(page_id), None)
            self.version += 1
        debug(
            f"[RUNTIME_RELOAD] type=page page_id={page_id} "
            f"expertise={expertise.get('id') if expertise else ''}"
        )
        return self.get_context(page_id)

    def reload_data_table(self, expertise_id):
        expertise_id = int(expertise_id)
        with self.lock:
            current = self.expertises_by_id.get(expertise_id)
        if not current:
            return self.reload_expertise(expertise_id)
        rows = self._load_rows(current.get("data_table") or "")
        index = SearchIndex(
            rows,
            field_map=current.get("field_map"),
            domain=current.get("domain"),
            data_fields_json=current.get("data_fields_json"),
        )
        updated = dict(current)
        updated["data_rows"] = rows
        updated["search_index"] = index
        self._replace_expertise_snapshot(updated)
        debug(f"[RUNTIME_RELOAD] type=data_table expertise_id={expertise_id} rows={len(rows)}")
        return updated

    def reload_rag(self, expertise_id):
        from database.expertise_manager import get_expertise

        raw = get_expertise(expertise_id)
        if not raw:
            return {}
        with self.lock:
            current = self.expertises_by_id.get(int(raw["id"]))
        if not current:
            return self.reload_expertise(expertise_id)
        records = parse_training_records(raw.get("training_content") or "")
        updated = dict(current)
        updated["training_content"] = raw.get("training_content") or ""
        updated["knowledge_records"] = records
        updated["parsed_knowledge_records"] = records
        self._replace_expertise_snapshot(updated)
        debug(f"[RUNTIME_RELOAD] type=rag expertise_id={raw['id']} records={len(records)}")
        return updated

    def _replace_expertise_snapshot(self, expertise):
        expertise_id = int(expertise["id"])
        with self.lock:
            old = self.expertises_by_id.get(expertise_id)
            self.expertises_by_id[expertise_id] = expertise
            for key, value in list(self.expertises_by_key.items()):
                if value is old:
                    self.expertises_by_key[key] = expertise
            self.data_by_expertise_id[expertise_id] = expertise.get("data_rows") or []
            self.indexes_by_expertise_id[expertise_id] = expertise.get("search_index")
            for page_id, context in list(self.contexts_by_page_id.items()):
                if context.get("expertise_id") == expertise_id:
                    self.contexts_by_page_id[page_id] = self._context(
                        self.pages_by_id[page_id], expertise
                    )
            self.version += 1


runtime_store = RuntimeStore()


def load_all():
    return runtime_store.load_all()


def reload_all():
    return runtime_store.reload_all()


def reload_expertise(expertise_id):
    return runtime_store.reload_expertise(expertise_id)


def reload_page(page_id):
    return runtime_store.reload_page(page_id)


def reload_data_table(expertise_id):
    return runtime_store.reload_data_table(expertise_id)


def reload_rag(expertise_id):
    return runtime_store.reload_rag(expertise_id)


def get_context(page_id):
    return runtime_store.get_context(page_id)
