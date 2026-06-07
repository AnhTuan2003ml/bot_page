import json
import re

from ai_agent.model_client import call_intent_model, call_model
from brain.knowledge_retriever import (
    has_specific_item,
    infer_intent_from_knowledge,
    is_identity_or_pronoun_message,
    knowledge_to_prompt,
    normalize_vi,
    parse_training_records,
    retrieve_knowledge,
)
from database.conversation_manager import add_conversation, get_recent_conversations
from database.conversation_state_manager import get_conversation_state, upsert_conversation_state
from database.dynamic_table_manager import list_dynamic_rows, search_dynamic_rows
from utils.logger import debug


VALID_INTENTS = {
    "GREETING", "SEARCH_ITEM", "SEARCH_PLATE", "ASK_PRICE", "ASK_STATUS",
    "ASK_PROCEDURE", "ASK_DISCOUNT", "NEGOTIATE_PRICE", "ASK_ZALO",
    "ASK_BUDGET", "ASK_VEHICLE_TYPE", "GENERAL_CHAT", "OUT_OF_DOMAIN",
    "UNKNOWN",
}
NO_DATA_INTENTS = {
    "GREETING", "ASK_PROCEDURE", "ASK_DISCOUNT", "NEGOTIATE_PRICE",
    "ASK_ZALO", "GENERAL_CHAT", "OUT_OF_DOMAIN", "UNKNOWN",
}
LLM_SKIP_INTENTS = {"GREETING", "ASK_PROCEDURE", "ASK_DISCOUNT", "ASK_ZALO"}
INTENT_ALIASES = {
    "GENERAL": "GENERAL_CHAT",
    "CHAT": "GENERAL_CHAT",
    "SEARCH": "SEARCH_ITEM",
    "FIND_ITEM": "SEARCH_ITEM",
    "FIND_PLATE": "SEARCH_PLATE",
    "CHECK_PRICE": "ASK_PRICE",
    "CHECK_STATUS": "ASK_STATUS",
    "PROCEDURE": "ASK_PROCEDURE",
    "DISCOUNT": "ASK_DISCOUNT",
    "NEGOTIATE": "NEGOTIATE_PRICE",
    "ASK_PHONE": "ASK_ZALO",
    "PROFILE_UPDATE": "GENERAL_CHAT",
    "PRONOUN_UPDATE": "GENERAL_CHAT",
    "ASK_PRONOUN": "GENERAL_CHAT",
}
ENTITY_KEYS = {
    "item_code", "plate", "province", "vehicle_type", "price_range", "budget", "status",
    "offer_price",
}
STATE_KEYS = {
    "selected_item", "selected_plate", "selected_province", "vehicle_type",
    "budget", "last_intent", "last_results", "pending_question",
}
PLATE_MEMORY_INTENTS = {"ASK_PRICE", "ASK_STATUS", "NEGOTIATE_PRICE"}
VEHICLE_DISPLAY = {"oto": "ô tô", "xe_may": "xe máy"}
PROVINCE_DISPLAY = {"ha_noi": "Hà Nội", "thai_binh": "Thái Bình"}


def _json_loads(value, default=None):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return default


def _extract_json(text):
    text = str(text or "").strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return {}
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}


def _empty_entities():
    return {key: "" for key in ENTITY_KEYS}


