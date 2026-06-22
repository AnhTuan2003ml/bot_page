import json
import re
import unicodedata
from typing import Any, Dict, List


def normalize_text(text: str) -> str:
    value = unicodedata.normalize("NFD", str(text or "").lower())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("đ", "d")
    value = re.sub(r"[^a-z0-9]+", " ", value).strip()
    return re.sub(r"\s+", " ", value)


def parse_row(row: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    value = row.get("content", row)
    if isinstance(value, dict):
        data = dict(value)
    else:
        text = str(value or "")
        try:
            parsed = json.loads(text)
            data = parsed if isinstance(parsed, dict) else {"content": text}
        except (TypeError, ValueError):
            data = {}
            for line in text.splitlines():
                if ":" not in line:
                    continue
                key, item_value = line.split(":", 1)
                key = key.strip()
                if key:
                    data[key] = item_value.strip()
            if not data:
                data = {"content": text}
    if row.get("id") not in (None, ""):
        data.setdefault("id", row.get("id"))
    return data


def key_norm(value: str) -> str:
    return normalize_text(value).replace(" ", "_")


ALIASES = {
    "item_code": {"id", "code", "ma", "ma_san_pham", "sku", "item_code", "bien_so", "ma_bien", "ma_bien_so", "ma_quan_ao", "plate", "license_plate"},
    "item_name": {"name", "ten", "ten_san_pham", "san_pham", "ten_quan_ao", "ten_mau", "mau"},
    "category": {"category", "product_type", "loai", "danh_muc", "loai_san_pham"},
    "price": {"price", "gia", "amount"},
    "status": {"status", "trang_thai", "ton_kho", "availability"},
    "province": {"province", "city", "location", "tinh", "khu_vuc"},
    "vehicle_type": {"vehicle", "vehicle_type", "loai_xe"},
    "size": {"size", "kich_thuoc"},
    "color": {"color", "mau", "mau_sac"},
    "material": {"material", "chat_lieu", "vai"},
    "gender": {"gender", "gioi_tinh"},
    "quantity": {"quantity", "so_luong", "so_luong_con"},
}


def pick(data: Dict[str, Any], canonical: str) -> str:
    aliases = ALIASES.get(canonical, {canonical})
    for key, value in (data or {}).items():
        if key_norm(key) in aliases and value not in (None, ""):
            return str(value).strip()
    return ""


def records_have_prefix(records: List[Dict[str, Any]], prefix: str) -> bool:
    return any(str(item.get("id") or "").startswith(prefix) for item in records or [])


class BaseDomainHandler:
    domain = "generic_commerce"

    def normalize_message(self, message: str) -> str:
        return str(message or "")

    def infer_intent(self, message, rag_route, analysis, state, context):
        result = dict(analysis or {})
        result.setdefault("intent", (rag_route or {}).get("intent_hint") or "UNKNOWN")
        result.setdefault("entities", {})
        result.setdefault("need_data", False)
        result.setdefault("reply_mode", (rag_route or {}).get("reply_mode_hint") or "GENERAL_REPLY")
        return result

    def extract_entities(self, message, analysis, state, context):
        return dict((analysis or {}).get("entities") or {})

    def should_search(self, intent, entities, state, context):
        return bool((context or {}).get("data_table")) and str(intent or "") in {"SEARCH_ITEM", "ASK_PRICE", "ASK_STOCK", "ASK_STATUS"}

    def build_search_filters(self, intent, entities, state, context):
        del intent, state, context
        return {key: value for key, value in (entities or {}).items() if value not in (None, "")}

    def render_reply(self, intent, entities, rows, knowledge_hits, state, context):
        if str(intent or "") == "GREETING":
            return self.safe_fallback(intent, entities, state, context)
        return ""

    def safe_fallback(self, intent, entities, state, context):
        del intent, entities, state
        label = (context or {}).get("domain_label") or (context or {}).get("expertise_name") or "chăm sóc khách hàng"
        return f"bên e hỗ trợ {label} ạ, mình cần tư vấn nội dung gì ạ"

    def update_state(self, state, intent, entities, rows, reply, context):
        del reply, context
        updated = dict(state or {})
        updated["last_intent"] = str(intent or "")
        updated["last_results"] = list(rows or [])[:3]
        for key in ["selected_item", "selected_product", "product_type", "category", "size", "color", "budget"]:
            if (entities or {}).get(key):
                updated[key] = entities[key]
        return updated
