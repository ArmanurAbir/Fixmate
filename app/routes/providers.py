from flask import Blueprint, current_app, jsonify
from pymongo.errors import PyMongoError

providers_bp = Blueprint("providers", __name__)


@providers_bp.get("")
def list_providers():
    database = current_app.extensions["mongo_db"]

    # Return selected public fields for this initial endpoint.
    fields = {
        "_id": 1,
        "businessName": 1,
        "organisationId": 1,
        "isVerified": 1,
        "ratingSummary": 1,
    }

    try:
        providers = list(
            database.providers.find(
                {"isActive": True}, fields
            ).sort("_id", 1).limit(20)
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