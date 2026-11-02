from flask import Blueprint, current_app, jsonify, request
from pymongo.errors import PyMongoError
import re
from datetime import datetime, timezone
from uuid import uuid4

from werkzeug.security import check_password_hash


availability_bp = Blueprint("availability", __name__)


@availability_bp.get("/<provider_id>/availability")
def list_availability(provider_id):
    database = current_app.extensions["mongo_db"]

    try:
        provider = database.providers.find_one(
            {"_id": provider_id, "isActive": True},
            {"availability": 1},
        )
    except PyMongoError:
        current_app.logger.exception("Availability query failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    if provider is None:
        return jsonify({"error": "Provider not found"}), 404

    availability = provider.get("availability", {})
    slots = availability.get("weeklySlots", [])

    return jsonify({
        "count": len(slots),
        "data": slots,
        "timezone": availability.get("timezone", "Europe/London"),
        "exceptions": availability.get("exceptions", []),
    }), 200
@availability_bp.get("/<provider_id>/availability/<availability_id>")
def get_availability(provider_id, availability_id):
    database = current_app.extensions["mongo_db"]

    try:
        provider = database.providers.find_one(
            {"_id": provider_id, "isActive": True},
            {"availability": 1},
        )
    except PyMongoError:
        current_app.logger.exception("Availability lookup failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    if provider is None:
        return jsonify({"error": "Provider not found"}), 404

    availability = provider.get("availability", {})
    slot = next(
        (
            item
            for item in availability.get("weeklySlots", [])
            if item.get("availabilityId") == availability_id
        ),
        None,
    )

    if slot is None:
        return jsonify({"error": "Availability slot not found"}), 404

    return jsonify({
        "data": slot,
        "timezone": availability.get("timezone", "Europe/London"),
    }), 200
@availability_bp.post("/<provider_id>/availability")
def add_availability(provider_id):
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
                provider["passwordHash"], credentials.password
            )
        ):
            return jsonify({"error": "Invalid provider credentials"}), 401

        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "Request body must be JSON"}), 400

        weekday = body.get("weekday")
        intervals = body.get("intervals")

        if type(weekday) is not int or not 1 <= weekday <= 7:
            return jsonify({
                "error": "weekday must be an integer from 1 to 7"
            }), 400

        if not isinstance(intervals, list) or not intervals:
            return jsonify({
                "error": "intervals must be a non-empty array"
            }), 400

        validated_intervals = []
        time_pattern = r"(?:[01]\d|2[0-3]):[0-5]\d"

        for interval in intervals:
            if not isinstance(interval, dict):
                return jsonify({"error": "Each interval must be an object"}), 400

            start = interval.get("start")
            end = interval.get("end")

            if (
                not isinstance(start, str)
                or not isinstance(end, str)
                or re.fullmatch(time_pattern, start) is None
                or re.fullmatch(time_pattern, end) is None
            ):
                return jsonify({
                    "error": "start and end must use HH:MM format"
                }), 400

            if start >= end:
                return jsonify({"error": "end must be after start"}), 400

            validated_intervals.append({"start": start, "end": end})

        validated_intervals.sort(key=lambda item: item["start"])

        for previous, following in zip(
            validated_intervals, validated_intervals[1:]
        ):
            if following["start"] < previous["end"]:
                return jsonify({"error": "Intervals must not overlap"}), 400

        slot = {
            "availabilityId": f"AV{uuid4().hex[:12].upper()}",
            "weekday": weekday,
            "intervals": validated_intervals,
        }

        result = database.providers.update_one(
            {
                "_id": provider_id,
                "isActive": True,
                "availability.weeklySlots.weekday": {"$ne": weekday},
            },
            {
                "$push": {"availability.weeklySlots": slot},
                "$set": {
                    "availability.timezone": "Europe/London",
                    "updatedAt": datetime.now(timezone.utc),
                },
            },
        )

        if result.matched_count == 0:
            return jsonify({
                "error": "Provider unavailable or weekday already configured"
            }), 409

    except PyMongoError:
        current_app.logger.exception("Availability creation failed")
        return jsonify({"error": "Database temporarily unavailable"}), 503

    return jsonify({
        "data": slot,
        "timezone": "Europe/London",
    }), 201

@availability_bp.patch("/<provider_id>/availability/<availability_id>")
def update_availability(provider_id, availability_id):
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
                provider["passwordHash"], credentials.password
            )
        ):
            return jsonify({"error": "Invalid provider credentials"}), 401

        slot = next(
            (
                item
                for item in provider.get("availability", {}).get(
                    "weeklySlots", []
                )
                if item.get("availabilityId") == availability_id
            ),
            None,
        )

        if slot is None:
            return jsonify({"error": "Availability slot not found"}), 404

        body = request.get_json(silent=True)

        if not isinstance(body, dict):
            return jsonify({"error": "Request body must be JSON"}), 400

        if set(body) - {"intervals"}:
            return jsonify({
                "error": "Only intervals can be updated with this endpoint"
            }), 400

        intervals = body.get("intervals")

        if not isinstance(intervals, list) or not intervals:
            return jsonify({
                "error": "intervals must be a non-empty array"
            }), 400

        validated_intervals = []
        time_pattern = r"(?:[01]\d|2[0-3]):[0-5]\d"

        for interval in intervals:
            if not isinstance(interval, dict):
                return jsonify({
                    "error": "Each interval must be an object"
                }), 400

            start = interval.get("start")
            end = interval.get("end")

            if (
                not isinstance(start, str)
                or not isinstance(end, str)
                or re.fullmatch(time_pattern, start) is None
                or re.fullmatch(time_pattern, end) is None
            ):
                return jsonify({
                    "error": "start and end must use HH:MM format"
                }), 400

            if start >= end:
                return jsonify({"error": "end must be after start"}), 400

            validated_intervals.append({"start": start, "end": end})

        validated_intervals.sort(key=lambda item: item["start"])

        for previous, following in zip(
            validated_intervals, validated_intervals[1:]
        ):
            if following["start"] < previous["end"]:
                return jsonify({"error": "Intervals must not overlap"}), 400

        result = database.providers.update_one(
            {
                "_id": provider_id,
                "isActive": True,
                "availability.weeklySlots.availabilityId": availability_id,
            },
            {
                "$set": {
                    "availability.weeklySlots.$.intervals": validated_intervals,
                    "updatedAt": datetime.now(timezone.utc),
                }
            },
        )

        if result.matched_count == 0:
            return jsonify({"error": "Availability slot not found"}), 404

    except PyMongoError:
        current_app.logger.exception("Availability update failed")
        return jsonify({"error": "Database temporarily unavailable"}), 503

    slot["intervals"] = validated_intervals
    return jsonify({"data": slot}), 200
@availability_bp.delete("/<provider_id>/availability/<availability_id>")
def delete_availability(provider_id, availability_id):
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
                provider["passwordHash"], credentials.password
            )
        ):
            return jsonify({"error": "Invalid provider credentials"}), 401

        result = database.providers.update_one(
            {
                "_id": provider_id,
                "isActive": True,
                "availability.weeklySlots.availabilityId": availability_id,
            },
            {
                "$pull": {
                    "availability.weeklySlots": {
                        "availabilityId": availability_id,
                    }
                },
                "$set": {
                    "updatedAt": datetime.now(timezone.utc),
                },
            },
        )

        if result.matched_count == 0:
            return jsonify({"error": "Availability slot not found"}), 404

    except PyMongoError:
        current_app.logger.exception("Availability deletion failed")
        return jsonify({"error": "Database temporarily unavailable"}), 503

    return jsonify({"message": "Availability slot deleted"}), 200