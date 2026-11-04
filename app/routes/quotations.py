from datetime import datetime, timedelta, timezone
from uuid import uuid4

from flask import Blueprint, current_app, g, jsonify, request
from pymongo.errors import PyMongoError

from app.routes.auth import (
    basic_auth_required,
    provider_basic_auth_required,
)


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


def prepare_line_items(items, service):
    if not isinstance(items, list) or not items:
        raise ValueError("lineItems must be a non-empty array")

    tasks = {
        task["taskId"]: task
        for task in service.get("tasks", [])
    }

    prepared = []

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each line item must be an object")

        task_id = item.get("taskId")

        if not isinstance(task_id, str) or task_id not in tasks:
            raise ValueError(
                "taskId must belong to the provider service"
            )

        description = item.get(
            "description",
            tasks[task_id].get("name"),
        )
        quantity = item.get("quantity")
        labour_price = item.get("unitLabourPricePence")
        materials = item.get("materials", [])

        if not isinstance(description, str) or not description.strip():
            raise ValueError("Each line item needs a description")

        if type(quantity) is not int or quantity <= 0:
            raise ValueError(
                "Line item quantity must be a positive integer"
            )

        if type(labour_price) is not int or labour_price < 0:
            raise ValueError(
                "unitLabourPricePence must be a non-negative integer"
            )

        if not isinstance(materials, list):
            raise ValueError("materials must be an array")

        prepared_materials = []
        materials_total = 0

        for material in materials:
            if not isinstance(material, dict):
                raise ValueError("Each material must be an object")

            name = material.get("name")
            unit = material.get("unit", "each")
            material_quantity = material.get("quantity")
            unit_price = material.get("unitPricePence")

            if not isinstance(name, str) or not name.strip():
                raise ValueError("Each material needs a name")

            if not isinstance(unit, str) or not unit.strip():
                raise ValueError(
                    "Material unit must be a non-empty string"
                )

            if (
                type(material_quantity) is not int
                or material_quantity <= 0
            ):
                raise ValueError(
                    "Material quantity must be a positive integer"
                )

            if type(unit_price) is not int or unit_price < 0:
                raise ValueError(
                    "unitPricePence must be a non-negative integer"
                )

            prepared_materials.append({
                "materialId": f"MAT{uuid4().hex[:12].upper()}",
                "name": name.strip(),
                "quantity": material_quantity,
                "unit": unit.strip(),
                "unitPricePence": unit_price,
            })

            # Material quantities are totals for this line item.
            materials_total += material_quantity * unit_price

        prepared.append({
            "lineItemId": f"LI{uuid4().hex[:12].upper()}",
            "taskId": task_id,
            "description": description.strip(),
            "quantity": quantity,
            "unitLabourPricePence": labour_price,
            "materials": prepared_materials,
            "subtotalPence": (
                quantity * labour_price + materials_total
            ),
        })

    return prepared


