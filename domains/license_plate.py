import re
from .base import BaseDomainHandler, normalize_text, parse_row, pick


PROVINCES = {
    "ha noi": "Hà Nội", "ha no": "Hà Nội", "hn": "Hà Nội",
    "thai binh": "Thái Bình", "thai bin": "Thái Bình", "tb": "Thái Bình",
}


def normalize_province(value):
    norm = normalize_text(value)
    for key, label in PROVINCES.items():
        if key == norm or key in norm:
            return label
    return str(value or "").strip()


def normalize_vehicle(value):
    norm = normalize_text(value)
    compact = norm.replace(" ", "")
    if norm in {"oto", "o to", "xe hoi", "xe oto", "xe o to"} or compact == "oto":
        return "ô tô"
    if norm in {"xe may", "motor"} or compact == "xemay":
        return "xe máy"
    return str(value or "").strip()


_STOP_PROVINCE_TOKENS = {
    "khong", "ko", "k", "kg", "a", "ạ", "nhe", "nha", "nua",
    "gia", "bao", "nhieu", "con", "het", "fix", "giam", "bot",
    "xe", "oto", "o", "to", "may", "loai", "bien", "so",
}


def _display_place(norm_value: str) -> str:
    words = [word for word in normalize_text(norm_value).split() if word]
    if not words:
        return ""
    # Title-case arbitrary province/location phrases without maintaining a hard-coded
    # province list. This lets queries like "biển hà giang", "biển nam định",
    # "biển quảng ninh" all produce a structured province filter.
    return " ".join(word.capitalize() for word in words)


def _display_place(norm_value: str) -> str:
    words = [word for word in normalize_text(norm_value).split() if word]
    if not words:
        return ""
    return " ".join(word.capitalize() for word in words)


def _display_place_from_original(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-zÀ-ỹà-ỹĐđ\s]+", " ", str(value or "")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return ""
    return " ".join(part[:1].upper() + part[1:].lower() for part in cleaned.split())


def extract_province_candidate(message: str) -> str:
    if re.search(r"\b(\d{2,3}\s*[A-Za-z]{1,2}\s*[-. ]?\s*\d{3,7})\b", str(message or "")):
        return ""
    raw = str(message or "")
    # Prefer the original text to preserve Vietnamese accents in replies while
    # using normalized tokens only to decide where the candidate stops.
    raw_patterns = [
        r"(?:có\s+|co\s+)?biển(?:\s+số)?\s+(.+)$",
        r"(?:có\s+|co\s+)?bien(?:\s+so)?\s+(.+)$",
        r"(?:tỉnh|tinh|thành|thanh|đầu\s+số|dau\s+so|mã\s+biển|ma\s+bien)\s+(.+)$",
    ]
    for pattern in raw_patterns:
        match = re.search(pattern, raw, flags=re.I)
        if not match:
            continue
        original_tokens = re.findall(r"[0-9A-Za-zÀ-ỹà-ỹĐđ]+", match.group(1))
        kept = []
        for token in original_tokens:
            if normalize_text(token) in _STOP_PROVINCE_TOKENS:
                break
            if normalize_text(token) in {"minh", "ben", "co", "can", "tim"}:
                continue
            kept.append(token)
            if len(kept) >= 4:
                break
        if kept:
            original_candidate = " ".join(kept)
            normalized_known = normalize_province(original_candidate)
            if normalized_known != original_candidate:
                return normalized_known
            return _display_place_from_original(original_candidate)

    normalized_known = normalize_province(raw)
    if normalized_known != raw.strip():
        return normalized_known
    return ""



