from flask import Blueprint, current_app, jsonify
from pymongo.errors import PyMongoError

service_categories_bp = Blueprint("service_categories", __name__)


@service_categories_bp.get("")
def list_service_categories():
    database = current_app.extensions["mongo_db"]

    try:
        categories = list(
            database.serviceCategories.find(
                {},
                {"_id": 1, "name": 1, "description": 1, "taskTypes": 1},
            ).sort("_id", 1)
        )
    except PyMongoError:
        current_app.logger.exception("Service category query failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({
        "count": len(categories),
        "data": categories,
    }), 200


@service_categories_bp.get("/<category_id>")
def get_service_category(category_id):
    database = current_app.extensions["mongo_db"]

    try:
        category = database.serviceCategories.find_one(
            {"_id": category_id}
        )
    except PyMongoError:
        current_app.logger.exception("Service category query failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    if category is None:
        return jsonify({"error": "Service category not found"}), 404

    return jsonify({"data": category}), 200