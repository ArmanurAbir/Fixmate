from datetime import datetime, timezone
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request
from pymongo.errors import PyMongoError

customers_bp = Blueprint("customers", __name__)


@customers_bp.get("")
def list_customers():
    database = current_app.extensions["mongo_db"]

    fields = {
        "_id": 1,
        "displayName": 1,
        "isActive": 1,
        "createdAt": 1,
    }

    try:
        customers = list(
            database.customers.find(
                {"isActive": True},
                fields,
            ).sort("_id", 1).limit(20)
        )
    except PyMongoError:
        current_app.logger.exception("Customer query failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({
        "count": len(customers),
        "data": customers,
    }), 200


@customers_bp.post("")
def create_customer():
    body = request.get_json(silent=True)

    if not isinstance(body, dict):
        return jsonify({"error": "Request body must be JSON"}), 400

    display_name = body.get("displayName")
    email = body.get("email")

    if not isinstance(display_name, str) or not display_name.strip():
        return jsonify({"error": "displayName is required"}), 400

    if not isinstance(email, str) or "@" not in email:
        return jsonify({"error": "A valid email is required"}), 400

    email = email.strip().lower()
    display_name = display_name.strip()
    database = current_app.extensions["mongo_db"]

    try:
        existing_customer = database.customers.find_one(
            {"email": email},
            {"_id": 1},
        )
        if existing_customer:
            return jsonify({"error": "Email is already registered"}), 409

        new_customer = {
            "_id": f"CUST{uuid4().hex[:12].upper()}",
            "displayName": display_name,
            "email": email,
            "isActive": True,
            "createdAt": datetime.now(timezone.utc),
            "preferences": {
                "notifications": {
                    "email": True,
                    "sms": False,
                },
                "preferredContact": "email",
            },
            "properties": [],
            "savedProviderIds": [],
        }

        database.customers.insert_one(new_customer)
    except PyMongoError:
        current_app.logger.exception("Customer creation failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({"data": new_customer}), 201