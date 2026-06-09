import json
import re
import unicodedata
from typing import Dict, List, Optional


FIELD_ALIASES = {
    "item_name": {"item_name", "name", "ten", "ten_san_pham", "san_pham", "ten_quan_ao", "ten_mau"},
    "item_code": {
        "id", "code", "ma", "sku", "item_code", "product_code", "ma_san_pham", "ma_quan_ao",
        "plate", "plate_number", "license_plate", "bien_so", "ma_bien",
    },
    "category": {"category", "product_type", "type", "loai", "loai_san_pham", "danh_muc"},
    "price": {"price", "amount", "gia"},
    "status": {"status", "availability", "trang_thai", "ton_kho", "so_luong_con"},
    "province": {"province", "city", "location", "tinh", "khu_vuc"},
    "vehicle_type": {"vehicle", "vehicle_type", "loai_xe"},
    "size": {"size", "kich_thuoc"},
    "color": {"color", "mau", "mau_sac"},
    "material": {"material", "chat_lieu", "vai"},
    "gender": {"gender", "gioi_tinh"},
}


def normalize_text(text: str) -> str:
    value = unicodedata.normalize("NFD", str(text or "").lower())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("đ", "d")
    value = re.sub(r"[^a-z0-9]+", " ", value).strip()
    return re.sub(r"\s+", " ", value)


def _field_key(value) -> str:
    return normalize_text(value).replace(" ", "_")


def _parse_content(content) -> Dict:
    if isinstance(content, dict):
        return dict(content)
    text = str(content or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except (TypeError, ValueError):
        pass
    data = {}
    for line in text.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
    return data or {"content": text}


def _configured_aliases(data_fields_json) -> Dict[str, str]:
    try:
        fields = json.loads(data_fields_json or "[]") if isinstance(data_fields_json, str) else data_fields_json
    except (TypeError, ValueError):
        fields = []
    aliases = {}
    for field in fields if isinstance(fields, list) else []:
        if not isinstance(field, dict):
            continue
        key = field.get("key") or field.get("field_key")
        label = field.get("label") or field.get("field_label")
        if key and label:
            aliases[_field_key(label)] = _field_key(key)
    return aliases


def _canonical_field(key: str, configured: Dict[str, str]) -> Optional[str]:
    normalized = configured.get(_field_key(key), _field_key(key))
    for canonical, aliases in FIELD_ALIASES.items():
        if normalized in aliases:
            return canonical
    return None


def _matches(expected: str, actual: str, exact: bool = False) -> bool:
    expected_norm = normalize_text(expected)
    actual_norm = normalize_text(actual)
    if not expected_norm:
        return True
    expected_compact = expected_norm.replace(" ", "")
    actual_compact = actual_norm.replace(" ", "")
    if expected_compact and expected_compact in actual_compact:
        return True
    if exact:
        return False
    expected_tokens = expected_norm.split()
    return all(
        any(a.startswith(e) or e.startswith(a) for a in actual_norm.split())
        for e in expected_tokens
    )


class SearchIndex:
    def __init__(self, rows=None, field_map=None, domain="", data_fields_json=None):
        self.rows = [dict(row) for row in (rows or [])]
        self.field_map = dict(field_map or {})
        self.domain = str(domain or "")
        self._configured = _configured_aliases(data_fields_json)
        self.normalized_rows = [self._normalize_row(row) for row in self.rows]

    @staticmethod
    def normalize_text(text: str) -> str:
        return normalize_text(text)

    def _normalize_row(self, row: Dict) -> Dict:
        payload = _parse_content(row.get("content"))
        payload.setdefault("id", row.get("id"))
        canonical = {key: "" for key in FIELD_ALIASES}
        for key, value in payload.items():
            field = _canonical_field(key, self._configured)
            if field and value not in (None, "") and not canonical[field]:
                canonical[field] = value
        canonical["item_code"] = canonical["item_code"] or row.get("id") or ""
        blob = " ".join([str(row.get("id") or "")] + [str(value) for value in payload.values()])
        return {
            "row": row,
            "payload": payload,
            "canonical": canonical,
            "text": normalize_text(blob),
        }

    def search(self, filters: dict, query: str = "", limit: int = 10) -> List[Dict]:
        filters = {key: value for key, value in (filters or {}).items() if value not in (None, "")}
        aliases = {
            "plate": "item_code",
            "item_code": "item_code",
            "product_type": "category",
            "category": "category",
            "vehicle": "vehicle_type",
        }
        if filters:
            matched = []
            for item in self.normalized_rows:
                canonical = item["canonical"]
                ok = True
                for key, expected in filters.items():
                    field = aliases.get(key, key)
                    actual = canonical.get(field) or item["payload"].get(key) or ""
                    if field == "category" and not actual:
                        actual = item["text"]
                    if not _matches(expected, actual, exact=field == "item_code"):
                        ok = False
                        break
                if ok:
                    matched.append(item["row"])
            return matched[:int(limit or 10)]

        query_norm = normalize_text(query)
        if not query_norm:
            return []
        tokens = [token for token in query_norm.split() if len(token) >= 2]
        scored = []
        for position, item in enumerate(self.normalized_rows):
            score = sum(1 for token in tokens if token in item["text"])
            if query_norm in item["text"]:
                score += max(1, len(tokens))
            if score:
                scored.append((score, position, item["row"]))
        scored.sort(key=lambda value: (-value[0], value[1]))
        return [row for _, _, row in scored[:int(limit or 10)]]

    def catalog_summary(self) -> dict:
        categories = set()
        provinces = set()
        statuses = {}
        prices = []
        for item in self.normalized_rows:
            canonical = item["canonical"]
            if canonical["category"]:
                categories.add(str(canonical["category"]))
            if canonical["province"]:
                provinces.add(str(canonical["province"]))
            if canonical["status"]:
                key = str(canonical["status"])
                statuses[key] = statuses.get(key, 0) + 1
            digits = re.sub(r"[^\d]", "", str(canonical["price"] or ""))
            if digits:
                prices.append(int(digits))
        return {
            "total": len(self.rows),
            "categories": sorted(categories),
            "provinces": sorted(provinces),
            "statuses": statuses,
            "price_min": min(prices) if prices else None,
            "price_max": max(prices) if prices else None,
        }
