import unittest
from unittest.mock import patch

from brain.knowledge_retriever import infer_intent_from_knowledge, parse_training_records
from brain.pipeline import (
    build_data_reply,
    filter_data_rows,
    normalize_intent,
    process_message,
    should_search_data,
)


TRAINING = """
{"id":"style_sale_bien_002","title":"Chào","content":"Chào ngắn.","tags":["chao_hoi","alo"]}
{"id":"style_sale_bien_006","title":"Giảm giá","content":"Linh động giá.","tags":["giam_gia","fix_gia"]}
{"id":"style_sale_bien_009","title":"Zalo","content":"086912888","tags":["zalo","so_dien_thoai"]}
{"id":"style_sale_bien_012","title":"Thủ tục","content":"Hỗ trợ sang tên.","tags":["sang_ten","cccd"]}
{"id":"procedure","title":"Thủ tục","content":"Hỗ trợ định danh.","tags":["thu_tuc","dinh_danh"]}
{"id":"discount","title":"Hỗ trợ giá","content":"Check giá tốt.","tags":["fix_gia","giam_gia"]}
"""


def context():
    return {
        "page_id": "test_page",
        "sender_psid": "test_sender",
        "expertise_id": 1,
        "expertise": {
            "id": 1,
            "name": "Generic sales",
            "persona_json": "{}",
            "training_content": TRAINING,
            "data_table": "items",
            "data_fields_json": "[]",
        },
    }