def _repair_mojibake(value):
    text = str(value or "")
    if not any(marker in text for marker in ("Ã", "Ä", "Æ", "á»", "áº")):
        return text
    for encoding in ("cp1252", "latin1"):
        try:
            fixed = text.encode(encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if fixed and fixed != text:
            return fixed
    return text


def _norm_text(value):
    return normalize_vi(_repair_mojibake(value))


def _compact_norm(value):
    return re.sub(r"[^a-z0-9]", "", _norm_text(value))


def _has_discount_signal(message):
    norm = _norm_text(message)
    return any(value in norm for value in [
        "fix", "fix gia", "giam", "bot", "ho tro gia", "gia tot",
        "linh dong", "cao qua",
    ])


def _has_procedure_signal(message):
    norm = _norm_text(message)
    return any(value in norm for value in [
        "sang ten", "cccd", "can cuoc", "dinh danh", "thu tuc", "giay to",
    ])


def _format_offer_price(number_text, unit):
    try:
        number = float(str(number_text or "").replace(",", "."))
    except (TypeError, ValueError):
        return ""
    unit_norm = _norm_text(unit)
    if unit_norm in {"tr", "trieu", "cu"}:
        return f"{number:g}tr"
    return f"{number:g}tr"


def _extract_offer_price(message, state=None):
    norm = _norm_text(message)
    pattern = (
        r"(?:(?:lay|chot|tra|de xuat|fix|bot|giam|con|gia)\s*)?"
        r"(\d+(?:[.,]\d+)?)\s*(tr|trieu|cu)\b"
    )
    match = re.search(pattern, norm)
    if not match:
        return ""
    has_negotiation = bool(re.search(
        r"\b(lay|chot|tra|de xuat|fix|bot|giam|con|duoc khong|dc khong|nhe)\b",
        norm,
    ))
    if not (has_negotiation or _plate_from_message(message) or (state or {}).get("selected_plate")):
        return ""
    return _format_offer_price(match.group(1), match.group(2))


def normalize_vehicle_type(value: str) -> str:
    norm = _norm_text(value)
    compact = re.sub(r"\s+", "", norm)
    if norm in {"oto", "o to", "xe hoi", "car", "xe oto", "xe o to"} or compact == "oto":
        return VEHICLE_DISPLAY["oto"]
    if norm in {"xe may", "motor"} or compact in {"xemay", "motor"}:
        return VEHICLE_DISPLAY["xe_may"]
    return str(value or "").strip()


def normalize_province(value: str) -> str:
    norm = _norm_text(value)
    compact = re.sub(r"\s+", "", norm)
    if norm in {"ha noi", "ha no", "hn"} or compact in {"hanoi", "hano"} or "ha noi" in norm:
        return PROVINCE_DISPLAY["ha_noi"]
    if norm in {"thai binh", "thai bin", "tb"} or compact in {"thaibinh", "thaibin"} or "thai binh" in norm:
        return PROVINCE_DISPLAY["thai_binh"]
    return str(value or "").strip()


def is_followup_query(message: str) -> bool:
    norm = _norm_text(message)
    return bool(
        re.search(r"\b(the|con)\b.*\bthi sao\b", norm)
        or norm.endswith("thi sao")
        or any(phrase in norm for phrase in [
            "xe may thi sao", "oto thi sao", "o to thi sao",
            "con loai xe may khong", "con bien xe may khong",
            "the con xe may", "the con oto", "the con o to",
        ])
    )


def merge_entities_with_state(entities: dict, state: dict, message: str) -> dict:
    merged = _empty_entities()
    merged.update({key: value for key, value in (entities or {}).items() if key in ENTITY_KEYS})
    followup = is_followup_query(message)

    if merged.get("province"):
        merged["province"] = normalize_province(merged["province"])
    elif followup and (state or {}).get("selected_province"):
        merged["province"] = normalize_province((state or {}).get("selected_province"))

    if merged.get("vehicle_type"):
        merged["vehicle_type"] = normalize_vehicle_type(merged["vehicle_type"])
    elif followup and (state or {}).get("vehicle_type"):
        merged["vehicle_type"] = normalize_vehicle_type((state or {}).get("vehicle_type"))

    if merged.get("plate") or merged.get("item_code"):
        plate = merged.get("plate") or merged.get("item_code")
        merged["plate"] = plate
        merged["item_code"] = plate
    elif merged.get("offer_price") and ((state or {}).get("selected_plate") or (state or {}).get("selected_item")):
        plate = (state or {}).get("selected_plate") or (state or {}).get("selected_item")
        merged["plate"] = plate
        merged["item_code"] = plate
    return merged


def _plate_from_message(message):
    match = re.search(
        r"\b(\d{2,3}\s*[A-Za-z]{1,2}\s*[-. ]?\s*\d{3,6})\b",
        str(message or ""),
    )
    return re.sub(r"\s+", "", match.group(1)).upper() if match else ""


def _extract_local_entities(message):
    norm = _norm_text(message)
    entities = _empty_entities()
    plate = _plate_from_message(message)
    entities["plate"] = plate
    entities["item_code"] = plate
    vehicle = normalize_vehicle_type(message)
    if vehicle in set(VEHICLE_DISPLAY.values()):
        entities["vehicle_type"] = vehicle
    if "xe may" in norm:
        entities["vehicle_type"] = "xe máy"
    elif "oto" in norm or "o to" in norm:
        entities["vehicle_type"] = "ô tô"
    budget = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(tr|trieu|ty|ti)\b", norm)
    if budget:
        entities["budget"] = budget.group(0)
    offer_price = _extract_offer_price(message)
    if offer_price:
        entities["offer_price"] = offer_price
    province = re.search(
        r"(?:bien(?: so)?|tinh|thanh)\s+([a-z ]+?)(?:\s+(?:xe may|o to|oto|gia|con|khong|ko|k)|$)",
        norm,
    )
    if province:
        candidate = province.group(1).strip()
        candidate_province = normalize_province(candidate)
        if candidate_province in set(PROVINCE_DISPLAY.values()):
            entities["province"] = candidate_province
        elif (
            candidate not in {"so", "xe", "nao"}
            and not any(token in candidate for token in ["xe may", "o to", "oto", "thi sao", "loai xe"])
        ):
            entities["province"] = candidate
    if entities.get("province"):
        entities["province"] = normalize_province(entities["province"])
    province_alias = normalize_province(message)
    if province_alias in set(PROVINCE_DISPLAY.values()):
        entities["province"] = province_alias
    return entities


def _schema():
    return {
        "intent": "UNKNOWN",
        "intents": [],
        "entities": _empty_entities(),
        "need_data": False,
        "context_policy": {"use_history": True, "reset_fields": []},
        "reply_mode": "GENERAL_REPLY",
    }


def normalize_intent(analysis: dict, message: str, rag_route: dict | None = None) -> dict:
    result = _schema()
    result.update(analysis or {})
    entities = _empty_entities()
    entities.update({
        key: value for key, value in ((analysis or {}).get("entities") or {}).items()
        if key in ENTITY_KEYS
    })
    for key, value in _extract_local_entities(message).items():
        if value:
            entities[key] = value

    rag_route = rag_route or {}
    confidence = float(rag_route.get("confidence") or 0)
    candidates = [
        rag_route.get("intent_hint") if confidence >= 0.85 else "",
        result.get("intent"),
        result.get("detected_intent"),
        result.get("next_action"),
    ]
    raw_intent = next((str(value).strip().upper() for value in candidates if value), "UNKNOWN")
    intent = INTENT_ALIASES.get(raw_intent, raw_intent)
    if intent not in VALID_INTENTS:
        intent = "UNKNOWN"

    norm = _norm_text(message)
    has_discount = _has_discount_signal(message)
    has_procedure = _has_procedure_signal(message)
    multi_intents = []
    if has_discount:
        multi_intents.append("ASK_DISCOUNT")
    if has_procedure:
        multi_intents.append("ASK_PROCEDURE")
    if is_identity_or_pronoun_message(message):
        intent = "GENERAL_CHAT"
    elif norm in {"hi", "hello", "alo", "chao", "xin chao", "chao shop"}:
        intent = "GREETING"
    elif entities.get("offer_price"):
        intent = "NEGOTIATE_PRICE"
    elif has_discount and has_procedure:
        intent = "ASK_DISCOUNT"
    elif has_procedure:
        intent = "ASK_PROCEDURE"
    elif any(value in norm for value in ["zalo", "sdt", "so dien thoai"]):
        intent = "ASK_ZALO"
    elif has_discount:
        intent = "ASK_DISCOUNT"
    elif any(value in norm for value in ["con khong", "con k", "con ko", "het chua"]):
        intent = "ASK_STATUS"
    elif has_specific_item(message) and any(value in norm for value in ["gia", "bao nhieu", "nhieu tien"]):
        intent = "ASK_PRICE"
    elif any(value in norm for value in ["bien", "dau so", "ma bien", "tinh", "thanh", "xe may", "o to", "oto"]):
        intent = "SEARCH_PLATE"

    specific = bool(entities["plate"] or entities["item_code"])
    if intent == "ASK_DISCOUNT" and specific:
        intent = "NEGOTIATE_PRICE"
    need_data = intent in {"SEARCH_ITEM", "SEARCH_PLATE", "ASK_PRICE"}
    if intent == "NEGOTIATE_PRICE":
        need_data = bool(specific)
    if intent in {"ASK_STATUS", "ASK_PROCEDURE"}:
        need_data = specific
    if len(multi_intents) > 1 and not specific:
        need_data = False
    if confidence >= 0.85 and rag_route.get("need_data_hint") is False and intent in NO_DATA_INTENTS:
        need_data = False
    if is_identity_or_pronoun_message(message):
        need_data = False

    reply_mode = {
        "GREETING": "GREETING_REPLY",
        "ASK_PROCEDURE": "DATA_REPLY" if need_data else "KNOWLEDGE_REPLY",
        "ASK_DISCOUNT": "KNOWLEDGE_REPLY",
        "NEGOTIATE_PRICE": "KNOWLEDGE_REPLY",
        "ASK_ZALO": "KNOWLEDGE_REPLY",
    }.get(intent, "DATA_REPLY" if need_data else "GENERAL_REPLY")
    result.update({
        "intent": intent,
        "intents": multi_intents or [intent],
        "entities": entities,
        "need_data": bool(need_data),
        "reply_mode": "NEGOTIATE_REPLY" if intent == "NEGOTIATE_PRICE" and entities.get("offer_price") else reply_mode,
    })
    for field in ["profile_update", "customer_profile_updates", "name", "pronoun"]:
        result.pop(field, None)
    return result


def analyze_message(
    persona_json,
    training_content,
    profile,
    state,
    history,
    message,
    page_config=None,
    intent_hint=None,
    knowledge_hits=None,
    rag_route=None,
):
    del persona_json, training_content, profile
    route = rag_route or {
        "intent_hint": intent_hint or "UNKNOWN",
        "need_data_hint": False,
        "reply_mode_hint": "GENERAL_REPLY",
        "confidence": 0,
    }
    payload = {
        "intent_hint": route.get("intent_hint"),
        "intent_hint_confidence": route.get("confidence"),
        "relevant_training_records": knowledge_to_prompt(knowledge_hits or []),
        "conversation_state": {key: value for key, value in (state or {}).items() if key in STATE_KEYS},
        "history": history or [],
        "new_message": message,
        "required_output_schema": _schema(),
        "rules": [
            "Only analyze intent and entities; do not reply to the customer.",
            "Do not extract customer name, gender, title, or pronoun.",
            "Follow a high-confidence intent_hint unless a clear item or plate code requires data.",
            "Greeting, procedure without an item, discount without an item, and Zalo do not need data.",
            "Return one valid JSON object matching required_output_schema.",
        ],
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You are an intent analyzer. Return JSON only. Never analyze customer "
                "name or pronoun and never address the customer."
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    try:
        raw = call_intent_model(messages, page_config=page_config, max_tokens=350)
        analysis = _extract_json(raw)
    except Exception as exc:
        debug(f"[ANALYZE] error={exc}")
        analysis = {}
    return normalize_intent(analysis, message, route)


def should_search_data(data_table, analysis, state=None) -> bool:
    if not data_table:
        return False
    intent = str((analysis or {}).get("intent") or "")
    entities = (analysis or {}).get("entities") or {}
    if intent == "NEGOTIATE_PRICE":
        return bool(
            entities.get("plate")
            or entities.get("item_code")
            or (state or {}).get("selected_plate")
            or (state or {}).get("selected_item")
        )
    if not bool((analysis or {}).get("need_data")):
        return False
    return intent in {
        "SEARCH_ITEM", "SEARCH_PLATE", "ASK_PRICE", "ASK_STATUS", "ASK_PROCEDURE",
    }


def _build_data_query(message, analysis, state):
    entities = (analysis or {}).get("entities") or {}
    parts = [
        entities.get("plate"),
        entities.get("item_code"),
        entities.get("province"),
        entities.get("vehicle_type"),
        entities.get("budget"),
    ]
    if not any(parts):
        parts.append(message)
    if (analysis or {}).get("intent") in {"ASK_PRICE", "ASK_STATUS", "NEGOTIATE_PRICE"}:
        parts.append((state or {}).get("selected_plate"))
        parts.append((state or {}).get("selected_item"))
    output = []
    for part in parts:
        part = str(part or "").strip()
        if part and part not in output:
            output.append(part)
    return " ".join(output)


def _row_payload(row):
    value = (row or {}).get("content", row or {})
    if isinstance(value, dict):
        data = dict(value)
    else:
        try:
            parsed = json.loads(str(value or ""))
            data = parsed if isinstance(parsed, dict) else {"content": str(value or "")}
        except (TypeError, ValueError):
            text = str(value or "")
            data = {}
            for line in text.splitlines():
                if ":" not in line:
                    continue
                key, item_value = line.split(":", 1)
                if key.strip():
                    data[key.strip()] = item_value.strip()
            if not data:
                data = {"content": text}
    if (row or {}).get("id") not in (None, ""):
        data.setdefault("id", (row or {}).get("id"))
    return data


def _field_alias(field):
    return _norm_text(field).replace(" ", "_")


FIELD_ALIASES = {
    "code": {
        "bien_so", "plate", "plate_number", "license_plate", "item_code",
        "code", "ma", "ma_bien", "id",
    },
    "price": {"gia", "price", "amount"},
    "vehicle": {"loai_xe", "vehicle", "vehicle_type", "type"},
    "status": {"trang_thai", "status", "availability"},
    "province": {"tinh", "province", "city", "location"},
}


def _pick_field(data, kind, data_fields_json=None):
    aliases = FIELD_ALIASES[kind]
    configured = _json_loads(data_fields_json, []) or []
    candidates = []
    for field in configured:
        if isinstance(field, dict):
            candidates.extend([field.get("name"), field.get("key"), field.get("label")])
        else:
            candidates.append(field)
    candidates.extend(data.keys())
    for candidate in candidates:
        if candidate is None:
            continue
        normalized = _field_alias(candidate)
        if normalized in aliases:
            for key, value in data.items():
                if _field_alias(key) == normalized and value not in (None, ""):
                    return value
    return ""


def _format_price(value):
    text = str(value or "").strip()
    if not text:
        return ""
    number_text = re.sub(r"[^\d]", "", text)
    if number_text:
        number = int(number_text)
        if number >= 1_000_000:
            return f"{number / 1_000_000:g}tr"
    return text.replace("triệu", "tr").replace("trieu", "tr")


def _format_vehicle(value):
    normalized = normalize_vehicle_type(value)
    if normalized in set(VEHICLE_DISPLAY.values()):
        return normalized
    norm = _norm_text(value)
    if norm in {"oto", "o to", "xe oto", "xe o to"}:
        return "ô tô"
    if norm in {"xe may", "xemay"}:
        return "xe máy"
    return str(value or "").strip()


def _format_status(value):
    norm = _norm_text(value)
    if norm in {"con", "available", "con hang"}:
        return "còn"
    if norm in {"het", "khong con", "k con", "sold", "sold out"}:
        return "k còn"
    return str(value or "").strip()


def _is_plate_context(source):
    hits = source if isinstance(source, list) else (source or {}).get("knowledge_hits") or []
    return any(
        str(hit.get("id") or "").startswith("style_sale_bien_")
        or "bien_so" in [normalize_vi(tag).replace(" ", "_") for tag in hit.get("tags") or []]
        for hit in hits
    )


def _prefix_phrase_match(expected, actual):
    expected_tokens = _norm_text(expected).split()
    actual_tokens = _norm_text(actual).split()
    if not expected_tokens:
        return True
    return all(
        any(
            actual_token.startswith(expected_token)
            or expected_token.startswith(actual_token)
            for actual_token in actual_tokens
        )
        for expected_token in expected_tokens
    )


def filter_data_rows(rows, analysis, data_fields_json=None):
    entities = (analysis or {}).get("entities") or {}
    expected_code = entities.get("plate") or entities.get("item_code") or ""
    expected_province = entities.get("province") or ""
    expected_vehicle = entities.get("vehicle_type") or ""
    filtered = []
    for row in rows or []:
        data = _row_payload(row)
        code = _pick_field(data, "code", data_fields_json)
        province = _pick_field(data, "province", data_fields_json)
        vehicle = _pick_field(data, "vehicle", data_fields_json)
        if expected_code:
            if _compact_norm(code) != _compact_norm(expected_code):
                continue
        if expected_province and _norm_text(normalize_province(expected_province)) != _norm_text(normalize_province(province)):
            continue
        if expected_vehicle and _norm_text(normalize_vehicle_type(expected_vehicle)) != _norm_text(normalize_vehicle_type(vehicle)):
            continue
        filtered.append(row)
    return filtered


def _build_structured_filters(analysis):
    entities = (analysis or {}).get("entities") or {}
    return {
        "plate": entities.get("plate") or entities.get("item_code") or "",
        "province": entities.get("province") or "",
        "vehicle_type": entities.get("vehicle_type") or "",
        "status": entities.get("status") or "",
    }


def _normalized_filters(filters):
    return {
        "plate": _compact_norm((filters or {}).get("plate")),
        "province": _norm_text(normalize_province((filters or {}).get("province"))),
        "vehicle_type": _norm_text(normalize_vehicle_type((filters or {}).get("vehicle_type"))),
        "status": _norm_text((filters or {}).get("status")),
    }


def _structured_filters_are_clear(filters):
    filters = filters or {}
    return bool(filters.get("province") and filters.get("vehicle_type"))


def _row_matches_structured_filters(row, filters, data_fields_json=None):
    data = _row_payload(row)
    code = _pick_field(data, "code", data_fields_json) or (row or {}).get("id") or ""
    province = _pick_field(data, "province", data_fields_json)
    vehicle = _pick_field(data, "vehicle", data_fields_json)
    status = _pick_field(data, "status", data_fields_json)
    normalized = _normalized_filters(filters)
    if normalized["plate"] and normalized["plate"] not in _compact_norm(code):
        return False
    if normalized["province"] and normalized["province"] != _norm_text(normalize_province(province)):
        return False
    if normalized["vehicle_type"] and normalized["vehicle_type"] != _norm_text(normalize_vehicle_type(vehicle)):
        return False
    if normalized["status"] and normalized["status"] not in _norm_text(status):
        return False
    return True


def search_structured_rows(table_name, analysis, data_fields_json=None, limit=10):
    filters = _build_structured_filters(analysis)
    if not any(filters.values()):
        return [], filters, _normalized_filters(filters), "none"
    rows = list_dynamic_rows(table_name, limit=10000)
    matched = [
        row for row in rows
        if _row_matches_structured_filters(row, filters, data_fields_json)
    ]
    return matched[:int(limit or 10)], filters, _normalized_filters(filters), "structured"


def build_data_reply(rows, analysis, data_fields_json=None):
    lines = []
    intent = str((analysis or {}).get("intent") or "")
    plate_context = _is_plate_context(analysis) or intent == "SEARCH_PLATE"
    entities = (analysis or {}).get("entities") or {}
    if (
        plate_context
        and intent == "SEARCH_PLATE"
        and entities.get("province")
        and entities.get("vehicle_type")
    ):
        lines.append(f"bÃªn e cÃ³ biá»ƒn {normalize_province(entities.get('province'))} áº¡")
    for row in (rows or [])[:5]:
        data = _row_payload(row)
        code = str(_pick_field(data, "code", data_fields_json) or "").strip()
        price = _format_price(_pick_field(data, "price", data_fields_json))
        vehicle = _format_vehicle(_pick_field(data, "vehicle", data_fields_json))
        status = _format_status(_pick_field(data, "status", data_fields_json))
        province = str(_pick_field(data, "province", data_fields_json) or "").strip()
        if intent == "ASK_PRICE" and code and price:
            if plate_context:
                lines.append(f"{code} {price} e bao định danh lên căn cước ạ")
            else:
                lines.append(f"{code} {price} ạ")
            continue
        if intent == "ASK_STATUS" and code:
            lines.append(f"{code} {status or 'bên e đang check'} ạ")
            continue
        details = " ".join(part for part in [code, price] if part)
        suffix = ", ".join(part for part in [
            f"{'biển' if plate_context else 'loại'} {vehicle}" if vehicle else "",
            status,
        ] if part)
        line = details
        if suffix:
            line += f", {suffix}"
        if not line and province:
            line = f"bên e có dữ liệu {province}"
        if line:
            lines.append(line.strip() + " ạ")
    return "\n".join(lines) if lines else build_no_data_reply(analysis=analysis)


def _row_brief(row, data_fields_json=None):
    data = _row_payload(row)
    code = str(_pick_field(data, "code", data_fields_json) or (row or {}).get("id") or "").strip()
    price = _format_price(_pick_field(data, "price", data_fields_json))
    vehicle = _format_vehicle(_pick_field(data, "vehicle", data_fields_json))
    province = normalize_province(_pick_field(data, "province", data_fields_json))
    return code, price, vehicle, province


def _related_last_result_line(province, vehicle_type, last_results, data_fields_json=None):
    province_norm = _norm_text(normalize_province(province))
    vehicle_norm = _norm_text(normalize_vehicle_type(vehicle_type))
    for row in last_results or []:
        code, price, other_vehicle, row_province = _row_brief(row, data_fields_json)
        if not code or _norm_text(row_province) != province_norm:
            continue
        if vehicle_norm and _norm_text(normalize_vehicle_type(other_vehicle)) == vehicle_norm:
            continue
        details = " ".join(part for part in [other_vehicle, code, price] if part)
        if details:
            return f"bÃªn e Ä‘ang cÃ³ biá»ƒn {details} áº¡"
    return ""


def build_no_data_reply(message=None, analysis=None, knowledge_hits=None, state=None, last_results=None, data_fields_json=None):
    if analysis is None and isinstance(message, dict):
        analysis = message
        message = ""
    del message, knowledge_hits
    entities = (analysis or {}).get("entities") or {}
    province = normalize_province(entities.get("province") or (state or {}).get("selected_province") or "")
    vehicle_type = normalize_vehicle_type(entities.get("vehicle_type") or "")
    has_province = bool(province)
    has_vehicle = vehicle_type in set(VEHICLE_DISPLAY.values())
    if _is_plate_context(analysis) or str((analysis or {}).get("intent") or "") == "SEARCH_PLATE":
        if has_province and has_vehicle:
            lines = [f"hiá»‡n bÃªn e chÆ°a tháº¥y biá»ƒn {vehicle_type} {province} áº¡"]
            related = _related_last_result_line(
                province,
                vehicle_type,
                last_results or (state or {}).get("last_results") or [],
                data_fields_json,
            )
            if related:
                lines.append(related)
            return "\n".join(lines)
        if has_province:
            return (
                f"hiá»‡n bÃªn e chÆ°a tháº¥y biá»ƒn {province} phÃ¹ há»£p áº¡\n"
                "cáº§n biá»ƒn xe mÃ¡y hay Ã´ tÃ´ Ä‘á»ƒ bÃªn e check thÃªm áº¡"
            )
        if has_vehicle:
            return (
                f"hiá»‡n bÃªn e chÆ°a tháº¥y biá»ƒn {vehicle_type} phÃ¹ há»£p áº¡\n"
                "cáº§n biá»ƒn tá»‰nh nÃ o Ä‘á»ƒ bÃªn e check thÃªm áº¡"
            )
    if _is_plate_context(analysis):
        return (
            "hiện bên e chưa thấy biển phù hợp ạ\n"
            "cần biển xe máy hay ô tô, tỉnh nào để bên e check thêm ạ"
        )
    return (
        "hiện bên e chưa thấy lựa chọn phù hợp ạ\n"
        "cần loại nào, khu vực nào để bên e check thêm ạ"
    )


def _related_last_result_line(province, vehicle_type, last_results, data_fields_json=None):
    province_norm = _norm_text(normalize_province(province))
    vehicle_norm = _norm_text(normalize_vehicle_type(vehicle_type))
    for row in last_results or []:
        code, price, other_vehicle, row_province = _row_brief(row, data_fields_json)
        if not code or _norm_text(row_province) != province_norm:
            continue
        if vehicle_norm and _norm_text(normalize_vehicle_type(other_vehicle)) == vehicle_norm:
            continue
        details = " ".join(part for part in [other_vehicle, code, price] if part)
        if details:
            return f"bên e đang có biển {details} ạ"
    return ""


def build_no_data_reply(message=None, analysis=None, knowledge_hits=None, state=None, last_results=None, data_fields_json=None):
    if analysis is None and isinstance(message, dict):
        analysis = message
        message = ""
    del message, knowledge_hits
    entities = (analysis or {}).get("entities") or {}
    province = normalize_province(entities.get("province") or (state or {}).get("selected_province") or "")
    vehicle_type = normalize_vehicle_type(entities.get("vehicle_type") or "")
    has_province = bool(province)
    has_vehicle = vehicle_type in set(VEHICLE_DISPLAY.values())
    if _is_plate_context(analysis) or str((analysis or {}).get("intent") or "") == "SEARCH_PLATE":
        if has_province and has_vehicle:
            lines = [f"hiện bên e chưa thấy biển {vehicle_type} {province} ạ"]
            related = _related_last_result_line(
                province,
                vehicle_type,
                last_results or (state or {}).get("last_results") or [],
                data_fields_json,
            )
            if related:
                lines.append(related)
            return "\n".join(lines)
        if has_province:
            return (
                f"hiện bên e chưa thấy biển {province} phù hợp ạ\n"
                "cần biển xe máy hay ô tô để bên e check thêm ạ"
            )
        if has_vehicle:
            return (
                f"hiện bên e chưa thấy biển {vehicle_type} phù hợp ạ\n"
                "cần biển tỉnh nào để bên e check thêm ạ"
            )
        return (
            "hiện bên e chưa thấy biển phù hợp ạ\n"
            "cần biển xe máy hay ô tô, tỉnh nào để bên e check thêm ạ"
        )
    return (
        "hiện bên e chưa thấy lựa chọn phù hợp ạ\n"
        "cần loại nào, khu vực nào để bên e check thêm ạ"
    )


def build_data_reply(rows, analysis, data_fields_json=None):
    lines = []
    intent = str((analysis or {}).get("intent") or "")
    plate_context = _is_plate_context(analysis) or intent == "SEARCH_PLATE"
    entities = (analysis or {}).get("entities") or {}
    if (
        plate_context
        and intent == "SEARCH_PLATE"
        and entities.get("province")
        and entities.get("vehicle_type")
    ):
        lines.append(f"bên e có biển {normalize_province(entities.get('province'))} ạ")
    for row in (rows or [])[:5]:
        data = _row_payload(row)
        code = str(_pick_field(data, "code", data_fields_json) or "").strip()
        price = _format_price(_pick_field(data, "price", data_fields_json))
        vehicle = _format_vehicle(_pick_field(data, "vehicle", data_fields_json))
        status = _format_status(_pick_field(data, "status", data_fields_json))
        province = str(_pick_field(data, "province", data_fields_json) or "").strip()
        if intent == "ASK_PRICE" and code and price:
            if plate_context:
                lines.append(f"{code} {price} e bao định danh lên căn cước ạ")
            else:
                lines.append(f"{code} {price} ạ")
            continue
        if intent == "ASK_STATUS" and code:
            lines.append(f"{code} {status or 'bên e đang check'} ạ")
            continue
        details = " ".join(part for part in [code, price] if part)
        suffix = ", ".join(part for part in [
            f"{'biển' if plate_context else 'loại'} {vehicle}" if vehicle else "",
            status,
        ] if part)
        line = details
        if suffix:
            line += f", {suffix}"
        if not line and province:
            line = f"bên e có dữ liệu {province}"
        if line:
            lines.append(line.strip() + " ạ")
    return "\n".join(lines) if lines else build_no_data_reply(analysis=analysis)


def _format_status(value):
    norm = _norm_text(value)
    if norm in {"con", "available", "con hang"}:
        return "còn"
    if norm in {"het", "khong con", "k con", "sold", "sold out"}:
        return "k còn"
    return str(value or "").strip()


def _price_number(value):
    text = str(value or "").strip()
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    if not digits:
        return None
    number = int(digits)
    if number < 1_000_000 and any(unit in _norm_text(text) for unit in ["tr", "trieu"]):
        number *= 1_000_000
    return number


def _row_summary(row, data_fields_json=None):
    data = _row_payload(row)
    price_raw = _pick_field(data, "price", data_fields_json)
    province_raw = _pick_field(data, "province", data_fields_json)
    return {
        "plate": str(_pick_field(data, "code", data_fields_json) or (row or {}).get("id") or "").strip(),
        "price": _format_price(price_raw),
        "price_number": _price_number(price_raw),
        "vehicle": _format_vehicle(_pick_field(data, "vehicle", data_fields_json)),
        "status": _format_status(_pick_field(data, "status", data_fields_json)),
        "province": normalize_province(province_raw) if province_raw else "",
    }


def _plate_price(item):
    return " ".join(part for part in [item.get("plate"), item.get("price")] if part)


def _group_key(item, include_status=True):
    key = [
        _norm_text(item.get("province")),
        _norm_text(normalize_vehicle_type(item.get("vehicle"))),
    ]
    if include_status:
        key.append(_norm_text(item.get("status")))
    return tuple(key)


def _group_label(item, include_status=True):
    parts = [item.get("province"), item.get("vehicle")]
    if include_status:
        parts.append(item.get("status"))
    return " ".join(part for part in parts if part).strip()


def _price_range(items):
    prices = [item["price_number"] for item in items if item.get("price_number") is not None]
    if not prices:
        return ""
    return f"{min(prices) / 1_000_000:g}-{max(prices) / 1_000_000:g}tr"


def build_data_reply(rows, analysis, data_fields_json=None):
    items = [_row_summary(row, data_fields_json) for row in rows or []]
    items = [item for item in items if item.get("plate") or item.get("province")]
    if not items:
        return build_no_data_reply(analysis=analysis)

    first = items[0]
    if str((analysis or {}).get("intent") or "") == "ASK_PRICE" and len(items) == 1:
        details = _plate_price(first)
        if details and re.search(r"\d{2,3}[A-Z]{1,2}[-. ]?\d{3,7}", first.get("plate") or "", flags=re.I):
            return f"{details} e bao định danh lên căn cước ạ"
        if details:
            return f"{details} ạ"
    if len(items) == 1:
        details = _plate_price(first)
        suffix = " ".join(part for part in [first.get("vehicle"), first.get("status")] if part)
        if suffix and details:
            return f"{details}, biển {suffix} ạ" if first.get("vehicle") else f"{details} ạ"
        if details:
            return f"{details} ạ"
        return f"bên e có dữ liệu {first.get('province')} ạ"

    same_group = len({_group_key(item, include_status=True) for item in items}) == 1
    same_province_vehicle = len({_group_key(item, include_status=False) for item in items}) == 1

    if 2 <= len(items) <= 3 and same_group:
        label = _group_label(first, include_status=False)
        plates = ", ".join(_plate_price(item) for item in items if _plate_price(item))
        if label and plates:
            return f"bên e có mấy biển {label} ạ\n{plates} ạ"

    if len(items) > 3 and same_province_vehicle:
        label = _group_label(first, include_status=False)
        prices = _price_range(items)
        preview = ", ".join(_plate_price(item) for item in items[:3] if _plate_price(item))
        if label and prices and preview:
            return f"bên e có {len(items)} biển {label}, giá từ {prices} ạ\ngửi trước: {preview} ạ"

    grouped = {}
    for item in items:
        grouped.setdefault(_group_key(item, include_status=True), []).append(item)
    lines = []
    for group_items in grouped.values():
        label = _group_label(group_items[0], include_status=True)
        plates = ", ".join(_plate_price(item) for item in group_items[:3] if _plate_price(item))
        if label and plates:
            lines.append(f"{label}: {plates}")
        elif plates:
            lines.append(plates)
    return "\n".join(lines) if lines else build_no_data_reply(analysis=analysis)


def build_negotiate_reply(rows, message, analysis, knowledge_hits=None, state=None, data_fields_json=None):
    del message, knowledge_hits
    entities = (analysis or {}).get("entities") or {}
    item = _row_summary((rows or [{}])[0], data_fields_json) if rows else {}
    plate = entities.get("plate") or entities.get("item_code") or item.get("plate") or (state or {}).get("selected_plate") or ""
    current_price = item.get("price") or ""
    offer_price = entities.get("offer_price") or ""
    if current_price and offer_price:
        subject = plate or "biển này"
        return (
            f"{subject} đang {current_price} ạ\n"
            f"{offer_price} bên e báo lại chủ biển xem hỗ trợ được không ạ"
        )
    if current_price:
        subject = plate or "biển này"
        return (
            f"{subject} đang {current_price} ạ\n"
            "chủ biển linh động giá được ạ"
        )
    if offer_price:
        return (
            f"{offer_price} bên e báo lại chủ biển xem hỗ trợ được không ạ\n"
            "gửi lại biển cụ thể bên e check chính xác ạ"
        )
    return (
        "chủ biển linh động giá được ạ\n"
        "ưng biển nào bên e check giá tốt ạ"
    )


def build_knowledge_reply(analysis, state=None, persona_json=None, knowledge_hits=None):
    del state, persona_json, knowledge_hits
    intents = list((analysis or {}).get("intents") or [])
    intent = str((analysis or {}).get("intent") or "")
    if intent and intent not in intents:
        intents.append(intent)
    intent_set = set(intents)
    if {"ASK_DISCOUNT", "ASK_PROCEDURE"}.issubset(intent_set):
        return (
            "chủ biển linh động giá được ạ\n"
            "bên e hỗ trợ sang tên/định danh lên căn cước ạ\n"
            "ưng biển nào bên e check giá tốt và thủ tục cụ thể ạ"
        )
    if "ASK_DISCOUNT" in intent_set:
        return (
            "chủ biển linh động giá được ạ\n"
            "ưng biển nào bên e check giá tốt ạ"
        )
    if "ASK_PROCEDURE" in intent_set:
        return (
            "bên e hỗ trợ sang tên/định danh lên căn cước ạ\n"
            "ưng biển nào bên e check thủ tục cụ thể ạ"
        )
    return ""


def _find_contact(persona_json, knowledge_hits):
    text = " ".join([
        str(persona_json or ""),
        " ".join(str(hit.get("content") or "") for hit in knowledge_hits or []),
    ])
    match = re.search(r"(?<!\d)(0\d{8,10})(?!\d)", text)
    return match.group(1) if match else ""


def _deterministic_reply(intent, state, persona_json, knowledge_hits):
    plate_context = _is_plate_context(knowledge_hits)
    if intent == "GREETING":
        if plate_context:
            return "bên e tư vấn biển số ạ, cần tìm biển tỉnh nào ạ"
        return "bên e tư vấn ạ, cần tìm loại nào hoặc khu vực nào ạ"
    if intent == "ASK_PROCEDURE":
        if plate_context:
            return (
                "bên e hỗ trợ sang tên/định danh lên căn cước ạ\n"
                "ưng biển nào bên e check thủ tục cụ thể ạ"
            )
        return (
            "bên e hỗ trợ thủ tục theo lựa chọn đã chốt ạ\n"
            "ưng lựa chọn nào bên e check thủ tục cụ thể ạ"
        )
    if intent == "ASK_DISCOUNT":
        if plate_context:
            return (
                "chủ biển linh động giá được ạ\n"
                "ưng biển nào bên e check giá tốt ạ"
            )
        return (
            "bên e linh động giá được ạ\n"
            "ưng lựa chọn nào bên e check giá tốt ạ"
        )
    if intent == "NEGOTIATE_PRICE":
        if (state or {}).get("selected_plate") or (state or {}).get("selected_item"):
            return (
                "bên e có thể check lại giá ạ\n"
                "đề xuất mức mong muốn bên e báo lại ạ"
            )
        return (
            "bên e linh động giá được ạ\n"
            "ưng lựa chọn nào bên e check giá tốt ạ"
        )
    if intent == "ASK_ZALO":
        contact = _find_contact(persona_json, knowledge_hits)
        if contact:
            return f"{contact} ạ\nnhắn zalo bên e gửi thêm thông tin ạ"
        return "để lại số điện thoại, bên e liên hệ qua zalo ạ"
    return ""


def generate_reply(
    expertise,
    persona_json,
    training_content,
    profile,
    state,
    analysis,
    retrieved_data,
    history,
    message,
    page_config=None,
    knowledge_hits=None,
):
    del training_content, profile
    knowledge_hits = knowledge_hits or (analysis or {}).get("knowledge_hits") or []
    payload = {
        "expertise": {
            "name": (expertise or {}).get("name"),
            "job_title": (expertise or {}).get("job_title"),
            "description": (expertise or {}).get("description"),
        },
        "persona": _json_loads(persona_json, {}) or {},
        "relevant_training_records": knowledge_to_prompt(knowledge_hits),
        "state": {key: value for key, value in (state or {}).items() if key in STATE_KEYS},
        "analysis": analysis or {},
        "product_rows": retrieved_data or [],
        "history": history or [],
        "message": message,
        "rules": [
            "Use only relevant training records and supplied product rows.",
            "Never mention RAG, knowledge, database, system, prompt, or internal data.",
            "Do not use the customer's name or address them as anh, chi, a/c.",
            "Use neutral Vietnamese phrasing such as 'bên e', 'e', and 'ạ'.",
            "Reply in one or two short sentences.",
            "If product_rows is empty, never claim an item exists.",
            "Do not change item codes, prices, or status from product_rows.",
        ],
    }
    try:
        return call_model([
            {
                "role": "system",
                "content": (
                    "Write a short neutral customer-service reply. Never address the "
                    "customer by name, gender, anh, chi, or a/c."
                ),
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ], page_config=page_config)
    except Exception as exc:
        debug(f"[REPLY] error={exc}")
        return "cần thêm tiêu chí để bên e hỗ trợ chính xác ạ"


def _neutralize_reply(reply):
    text = str(reply or "").strip()
    for pattern, replacement in [
        (r"\b[Dd]ạ\s+anh\b", "dạ"),
        (r"\b[Dd]ạ\s+chị\b", "dạ"),
        (r"\banh/chị\b", ""),
        (r"\ba/c\b", ""),
        (r"\bAnh\s+[A-ZÀ-Ỹ][\wÀ-ỹ]*\b", ""),
        (r"\bChị\s+[A-ZÀ-Ỹ][\wÀ-ỹ]*\b", ""),
        (r"\ba\s+(đang|lấy|cần|muốn|thích|đề xuất)\b", r"\1"),
        (r"\bcho\s+a\b", "ạ"),
    ]:
        text = re.sub(pattern, replacement, text, flags=re.I)
    return re.sub(r"[ \t]+", " ", text).strip()


def _clean_state(state, analysis, rows):
    previous = {key: value for key, value in (state or {}).items() if key in STATE_KEYS}
    entities = (analysis or {}).get("entities") or {}
    first_row = _row_payload((rows or [{}])[0]) if rows else {}
    row_plate = _pick_field(first_row, "code") if first_row else ""
    row_province = _pick_field(first_row, "province") if first_row else ""
    row_vehicle = _pick_field(first_row, "vehicle") if first_row else ""
    plate = entities.get("plate") or entities.get("item_code") or ""
    if plate or row_plate:
        plate = plate or row_plate
        previous["selected_plate"] = plate
        previous["selected_item"] = plate
    if entities.get("province") or row_province:
        previous["selected_province"] = normalize_province(entities.get("province") or row_province)
    if entities.get("vehicle_type") or row_vehicle:
        previous["vehicle_type"] = normalize_vehicle_type(entities.get("vehicle_type") or row_vehicle)
    if entities.get("budget"):
        previous["budget"] = entities["budget"]
    previous["last_intent"] = (analysis or {}).get("intent") or ""
    previous["last_results"] = (rows or [])[:3]
    previous["pending_question"] = ""
    return {key: previous.get(key, [] if key == "last_results" else "") for key in STATE_KEYS}


def _mask_sender(sender_id):
    value = str(sender_id or "")
    return ("*" * max(0, len(value) - 4)) + value[-4:] if value else ""


def _delimiter(persona):
    if not isinstance(persona, dict):
        return "---MSG---"
    return ((persona.get("tach_tin_nhan") or {}).get("delimiter") or "---MSG---")


def split_reply(reply_text, persona_json):
    persona = _json_loads(persona_json, {}) or {}
    delimiter = _delimiter(persona)
    if delimiter and delimiter in str(reply_text or ""):
        return [part.strip() for part in str(reply_text).split(delimiter) if part.strip()]
    return [str(reply_text or "").strip()] if str(reply_text or "").strip() else []


def process_message(
    chat_id,
    user_message,
    page_config=None,
    sender_name=None,
    raw_context=None,
    runtime_context=None,
):
    del sender_name
    page_config = runtime_context or page_config or {}
    page_id = page_config.get("page_id") or (raw_context or {}).get("page_id") or "default_page"
    sender_id = (
        page_config.get("sender_psid")
        or (raw_context or {}).get("sender_psid")
        or str(chat_id).split(":")[-1]
    )
    expertise = page_config.get("expertise") or {}
    expertise_id = expertise.get("id") or page_config.get("expertise_id")
    if not expertise_id:
        return "Page này chưa được gán Chuyên môn AI phụ trách."

    persona_json = expertise.get("persona_json") or page_config.get("persona_json") or "{}"
    training_content = expertise.get("training_content") or page_config.get("training_content") or ""
    data_table = expertise.get("data_table") or page_config.get("data_table") or ""
    data_fields_json = expertise.get("data_fields_json") or page_config.get("data_fields_json") or "[]"
    state = get_conversation_state(page_id, sender_id, expertise_id)
    history = get_recent_conversations(page_id, sender_id, limit=10)
    records = parse_training_records(training_content)
    rag_route = infer_intent_from_knowledge(user_message, records)
    knowledge_hits = rag_route["knowledge_hits"]

    if not str(user_message or "").strip():
        analysis = normalize_intent({}, user_message, rag_route)
    elif (
        rag_route["confidence"] >= 0.85
        and (
            rag_route["intent_hint"] in LLM_SKIP_INTENTS
            or is_identity_or_pronoun_message(user_message)
        )
    ):
        analysis = normalize_intent({}, user_message, rag_route)
    else:
        analysis = analyze_message(
            persona_json,
            training_content,
            None,
            state,
            history,
            user_message,
            page_config=page_config,
            intent_hint=rag_route["intent_hint"],
            knowledge_hits=knowledge_hits,
            rag_route=rag_route,
        )

    offer_price = _extract_offer_price(user_message, state)
    if offer_price:
        analysis.setdefault("entities", {})["offer_price"] = offer_price
        analysis["intent"] = "NEGOTIATE_PRICE"
        analysis["need_data"] = bool(
            (analysis.get("entities") or {}).get("plate")
            or (analysis.get("entities") or {}).get("item_code")
            or state.get("selected_plate")
            or state.get("selected_item")
        )
        analysis["reply_mode"] = "NEGOTIATE_REPLY"
    is_followup = is_followup_query(user_message)
    entities_before_merge = dict((analysis or {}).get("entities") or {})
    state_before_merge = {key: state.get(key) for key in STATE_KEYS if state.get(key) not in (None, "", [])}
    analysis["entities"] = merge_entities_with_state(analysis.get("entities") or {}, state, user_message)
    knowledge_hits = []
    hit_ids = set()
    retrieve_intents = list(analysis.get("intents") or [analysis["intent"]])
    if analysis["intent"] not in retrieve_intents:
        retrieve_intents.append(analysis["intent"])
    for retrieve_intent in retrieve_intents:
        for hit in retrieve_knowledge(user_message, records, intent=retrieve_intent, top_k=8):
            hit_id = str(hit.get("id") or "")
            if hit_id not in hit_ids:
                knowledge_hits.append(hit)
                hit_ids.add(hit_id)
    analysis["knowledge_hits"] = knowledge_hits
    search_data = should_search_data(data_table, analysis, state)
    rows = []
    structured_filters = {}
    normalized_filters = {}
    search_mode = "none"
    no_data_reason = ""
    if search_data:
        query = _build_data_query(user_message, analysis, state)
        try:
            rows, structured_filters, normalized_filters, search_mode = search_structured_rows(
                data_table, analysis, data_fields_json, limit=10
            )
            if not rows and not _structured_filters_are_clear(structured_filters) and query:
                rows = search_dynamic_rows(data_table, query, limit=10)
                rows = filter_data_rows(rows, analysis, data_fields_json)
                search_mode = "fulltext"
            if not rows:
                if structured_filters.get("province") and structured_filters.get("vehicle_type"):
                    no_data_reason = "no rows for province+vehicle_type"
                elif structured_filters.get("province"):
                    no_data_reason = "no rows for province"
                elif structured_filters.get("vehicle_type"):
                    no_data_reason = "no rows for vehicle_type"
                else:
                    no_data_reason = "no matching rows"
        except Exception as exc:
            debug(f"[DATA_SEARCH] error={exc}")
            rows = []
            search_mode = "none"
            no_data_reason = f"search error: {exc}"

    if analysis["intent"] == "NEGOTIATE_PRICE":
        reply = build_negotiate_reply(
            rows,
            user_message,
            analysis,
            knowledge_hits,
            state=state,
            data_fields_json=data_fields_json,
        )
        analysis["reply_mode"] = "NEGOTIATE_REPLY"
    elif len(set(analysis.get("intents") or [])) > 1 and not analysis["need_data"]:
        reply = build_knowledge_reply(analysis, state, persona_json, knowledge_hits)
        if not reply:
            reply = _deterministic_reply(
                analysis["intent"], state, persona_json, knowledge_hits
            )
        analysis["reply_mode"] = "KNOWLEDGE_REPLY"
    elif analysis["need_data"]:
        if rows:
            reply = build_data_reply(rows, analysis, data_fields_json)
            analysis["reply_mode"] = "DATA_REPLY"
        else:
            reply = build_no_data_reply(
                user_message,
                analysis,
                knowledge_hits,
                state=state,
                last_results=(state or {}).get("last_results") or [],
                data_fields_json=data_fields_json,
            )
            analysis["reply_mode"] = "NO_DATA_REPLY"
    else:
        reply = build_knowledge_reply(analysis, state, persona_json, knowledge_hits)
        if not reply:
            reply = _deterministic_reply(
            analysis["intent"], state, persona_json, knowledge_hits
            )
        if not reply:
            if is_identity_or_pronoun_message(user_message):
                reply = "cần tìm loại nào hoặc khu vực nào bên e check ạ"
            else:
                reply = generate_reply(
                    expertise, persona_json, "", None, state, analysis, [], history,
                    user_message, page_config=page_config, knowledge_hits=knowledge_hits,
                )
    reply = _neutralize_reply(reply)
    new_state = _clean_state(state, analysis, rows)
    upsert_conversation_state(page_id, sender_id, expertise_id, new_state)
    add_conversation(page_id, sender_id, expertise_id, "user", user_message)
    for part in split_reply(reply, persona_json):
        add_conversation(page_id, sender_id, expertise_id, "assistant", part)

    debug(
        "[RUNTIME_AI] "
        f"page_id={page_id} sender={_mask_sender(sender_id)} "
        f"expertise_id={expertise_id} expertise_name={expertise.get('name') or ''} "
        f"data_table={data_table} rag_intent={rag_route['intent_hint']} "
        f"rag_need_data={rag_route['need_data_hint']} "
        f"rag_confidence={rag_route['confidence']:.2f} "
        f"knowledge_ids={[hit.get('id') for hit in knowledge_hits]} "
        f"raw_message={user_message!r} is_followup={is_followup} "
        f"entities_before_merge={entities_before_merge} "
        f"state_before_merge={state_before_merge} "
        f"entities_after_merge={analysis.get('entities') or {}} "
        f"structured_filters={structured_filters} normalized_filters={normalized_filters} "
        f"search_mode={search_mode} no_data_reason={no_data_reason!r} "
        f"final_intent={analysis['intent']} final_need_data={analysis['need_data']} "
        f"should_search_data={search_data} result_count={len(rows)} "
        f"reply_mode={analysis['reply_mode']}"
    )
    return reply
