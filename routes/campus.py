from flask import Blueprint, jsonify
from routes.helpers import api_error, store

bp = Blueprint("campus", __name__, url_prefix="/api/campus")


@bp.get("/blocks")
def blocks():
    rows = store().get_all("blocks")
    for row in rows:
        labs = store().get_all("labs", {"block_id": row["block_id"]})
        row["systems"] = sum(lab["number_of_systems"] for lab in labs)
        row["labs"] = len(labs)
    return jsonify({"ok": True, "blocks": rows})


@bp.get("/blocks/<block_id>/labs")
def labs(block_id):
    block = store().get_one("blocks", {"block_id": block_id})
    if not block:
        return api_error("Campus block not found.", 404)
    labs = store().get_all("labs", {"block_id": block_id})
    assignments = store().get_all("assignments")
    for lab in labs:
        lab["current_assignments"] = [item for item in assignments if item["resource_id"] == lab["lab_id"] and item.get("status") in {"locked", "outage"}]
    return jsonify({"ok": True, "block": block, "labs": labs})
