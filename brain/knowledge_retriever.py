import json
import logging
import re
import unicodedata


logger = logging.getLogger(__name__)

STOPWORDS = {
    "hi", "hello", "alo", "ok", "oke", "uh", "uhm", "u", "da", "vang",
    "shop", "oi", "a", "anh", "chi", "em", "minh", "toi", "can", "muon",
    "hoi", "ben", "co", "khong", "ko", "k",
}

INTENT_RECORD_HINTS = {
    "GREETING": {"chao_hoi", "alo", "tin_dau", "greeting", "style_sale_bien_002"},
    "ASK_PROCEDURE": {
        "procedure", "thu_tuc", "sang_ten", "cccd", "dinh_danh", "can_cuoc",
        "giay_to", "style_sale_bien_012",
    },
    "ASK_DISCOUNT": {
        "discount", "giam_gia", "fix_gia", "ho_tro_gia", "linh_dong_gia",
        "gia_cao", "style_sale_bien_006",
    },
    "NEGOTIATE_PRICE": {
        "discount", "giam_gia", "fix_gia", "ho_tro_gia", "linh_dong_gia",
        "gia_cao", "style_sale_bien_006",
    },
    "ASK_ZALO": {"zalo", "sdt", "so_dien_thoai", "lien_he", "style_sale_bien_009"},
    "ASK_PRICE": {"bao_gia", "gia", "bien_cu_the", "price", "style_sale_bien_004"},
    "ASK_STATUS": {"het_hang", "khong_con", "con_khong", "status", "style_sale_bien_005"},
    "SEARCH_ITEM": {
        "hoi_nhu_cau", "tinh_thanh", "dau_so", "bien_so", "search", "product",
        "style_sale_bien_003",
    },
    "SEARCH_PLATE": {
        "hoi_nhu_cau", "tinh_thanh", "dau_so", "bien_so", "search", "product",
        "style_sale_bien_003",
    },
    "ASK_BUDGET": {"ngan_sach", "tai_chinh", "gia_thap", "budget", "style_sale_bien_008"},
    "ASK_VEHICLE_TYPE": {"xe_may", "oto", "o_to", "vehicle", "loai_xe"},
}

GLOBAL_STYLE_IDS = {
    "style_sale_bien_001",
    "style_sale_bien_010",
    "style_sale_bien_011",
}

GREETING_WORDS = {"hi", "hello", "alo", "chao", "xin chao", "chao shop"}
PROCEDURE_PHRASES = {"sang ten", "cccd", "can cuoc", "dinh danh", "thu tuc", "giay to"}
DISCOUNT_PHRASES = {"fix gia", "fix", "giam", "bot", "ho tro gia", "gia tot", "cao qua", "linh dong"}
ZALO_PHRASES = {"zalo", "sdt", "so dien thoai", "lien he"}
STATUS_PHRASES = {"con khong", "con k", "con ko", "het chua", "con hang"}
PRICE_PHRASES = {"gia", "bao nhieu", "nhieu tien", " bn "}
VEHICLE_PHRASES = {"xe may", "oto", "o to", "o-to", "loai xe"}
PLATE_SEARCH_PHRASES = {"bien", "bien so", "dau so", "ma bien", "tinh", "thanh"}


def normalize_vi(text: str) -> str:
    text = str(text or "").replace("đ", "d").replace("Đ", "D").lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> list[str]:
    tokens = []
    for token in normalize_vi(text).split():
        code_like = bool(re.fullmatch(r"(?=.*[a-z])(?=.*\d)[a-z0-9]+", token))
        if token in STOPWORDS or (len(token) < 3 and not code_like):
            continue
        tokens.append(token)
    return tokens


def _safe_record(value, index):
    if not isinstance(value, dict):
        return None
    tags = value.get("tags", [])
    if isinstance(tags, str):
        tags = [part.strip() for part in re.split(r"[,;]", tags) if part.strip()]
    elif not isinstance(tags, list):
        tags = []
    record_id = str(value.get("id") or f"record_{index}").strip()
    title = str(value.get("title") or record_id or f"Record {index}").strip()
    content = str(value.get("content") or "").strip()
    try:
        priority = int(value.get("priority") or 0)
    except (TypeError, ValueError):
        priority = 0
    return {
        "id": record_id,
        "title": title,
        "content": content,
        "tags": [str(tag).strip() for tag in tags if str(tag).strip()],
        "priority": priority,
    }


