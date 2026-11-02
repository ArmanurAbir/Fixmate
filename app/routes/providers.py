from datetime import datetime, timezone
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request
from pymongo.errors import PyMongoError
from werkzeug.security import check_password_hash, generate_password_hash

from app.routes.auth import basic_auth_required

providers_bp = Blueprint("providers", __name__)


@providers_bp.get("")
def list_providers():
    database = current_app.extensions["mongo_db"]

    fields = {
        "_id": 1,
        "businessName": 1,
        "organisationId": 1,
        "isVerified": 1,
        "ratingSummary": 1,
    }

    try:
        providers = list(
            database.providers.find({"isActive": True}, fields)
            .sort("_id", 1)
            .limit(20)
        )
    except PyMongoError:
        current_app.logger.exception("Provider query failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({
        "count": len(providers),
        "data": providers,
    }), 200


@providers_bp.post("")
def create_provider():
    body = request.get_json(silent=True)

    if not isinstance(body, dict):
        return jsonify({"error": "Request body must be JSON"}), 400

    business_name = body.get("businessName")
    organisation_id = body.get("organisationId")
    email = body.get("email")
    password = body.get("password")

    if not isinstance(business_name, str) or not business_name.strip():
        return jsonify({"error": "businessName is required"}), 400

    if not isinstance(organisation_id, str) or not organisation_id.strip():
        return jsonify({"error": "organisationId is required"}), 400

    if not isinstance(email, str) or "@" not in email:
        return jsonify({"error": "A valid email is required"}), 400

    if not isinstance(password, str) or len(password) < 8:
        return jsonify({
            "error": "Password must be at least 8 characters"
        }), 400

    database = current_app.extensions["mongo_db"]
    email = email.strip().lower()
    organisation_id = organisation_id.strip()

    try:
        if database.providers.find_one({"email": email}, {"_id": 1}):
            return jsonify({"error": "Email is already registered"}), 409

        provider = {
            "_id": f"PROV{uuid4().hex[:12].upper()}",
            "organisationId": organisation_id,
            "businessName": business_name.strip(),
            "email": email,
            "passwordHash": generate_password_hash(password),
            "isActive": True,
            "isVerified": False,
            "location": body.get("location", {}),
            "serviceRadiusKm": body.get("serviceRadiusKm", 25),
            "services": body.get("services", []),
            "ratingSummary": {
                "average": 0,
                "count": 0,
            },
            "createdAt": datetime.now(timezone.utc),
        }

        database.providers.insert_one(provider)

    except PyMongoError:
        current_app.logger.exception("Provider creation failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    provider.pop("passwordHash", None)
    return jsonify({"data": provider}), 201


@providers_bp.get("/<provider_id>")
def get_provider(provider_id):
    database = current_app.extensions["mongo_db"]

    fields = {
        "_id": 1,
        "businessName": 1,
        "organisationId": 1,
        "isVerified": 1,
        "services": 1,
        "ratingSummary": 1,
    }

    try:
        provider = database.providers.find_one(
            {"_id": provider_id, "isActive": True},
            fields,
        )
    except PyMongoError:
        current_app.logger.exception("Provider query failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    if provider is None:
        return jsonify({"error": "Provider not found"}), 404

    return jsonify({"data": provider}), 200
@providers_bp.patch("/<provider_id>")
def update_provider(provider_id):
    credentials = request.authorization

    if (
        credentials is None
        or credentials.type.lower() != "basic"
        or not credentials.username
        or not credentials.password
    ):
        return jsonify({"error": "Basic authentication is required"}), 401

    database = current_app.extensions["mongo_db"]

    try:
        provider = database.providers.find_one({
            "_id": provider_id,
            "isActive": True,
        })

        if (
            provider is None
            or provider.get("email", "").lower()
            != credentials.username.strip().lower()
            or not provider.get("passwordHash")
            or not check_password_hash(
                provider["passwordHash"],
                credentials.password,
            )
        ):
            return jsonify({"error": "Invalid provider credentials"}), 401

        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "Request body must be JSON"}), 400

        allowed_fields = {
            "businessName",
            "location",
            "serviceRadiusKm",
            "services",
        }
        updates = {
            key: value
            for key, value in body.items()
            if key in allowed_fields
        }

        if not updates:
            return jsonify({"error": "No editable fields supplied"}), 400

        if "businessName" in updates:
            if not isinstance(updates["businessName"], str) or not updates["businessName"].strip():
                return jsonify({"error": "businessName must not be empty"}), 400
            updates["businessName"] = updates["businessName"].strip()

        updates["updatedAt"] = datetime.now(timezone.utc)

        database.providers.update_one(
            {"_id": provider_id},
            {"$set": updates},
        )

        updated_provider = database.providers.find_one(
            {"_id": provider_id},
            {"passwordHash": 0},
        )

    except PyMongoError:
        current_app.logger.exception("Provider update failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({"data": updated_provider}), 200

@providers_bp.delete("/<provider_id>")
def delete_provider(provider_id):
    credentials = request.authorization

    if (
        credentials is None
        or credentials.type.lower() != "basic"
        or not credentials.username
        or not credentials.password
    ):
        return jsonify({
            "error": "Basic authentication is required"
        }), 401

    database = current_app.extensions["mongo_db"]
    email = credentials.username.strip().lower()

    try:
        provider = database.providers.find_one({
            "_id": provider_id,
            "isActive": True,
        })

        if (
            provider is None
            or provider.get("email", "").lower() != email
            or not provider.get("passwordHash")
            or not check_password_hash(
                provider["passwordHash"],
                credentials.password,
            )
        ):
            return jsonify({
                "error": "Invalid provider credentials"
            }), 401

        result = database.providers.update_one(
            {
                "_id": provider_id,
                "email": email,
                "isActive": True,
            },
            {
                "$set": {
                    "isActive": False,
                    "updatedAt": datetime.now(timezone.utc),
                }
            },
        )

        if result.matched_count == 0:
            return jsonify({"error": "Provider not found"}), 404

    except PyMongoError:
        current_app.logger.exception("Provider deletion failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({"message": "Provider deleted"}), 200