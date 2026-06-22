"""Dynamic data helper for Chuyên môn AI. Old skill_items/skill_fields logic removed."""
from database.dynamic_table_manager import search_dynamic_rows
from database.expertise_manager import get_expertise


def get_skill_data_context(skill_name, query=None, limit=10):
    expertise = get_expertise(skill_name)
    if not expertise or not expertise.get('data_table') or not query:
        return {'items_for_ai': []}
    rows = search_dynamic_rows(expertise['data_table'], query, limit=limit)
    return {'items_for_ai': rows}
