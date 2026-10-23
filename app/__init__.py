import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from pymongo import MongoClient



def create_app():
    project_folder = Path(__file__).resolve().parent.parent
    load_dotenv(project_folder / ".env")

    app = Flask(__name__)

    client = MongoClient(
        os.environ["MONGO_URI"],
        serverSelectionTimeoutMS=5000,
        tz_aware=True,
    )
    client.admin.command("ping")

    app.extensions["mongo_client"] = client
    app.extensions["mongo_db"] = client[
        os.environ["MONGO_DB_NAME"]
    ]

    from app.routes.providers import providers_bp
    from app.routes.service_categories import service_categories_bp

    app.register_blueprint(
        providers_bp,
        url_prefix="/api/v1.0/providers",
    )
    app.register_blueprint(
        service_categories_bp,
        url_prefix="/api/v1.0/services",
    )

    from app.routes.customer import customers_bp        
    app.register_blueprint(
        customers_bp,
        url_prefix="/api/v1.0/customers",
    )
    
    return app