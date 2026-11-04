
from flask import Blueprint, current_app, jsonify
from pymongo.errors import PyMongoError

reports_bp = Blueprint("reports", __name__)


@reports_bp.get("/provider-performance")
def provider_performance():
    database = current_app.extensions["mongo_db"]

    pipeline = [
        {
            "$group": {
                "_id": "$providerId",
                "totalBookings": {"$sum": 1},
                "completedJobs": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$status", "Completed"]},
                            1, 0
                        ]
                    }
                },
                "cancelledBookings": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$status", "Cancelled"]},
                            1, 0
                        ]
                    }
                },
                "ratings": {
                    "$push": "$reviews.rating"
                }
            }
        },
        {
            "$project": {
                "_id": 0,
                "providerId": "$_id",
                "totalBookings": 1,
                "completedJobs": 1,
                "cancelledBookings": 1,
                "completionRate": {
                    "$round": [
                        {
                            "$multiply": [
                                {
                                    "$divide": [
                                        "$completedJobs",
                                        "$totalBookings"
                                    ]
                                },
                                100
                            ]
                        },
                        2
                    ]
                },
                "ratings": 1
            }
        },
        {
            "$sort": {
                "totalBookings": -1
            }
        }
    ]

    try:
        results = list(
            database.bookings.aggregate(pipeline)
        )

        for provider in results:
            ratings = [
                rating
                for group in provider.pop("ratings", [])
                for rating in group
                if isinstance(rating, (int, float))
                and not isinstance(rating, bool)
            ]

            provider["averageRating"] = (
                round(sum(ratings) / len(ratings), 2)
                if ratings else None
            )

            provider["reviewCount"] = len(ratings)

    except PyMongoError:
        current_app.logger.exception(
            "Provider performance report failed"
        )
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({
        "count": len(results),
        "data": results
    }), 200

@reports_bp.get("/monthly-revenue")
def monthly_revenue():
    database = current_app.extensions["mongo_db"]

    pipeline = [
        {
            "$match": {
                "status": "Completed",
                "totalPence": {"$type": "number"}
            }
        },
        {
            "$addFields": {
                "reportDate": {
                    "$convert": {
                        "input": "$updatedAt",
                        "to": "date",
                        "onError": None,
                        "onNull": None
                    }
                }
            }
        },
        {
            "$match": {
                "reportDate": {"$ne": None}
            }
        },
        {
            "$group": {
                "_id": {
                    "$dateToString": {
                        "format": "%Y-%m",
                        "date": "$reportDate",
                        "timezone": "UTC"
                    }
                },
                "totalRevenuePence": {
                    "$sum": "$totalPence"
                },
                "completedBookings": {
                    "$sum": 1
                }
            }
        },
        {
            "$sort": {"_id": 1}
        },
        {
            "$project": {
                "_id": 0,
                "month": "$_id",
                "completedBookings": 1,
                "totalRevenuePence": 1,
                "totalRevenueGBP": {
                    "$round": [
                        {"$divide": ["$totalRevenuePence", 100]},
                        2
                    ]
                }
            }
        }
    ]

    try:
        results = list(
            database.bookings.aggregate(pipeline)
        )

    except PyMongoError:
        current_app.logger.exception(
            "Monthly revenue report failed"
        )
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({
        "count": len(results),
        "currency": "GBP",
        "data": results
    }), 200

@reports_bp.get("/service-demand")
def service_demand():
    database = current_app.extensions["mongo_db"]

    pipeline = [
        {
            "$group": {
                "_id": "$serviceCategoryId",
                "totalRequests": {"$sum": 1},
                "acceptedRequests": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$status", "Accepted"]},
                            1,
                            0
                        ]
                    }
                }
            }
        },
        {
            "$project": {
                "_id": 0,
                "serviceCategoryId": "$_id",
                "totalRequests": 1,
                "acceptedRequests": 1
            }
        },
        {
            "$sort": {
                "totalRequests": -1
            }
        }
    ]

    try:
        results = list(
            database.serviceRequests.aggregate(pipeline)
        )

    except PyMongoError:
        current_app.logger.exception(
            "Service demand report failed"
        )
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({
        "count": len(results),
        "data": results
    }), 200

@reports_bp.get("/cancellations")
def cancellations_report():
    database = current_app.extensions["mongo_db"]

    pipeline = [
        {
            "$group": {
                "_id": "$providerId",
                "totalBookings": {"$sum": 1},
                "cancelledBookings": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$status", "Cancelled"]},
                            1,
                            0
                        ]
                    }
                }
            }
        },
        {
            "$project": {
                "_id": 0,
                "providerId": "$_id",
                "totalBookings": 1,
                "cancelledBookings": 1,
                "cancellationRate": {
                    "$round": [
                        {
                            "$multiply": [
                                {
                                    "$divide": [
                                        "$cancelledBookings",
                                        "$totalBookings"
                                    ]
                                },
                                100
                            ]
                        },
                        2
                    ]
                }
            }
        },
        {
            "$sort": {
                "cancelledBookings": -1,
                "providerId": 1
            }
        }
    ]

    try:
        results = list(
            database.bookings.aggregate(pipeline)
        )

    except PyMongoError:
        current_app.logger.exception(
            "Cancellations report failed"
        )
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    return jsonify({
        "count": len(results),
        "data": results
    }), 200
