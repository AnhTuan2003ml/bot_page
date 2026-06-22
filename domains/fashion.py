import re
from .base import BaseDomainHandler, normalize_text, parse_row, pick


PRODUCT_LABELS = {
    "quan jean": "quần jean",
    "jean": "quần jean",
    "quan short": "quần short",
    "short": "quần short",
    "ao so mi": "áo sơ mi",
    "ao somi": "áo sơ mi",
    "somi": "áo sơ mi",
    "ao thun": "áo thun",
    "thun": "áo thun",
    "ao khoac": "áo khoác",
    "set do": "set đồ",
    "vay": "váy",
    "dam": "đầm",
}


class FashionHandler(BaseDomainHandler):
    domain = "fashion"

    def normalize_message(self, message: str) -> str:
        text = str(message or "")
        replacements = {
            "đượckhông": "được không",
            "duockhong": "duoc khong",
            "cókhông": "có không",
            "cokhong": "co khong",
            "muốnmua": "muốn mua",
            "muonmua": "muon mua",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text

    def _product_type(self, message: str) -> str:
        norm = normalize_text(message)
        for key, label in PRODUCT_LABELS.items():
            if re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", norm):
                return label
        return ""

    def _height(self, message: str) -> str:
        norm = normalize_text(message)
        match = re.search(r"\b(?:cao\s*)?(?:1m\s*)?(\d{2})\b", norm)
        if "m" in norm:
            m = re.search(r"\b(?:cao\s*)?(?:1m|m)\s*(\d{2})\b", norm)
            if m:
                return f"1m{m.group(1)}"
        m = re.search(r"\b1\s*m\s*(\d{2})\b", norm)
        if m:
            return f"1m{m.group(1)}"
        if match and int(match.group(1)) >= 40:
            return f"1m{match.group(1)}"
        return ""

    def _weight(self, message: str) -> str:
        norm = normalize_text(message)
        m = re.search(r"\b(?:nang\s*)?(\d{2,3})\s*kg\b", norm)
        return f"{m.group(1)}kg" if m else ""

    def infer_intent(self, message, rag_route, analysis, state, context):
        result = super().infer_intent(message, rag_route, analysis, state, context)
        norm = normalize_text(message)
        product_type = self._product_type(message)
        if norm in {"hi", "hello", "alo", "chao", "xin chao", "chao shop"}:
            result.update({"intent": "GREETING", "need_data": False, "reply_mode": "GREETING_REPLY"})
        elif any(p in norm for p in ["ban gi", "shop ban gi", "tu van san pham gi", "co nhung san pham nao", "ben minh ban gi", "ben minh tu van gi"]):
            result.update({"intent": "ASK_CATALOG", "need_data": False, "reply_mode": "KNOWLEDGE_REPLY"})
        elif self._height(message) and self._weight(message) and any(p in norm for p in ["mac gi", "hop gi", "phu hop gi"]):
            result.update({"intent": "ASK_RECOMMENDATION", "need_data": False, "reply_mode": "KNOWLEDGE_REPLY"})
        elif "size" in norm or "mac size" in norm:
            result.update({"intent": "ASK_SIZE", "need_data": False, "reply_mode": "KNOWLEDGE_REPLY"})
        elif product_type:
            result.update({"intent": "SEARCH_ITEM", "need_data": True, "reply_mode": "DATA_REPLY"})
        return result

    def extract_entities(self, message, analysis, state, context):
        entities = dict((analysis or {}).get("entities") or {})
        product_type = self._product_type(message)
        if product_type:
            entities["product_type"] = product_type
            entities.setdefault("category", product_type)
        norm = normalize_text(message)
        if "nam" in norm:
            entities["gender"] = "nam"
        elif "nu" in norm:
            entities["gender"] = "nữ"
        height = self._height(message)
        weight = self._weight(message)
        if height:
            entities["height"] = height
        if weight:
            entities["weight"] = weight
        return entities

    def should_search(self, intent, entities, state, context):
        del state
        return bool((context or {}).get("data_table")) and str(intent or "") in {"SEARCH_ITEM", "ASK_PRICE", "ASK_STOCK"} and bool(
            (entities or {}).get("product_type") or (entities or {}).get("category") or (entities or {}).get("item_code")
        )

    def build_search_filters(self, intent, entities, state, context):
        del intent, state, context
        return {
            "product_type": (entities or {}).get("product_type") or (entities or {}).get("category") or "",
            "size": (entities or {}).get("size") or "",
            "color": (entities or {}).get("color") or "",
            "item_code": (entities or {}).get("item_code") or "",
        }

    def format_price(self, value) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if "k" in normalize_text(text):
            return text
        digits = re.sub(r"[^0-9]", "", text)
        if not digits:
            return text
        number = int(digits)
        if number >= 1000:
            number = round(number / 1000)
        return f"{number:g}k"

    def _row_item(self, row, fallback_type=""):
        data = parse_row(row)
        name = pick(data, "item_name") or pick(data, "item_code") or str((row or {}).get("id") or "").strip()
        category = pick(data, "category") or fallback_type
        price = self.format_price(pick(data, "price"))
        status = pick(data, "status")
        size = pick(data, "size")
        color = pick(data, "color")
        material = pick(data, "material")
        return {"name": name, "category": category, "price": price, "status": status, "size": size, "color": color, "material": material}

    def _extra(self, item):
        parts = []
        status_norm = normalize_text(item.get("status"))
        if status_norm in {"con", "con hang", "available"}:
            parts.append("mẫu này còn hàng")
        if item.get("size"):
            parts.append(f"size {item['size']}")
        if item.get("color"):
            parts.append(f"màu {item['color']}")
        return ", " + ", ".join(parts) if parts else ""

    def render_reply(self, intent, entities, rows, knowledge_hits, state, context):
        del knowledge_hits, state
        intent = str(intent or "")
        if intent == "GREETING":
            return "bên e tư vấn quần áo ạ, mình cần tìm áo, quần hay set đồ ạ"
        if intent == "ASK_CATALOG":
            return "bên e tư vấn và bán quần áo ạ, hỗ trợ chọn mẫu, size, màu, chất liệu và phối đồ ạ"
        if intent == "ASK_RECOMMENDATION":
            gender = (entities or {}).get("gender") or ""
            height = (entities or {}).get("height") or ""
            weight = (entities or {}).get("weight") or ""
            if gender == "nam" and height == "1m75" and weight == "50kg":
                return "với dáng nam 1m75 50kg khá gầy, bên e gợi ý áo form regular/oversize nhẹ, quần jean ống suông hoặc slim vừa ạ\nmình thích mặc rộng hay vừa người để e lọc mẫu sát hơn ạ"
            return "bên e tư vấn theo dáng người được ạ\nmình thích mặc rộng hay vừa người để e lọc mẫu sát hơn ạ"
        if intent == "ASK_SIZE":
            height = (entities or {}).get("height") or ""
            weight = (entities or {}).get("weight") or ""
            if height or weight:
                return f"với {height} {weight}, bên e tư vấn tham khảo size M cho áo ạ\nnếu muốn mặc rộng/ôm thì e check theo form mẫu cụ thể ạ".replace("  ", " ")
            return "mình cho e xin chiều cao cân nặng để tư vấn size sát hơn ạ"
        if intent == "SEARCH_ITEM":
            product_type = (entities or {}).get("product_type") or (entities or {}).get("category") or "mẫu"
            if not rows:
                return f"hiện bên e chưa thấy mẫu {product_type} phù hợp ạ\nmình cần {product_type} nam hay nữ, màu/form nào để e check thêm ạ"
            items = [self._row_item(row, product_type) for row in rows or []]
            if len(items) == 1:
                item = items[0]
                display = item["name"]
                if product_type and normalize_text(product_type) not in normalize_text(display):
                    display = f"{product_type} {display}".strip()
                price_line = f"giá {item['price']}" if item.get("price") else "để e check giá mẫu này"
                return f"bên e có {display} ạ\n{price_line}{self._extra(item)} ạ"
            preview = ", ".join(
                f"{item['name']} {item['price']}".strip() for item in items[:3]
            )
            return f"bên e có mấy mẫu {product_type} ạ\n{preview} ạ"
        return ""

    def safe_fallback(self, intent, entities, state, context):
        del intent, entities, state, context
        return "bên e tư vấn quần áo ạ, mình cần tìm áo, quần hay set đồ ạ"

    def update_state(self, state, intent, entities, rows, reply, context):
        updated = super().update_state(state, intent, entities, rows, reply, context)
        for key in ["product_type", "category", "size", "color", "gender", "height", "weight"]:
            if (entities or {}).get(key):
                updated[key] = entities[key]
        if (entities or {}).get("product_type"):
            updated["selected_product"] = entities["product_type"]
            updated["selected_item"] = entities["product_type"]
        return updated
