
import os
import json
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient
from bson import json_util

# Load FixMate database settings
project_dir = Path(__file__).resolve().parent
load_dotenv(project_dir / ".env")

client = MongoClient(
    os.environ["MONGO_URI"],
    serverSelectionTimeoutMS=5000
)

client.admin.command("ping")
db = client[os.environ["MONGO_DB_NAME"]]

# Create a separate backup folder
backup_dir = project_dir / "fixmate_backup"
backup_dir.mkdir(exist_ok=True)

# Export all collections as Extended JSON
for collection_name in db.list_collection_names():
    documents = list(db[collection_name].find({}))

    output_file = backup_dir / f"{collection_name}.json"

    with open(output_file, "w", encoding="utf-8") as file:
        file.write(json_util.dumps(documents, indent=2))

    print(f"Backed up {collection_name}: {len(documents)} documents")

# Save collection index definitions
indexes = {
    name: list(db[name].list_indexes())
    for name in db.list_collection_names()
}

with open(backup_dir / "indexes.json", "w", encoding="utf-8") as file:
    file.write(json_util.dumps(indexes, indent=2))

print("Backup completed successfully!")
client.close()
