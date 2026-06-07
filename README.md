# Bot FB v1 - Chuyên môn AI

Bản này giữ nguyên logic Page hiện tại. Phần Skill cũ đã được thay bằng Chuyên môn AI thông qua bảng `expertises`.

Runtime mới:

`page_id -> pages.ai_skill -> expertises -> persona_json + training_content + data_table -> AI phân tích -> search data nếu cần -> phản hồi`

Không còn domain/RAG file/skill item JSONL trong runtime.
