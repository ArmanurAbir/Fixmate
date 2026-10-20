import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

COLLECTIONS = [
    "serviceCategories",
    "organisations",
    "customers",
    "providers",
    "serviceRequests",
    "bookings",
]

DATE_FIELDS = {
    "createdAt",
    "installedAt",
    "expiresAt",
    "requestedStart",
    "requestedEnd",
    "scheduledStart",
    "scheduledEnd",
    "occurredAt",
}


def convert_dates(value):
    """Convert timestamps inside objects and nested arrays."""
    if isinstance(value, list):
        return [convert_dates(item) for item in value]

    if isinstance(value, dict):
        converted = {}

        for key, item in value.items():
            if key in DATE_FIELDS and isinstance(item, str):
                converted[key] = datetime.fromisoformat(
                    item.replace("Z", "+00:00")
                )
            else:
                converted[key] = convert_dates(item)

        return converted

    return value


def main():
    dataset_path = BASE_DIR / "fixmate_dataset_v3.json"

    with dataset_path.open(encoding="utf-8") as file:
        dataset = json.load(file)

    prepared = {
        name: convert_dates(dataset[name])
        for name in COLLECTIONS
    }

    with MongoClient(
        os.environ["MONGO_URI"],
        serverSelectionTimeoutMS=5000,
    ) as client:
        client.admin.command("ping")
        database = client[os.environ["MONGO_DB_NAME"]]

        populated = [
            name for name in COLLECTIONS
            if database[name].count_documents({}) > 0
        ]

        if populated:
            raise RuntimeError(
                "Import stopped. Collections already contain data: "
                + ", ".join(populated)
            )

        for name, documents in prepared.items():
            if documents:
                result = database[name].insert_many(documents)
                print(f"{name}: {len(result.inserted_ids)} imported")

    print("Dataset import completed.")


if __name__ == "__main__":
    main()