def parse_training_records(training_content: str) -> list[dict]:
    if isinstance(training_content, list):
        return [
            record for index, value in enumerate(training_content, 1)
            if (record := _safe_record(value, index))
        ]
    text = str(training_content or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        parsed = None
    if isinstance(parsed, list):
        return [
            record for index, value in enumerate(parsed, 1)
            if (record := _safe_record(value, index))
        ]
    if isinstance(parsed, dict):
        record = _safe_record(parsed, 1)
        return [record] if record else []

    records = []
    json_lines = 0
    non_json_lines = 0
    for index, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        if not line.startswith(("{", "[")):
            non_json_lines += 1
            continue
        try:
            value = json.loads(line)
        except (TypeError, ValueError) as exc:
            logger.warning("Skipping invalid training JSON line %s: %s", index, exc)
            json_lines += 1
            continue
        json_lines += 1
        record = _safe_record(value, index)
        if record:
            records.append(record)
    if records or (json_lines and not non_json_lines):
        return records
    return [{
        "id": "training_content",
        "title": "Training content",
        "content": text,
        "tags": [],
        "priority": 0,
    }]


def _contains_any(text, phrases):
    return any(_matches_record_hint(text, phrase) for phrase in phrases)


def _matches_record_hint(blob, hint):
    return bool(hint and re.search(rf"(?<![a-z0-9]){re.escape(hint)}(?![a-z0-9])", blob))


def has_specific_item(message: str) -> bool:
    compact = re.sub(r"[^A-Za-z0-9]", "", str(message or ""))
    return bool(
        re.search(r"\b\d{2,3}\s*[A-Za-z]{1,2}\s*[-. ]?\s*\d{3,6}\b", str(message or ""))
        or re.search(r"(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9]{4,}", compact)
    )


def is_identity_or_pronoun_message(message: str) -> bool:
    norm = normalize_vi(message)
    return bool(re.fullmatch(r"(anh|chi|a|c)", norm) or re.match(r"^toi ten\b", norm))




def _record_domain(record: dict) -> str:
    blob = normalize_vi(" ".join([
        str((record or {}).get("id") or ""),
        str((record or {}).get("title") or ""),
        " ".join(str(tag) for tag in (record or {}).get("tags") or []),
    ]))
    if "style_sale_clothes" in blob or "quan ao" in blob or "clothes" in blob or "fashion" in blob:
        return "fashion"
    if "style_sale_bien" in blob or "bien so" in blob or "bien xe" in blob or "license plate" in blob:
        return "license_plate"
    return "generic"


def _filter_records_by_domain(records: list[dict], domain: str) -> list[dict]:
    domain = str(domain or "").strip()
    if domain not in {"fashion", "license_plate"}:
        return records or []
    filtered = []
    for record in records or []:
        record_domain = _record_domain(record)
        if record_domain in {domain, "generic"}:
            filtered.append(record)
    return filtered

def retrieve_knowledge(
    message: str,
    records: list[dict],
    intent: str = "",
    top_k: int = 5,
    domain: str = "",
) -> list[dict]:
    records = _filter_records_by_domain(records, domain)
    message_norm = normalize_vi(message)
    message_tokens = set(tokenize(message))
    intent_hints = {normalize_vi(value) for value in INTENT_RECORD_HINTS.get(
        str(intent or "").upper(), set()
    )}
    scored = []
    plate_context = any("bien" in normalize_vi(" ".join([
        str(record.get("id") or ""),
        str(record.get("title") or ""),
        " ".join(record.get("tags") or []),
    ])) for record in records)

    for record in records or []:
        record_id = normalize_vi(record.get("id"))
        title = normalize_vi(record.get("title"))
        content = normalize_vi(record.get("content"))
        tags = [normalize_vi(tag) for tag in record.get("tags") or []]
        blob = " ".join([record_id, title, content, *tags])
        score = 0
        for tag in tags:
            if tag and (
                tag == message_norm
                or _matches_record_hint(message_norm, tag)
                or (
                    len(message_norm) >= 3
                    and _matches_record_hint(tag, message_norm)
                )
            ):
                score += 5
        if record_id and _matches_record_hint(message_norm, record_id):
            score += 5
        if title and (
            _matches_record_hint(message_norm, title)
            or (
                len(message_norm) >= 4
                and _matches_record_hint(title, message_norm)
            )
        ):
            score += 3
        score += sum(1 for token in message_tokens if token in content)
        phrases = [value for value in [title, *tags] if len(value.split()) >= 2]
        if any(phrase in message_norm for phrase in phrases):
            score += 4
        if any(_matches_record_hint(blob, hint) for hint in intent_hints):
            score += 6
        priority = int(record.get("priority") or 0)
        score += max(0, priority)
        if score > 0:
            enriched = dict(record)
            enriched["score"] = score
            scored.append((score, priority, enriched))

    scored.sort(key=lambda item: (-item[0], -item[1], str(item[2].get("id") or "")))
    hits = [item[2] for item in scored[:max(0, int(top_k or 5))]]
    hit_ids = {str(hit.get("id") or "") for hit in hits}
    if plate_context or any(hit_id.startswith("style_sale_bien_") for hit_id in hit_ids):
        for record in records or []:
            record_id = str(record.get("id") or "")
            if record_id in GLOBAL_STYLE_IDS and record_id not in hit_ids:
                hits.append(dict(record))
                hit_ids.add(record_id)
    return hits


def infer_intent_from_knowledge(message: str, records: list[dict], domain: str = "") -> dict:
    norm = normalize_vi(message)
    tokens = norm.split()
    specific_item = has_specific_item(message)
    intent = "UNKNOWN"
    need_data = False
    reply_mode = "GENERAL_REPLY"
    confidence = 0.35
    intents = []
    has_discount = _contains_any(norm, DISCOUNT_PHRASES)
    has_procedure = _contains_any(norm, PROCEDURE_PHRASES)
    if has_discount:
        intents.append("ASK_DISCOUNT")
    if has_procedure:
        intents.append("ASK_PROCEDURE")

    if not norm:
        confidence = 1.0
    elif norm in GREETING_WORDS or (len(tokens) <= 2 and _contains_any(norm, GREETING_WORDS)):
        intent, reply_mode, confidence = "GREETING", "GREETING_REPLY", 0.99
    elif is_identity_or_pronoun_message(message):
        intent, reply_mode, confidence = "GENERAL_CHAT", "GENERAL_REPLY", 0.98
    elif has_discount and has_procedure:
        intent, need_data, reply_mode, confidence = "ASK_DISCOUNT", False, "KNOWLEDGE_REPLY", 0.97
    elif has_procedure:
        intent, need_data, reply_mode, confidence = (
            "ASK_PROCEDURE", specific_item,
            "DATA_REPLY" if specific_item else "KNOWLEDGE_REPLY", 0.96,
        )
    elif _contains_any(norm, ZALO_PHRASES):
        intent, reply_mode, confidence = "ASK_ZALO", "KNOWLEDGE_REPLY", 0.97
    elif has_discount:
        intent, reply_mode, confidence = "ASK_DISCOUNT", "KNOWLEDGE_REPLY", 0.95
    elif _contains_any(norm, STATUS_PHRASES):
        intent, need_data, reply_mode, confidence = (
            "ASK_STATUS", specific_item,
            "DATA_REPLY" if specific_item else "KNOWLEDGE_REPLY", 0.91,
        )
    elif _contains_any(norm, PRICE_PHRASES) and specific_item:
        intent, need_data, reply_mode, confidence = "ASK_PRICE", True, "DATA_REPLY", 0.94
    elif _contains_any(norm, VEHICLE_PHRASES) or _contains_any(norm, PLATE_SEARCH_PHRASES):
        intent, need_data, reply_mode, confidence = "SEARCH_PLATE", True, "DATA_REPLY", 0.86
    elif records:
        initial_hits = retrieve_knowledge(message, records, top_k=3, domain=domain)
        if initial_hits:
            intent, reply_mode, confidence = "GENERAL_CHAT", "KNOWLEDGE_REPLY", 0.58

    hits = retrieve_knowledge(message, records, intent=intent, top_k=8 if len(intents) > 1 else 5, domain=domain)
    if len(intents) > 1:
        hit_ids = {str(hit.get("id") or "") for hit in hits}
        for extra_intent in intents:
            for hit in retrieve_knowledge(message, records, intent=extra_intent, top_k=8, domain=domain):
                hit_id = str(hit.get("id") or "")
                if hit_id not in hit_ids:
                    hits.append(hit)
                    hit_ids.add(hit_id)
    return {
        "intent_hint": intent,
        "intents_hint": intents or [intent],
        "need_data_hint": need_data,
        "reply_mode_hint": reply_mode,
        "knowledge_hits": hits,
        "confidence": confidence,
    }


def knowledge_to_prompt(knowledge_hits: list[dict]) -> str:
    blocks = []
    for hit in knowledge_hits or []:
        record_id = str(hit.get("id") or "record")
        title = str(hit.get("title") or record_id)
        content = str(hit.get("content") or "").strip()
        tags = ", ".join(str(tag) for tag in hit.get("tags") or [])
        block = f"[{record_id}] {title}: {content}"
        if tags:
            block += f"\nTags: {tags}"
        blocks.append(block)
    return "\n\n".join(blocks)