class LicensePlateHandler(BaseDomainHandler):
    domain = "license_plate"

    def _set_intent(self, result, intent, need_data=False, reply_mode="GENERAL_REPLY", intents=None):
        result.update({
            "intent": intent,
            "intents": list(intents or [intent]),
            "need_data": bool(need_data),
            "reply_mode": reply_mode,
        })
        return result

    def _plate(self, message):
        m = re.search(r"\b(\d{2,3}\s*[A-Za-z]{1,2}\s*[-. ]?\s*\d{3,7})\b", str(message or ""))
        return re.sub(r"\s+", "", m.group(1)).upper() if m else ""

    def infer_intent(self, message, rag_route, analysis, state, context):
        result = super().infer_intent(message, rag_route, analysis, state, context)
        norm = normalize_text(message)
        has_search_signal = bool(
            self._plate(message)
            or extract_province_candidate(message)
            or any(p in norm for p in ["bien", "dau so", "ma bien", "tinh", "xe may", "oto", "o to"])
        )
        has_procedure = any(p in norm for p in ["sang ten", "cccd", "can cuoc", "dinh danh", "thu tuc", "giay to"])
        has_discount = any(p in norm for p in ["fix", "giam", "bot", "ho tro gia", "gia tot", "linh dong"])

        if norm in {"hi", "hello", "alo", "chao", "xin chao", "chao shop"}:
            return self._set_intent(result, "GREETING", False, "GREETING_REPLY")

        # Explicit search/query for a plate/province/vehicle must win over noisy
        # RAG hits. This is generic for any province phrase after "biển", not a
        # hard-coded Hà Giang special case.
        if self._plate(message) and any(p in norm for p in ["gia", "bao nhieu", "nhieu tien"]):
            return self._set_intent(result, "ASK_PRICE", True, "DATA_REPLY")
        if has_search_signal and not (has_discount or has_procedure):
            return self._set_intent(result, "SEARCH_PLATE", True, "DATA_REPLY")

        if has_discount and has_procedure:
            return self._set_intent(
                result, "ASK_DISCOUNT", False, "KNOWLEDGE_REPLY",
                intents=["ASK_DISCOUNT", "ASK_PROCEDURE"],
            )
        if has_procedure:
            return self._set_intent(result, "ASK_PROCEDURE", False, "KNOWLEDGE_REPLY")
        if has_discount:
            return self._set_intent(result, "ASK_DISCOUNT", False, "KNOWLEDGE_REPLY")
        if has_search_signal:
            return self._set_intent(result, "SEARCH_PLATE", True, "DATA_REPLY")
        return result

    def extract_entities(self, message, analysis, state, context):
        entities = dict((analysis or {}).get("entities") or {})
        plate = self._plate(message)
        if plate:
            entities["plate"] = plate
            entities["item_code"] = plate
        province = extract_province_candidate(message)
        if province:
            entities["province"] = province
        vehicle = normalize_vehicle(message)
        if vehicle in {"ô tô", "xe máy"}:
            entities["vehicle_type"] = vehicle
        if not entities.get("province") and (state or {}).get("selected_province") and any(p in normalize_text(message) for p in ["thi sao", "the", "con"]):
            entities["province"] = state.get("selected_province")
        if (analysis or {}).get("intents"):
            entities["_intents"] = list((analysis or {}).get("intents") or [])
        return entities

    def should_search(self, intent, entities, state, context):
        if not (context or {}).get("data_table"):
            return False
        intent = str(intent or "")
        if intent in {"SEARCH_PLATE", "ASK_PRICE", "ASK_STATUS"}:
            return True
        if intent == "NEGOTIATE_PRICE":
            return bool((entities or {}).get("plate") or (state or {}).get("selected_plate"))
        return False

    def build_search_filters(self, intent, entities, state, context):
        del context
        intent_text = str(intent or "")
        return {
            "plate": (entities or {}).get("plate") or (entities or {}).get("item_code") or ((state or {}).get("selected_plate") if intent_text in {"ASK_PRICE", "ASK_STATUS", "NEGOTIATE_PRICE"} else ""),
            "province": (entities or {}).get("province") or "",
            "vehicle_type": (entities or {}).get("vehicle_type") or "",
            "status": (entities or {}).get("status") or "",
        }

    def format_price(self, value):
        text = str(value or "").strip()
        if not text:
            return ""
        if "tr" in normalize_text(text):
            return text.replace("triệu", "tr").replace("trieu", "tr")
        digits = re.sub(r"[^0-9]", "", text)
        if not digits:
            return text
        number = int(digits)
        if number >= 1_000_000:
            number = number / 1_000_000
        return f"{number:g}tr"

    def _status(self, value):
        norm = normalize_text(value)
        if norm in {"con", "con hang", "available"}:
            return "còn"
        if norm in {"het", "khong con", "k con", "sold", "sold out"}:
            return "k còn"
        return str(value or "").strip()

    def _row_item(self, row):
        data = parse_row(row)
        return {
            "plate": pick(data, "item_code") or str((row or {}).get("id") or "").strip(),
            "price": self.format_price(pick(data, "price")),
            "province": normalize_province(pick(data, "province")),
            "vehicle": normalize_vehicle(pick(data, "vehicle_type")),
            "status": self._status(pick(data, "status")),
        }

    def _plate_price(self, item):
        return " ".join(part for part in [item.get("plate"), item.get("price")] if part)

    def _related_last_result_line(self, province, vehicle, state):
        province_norm = normalize_text(province)
        vehicle_norm = normalize_text(vehicle)
        for row in (state or {}).get("last_results") or []:
            item = self._row_item(row)
            if not item.get("plate") or normalize_text(item.get("province")) != province_norm:
                continue
            if vehicle_norm and normalize_text(item.get("vehicle")) == vehicle_norm:
                continue
            details = " ".join(part for part in [item.get("vehicle"), item.get("plate"), item.get("price")] if part)
            if details:
                return f"bên e đang có biển {details} ạ"
        return ""

    def render_reply(self, intent, entities, rows, knowledge_hits, state, context):
        del context
        intent = str(intent or "")
        if intent == "GREETING":
            return "bên e tư vấn biển số ạ, cần tìm biển tỉnh nào ạ"
        intents = set((entities or {}).get("_intents") or [])
        if intent == "ASK_DISCOUNT" and "ASK_PROCEDURE" in intents:
            return "chủ biển linh động giá được ạ\nbên e hỗ trợ sang tên/định danh lên căn cước ạ\nưng biển nào bên e check giá tốt và thủ tục cụ thể ạ"
        if intent == "ASK_DISCOUNT":
            return "chủ biển linh động giá được ạ\nưng biển nào bên e check giá tốt ạ"
        if intent == "ASK_PROCEDURE":
            return "bên e hỗ trợ sang tên/định danh lên căn cước ạ\nưng biển nào bên e check thủ tục cụ thể ạ"
        if intent == "ASK_ZALO":
            return "086912888 ạ\nnhắn zalo bên e gửi thêm biển ạ"
        if intent == "NEGOTIATE_PRICE":
            item = self._row_item(rows[0]) if rows else {}
            plate = (entities or {}).get("plate") or item.get("plate") or (state or {}).get("selected_plate") or "biển này"
            offer = (entities or {}).get("offer_price") or ""
            if item.get("price") and offer:
                return f"{plate} đang {item['price']} ạ\n{offer} bên e báo lại chủ biển xem hỗ trợ được không ạ"
            return "chủ biển linh động giá được ạ\nưng biển nào bên e check giá tốt ạ"
        if intent in {"SEARCH_PLATE", "ASK_PRICE", "ASK_STATUS"}:
            if not rows:
                province = (entities or {}).get("province") or ""
                vehicle = (entities or {}).get("vehicle_type") or ""
                if province and vehicle:
                    lines = [f"hiện bên e chưa thấy biển {vehicle} {province} ạ"]
                    related = self._related_last_result_line(province, vehicle, state)
                    if related:
                        lines.append(related)
                    return "\n".join(lines)
                if province:
                    return f"hiện bên e chưa thấy biển {province} phù hợp ạ\ncần biển xe máy hay ô tô để bên e check thêm ạ"
                return "hiện bên e chưa thấy biển phù hợp ạ\ncần biển xe máy hay ô tô, tỉnh nào để bên e check thêm ạ"
            items = [self._row_item(row) for row in rows]
            if intent == "ASK_PRICE" and len(items) == 1:
                return f"{items[0]['plate']} {items[0]['price']} e bao định danh lên căn cước ạ"
            if len(items) == 1:
                it = items[0]
                suffix = " ".join(part for part in [it.get("vehicle"), it.get("status")] if part)
                return f"{it['plate']} {it['price']}, biển {suffix} ạ".strip()
            first = items[0]
            same_group = all(normalize_text(i.get("province")) == normalize_text(first.get("province")) and normalize_text(i.get("vehicle")) == normalize_text(first.get("vehicle")) for i in items)
            if same_group:
                label = " ".join(part for part in [first.get("province"), first.get("vehicle")] if part)
                plates = ", ".join(self._plate_price(i) for i in items[:3] if self._plate_price(i))
                return f"bên e có mấy biển {label} ạ\n{plates} ạ"
        return ""

    def safe_fallback(self, intent, entities, state, context):
        del intent, entities, state, context
        return "bên e tư vấn biển số ạ, cần tìm biển tỉnh nào ạ"

    def update_state(self, state, intent, entities, rows, reply, context):
        updated = super().update_state(state, intent, entities, rows, reply, context)
        if rows:
            item = self._row_item(rows[0])
            if item.get("plate"):
                updated["selected_plate"] = item["plate"]
                updated["selected_item"] = item["plate"]
            if item.get("province"):
                updated["selected_province"] = item["province"]
            if item.get("vehicle"):
                updated["vehicle_type"] = item["vehicle"]
        for key in ["province", "vehicle_type", "plate", "item_code"]:
            if (entities or {}).get(key):
                if key == "province":
                    updated["selected_province"] = entities[key]
                elif key == "plate":
                    updated["selected_plate"] = entities[key]
                else:
                    updated[key] = entities[key]
        return updated
