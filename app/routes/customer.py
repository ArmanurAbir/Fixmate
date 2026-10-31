from datetime import datetime, timezone
from uuid import uuid4

from flask import Blueprint, current_app, g, jsonify, request
from pymongo.errors import PyMongoError
from werkzeug.security import generate_password_hash

from app.routes.auth import basic_auth_required

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


@customers_bp.get("/<customer_id>")
@basic_auth_required
def get_customer(customer_id):
    if g.current_customer["_id"] != customer_id:
        return jsonify({
            "error": "You can only access your own customer account"
        }), 403

    database = current_app.extensions["mongo_db"]

    try:
        customer = database.customers.find_one(
            {"_id": customer_id, "isActive": True},
            {"passwordHash": 0},
        )
    except PyMongoError:
        current_app.logger.exception("Customer query failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    if customer is None:
        return jsonify({"error": "Customer not found"}), 404

    return jsonify({"data": customer}), 200


@customers_bp.patch("/<customer_id>")
@basic_auth_required
def update_customer(customer_id):
    if g.current_customer["_id"] != customer_id:
        return jsonify({
            "error": "You can only access your own customer account"
        }), 403

    body = request.get_json(silent=True)

    if not isinstance(body, dict) or not body:
        return jsonify({
            "error": "Request body must be a non-empty JSON object"
        }), 400

    allowed_fields = {"displayName", "email", "preferences"}
    unknown_fields = set(body) - allowed_fields

    if unknown_fields:
        return jsonify({
            "error": f"Fields cannot be updated: {', '.join(sorted(unknown_fields))}"
        }), 400

    updates = {}

    if "displayName" in body:
        name = body["displayName"]
        if not isinstance(name, str) or not name.strip():
            return jsonify({
                "error": "displayName must be a non-empty string"
            }), 400
        updates["displayName"] = name.strip()

    if "email" in body:
        email = body["email"]
        if not isinstance(email, str) or "@" not in email:
            return jsonify({"error": "A valid email is required"}), 400
        updates["email"] = email.strip().lower()

    if "preferences" in body:
        if not isinstance(body["preferences"], dict):
            return jsonify({
                "error": "preferences must be a JSON object"
            }), 400
        updates["preferences"] = body["preferences"]

    database = current_app.extensions["mongo_db"]

    try:
        customer = database.customers.find_one(
            {"_id": customer_id, "isActive": True},
            {"_id": 1},
        )

        if customer is None:
            return jsonify({"error": "Customer not found"}), 404

        if "email" in updates:
            duplicate = database.customers.find_one(
                {
                    "email": updates["email"],
                    "_id": {"$ne": customer_id},
                },
                {"_id": 1},
            )
            if duplicate:
                return jsonify({
                    "error": "Email is already registered"
                }), 409

        updates["updatedAt"] = datetime.now(timezone.utc)

        result = database.customers.update_one(
            {"_id": customer_id, "isActive": True},
            {"$set": updates},
        )

        if result.matched_count == 0:
            return jsonify({"error": "Customer not found"}), 404

        updated_customer = database.customers.find_one(
            {"_id": customer_id},
            {"passwordHash": 0},
        )

    except PyMongoError:
        current_app.logger.exception("Customer update failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({"data": updated_customer}), 200


@customers_bp.post("")
def create_customer():
    body = request.get_json(silent=True)

    if not isinstance(body, dict):
        return jsonify({"error": "Request body must be JSON"}), 400

    display_name = body.get("displayName")
    email = body.get("email")
    password = body.get("password")

    if not isinstance(display_name, str) or not display_name.strip():
        return jsonify({"error": "displayName is required"}), 400

    if not isinstance(email, str) or "@" not in email:
        return jsonify({"error": "A valid email is required"}), 400

    if not isinstance(password, str) or len(password) < 8:
        return jsonify({
            "error": "Password must be at least 8 characters"
        }), 400

    email = email.strip().lower()
    display_name = display_name.strip()
    database = current_app.extensions["mongo_db"]

    try:
        existing_customer = database.customers.find_one(
            {"email": email},
            {"_id": 1},
        )
        if existing_customer:
            return jsonify({
                "error": "Email is already registered"
            }), 409

        new_customer = {
            "_id": f"CUST{uuid4().hex[:12].upper()}",
            "displayName": display_name,
            "email": email,
            "passwordHash": generate_password_hash(password),
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

    new_customer.pop("passwordHash", None)

    return jsonify({"data": new_customer}), 201


@customers_bp.delete("/<customer_id>")
@basic_auth_required
def delete_customer(customer_id):
    if g.current_customer["_id"] != customer_id:
        return jsonify({
            "error": "You can only access your own customer account"
        }), 403

    database = current_app.extensions["mongo_db"]

    try:
        result = database.customers.update_one(
            {"_id": customer_id, "isActive": True},
            {
                "$set": {
                    "isActive": False,
                    "updatedAt": datetime.now(timezone.utc),
                }
            },
        )
    except PyMongoError:
        current_app.logger.exception("Customer deletion failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    if result.matched_count == 0:
        return jsonify({"error": "Customer not found"}), 404

    return jsonify({
        "message": "Customer deactivated",
        "data": {
            "_id": customer_id,
            "isActive": False,
        },
    }), 200