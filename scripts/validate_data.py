"""Validate the directory's checked-in JSON. No network or third-party modules."""
import datetime as dt
import json
import math
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def iso_date(value):
    require(isinstance(value, str), "date must be an ISO string")
    if len(value) == 10:
        require(dt.date.fromisoformat(value).isoformat() == value, "invalid ISO date")
    else:
        require("T" in value, "timestamp must contain T")
        dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate(doc, key):
    require(isinstance(doc, dict), "document must be an object")
    rows = doc.get(key)
    require(isinstance(rows, list), f"{key} must be an array")
    if key == "martinis":
        require(type(doc.get("count")) is int and doc["count"] == len(rows), "count must match martinis")
    if "generated_at" in doc:
        iso_date(doc["generated_at"])
    guids = set()
    for index, row in enumerate(rows):
        label = f"{key}[{index}]"
        require(isinstance(row, dict), f"{label} must be an object")
        guid = row.get("guid")
        require(isinstance(guid, str) and guid.strip(), f"{label}: missing guid")
        require(guid not in guids, f"{label}: duplicate guid {guid}")
        guids.add(guid)
        require(isinstance(row.get("name"), str) and row["name"].strip(), f"{label}: missing name")
        for field, low, high in (("lat", 42.5, 43.6), ("lng", -88.6, -87.5)):
            value = row.get(field)
            require(type(value) in (int, float) and math.isfinite(value) and low <= value <= high,
                    f"{label}: invalid Milwaukee-area {field}")
        if "confidence" in row:
            require(row["confidence"] in ("menu", "stale", "reported"), f"{label}: invalid confidence")
        for field in ("seen_at", "verified_at", "updated_at", "generated_at"):
            if field in row:
                iso_date(row[field])
        items = row.get("items")
        require(isinstance(items, list), f"{label}: items must be an array")
        for obj in [row] + items:
            require(isinstance(obj, dict), f"{label}: item must be an object")
            for field in ("price_cents", "hh_price_cents"):
                require(field in obj, f"{label}: missing {field}")
                value = obj[field]
                require(value is None or (type(value) is int and value > 0), f"{label}: invalid {field}")
    return len(rows)


def main():
    root = Path(__file__).resolve().parent.parent
    for filename, key in (("martinis", "martinis"), ("cow", "cows"), ("manual", "entries")):
        path = root / "data" / f"{filename}.json"
        try:
            count = validate(json.loads(path.read_text()), key)
        except (ValueError, OSError) as exc:
            raise SystemExit(f"{path.relative_to(root)}: {exc}") from exc
        print(f"data/{filename}.json: {count} valid rows")


if __name__ == "__main__":
    main()
