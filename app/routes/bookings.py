import uuid
from datetime import datetime, timezone

from flask import Blueprint, current_app, g, jsonify, request
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from app.routes.auth import basic_auth_required


bookings_bp = Blueprint("bookings", __name__)


def customer_booking_filter(booking_id=None):
    query = {
        "customerId": g.current_customer["_id"],
    }

    if booking_id is not None:
        query["_id"] = booking_id

    return query


@bookings_bp.get("")
@basic_auth_required
def list_bookings():
    database = current_app.extensions["mongo_db"]

    try:
        bookings = list(
            database.bookings.find(
                customer_booking_filter()
            )
            .sort("_id", 1)
            .limit(20)
        )
    except PyMongoError:
        current_app.logger.exception("Booking query failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({
        "count": len(bookings),
        "data": bookings,
    }), 200


@bookings_bp.get("/<booking_id>")
@basic_auth_required
def get_booking(booking_id):
    database = current_app.extensions["mongo_db"]

    try:
        booking = database.bookings.find_one(
            customer_booking_filter(booking_id)
        )
    except PyMongoError:
        current_app.logger.exception("Booking lookup failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    if booking is None:
        return jsonify({"error": "Booking not found"}), 404

    return jsonify({"data": booking}), 200


@bookings_bp.patch("/<booking_id>")
@basic_auth_required
def update_booking(booking_id):
    body = request.get_json(silent=True)

    if not isinstance(body, dict):
        return jsonify({"error": "Request body must be JSON"}), 400

    allowed_fields = {
        "scheduledStart",
        "scheduledEnd",
        "customerNotes",
        "accessInstructions",
    }

    updates = {
        key: value
        for key, value in body.items()
        if key in allowed_fields
    }

    if not updates:
        return jsonify({
            "error": "No valid booking fields supplied"
        }), 400

    updates["updatedAt"] = datetime.now(timezone.utc)
    database = current_app.extensions["mongo_db"]

    try:
        booking = database.bookings.find_one_and_update(
            customer_booking_filter(booking_id),
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
    except PyMongoError:
        current_app.logger.exception("Booking update failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    if booking is None:
        return jsonify({"error": "Booking not found"}), 404

    return jsonify({"data": booking}), 200



@bookings_bp.patch("/<booking_id>/status")
@basic_auth_required
def update_booking_status(booking_id):
    body = request.get_json(silent=True)

    if not isinstance(body, dict):
        return jsonify({
            "error": "Request body must be JSON"
        }), 400

    new_status = body.get("status")

    if not isinstance(new_status, str) or not new_status.strip():
        return jsonify({
            "error": "status is required"
        }), 400

    new_status = new_status.strip()
    database = current_app.extensions["mongo_db"]

    allowed_transitions = {
        "Pending": {"Confirmed", "Cancelled"},
        "Confirmed": {"In Progress", "Cancelled"},
        "In Progress": {"Completed", "Cancelled"},
        "Completed": set(),
        "Cancelled": set(),
    }

    try:
        existing_booking = database.bookings.find_one(
            customer_booking_filter(booking_id)
        )

        if existing_booking is None:
            return jsonify({
                "error": "Booking not found"
            }), 404

        current_status = existing_booking.get(
            "status", "Pending"
        )

        permitted_statuses = allowed_transitions.get(
            current_status, set()
        )

        if new_status not in permitted_statuses:
            return jsonify({
                "error": (
                    f"Status cannot change from "
                    f"{current_status} to {new_status}"
                )
            }), 409

        now = datetime.now(timezone.utc)

        status_event = {
            "eventId": f"EVT{uuid.uuid4().hex[:12].upper()}",
            "status": new_status,
            "occurredAt": now,
        }

        booking = database.bookings.find_one_and_update(
            {
                **customer_booking_filter(booking_id),
                "status": current_status,
            },
            {
                "$set": {
                    "status": new_status,
                    "updatedAt": now,
                },
                "$push": {
                    "statusHistory": status_event,
                },
            },
            return_document=ReturnDocument.AFTER,
        )

        if booking is None:
            return jsonify({
                "error": "Booking status changed. Please retry."
            }), 409

    except PyMongoError:
        current_app.logger.exception(
            "Booking status update failed"
        )
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({"data": booking}), 200



@bookings_bp.delete("/<booking_id>")
@basic_auth_required
def delete_booking(booking_id):
    database = current_app.extensions["mongo_db"]

    try:
        booking = database.bookings.find_one(
            customer_booking_filter(booking_id)
        )

        if booking is None:
            return jsonify({"error": "Booking not found"}), 404

        if booking.get("status") not in {
            "Pending",
            "Requested",
            "Cancelled",
        }:
            return jsonify({
                "error": "This booking cannot be deleted in its current status"
            }), 409

        database.bookings.delete_one(
            customer_booking_filter(booking_id)
        )
    except PyMongoError:
        current_app.logger.exception("Booking deletion failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({
        "message": "Booking deleted"
    }), 200