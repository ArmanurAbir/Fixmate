
import uuid
from datetime import datetime, timezone

from flask import Blueprint, current_app, g, jsonify, request
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError
from app.routes.auth import basic_auth_required


reviews_bp = Blueprint("reviews", __name__)


@reviews_bp.post("/bookings/<booking_id>/reviews")
@basic_auth_required
def create_review(booking_id):
    body = request.get_json(silent=True)

    if not isinstance(body, dict):
        return jsonify({
            "error": "Request body must be JSON"
        }), 400

    rating = body.get("rating")
    comment = body.get("comment", "")

    if type(rating) is not int or not 1 <= rating <= 5:
        return jsonify({
            "error": "Rating must be an integer from 1 to 5"
        }), 400

    if not isinstance(comment, str):
        return jsonify({
            "error": "Comment must be a string"
        }), 400

    comment = comment.strip()

    if len(comment) > 2000:
        return jsonify({
            "error": "Comment cannot exceed 2000 characters"
        }), 400

    database = current_app.extensions["mongo_db"]

    try:
        booking = database.bookings.find_one({
            "_id": booking_id,
            "customerId": g.current_customer["_id"],
        })

        if booking is None:
            return jsonify({
                "error": "Booking not found"
            }), 404

        if booking.get("status") != "Completed":
            return jsonify({
                "error": "Only completed bookings can be reviewed"
            }), 409

        review = {
            "_id": f"REV{uuid.uuid4().hex[:12].upper()}",
            "bookingId": booking_id,
            "customerId": g.current_customer["_id"],
            "providerId": booking["providerId"],
            "rating": rating,
            "comment": comment,
            "createdAt": datetime.now(timezone.utc),
        }

        result = database.bookings.update_one(
            {
                "_id": booking_id,
                "customerId": g.current_customer["_id"],
                "status": "Completed",
                "reviews.0": {"$exists": False},
            },
            {
                "$push": {"reviews": review},
                "$set": {
                    "updatedAt": datetime.now(timezone.utc)
                },
            },
        )

        if result.modified_count == 0:
            return jsonify({
                "error": "Booking already reviewed or no longer eligible"
            }), 409

    except PyMongoError:
        current_app.logger.exception("Review creation failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({"data": review}), 201

@reviews_bp.get("/bookings/<booking_id>/reviews")
@basic_auth_required
def list_booking_reviews(booking_id):
    database = current_app.extensions["mongo_db"]

    try:
        booking = database.bookings.find_one({
            "_id": booking_id,
            "customerId": g.current_customer["_id"],
        })

        if booking is None:
            return jsonify({
                "error": "Booking not found"
            }), 404

        reviews = booking.get("reviews", [])

    except PyMongoError:
        current_app.logger.exception(
            "Review lookup failed"
        )
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({
        "count": len(reviews),
        "data": reviews
    }), 200


@reviews_bp.patch("/bookings/<booking_id>/reviews/<review_id>")
@basic_auth_required
def update_review(booking_id, review_id):
    body = request.get_json(silent=True)

    if not isinstance(body, dict):
        return jsonify({
            "error": "Request body must be JSON"
        }), 400

    updates = {}

    if "rating" in body:
        rating = body["rating"]
        if type(rating) is not int or not 1 <= rating <= 5:
            return jsonify({
                "error": "Rating must be an integer from 1 to 5"
            }), 400
        updates["reviews.$.rating"] = rating

    if "comment" in body:
        comment = body["comment"]
        if not isinstance(comment, str):
            return jsonify({
                "error": "Comment must be a string"
            }), 400

        comment = comment.strip()

        if len(comment) > 2000:
            return jsonify({
                "error": "Comment cannot exceed 2000 characters"
            }), 400

        updates["reviews.$.comment"] = comment

    if not updates:
        return jsonify({
            "error": "No valid review fields supplied"
        }), 400

    now = datetime.now(timezone.utc)
    updates["reviews.$.updatedAt"] = now
    updates["updatedAt"] = now

    database = current_app.extensions["mongo_db"]

    try:
        booking = database.bookings.find_one_and_update(
            {
                "_id": booking_id,
                "customerId": g.current_customer["_id"],
                "reviews._id": review_id,
            },
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )

        if booking is None:
            return jsonify({
                "error": "Review not found"
            }), 404

        updated_review = next(
            review for review in booking["reviews"]
            if review["_id"] == review_id
        )

    except PyMongoError:
        current_app.logger.exception("Review update failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({"data": updated_review}), 200

@reviews_bp.delete("/bookings/<booking_id>/reviews/<review_id>")
@basic_auth_required
def delete_review(booking_id, review_id):
    database = current_app.extensions["mongo_db"]

    try:
        result = database.bookings.update_one(
            {
                "_id": booking_id,
                "customerId": g.current_customer["_id"],
                "reviews._id": review_id,
            },
            {
                "$pull": {
                    "reviews": {"_id": review_id}
                },
                "$set": {
                    "updatedAt": datetime.now(timezone.utc)
                },
            },
        )

        if result.modified_count == 0:
            return jsonify({
                "error": "Review not found"
            }), 404

    except PyMongoError:
        current_app.logger.exception(
            "Review deletion failed"
        )
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({
        "message": "Review deleted successfully"
    }), 200


@reviews_bp.get("/providers/<provider_id>/reviews")
def list_provider_reviews(provider_id):
    database = current_app.extensions["mongo_db"]

    try:
        bookings = database.bookings.find(
            {"providerId": provider_id},
            {"reviews": 1}
        )

        reviews = []

        for booking in bookings:
            reviews.extend(
                booking.get("reviews", [])
            )

        average_rating = (
            round(
                sum(r["rating"] for r in reviews) / len(reviews),
                2
            )
            if reviews else None
        )

    except PyMongoError:
        current_app.logger.exception(
            "Provider reviews lookup failed"
        )
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({
        "providerId": provider_id,
        "count": len(reviews),
        "averageRating": average_rating,
        "data": reviews,
    }), 200
