import json
import os
import tempfile


LOCAL_DATA_FILE = os.path.join(os.path.dirname(__file__), "local_data.json")


def load_items(collection):
    try:
        with open(LOCAL_DATA_FILE, encoding="utf-8") as local_file:
            data = json.load(local_file)
        return data.get(collection, [])
    except FileNotFoundError:
        return []


def save_items(collection, items):
    data = {}
    try:
        with open(LOCAL_DATA_FILE, encoding="utf-8") as local_file:
            data = json.load(local_file)
    except FileNotFoundError:
        pass

    data[collection] = items
    directory = os.path.dirname(LOCAL_DATA_FILE)
    fd, temp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as local_file:
            json.dump(data, local_file, indent=2)
        os.replace(temp_path, LOCAL_DATA_FILE)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def add_price_record(record):
    records = load_items("price_history")
    key = (record["RouteId"], record["Timestamp"])
    records = [
        existing for existing in records
        if (existing.get("RouteId"), existing.get("Timestamp")) != key
    ]
    records.append(record)
    save_items("price_history", records)


def latest_price_record(route_id):
    records = [
        record for record in load_items("price_history")
        if record.get("RouteId") == str(route_id)
    ]
    if not records:
        return None
    return max(records, key=lambda record: record.get("Timestamp", ""))
