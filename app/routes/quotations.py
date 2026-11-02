from flask import Blueprint, current_app, g, jsonify
from pymongo.errors import PyMongoError

from app.routes.auth import basic_auth_required


quotations_bp = Blueprint("quotations", __name__)


@quotations_bp.get("/<request_id>/quotations")
@basic_auth_required
def list_quotations(request_id):
    database = current_app.extensions["mongo_db"]

    try:
        service_request = database.serviceRequests.find_one({
            "_id": request_id,
            "customerId": g.current_customer["_id"],
        })

    except PyMongoError:
        current_app.logger.exception("Quotation query failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    if service_request is None:
        return jsonify({"error": "Service request not found"}), 404

    quotations = service_request.get("quotations", [])

    return jsonify({
        "count": len(quotations),
        "data": quotations,
    }), 200