@quotations_bp.post("/<request_id>/quotations")
@provider_basic_auth_required
def submit_quotation(request_id):
    body = request.get_json(silent=True)

    if not isinstance(body, dict):
        return jsonify({"error": "Request body must be JSON"}), 400

    service_id = body.get("serviceId")

    if not isinstance(service_id, str) or not service_id.strip():
        return jsonify({"error": "serviceId is required"}), 400

    service_id = service_id.strip()
    provider = g.current_provider
    print("DEBUG provider ID:", provider.get("_id") if provider else None)
    print("DEBUG requested service:", repr(service_id))
    print("DEBUG provider services:", provider.get("services", []) if provider else [])

    service = next(
        (
            item
            for item in provider.get("services", [])
            if item.get("serviceId") == service_id
        ),
        None,
    )

    if service is None:
        return jsonify({"error": "Provider service not found"}), 404

    call_out_fee = body.get(
        "callOutFeePence",
        service.get("pricing", {}).get("callOutFeePence", 0),
    )

    if type(call_out_fee) is not int or call_out_fee < 0:
        return jsonify({
            "error": (
                "callOutFeePence must be a non-negative integer"
            )
        }), 400

    try:
        line_items = prepare_line_items(
            body.get("lineItems"),
            service,
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    total = call_out_fee + sum(
        item["subtotalPence"]
        for item in line_items
    )

    if total <= 0:
        return jsonify({
            "error": "Quotation total must be positive"
        }), 400

    database = current_app.extensions["mongo_db"]

    try:
        service_request = database.serviceRequests.find_one({
            "_id": request_id,
        })

        if service_request is None:
            return jsonify({
                "error": "Service request not found"
            }), 404

        if service_request.get("status") not in (
            None,
            "Open",
            "Quoted",
        ):
            return jsonify({
                "error": (
                    "This service request is not accepting quotations"
                )
            }), 409

        if (
            service.get("categoryId")
            != service_request.get("categoryId")
        ):
            return jsonify({
                "error": (
                    "Provider service must match the request category"
                )
            }), 400

        now = datetime.now(timezone.utc)

        quotation = {
            "quoteId": f"Q{uuid4().hex[:12].upper()}",
            "providerId": provider["_id"],
            "serviceId": service_id,
            "lineItems": line_items,
            "callOutFeePence": call_out_fee,
            "totalPence": total,
            "currency": "GBP",
            "status": "Pending",
            "createdAt": now,
            "expiresAt": now + timedelta(days=7),
        }

        result = database.serviceRequests.update_one(
            {
                "_id": request_id,
                "categoryId": service["categoryId"],
                "status": {
                    "$in": [None, "Open", "Quoted"],
                },
                "quotations.status": {
                    "$ne": "Accepted",
                },
                "quotations": {
                    "$not": {
                        "$elemMatch": {
                            "providerId": provider["_id"],
                            "status": "Pending",
                        }
                    }
                },
            },
            {
                "$push": {
                    "quotations": quotation,
                },
                "$set": {
                    "status": "Quoted",
                    "updatedAt": now,
                },
            },
        )

        if result.matched_count == 0:
            return jsonify({
                "error": (
                    "Request unavailable or this provider already "
                    "has a pending quotation"
                )
            }), 409

    except PyMongoError:
        current_app.logger.exception("Quotation submission failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({"data": quotation}), 201

@quotations_bp.get("/<request_id>/quotations/<quote_id>")
@basic_auth_required
def get_quotation(request_id, quote_id):
    database = current_app.extensions["mongo_db"]

    try:
        service_request = database.serviceRequests.find_one({
            "_id": request_id,
            "customerId": g.current_customer["_id"],
        })
    except PyMongoError:
        current_app.logger.exception("Quotation lookup failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    if service_request is None:
        return jsonify({"error": "Service request not found"}), 404

    quotation = next(
        (
            item
            for item in service_request.get("quotations", [])
            if item.get("quoteId") == quote_id
        ),
        None,
    )

    if quotation is None:
        return jsonify({"error": "Quotation not found"}), 404

    return jsonify({"data": quotation}), 200
@quotations_bp.patch("/<request_id>/quotations/<quote_id>")
@provider_basic_auth_required
def update_quotation(request_id, quote_id):
    body = request.get_json(silent=True)

    if not isinstance(body, dict) or not body:
        return jsonify({
            "error": "Request body must be a non-empty JSON object"
        }), 400

    allowed_fields = {"lineItems", "callOutFeePence"}

    if not set(body).issubset(allowed_fields):
        return jsonify({"error": "Request contains unsupported fields"}), 400

    database = current_app.extensions["mongo_db"]
    provider = g.current_provider

    try:
        service_request = database.serviceRequests.find_one({
            "_id": request_id,
        })

        if service_request is None:
            return jsonify({"error": "Service request not found"}), 404

        quotation = next(
            (
                item
                for item in service_request.get("quotations", [])
                if item.get("quoteId") == quote_id
                and item.get("providerId") == provider["_id"]
            ),
            None,
        )

        if quotation is None:
            return jsonify({"error": "Quotation not found"}), 404

        now = datetime.now(timezone.utc)
        expires_at = quotation.get("expiresAt")

        if (
            service_request.get("status") not in (None, "Open", "Quoted")
            or quotation.get("status") != "Pending"
            or not isinstance(expires_at, datetime)
            or expires_at <= now
        ):
            return jsonify({
                "error": "This quotation cannot be updated"
            }), 409

        changes = {}

        if "callOutFeePence" in body:
            fee = body["callOutFeePence"]

            if type(fee) is not int or fee < 0:
                return jsonify({
                    "error": (
                        "callOutFeePence must be a non-negative integer"
                    )
                }), 400

            changes["callOutFeePence"] = fee

        if "lineItems" in body:
            service = next(
                (
                    item
                    for item in provider.get("services", [])
                    if item.get("serviceId") == quotation["serviceId"]
                ),
                None,
            )

            if service is None:
                return jsonify({"error": "Provider service not found"}), 404

            try:
                changes["lineItems"] = prepare_line_items(
                    body["lineItems"], service
                )
            except ValueError as error:
                return jsonify({"error": str(error)}), 400

        line_items = changes.get("lineItems", quotation["lineItems"])
        fee = changes.get(
            "callOutFeePence", quotation["callOutFeePence"]
        )

        total = fee + sum(item["subtotalPence"] for item in line_items)

        if total <= 0:
            return jsonify({
                "error": "Quotation total must be positive"
            }), 400

        changes["totalPence"] = total
        changes["updatedAt"] = now

        updates = {
            f"quotations.$.{key}": value
            for key, value in changes.items()
        }
        updates["updatedAt"] = now

        result = database.serviceRequests.update_one(
            {
                "_id": request_id,
                "status": {"$in": [None, "Open", "Quoted"]},
                "quotations.status": {"$ne": "Accepted"},
                "quotations": {
                    "$elemMatch": {
                        "quoteId": quote_id,
                        "providerId": provider["_id"],
                        "status": "Pending",
                        "expiresAt": {"$gt": now},
                        "updatedAt": quotation.get("updatedAt"),
                    }
                },
            },
            {"$set": updates},
        )

        if result.matched_count == 0:
            return jsonify({
                "error": "Quotation changed or is no longer editable"
            }), 409

    except PyMongoError:
        current_app.logger.exception("Quotation update failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    quotation.update(changes)
    return jsonify({"data": quotation}), 200

@quotations_bp.delete("/<request_id>/quotations/<quote_id>")
@provider_basic_auth_required
def delete_quotation(request_id, quote_id):
    database = current_app.extensions["mongo_db"]
    provider_id = g.current_provider["_id"]

    try:
        service_request = database.serviceRequests.find_one({
            "_id": request_id,
        })

        if service_request is None:
            return jsonify({"error": "Service request not found"}), 404

        quotation = next(
            (
                item
                for item in service_request.get("quotations", [])
                if item.get("quoteId") == quote_id
                and item.get("providerId") == provider_id
            ),
            None,
        )

        if quotation is None:
            return jsonify({"error": "Quotation not found"}), 404

        if (
            quotation.get("status") != "Pending"
            or service_request.get("status")
            not in (None, "Open", "Quoted")
        ):
            return jsonify({
                "error": "This quotation cannot be deleted"
            }), 409

        now = datetime.now(timezone.utc)

        result = database.serviceRequests.update_one(
            {
                "_id": request_id,
                "status": {"$in": [None, "Open", "Quoted"]},
                "quotations.status": {"$ne": "Accepted"},
                "quotations": {
                    "$elemMatch": {
                        "quoteId": quote_id,
                        "providerId": provider_id,
                        "status": "Pending",
                        "updatedAt": quotation.get("updatedAt"),
                    }
                },
            },
            [
                {
                    "$set": {
                        "quotations": {
                            "$filter": {
                                "input": "$quotations",
                                "as": "quotation",
                                "cond": {
                                    "$ne": [
                                        "$$quotation.quoteId",
                                        {"$literal": quote_id},
                                    ]
                                },
                            }
                        },
                        "updatedAt": now,
                    }
                },
                {
                    "$set": {
                        "status": {
                            "$cond": [
                                {"$eq": [{"$size": "$quotations"}, 0]},
                                "Open",
                                "Quoted",
                            ]
                        }
                    }
                },
            ],
        )

        if result.matched_count == 0:
            return jsonify({
                "error": "Quotation changed or is no longer deletable"
            }), 409

    except PyMongoError:
        current_app.logger.exception("Quotation deletion failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({"message": "Quotation deleted"}), 200

@quotations_bp.post("/<request_id>/quotations/<quote_id>/accept")
@basic_auth_required
def accept_quotation(request_id, quote_id):
    """Accept a quotation and ensure its booking exists (safe to retry)."""
    from pymongo.errors import DuplicateKeyError

    database = current_app.extensions["mongo_db"]
    customer_id = g.current_customer["_id"]
    now = datetime.now(timezone.utc)

    try:
        service_request = database.serviceRequests.find_one({
            "_id": request_id,
            "customerId": customer_id,
        })
        if service_request is None:
            return jsonify({"error": "Service request not found"}), 404

        quotation = next((q for q in service_request.get("quotations", [])
                          if q.get("quoteId") == quote_id), None)
        if quotation is None:
            return jsonify({"error": "Quotation not found"}), 404

        accepted_already = (
            service_request.get("status") == "Accepted"
            and service_request.get("acceptedQuoteId") == quote_id
            and quotation.get("status") == "Accepted"
        )
        if not accepted_already:
            expires_at = quotation.get("expiresAt")
            if (service_request.get("status") not in (None, "Open", "Quoted")
                    or quotation.get("status") != "Pending"
                    or not isinstance(expires_at, datetime)
                    or expires_at <= now):
                return jsonify({"error": "This quotation cannot be accepted"}), 409

        # The unique index on bookings.requestId is required to prevent duplicates.
        existing = database.bookings.find_one({"requestId": request_id})
        if existing is not None and existing.get("acceptedQuoteId") != quote_id:
            return jsonify({"error": "A different quotation already has a booking"}), 409

        created_here = False
        if existing is None:
            booking = {
                "_id": f"BKG{uuid4().hex[:12].upper()}",
                "requestId": request_id,
                "customerId": customer_id,
                "providerId": quotation["providerId"],
                "acceptedQuoteId": quote_id,
                "status": "Pending",
                "totalPence": quotation["totalPence"],
                "currency": quotation.get("currency", "GBP"),
                "createdAt": now,
                "updatedAt": now,
                "scheduledStart": None,
                "scheduledEnd": None,
                "customerNotes": "",
                "accessInstructions": "",
                "payments": [],
                "reviews": [],
                "statusHistory": [{
                    "eventId": f"EVT{uuid4().hex[:12].upper()}",
                    "status": "Pending",
                    "occurredAt": now,
                }],
            }
            for key in ("organisationId", "propertyId", "roomId", "assetId"):
                if key in service_request:
                    booking[key] = service_request[key]
            try:
                database.bookings.insert_one(booking)
                created_here = True
                existing = booking
            except DuplicateKeyError:
                # Another request may have created the booking concurrently.
                existing = database.bookings.find_one({"requestId": request_id})
                if existing is None or existing.get("acceptedQuoteId") != quote_id:
                    return jsonify({"error": "Booking conflict; retry the request"}), 409

        if not accepted_already:
            result = database.serviceRequests.update_one(
                {
                    "_id": request_id,
                    "customerId": customer_id,
                    "status": {"$in": [None, "Open", "Quoted"]},
                    "quotations.status": {"$ne": "Accepted"},
                    "quotations": {"$elemMatch": {
                        "quoteId": quote_id,
                        "status": "Pending",
                        "expiresAt": {"$gt": now},
                    }},
                },
                [{"$set": {
                    "quotations": {"$map": {
                        "input": "$quotations",
                        "as": "q",
                        "in": {"$cond": [
                            {"$eq": ["$$q.quoteId", {"$literal": quote_id}]},
                            {"$mergeObjects": ["$$q", {
                                "status": "Accepted", "acceptedAt": now,
                            }]},
                            {"$cond": [
                                {"$eq": ["$$q.status", "Pending"]},
                                {"$mergeObjects": ["$$q", {"status": "Rejected"}]},
                                "$$q",
                            ]},
                        ]},
                    }},
                    "status": "Accepted",
                    "acceptedQuoteId": {"$literal": quote_id},
                    "updatedAt": now,
                }}],
            )
            if result.matched_count == 0:
                # Delete only the provisional booking inserted by this call.
                # The request may have been accepted by a concurrent call.
                if created_here:
                    database.bookings.delete_one({
                        "_id": existing["_id"],
                        "requestId": request_id,
                    })
                return jsonify({"error": "Quotation changed; retry the request"}), 409

        # Return the booking even for an already accepted quotation.
        return jsonify({
            "message": "Quotation accepted; booking available",
            "bookingId": existing["_id"],
            "booking": existing,
            "data": {**quotation, "status": "Accepted",
                     "acceptedAt": quotation.get("acceptedAt", now)},
        }), 200 if accepted_already else 201

    except (PyMongoError, KeyError, TypeError):
        current_app.logger.exception("Quotation acceptance / booking creation failed")
        return jsonify({
            "error": "Could not complete booking; retry safely using the same request"
        }), 503
