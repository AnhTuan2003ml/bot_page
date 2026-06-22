from database.plate_manager import (
    add_plate,
    delete_plate,
    get_all_plates,
    get_available_plates,
    get_stats,
    update_plate_meta,
    update_plate_price,
    update_plate_status,
)
from utils.cache import invalidate_plates_cache


def list_plates():
    return {"success": True, "data": get_all_plates()}, 200


def list_available_plates():
    return {"success": True, "data": get_available_plates()}, 200


def create_plate(data):
    data = data or {}
    plate_number = data.get("plate_number")
    price = data.get("price", 0)
    status = data.get("status", "available")
    vehicle_type = data.get("vehicle_type", "")
    if not plate_number:
        return {"success": False, "error": "Plate number required"}, 400

    try:
        add_plate(plate_number, price, status, vehicle_type)
        invalidate_plates_cache()
        return {"success": True, "message": f"Added {plate_number}"}, 200
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def update_plate(plate_number, data):
    data = data or {}
    updates = {}
    for key in ("price", "status", "plate_number", "vehicle_type"):
        if key in data:
            updates[key] = data[key]

    try:
        if "price" in updates:
            update_plate_price(plate_number, updates["price"])
        if "status" in updates:
            update_plate_status(plate_number, updates["status"])
        if "vehicle_type" in updates:
            update_plate_meta(plate_number, updates.get("vehicle_type"))
        if "plate_number" in updates and updates["plate_number"] != plate_number:
            from database.plate_manager import update_plate_number
            update_plate_number(plate_number, updates["plate_number"])

        invalidate_plates_cache()
        return {"success": True, "message": f"Updated {plate_number}"}, 200
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def remove_plate(plate_number):
    try:
        delete_plate(plate_number)
        invalidate_plates_cache()
        return {"success": True, "message": f"Deleted {plate_number}"}, 200
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def database_stats():
    return {"success": True, "data": get_stats()}, 200