class PipelineTests(unittest.TestCase):
    def _run(self, message, state=None, rows=None):
        state = state or {}
        rows = rows or []
        with (
            patch("brain.pipeline.get_conversation_state", return_value=state),
            patch("brain.pipeline.get_recent_conversations", return_value=[]),
            patch("brain.pipeline.upsert_conversation_state"),
            patch("brain.pipeline.add_conversation"),
            patch("brain.pipeline.search_dynamic_rows", return_value=rows) as search,
            patch("brain.pipeline.call_intent_model", return_value='{"intent":"UNKNOWN"}'),
            patch("brain.pipeline.call_model", return_value="cần thêm tiêu chí để bên e check ạ"),
        ):
            reply = process_message("test", message, page_config=context())
        return reply, search

    def test_no_data_routes_never_search(self):
        for message in [
            "hi", "alo", "tôi tên Tuấn", "anh", "chị",
            "sang tên thế nào", "cccd làm sao", "có fix giá không",
            "zalo bên em là gì",
        ]:
            with self.subTest(message=message):
                reply, search = self._run(message)
                search.assert_not_called()
                self.assertNotRegex(
                    reply.lower(),
                    r"dạ anh|dạ chị|anh/chị|anh tuấn|chị linh|anh cần|chị cần",
                )

    def test_search_and_price_routes(self):
        row = {
            "id": "1",
            "content": (
                '{"biển số":"30A-123456","giá":30000000,'
                '"loại xe":"oto","trạng thái":"còn","tỉnh":"Hà Nội"}'
            ),
        }
        reply, search = self._run("giá 30A-123456 bao nhiêu", rows=[row])
        search.assert_called_once()
        self.assertIn("30A-123456 30tr", reply)

    def test_status_searches_specific_item(self):
        route = infer_intent_from_knowledge(
            "30A-123456 còn không", parse_training_records(TRAINING)
        )
        analysis = normalize_intent({}, "30A-123456 còn không", route)
        self.assertEqual("ASK_STATUS", analysis["intent"])
        self.assertTrue(should_search_data("items", analysis))

    def test_discount_uses_selected_item_without_search(self):
        reply, search = self._run(
            "giảm được không",
            state={"selected_plate": "30A-123456"},
        )
        search.assert_not_called()
        self.assertIn("check giá tốt", reply)

    def test_no_rows_is_deterministic(self):
        reply, search = self._run("có biển thái bình không")
        search.assert_called_once()
        self.assertIn("chưa thấy", reply)
        self.assertNotIn("30A-", reply)

    def test_generic_data_fields(self):
        reply = build_data_reply([{
            "id": "sku-1",
            "content": '{"code":"AB12","amount":120000000,"availability":"available"}',
        }], {"intent": "ASK_PRICE"}, "[]")
        self.assertEqual("AB12 120tr ạ", reply)

    def test_key_value_row_format(self):
        reply = build_data_reply([{
            "id": "30A-123456",
            "content": (
                "mã biển: 30A-123456\n"
                "giá: 30000000\n"
                "loại xe: oto\n"
                "trạng thái: còn\n"
                "tỉnh: hà nội"
            ),
        }], {"intent": "ASK_PRICE"}, '[{"key":"plate_number","label":"mã biển"}]')
        self.assertEqual("30A-123456 30tr e bao định danh lên căn cước ạ", reply)

    def test_filter_rows_by_exact_code_and_fuzzy_province(self):
        rows = [
            {
                "id": "30A-123456",
                "content": "mã biển: 30A-123456\ntỉnh: hà nội",
            },
            {
                "id": "17A-123456",
                "content": "mã biển: 17A-123456\ntỉnh: thái bình",
            },
        ]
        by_code = filter_data_rows(
            rows,
            {"entities": {"plate": "30A-123456"}},
        )
        by_province = filter_data_rows(
            rows,
            {"entities": {"province": "ha no"}},
        )
        self.assertEqual(["30A-123456"], [row["id"] for row in by_code])
        self.assertEqual(["30A-123456"], [row["id"] for row in by_province])

    def test_followup_uses_previous_province_and_mentions_other_vehicle(self):
        state = {
            "selected_province": "Hà Nội",
            "vehicle_type": "ô tô",
            "selected_plate": "30A-123456",
            "last_results": [{
                "id": "30A-123456",
                "content": {
                    "plate": "30A-123456",
                    "price": 30000000,
                    "vehicle_type": "oto",
                    "province": "Hà Nội",
                    "status": "còn",
                },
            }],
        }
        with (
            patch("brain.pipeline.get_conversation_state", return_value=state),
            patch("brain.pipeline.get_recent_conversations", return_value=[]),
            patch("brain.pipeline.upsert_conversation_state") as save_state,
            patch("brain.pipeline.add_conversation"),
            patch("brain.pipeline.list_dynamic_rows", return_value=[]),
            patch("brain.pipeline.search_dynamic_rows") as fulltext,
            patch("brain.pipeline.call_intent_model", return_value='{"intent":"UNKNOWN"}'),
            patch("brain.pipeline.call_model", return_value=""),
        ):
            reply = process_message("test", "thế biển xe máy thì sao", page_config=context())

        fulltext.assert_not_called()
        saved = save_state.call_args.args[3]
        self.assertEqual("Hà Nội", saved["selected_province"])
        self.assertEqual("xe máy", saved["vehicle_type"])
        self.assertIn("xe máy Hà Nội", reply)
        self.assertIn("ô tô 30A-123456 30tr", reply)
        self.assertNotIn("tỉnh nào", reply)

    def test_structured_search_matches_thai_binh_oto_alias(self):
        rows = [{
            "id": "17A-123456",
            "content": {
                "plate": "17A-123456",
                "price": 30000000,
                "vehicle_type": "oto",
                "province": "Thái Bình",
                "status": "còn",
            },
        }]
        with (
            patch("brain.pipeline.get_conversation_state", return_value={}),
            patch("brain.pipeline.get_recent_conversations", return_value=[]),
            patch("brain.pipeline.upsert_conversation_state") as save_state,
            patch("brain.pipeline.add_conversation"),
            patch("brain.pipeline.list_dynamic_rows", return_value=rows),
            patch("brain.pipeline.search_dynamic_rows") as fulltext,
            patch("brain.pipeline.call_intent_model", return_value='{"intent":"UNKNOWN"}'),
            patch("brain.pipeline.call_model", return_value=""),
        ):
            reply = process_message("test", "bên mình có biển oto thái bình ko", page_config=context())

        fulltext.assert_not_called()
        saved = save_state.call_args.args[3]
        self.assertEqual("Thái Bình", saved["selected_province"])
        self.assertEqual("ô tô", saved["vehicle_type"])
        self.assertEqual("17A-123456 30tr, biển ô tô còn ạ", reply)

    def test_province_only_search_returns_matching_rows(self):
        rows = [{
            "id": "17A-123456",
            "content": {
                "plate": "17A-123456",
                "price": 30000000,
                "vehicle_type": "ô tô",
                "province": "Thái Bình",
                "status": "còn",
            },
        }]
        with (
            patch("brain.pipeline.get_conversation_state", return_value={}),
            patch("brain.pipeline.get_recent_conversations", return_value=[]),
            patch("brain.pipeline.upsert_conversation_state"),
            patch("brain.pipeline.add_conversation"),
            patch("brain.pipeline.list_dynamic_rows", return_value=rows),
            patch("brain.pipeline.search_dynamic_rows") as fulltext,
            patch("brain.pipeline.call_intent_model", return_value='{"intent":"UNKNOWN"}'),
            patch("brain.pipeline.call_model", return_value=""),
        ):
            reply = process_message("test", "bên mình có biển thái bình ko", page_config=context())

        fulltext.assert_not_called()
        self.assertIn("17A-123456", reply)

    def test_followup_vehicle_type_does_not_search_old_plate(self):
        state = {
            "selected_province": "Thái Bình",
            "vehicle_type": "xe máy",
            "selected_plate": "88B-999999",
        }
        rows = [{
            "id": "17A-123456",
            "content": {
                "plate": "17A-123456",
                "price": 30000000,
                "vehicle_type": "oto",
                "province": "Thái Bình",
                "status": "còn",
            },
        }]
        with (
            patch("brain.pipeline.get_conversation_state", return_value=state),
            patch("brain.pipeline.get_recent_conversations", return_value=[]),
            patch("brain.pipeline.upsert_conversation_state"),
            patch("brain.pipeline.add_conversation"),
            patch("brain.pipeline.list_dynamic_rows", return_value=rows),
            patch("brain.pipeline.search_dynamic_rows") as fulltext,
            patch("brain.pipeline.call_intent_model", return_value='{"intent":"UNKNOWN"}'),
            patch("brain.pipeline.call_model", return_value=""),
        ):
            reply = process_message("test", "oto thì sao", page_config=context())

        fulltext.assert_not_called()
        self.assertIn("17A-123456", reply)
        self.assertNotIn("88B-999999", reply)

    def test_group_same_province_vehicle_status_two_to_three_rows(self):
        rows = [
            {"id": "1", "content": {"plate": "30A-123456", "price": 30000000, "vehicle_type": "oto", "province": "Hà Nội", "status": "còn"}},
            {"id": "2", "content": {"plate": "30A-123457", "price": 35000000, "vehicle_type": "ô tô", "province": "Hà Nội", "status": "còn"}},
            {"id": "3", "content": {"plate": "30K-1234567", "price": 35000000, "vehicle_type": "oto", "province": "Hà Nội", "status": "còn"}},
        ]
        reply = build_data_reply(rows, {"intent": "SEARCH_PLATE"}, "[]")
        self.assertEqual(
            "bên e có mấy biển Hà Nội ô tô ạ\n"
            "30A-123456 30tr, 30A-123457 35tr, 30K-1234567 35tr ạ",
            reply,
        )

    def test_group_same_province_vehicle_more_than_three_rows_price_range(self):
        rows = [
            {"id": "1", "content": {"plate": "30A-123456", "price": 30000000, "vehicle_type": "oto", "province": "Hà Nội", "status": "còn"}},
            {"id": "2", "content": {"plate": "30A-123457", "price": 35000000, "vehicle_type": "oto", "province": "Hà Nội", "status": "còn"}},
            {"id": "3", "content": {"plate": "30K-1234567", "price": 35000000, "vehicle_type": "oto", "province": "Hà Nội", "status": "còn"}},
            {"id": "4", "content": {"plate": "30H-999999", "price": 40000000, "vehicle_type": "oto", "province": "Hà Nội", "status": "hết"}},
        ]
        reply = build_data_reply(rows, {"intent": "SEARCH_PLATE"}, "[]")
        self.assertEqual(
            "bên e có 4 biển Hà Nội ô tô, giá từ 30-40tr ạ\n"
            "gửi trước: 30A-123456 30tr, 30A-123457 35tr, 30K-1234567 35tr ạ",
            reply,
        )

    def test_group_mixed_rows_by_province_vehicle_status(self):
        rows = [
            {"id": "1", "content": {"plate": "30A-123456", "price": 30000000, "vehicle_type": "oto", "province": "Hà Nội", "status": "còn"}},
            {"id": "2", "content": {"plate": "30A-123457", "price": 35000000, "vehicle_type": "oto", "province": "Hà Nội", "status": "còn"}},
            {"id": "3", "content": {"plate": "17A-123456", "price": 30000000, "vehicle_type": "xe máy", "province": "Thái Bình", "status": "còn"}},
        ]
        reply = build_data_reply(rows, {"intent": "SEARCH_PLATE"}, "[]")
        self.assertEqual(
            "Hà Nội ô tô còn: 30A-123456 30tr, 30A-123457 35tr\n"
            "Thái Bình xe máy còn: 17A-123456 30tr",
            reply,
        )


    def test_multi_intent_discount_and_procedure_reply(self):
        route = infer_intent_from_knowledge(
            "bên e fix giá và hỗ trợ sang tên không",
            parse_training_records(TRAINING),
        )
        analysis = normalize_intent({}, "bên e fix giá và hỗ trợ sang tên không", route)
        self.assertIn("ASK_DISCOUNT", analysis["intents"])
        self.assertIn("ASK_PROCEDURE", analysis["intents"])
        self.assertFalse(should_search_data("items", analysis, {}))
        hit_ids = {hit.get("id") for hit in route["knowledge_hits"]}
        self.assertIn("discount", hit_ids)
        self.assertIn("procedure", hit_ids)
        self.assertIn("style_sale_bien_006", hit_ids)
        self.assertIn("style_sale_bien_012", hit_ids)

        reply, search = self._run("bên e fix giá và hỗ trợ sang tên không")
        search.assert_not_called()
        self.assertEqual(
            "chủ biển linh động giá được ạ\n"
            "bên e hỗ trợ sang tên/định danh lên căn cước ạ\n"
            "ưng biển nào bên e check giá tốt và thủ tục cụ thể ạ",
            reply,
        )

    def test_negotiate_offer_with_plate_uses_current_price(self):
        rows = [{
            "id": "30A-123457",
            "content": {
                "plate": "30A-123457",
                "price": 35000000,
                "vehicle_type": "oto",
                "province": "Hà Nội",
                "status": "còn",
            },
        }]
        with (
            patch("brain.pipeline.get_conversation_state", return_value={}),
            patch("brain.pipeline.get_recent_conversations", return_value=[]),
            patch("brain.pipeline.upsert_conversation_state"),
            patch("brain.pipeline.add_conversation"),
            patch("brain.pipeline.list_dynamic_rows", return_value=rows),
            patch("brain.pipeline.search_dynamic_rows") as fulltext,
            patch("brain.pipeline.call_intent_model", return_value='{"intent":"UNKNOWN"}'),
            patch("brain.pipeline.call_model", return_value=""),
        ):
            reply = process_message("test", "thế biển này 30A-123457 a lấy 20tr nhé", page_config=context())

        fulltext.assert_not_called()
        self.assertEqual(
            "30A-123457 đang 35tr ạ\n"
            "20tr bên e báo lại chủ biển xem hỗ trợ được không ạ",
            reply,
        )

    def test_negotiate_offer_uses_selected_plate_from_state(self):
        state = {"selected_plate": "30A-123457"}
        rows = [{
            "id": "30A-123457",
            "content": {
                "plate": "30A-123457",
                "price": 35000000,
                "vehicle_type": "oto",
                "province": "Hà Nội",
                "status": "còn",
            },
        }]
        with (
            patch("brain.pipeline.get_conversation_state", return_value=state),
            patch("brain.pipeline.get_recent_conversations", return_value=[]),
            patch("brain.pipeline.upsert_conversation_state"),
            patch("brain.pipeline.add_conversation"),
            patch("brain.pipeline.list_dynamic_rows", return_value=rows),
            patch("brain.pipeline.search_dynamic_rows") as fulltext,
            patch("brain.pipeline.call_intent_model", return_value='{"intent":"UNKNOWN"}'),
            patch("brain.pipeline.call_model", return_value=""),
        ):
            reply = process_message("test", "20tr được không", page_config=context())

        fulltext.assert_not_called()
        self.assertEqual(
            "30A-123457 đang 35tr ạ\n"
            "20tr bên e báo lại chủ biển xem hỗ trợ được không ạ",
            reply,
        )

    def test_ask_price_is_not_negotiate(self):
        rows = [{
            "id": "30A-123457",
            "content": {
                "plate": "30A-123457",
                "price": 35000000,
                "vehicle_type": "oto",
                "province": "Hà Nội",
                "status": "còn",
            },
        }]
        with (
            patch("brain.pipeline.get_conversation_state", return_value={}),
            patch("brain.pipeline.get_recent_conversations", return_value=[]),
            patch("brain.pipeline.upsert_conversation_state"),
            patch("brain.pipeline.add_conversation"),
            patch("brain.pipeline.list_dynamic_rows", return_value=rows),
            patch("brain.pipeline.search_dynamic_rows") as fulltext,
            patch("brain.pipeline.call_intent_model", return_value='{"intent":"UNKNOWN"}'),
            patch("brain.pipeline.call_model", return_value=""),
        ):
            reply = process_message("test", "giá 30A-123457 bao nhiêu", page_config=context())

        fulltext.assert_not_called()
        self.assertEqual("30A-123457 35tr e bao định danh lên căn cước ạ", reply)


if __name__ == "__main__":
    unittest.main()
