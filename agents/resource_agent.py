from __future__ import annotations

from services.availability_service import equipment_available_quantity, resource_is_available


def recommend_equipment(store, requirements, start, end):
    requested = requirements.get("required_equipment", [])
    equipment = []
    for need in requested:
        candidate = next((item for item in store.get_all("equipment") if item["type"].lower() == need["type"].lower() and item.get("status") == "active"), None)
        if candidate:
            remaining = equipment_available_quantity(store, candidate, start, end)
            equipment.append({"resource_id": candidate["equipment_id"], "resource_type": "equipment", "name": candidate["name"], "quantity": need["quantity"], "assignment_type": "equipment",
                              "score": 100 if remaining >= need["quantity"] else 0, "positive_reasons": [f"{remaining} units available in selected slot"], "negative_reasons": [] if remaining >= need["quantity"] else ["Insufficient available quantity"]})
    return equipment


def recommend_vehicle(store, requirements, start, end):
    if not requirements.get("transport_required"):
        return []
    vehicle = next((row for row in store.get_all("vehicles") if row.get("status") == "active" and resource_is_available(store, row["vehicle_id"], start, end)), None)
    return [] if not vehicle else [{"resource_id": vehicle["vehicle_id"], "resource_type": "vehicle", "name": f"{vehicle['type']} · {vehicle['driver']}", "quantity": 1, "assignment_type": "guest transport"}]
