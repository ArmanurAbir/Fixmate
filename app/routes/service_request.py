from datetime import datetime, timezone
from uuid import uuid4

from flask import Blueprint, current_app, g, jsonify, request
from pymongo.errors import PyMongoError

from app.routes.auth import basic_auth_required


service_requests_bp = Blueprint("service_requests", __name__)


@service_requests_bp.get("")
def list_service_requests():
    database = current_app.extensions["mongo_db"]

    try:
        service_requests = list(
            database.serviceRequests.find({})
            .sort("_id", 1)
            .limit(20)
        )
    except PyMongoError:
        current_app.logger.exception("Service request query failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({
        "count": len(service_requests),
        "data": service_requests,
    }), 200


@service_requests_bp.post("")
@basic_auth_required
def create_service_request():
    body = request.get_json(silent=True)

    if not isinstance(body, dict):
        return jsonify({"error": "Request body must be JSON"}), 400

    category_id = body.get("categoryId")
    description = body.get("description")
    budget_pence = body.get("budgetPence")
    details = body.get("details", {})
    attachments = body.get("attachments", [])

    if not isinstance(category_id, str) or not category_id.strip():
        return jsonify({"error": "categoryId is required"}), 400

    if not isinstance(description, str) or not description.strip():
        return jsonify({"error": "description is required"}), 400

    if type(budget_pence) is not int or budget_pence <= 0:
        return jsonify({
            "error": "budgetPence must be a positive integer"
        }), 400

    if not isinstance(details, dict):
        return jsonify({"error": "details must be an object"}), 400

    if not isinstance(attachments, list):
        return jsonify({"error": "attachments must be an array"}), 400

    database = current_app.extensions["mongo_db"]
    category_id = category_id.strip()

    try:
        category = database.serviceCategories.find_one(
            {"_id": category_id},
            {"_id": 1},
        )

        if category is None:
            return jsonify({"error": "Service category not found"}), 404

        new_request = {
            "_id": f"REQ{uuid4().hex[:12].upper()}",
            "customerId": g.current_customer["_id"],
            "categoryId": category_id,
            "description": description.strip(),
            "budgetPence": budget_pence,
            "assetId": body.get("assetId"),
            "details": details,
            "attachments": attachments,
            "createdAt": datetime.now(timezone.utc),
        }

        database.serviceRequests.insert_one(new_request)

    except PyMongoError:
        current_app.logger.exception("Service request creation failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({"data": new_request}), 201


@service_requests_bp.get("/<request_id>")
@basic_auth_required
def get_service_request(request_id):
    database = current_app.extensions["mongo_db"]

    try:
        service_request = database.serviceRequests.find_one({
            "_id": request_id,
            "customerId": g.current_customer["_id"],
        })
    except PyMongoError:
        current_app.logger.exception("Service request lookup failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    if service_request is None:
        return jsonify({"error": "Service request not found"}), 404

    return jsonify({"data": service_request}), 200


@service_requests_bp.patch("/<request_id>")
@basic_auth_required
def update_service_request(request_id):
    body = request.get_json(silent=True)

    if not isinstance(body, dict) or not body:
        return jsonify({
            "error": "Request body must be a non-empty JSON object"
        }), 400

    allowed_fields = {
        "categoryId",
        "description",
        "budgetPence",
        "assetId",
        "details",
        "attachments",
    }

    if not set(body).issubset(allowed_fields):
        return jsonify({
            "error": "Request contains unsupported fields"
        }), 400

    updates = {}

    if "categoryId" in body:
        category_id = body["categoryId"]

        if not isinstance(category_id, str) or not category_id.strip():
            return jsonify({"error": "categoryId must be a non-empty string"}), 400

        updates["categoryId"] = category_id.strip()

    if "description" in body:
        description = body["description"]

        if not isinstance(description, str) or not description.strip():
            return jsonify({"error": "description must be a non-empty string"}), 400

        updates["description"] = description.strip()

    if "budgetPence" in body:
        budget_pence = body["budgetPence"]

        if type(budget_pence) is not int or budget_pence <= 0:
            return jsonify({
                "error": "budgetPence must be a positive integer"
            }), 400

        updates["budgetPence"] = budget_pence

    if "assetId" in body:
        updates["assetId"] = body["assetId"]

    if "details" in body:
        if not isinstance(body["details"], dict):
            return jsonify({"error": "details must be an object"}), 400
        updates["details"] = body["details"]

    if "attachments" in body:
        if not isinstance(body["attachments"], list):
            return jsonify({"error": "attachments must be an array"}), 400
        updates["attachments"] = body["attachments"]

    database = current_app.extensions["mongo_db"]

    try:
        if "categoryId" in updates:
            category = database.serviceCategories.find_one(
                {"_id": updates["categoryId"]},
                {"_id": 1},
            )
            if category is None:
                return jsonify({"error": "Service category not found"}), 404

        result = database.serviceRequests.update_one(
            {
                "_id": request_id,
                "customerId": g.current_customer["_id"],
            },
            {
                "$set": {
                    **updates,
                    "updatedAt": datetime.now(timezone.utc),
                }
            },
        )

        if result.matched_count == 0:
            return jsonify({"error": "Service request not found"}), 404

        updated_request = database.serviceRequests.find_one({
            "_id": request_id,
            "customerId": g.current_customer["_id"],
        })

    except PyMongoError:
        current_app.logger.exception("Service request update failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({"data": updated_request}), 200

@service_requests_bp.delete("/<request_id>")
@basic_auth_required
def delete_service_request(request_id):
    database = current_app.extensions["mongo_db"]
    customer_id = g.current_customer["_id"]

    try:
        result = database.serviceRequests.delete_one({
            "_id": request_id,
            "customerId": customer_id,
        })
    except PyMongoError:
        current_app.logger.exception("Service request deletion failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    if result.deleted_count == 0:
        return jsonify({"error": "Service request not found"}), 404

    return jsonify({"message": "Service request deleted"}), 200