from brain.knowledge_retriever import (
    infer_intent_from_knowledge,
    parse_training_records,
    retrieve_knowledge,
)
from brain.pipeline import (
    _build_data_query,
    _deterministic_reply,
    build_data_reply,
    build_no_data_reply,
    filter_data_rows,
    normalize_intent,
    should_search_data,
)
from database.dynamic_table_manager import search_dynamic_rows
from database.expertise_manager import get_expertise


MESSAGES = [
    "hi",
    "alo",
    "tôi tên Tuấn",
    "anh",
    "chị",
    "sang tên thế nào",
    "cccd làm sao",
    "có fix giá không",
    "zalo bên em là gì",
    "tôi muốn xem biển hà nội",
    "tôi muốn xem biển hà nộ",
    "giá 30A-123456 bao nhiêu",
    "30A-123456 còn không",
    "có biển thái bình không",
]


def simulate():
    expertise = get_expertise(1) or {}
    records = parse_training_records(expertise.get("training_content") or "")
    table = expertise.get("data_table") or ""
    data_fields = expertise.get("data_fields_json") or "[]"
    state = {}

    for message in MESSAGES:
        route = infer_intent_from_knowledge(message, records)
        analysis = normalize_intent({}, message, route)
        hits = retrieve_knowledge(message, records, analysis["intent"])
        analysis["knowledge_hits"] = hits
        search = should_search_data(table, analysis, state)
        rows = []
        if search:
            query = _build_data_query(message, analysis, state)
            rows = search_dynamic_rows(table, query, limit=10) if query else []
            rows = filter_data_rows(rows, analysis, data_fields)
        if analysis["need_data"]:
            reply = (
                build_data_reply(rows, analysis, data_fields)
                if rows else build_no_data_reply(analysis)
            )
        else:
            reply = _deterministic_reply(
                analysis["intent"], state, expertise.get("persona_json"), hits
            ) or "cần tìm loại nào hoặc khu vực nào bên e check ạ"
        plate = analysis["entities"].get("plate")
        if plate:
            state["selected_plate"] = plate

        print(f"message: {message}")
        print(f"rag intent: {route['intent_hint']}")
        print(f"final intent: {analysis['intent']}")
        print(f"should_search_data: {search}")
        print(f"knowledge_hit ids: {[hit.get('id') for hit in hits]}")
        print(f"result count: {len(rows)}")
        print(f"reply: {reply}")
        print("-" * 60)

    follow_up = "giảm được không"
    route = infer_intent_from_knowledge(follow_up, records)
    analysis = normalize_intent({}, follow_up, route)
    if state.get("selected_plate") and analysis["intent"] == "ASK_DISCOUNT":
        analysis["intent"] = "NEGOTIATE_PRICE"
    hits = retrieve_knowledge(follow_up, records, analysis["intent"])
    reply = _deterministic_reply(
        analysis["intent"], state, expertise.get("persona_json"), hits
    )
    print(f"message: {follow_up} (after selected plate)")
    print(f"rag intent: {route['intent_hint']}")
    print(f"final intent: {analysis['intent']}")
    print("should_search_data: False")
    print(f"knowledge_hit ids: {[hit.get('id') for hit in hits]}")
    print("result count: 0")
    print(f"reply: {reply}")


if __name__ == "__main__":
    simulate()
