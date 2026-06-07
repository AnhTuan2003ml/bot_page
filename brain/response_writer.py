import json


SYSTEM_PROMPT = """Bạn là AI Writer. Hãy viết câu trả lời đúng theo skill, nhân vật, mục tiêu và quy trình được cung cấp.

VAI TRÒ:
- Bạn chỉ viết lại câu trả lời cho tự nhiên.
- Bạn không được quyết định action.
- Bạn không được đổi ý decision.
- Bạn không được quyết định dữ liệu.
- Dữ liệu đúng/sai đã được hệ thống quyết định trong DECISION.

LUẬT DỮ LIỆU:
- Chỉ dùng ITEMS trong DECISION.
- Không thêm sản phẩm, biển số, giá, tồn kho ngoài ITEMS.
- Nếu ACTION là NO_ITEMS_FOUND thì không được nói có hàng.
- Nếu ACTION là NO_PROVINCE_PLATES thì không được nói có biển.
- Nếu ACTION là SHOW_ITEMS thì chỉ liệt kê ITEMS.
- Nếu REPLY_DRAFT có sẵn, giữ ý chính và chỉ làm mượt câu.
- Nếu ACTION là NEGOTIATE_PRICE thì không được nói giá khách đề xuất đã được chấp nhận.
- Với NEGOTIATE_PRICE, không dùng các câu "được ạ", "chốt được", "ok giá", "giá này được"; chỉ nói sẽ check lại chủ biển và báo lại.

STYLE:
- Theo skill nếu có.
- Theo RAG nếu có.
- Không emoji.
- Không nói văn tổng đài.
- Trả lời ngắn, tự nhiên.
- Không nhắc RAG/database/context/system.
- Không gọi khách bằng tên, anh, chị hoặc a/c.
- Dùng cách nói trung tính: "bên e", "e", "ạ".

[Quy tắc bắt buộc]
- Chỉ trả lời theo nghiệp vụ của skill hiện tại.
- Không tự nhắc đến biển số xe nếu business_domain không phải plate_sales.
- Không tự nhận là shop quần áo nếu business_domain không phải fashion_sales.
- Không tự bán hàng nếu business_domain là companion_chat hoặc generic_chat.
- Nếu thiếu dữ liệu giá/tồn kho/sản phẩm, hãy hỏi lại hoặc nói sẽ kiểm tra, không bịa.
"""


OUT_OF_DOMAIN_SYSTEM_PROMPT = """Bạn là AI Writer. Hãy viết câu trả lời lịch sự, tự nhiên theo ngữ cảnh.

Đây là câu ngoài phạm vi công việc.
- Trả lời trực tiếp, lịch sự, tự nhiên.
- Không lặp lại nguyên văn câu khách.
- Không giả vờ có quan hệ cá nhân.
- Không đồng ý đi gặp/cafe/hẹn hò.
- Chỉ giới thiệu tên nếu khách hỏi tên/bạn là ai.
- Nếu khách rủ đi cafe thì không trả "e tên Linh".
- Không dùng template identity.
- Không nhắc thủ tục/CCCD/giá/biển số nếu khách không hỏi.
- Không nhắc database nếu khách không hỏi.
- Có thể kéo nhẹ về công việc tư vấn ở cuối câu.
- Không emoji.
- Trả lời ngắn.
"""


def _skill_prompt_block(skill=None, skill_config=None):
    skill_config = skill_config or {}
    style = skill_config.get("system_prompt") or skill or ""
    skill_id = skill_config.get("skill_id") or ""
    business_domain = skill_config.get("business_domain") or ""
    character_name = skill_config.get("character_name") or ""
    personality = skill_config.get("personality") or ""
    target = skill_config.get("target_description") or ""
    workflow = skill_config.get("workflow_prompt") or ""
    parts = []
    if skill_id or business_domain:
        parts.append("[Skill đang dùng]\nMã kỹ năng: " + str(skill_id) + "\nNghiệp vụ: " + str(business_domain))
    if character_name:
        parts.append("[Nhân vật]\nTên nhân vật: " + str(character_name))
    if personality:
        parts.append("[Tính cách]\n" + str(personality))
    if style:
        parts.append("[Prompt hệ thống của skill]\n" + str(style))
    if target:
        parts.append("[Mục tiêu công việc]\n" + str(target))
    if workflow:
        parts.append("[Quy trình phản hồi]\n" + str(workflow))
    return "\n\n".join(parts)


def build_messages(decision, rag_context, skill=None, skill_config=None, memory=None, domain_prompt=None):
    decision_dict = decision.to_dict() if hasattr(decision, "to_dict") else dict(decision or {})
    metadata = decision_dict.get("metadata", {}) or {}
    no_domain_rag = bool(metadata.get("no_domain_rag"))
    out_of_domain = decision_dict.get("action") == "OUT_OF_DOMAIN_CHAT" or metadata.get("scope") == "out_of_domain"
    history = (memory or {}).get("messages", [])[-12:] if isinstance(memory, dict) else []
    last_user_message = ""
    for message in reversed(history):
        if message.get("role") == "user":
            last_user_message = message.get("content", "")
            break
    user_message = (
        metadata.get("user_message")
        or (metadata.get("parsed_intent") or {}).get("raw_user_message", "")
        or decision_dict.get("user_message", "")
        or last_user_message
    )
    payload = {
        "action": decision_dict.get("action"),
        "reply_draft": decision_dict.get("reply", ""),
        "state": decision_dict.get("state", {}),
        "items": decision_dict.get("items", []),
        "nearby_items": decision_dict.get("nearby_items", []),
        "matched_items": metadata.get("matched_items", decision_dict.get("items", [])),
        "rag_context": "" if no_domain_rag else (rag_context or ""),
        "metadata": metadata,
        "parsed_intent": metadata.get("parsed_intent"),
        "user_message": user_message,
        "history": history,
    }
    system = OUT_OF_DOMAIN_SYSTEM_PROMPT if out_of_domain else SYSTEM_PROMPT
    if domain_prompt and not no_domain_rag:
        system += "\n\nDOMAIN STYLE:\n" + str(domain_prompt)
    skill_block = _skill_prompt_block(skill=skill, skill_config=skill_config)
    if skill_block:
        system += "\n\nSKILL:\n" + skill_block
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
    ]
