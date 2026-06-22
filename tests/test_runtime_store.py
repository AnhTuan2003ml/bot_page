import unittest
from unittest.mock import patch

from brain.pipeline import process_message
from services.runtime_store import RuntimeStore, resolve_domain
from services.search_index import SearchIndex


class SearchIndexTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {
                "id": "30A-123456",
                "content": {
                    "plate": "30A-123456",
                    "price": 30000000,
                    "vehicle_type": "ô tô",
                    "province": "Hà Nội",
                    "status": "còn",
                },
            },
            {
                "id": "JEAN-01",
                "content": {
                    "product_type": "quần jean",
                    "size": "M",
                    "color": "đen",
                    "price": 450000,
                },
            },
        ]

    def test_structured_search_uses_memory_rows(self):
        index = SearchIndex(self.rows)
        result = index.search({"province": "ha noi", "vehicle_type": "oto"})
        self.assertEqual(["30A-123456"], [row["id"] for row in result])

    def test_clear_filter_does_not_fallback_to_fulltext(self):
        index = SearchIndex(self.rows)
        result = index.search({"product_type": "quần kaki"}, query="quần jean")
        self.assertEqual([], result)

    def test_domain_is_resolved_from_expertise_not_message(self):
        expertise = {"name": "Tư vấn quần áo"}
        self.assertEqual("fashion", resolve_domain(expertise, {}))


class RuntimeStoreTests(unittest.TestCase):
    def test_load_all_builds_page_context_and_index_once(self):
        store = RuntimeStore()
        expertise = {
            "id": 2,
            "name": "Tư vấn quần áo",
            "job_title": "",
            "description": "",
            "persona_json": '{"legacy_skill_id":"tu_van_quan_ao"}',
            "training_content": '{"id":"hello","content":"Xin chào","tags":["chao_hoi"]}',
            "data_table": "fashion_items",
            "data_fields_json": "[]",
            "domain": "fashion",
        }
        page = {
            "page_id": "page-1",
            "page_name": "Fashion",
            "page_access_token": "token",
            "ai_skill": "tu_van_quan_ao",
            "is_active": 1,
        }
        rows = [{"id": "JEAN-01", "content": {"product_type": "quần jean"}}]

        with (
            patch("services.runtime_store.load_config_cache"),
            patch("database.expertise_manager.list_expertises", return_value=[expertise]),
            patch("database.page_manager.get_all_pages", return_value=[page]),
            patch("database.dynamic_table_manager.list_dynamic_rows", return_value=rows) as load_rows,
        ):
            store.load_all()

        context = store.get_context("page-1")
        self.assertEqual("fashion", context["domain"])
        self.assertEqual(1, len(context["knowledge_records"]))
        self.assertEqual(["JEAN-01"], [row["id"] for row in context["search_index"].search({"product_type": "quần jean"})])
        load_rows.assert_called_once_with("fashion_items", limit=1_000_000_000)

    def test_reload_data_table_swaps_index_for_next_message(self):
        store = RuntimeStore()
        expertise = {
            "id": 2,
            "name": "Tư vấn quần áo",
            "persona_json": "{}",
            "training_content": "",
            "data_table": "fashion_items",
            "data_fields_json": "[]",
            "domain": "fashion",
        }
        runtime = store._build_expertise(expertise, load_rows=False)
        store.expertises_by_id[2] = runtime
        store.data_by_expertise_id[2] = []
        store.indexes_by_expertise_id[2] = runtime["search_index"]

        new_rows = [{"id": "JEAN-NEW", "content": {"product_type": "quần jean"}}]
        with patch.object(store, "_load_rows", return_value=new_rows):
            store.reload_data_table(2)

        result = store.indexes_by_expertise_id[2].search({"product_type": "quần jean"})
        self.assertEqual(["JEAN-NEW"], [row["id"] for row in result])

    def test_message_path_does_not_reload_runtime_data(self):
        rows = [{
            "id": "30A-123456",
            "content": {
                "plate": "30A-123456",
                "province": "Hà Nội",
                "vehicle_type": "ô tô",
                "price": 30000000,
            },
        }]
        expertise = {
            "id": 1,
            "name": "Tư vấn biển số",
            "persona_json": "{}",
            "training_content": "",
            "data_table": "plates",
            "data_fields_json": "[]",
            "domain": "license_plate",
            "domain_label": "biển số",
            "data_rows": rows,
            "search_index": SearchIndex(rows, domain="license_plate"),
        }
        context = {
            "page_id": "page-1",
            "sender_psid": "sender",
            "expertise_id": 1,
            "expertise": expertise,
            "domain": "license_plate",
            "domain_label": "biển số",
            "data_rows": rows,
            "search_index": expertise["search_index"],
        }
        with (
            patch("brain.pipeline.get_conversation_state", return_value={}),
            patch("brain.pipeline.upsert_conversation_state"),
            patch("brain.pipeline.add_conversation"),
            patch("brain.pipeline.call_intent_model", return_value='{"intent":"UNKNOWN"}'),
            patch("brain.pipeline.call_model", return_value=""),
            patch("database.page_manager.get_page", side_effect=AssertionError("page DB read")),
            patch("database.expertise_manager.get_expertise", side_effect=AssertionError("expertise DB read")),
            patch("database.dynamic_table_manager.list_dynamic_rows", side_effect=AssertionError("data DB read")),
        ):
            replies = [
                process_message("sender", "biển hà nội", page_config=context)
                for _ in range(10)
            ]
        self.assertTrue(all("30A-123456" in reply for reply in replies))


if __name__ == "__main__":
    unittest.main()
