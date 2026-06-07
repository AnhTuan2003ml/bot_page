import unittest

from brain.knowledge_retriever import (
    infer_intent_from_knowledge,
    normalize_vi,
    parse_training_records,
    retrieve_knowledge,
    tokenize,
)


TRAINING = """
{"id":"style_sale_bien_002","title":"Chào hỏi","content":"Trả lời chào ngắn.","tags":["chao_hoi","alo"]}
{"id":"style_sale_bien_006","title":"Hỗ trợ giá","content":"Bên e linh động giá.","tags":["giam_gia","fix_gia"]}
{"id":"style_sale_bien_012","title":"Thủ tục","content":"Bên e hỗ trợ sang tên.","tags":["sang_ten","cccd"]}
{"id":"procedure","title":"Sang tên","content":"Hỗ trợ định danh căn cước.","tags":["thu_tuc","dinh_danh"]}
{"id":"discount","title":"Giảm giá","content":"Check giá tốt.","tags":["fix_gia","ho_tro_gia"]}
"""


class KnowledgeRetrieverTests(unittest.TestCase):
    def setUp(self):
        self.records = parse_training_records(TRAINING)

    def test_parse_and_normalize(self):
        self.assertEqual(5, len(self.records))
        self.assertEqual("thai binh", normalize_vi("Thái Bình"))
        self.assertIn("30a", tokenize("hi 30A"))

    def test_greeting_does_not_need_data(self):
        route = infer_intent_from_knowledge("hi", self.records)
        self.assertEqual("GREETING", route["intent_hint"])
        self.assertFalse(route["need_data_hint"])

    def test_procedure_hits(self):
        route = infer_intent_from_knowledge("sang tên thế nào", self.records)
        ids = {hit["id"] for hit in route["knowledge_hits"]}
        self.assertEqual("ASK_PROCEDURE", route["intent_hint"])
        self.assertFalse(route["need_data_hint"])
        self.assertIn("procedure", ids)
        self.assertIn("style_sale_bien_012", ids)

    def test_discount_hits(self):
        hits = retrieve_knowledge("có fix giá không", self.records, "ASK_DISCOUNT")
        ids = {hit["id"] for hit in hits}
        self.assertIn("discount", ids)
        self.assertIn("style_sale_bien_006", ids)

    def test_bad_json_line_is_skipped(self):
        records = parse_training_records('{"id":"ok","content":"x"}\n{bad json}')
        self.assertEqual(["ok"], [record["id"] for record in records])


if __name__ == "__main__":
    unittest.main()
