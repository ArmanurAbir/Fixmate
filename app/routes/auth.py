from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request
from pymongo.errors import PyMongoError
from werkzeug.security import check_password_hash, generate_password_hash


auth_bp = Blueprint("auth", __name__)


def basic_auth_required(view_function):
    @wraps(view_function)
    def decorated(*args, **kwargs):
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

        email = credentials.username.strip().lower()
        password = credentials.password
        database = current_app.extensions["mongo_db"]

        try:
            customer = database.customers.find_one({
                "email": email,
                "isActive": True,
            })
        except PyMongoError:
            current_app.logger.exception("Authentication query failed")
            return jsonify({
                "error": "Database temporarily unavailable"
            }), 503

        if (
            customer is None
            or not customer.get("passwordHash")
            or not check_password_hash(customer["passwordHash"], password)
        ):
            return jsonify({
                "error": "Invalid email or password"
            }), 401

        customer.pop("passwordHash", None)
        g.current_customer = customer

        return view_function(*args, **kwargs)

    return decorated


@auth_bp.post("/register")
def register():
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
    database = current_app.extensions["mongo_db"]

    try:
        if database.customers.find_one({"email": email}, {"_id": 1}):
            return jsonify({"error": "Email is already registered"}), 409

        customer = {
            "_id": f"CUST{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "displayName": display_name.strip(),
            "email": email,
            "passwordHash": generate_password_hash(password),
            "isActive": True,
            "createdAt": datetime.now(timezone.utc),
            "preferences": {
                "notifications": {"email": True, "sms": False},
                "preferredContact": "email",
            },
            "properties": [],
            "savedProviderIds": [],
        }

        database.customers.insert_one(customer)

    except PyMongoError:
        current_app.logger.exception("Registration failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    customer.pop("passwordHash", None)
    return jsonify({"data": customer}), 201


@auth_bp.post("/login")
def login():
    body = request.get_json(silent=True)

    if not isinstance(body, dict):
        return jsonify({"error": "Request body must be JSON"}), 400

    email = body.get("email")
    password = body.get("password")

    if not isinstance(email, str) or not isinstance(password, str):
        return jsonify({
            "error": "Email and password are required"
        }), 400

    database = current_app.extensions["mongo_db"]

    try:
        customer = database.customers.find_one({
            "email": email.strip().lower(),
            "isActive": True,
        })
    except PyMongoError:
        current_app.logger.exception("Login failed")
        return jsonify({
            "error": "Database temporarily unavailable"
        }), 503

    if (
        customer is None
        or not customer.get("passwordHash")
        or not check_password_hash(customer["passwordHash"], password)
    ):
        return jsonify({"error": "Invalid email or password"}), 401

    customer.pop("passwordHash", None)
    return jsonify({
        "message": "Login successful. Use these credentials with Basic Auth.",
        "data": customer,
    }), 200