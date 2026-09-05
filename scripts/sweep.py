#!/usr/bin/env python3
"""Sweep Milwaukee ordering platforms for espresso martinis and write data/martinis.json."""
from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import re
import sys
import time
from pathlib import Path

import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Instinct/1.0", "Accept-Language": "en-US,en;q=0.8"}
TOAST_API = "https://ws-api.toasttab.com/do-federated-gateway/v1/graphql"
# Milwaukee bounding box (south, west, north, east), same box the coffee site uses.
MKE = (42.92, -88.07, 43.20, -87.86)
GRID_LAT, GRID_LNG, RADIUS_MI, PAGE_CAP = 0.05, 0.06, 3, 299
MARTINI = re.compile(r"espresso", re.I)
MARTINI_2 = re.compile(r"martini|\btini\b", re.I)
NOMINATIM = "https://nominatim.openstreetmap.org/reverse"


def get(url, **kw):
    r = requests.get(url, headers=UA, timeout=30, **kw)
    r.raise_for_status()
    return r


def toast_query(query: str) -> dict:
    payload = get(TOAST_API, params={"query": query}).json()
    for err in payload.get("errors") or []:
        print(f"Toast GraphQL: {err.get('message')}", file=sys.stderr)
    return payload.get("data") or {}


def toast_directory() -> dict[str, dict]:
    south, west, north, east = MKE
    when = f"{dt.date.today().isoformat()}T12:00:00.000Z"
    found: dict[str, dict] = {}
    lats = [south + i * GRID_LAT for i in range(int((north - south) / GRID_LAT) + 2)]
    lngs = [west + i * GRID_LNG for i in range(int((east - west) / GRID_LNG) + 2)]
    for lat, lng in itertools.product(lats, lngs):
        q = ('{nearbyRestaurants(input:{diningOption:TAKE_OUT,fulfillmentDateTime:"%s",'
             "latitude:%.4f,longitude:%.4f,radius:%d}){guid name shortUrl "
             "location{address1 city state latitude longitude}}}" % (when, lat, lng, RADIUS_MI))
        try:
            rows = toast_query(q).get("nearbyRestaurants") or []
        except Exception as exc:
            print(f"directory {lat:.2f},{lng:.2f}: {exc}", file=sys.stderr)
            continue
        if len(rows) >= PAGE_CAP:
            print(f"directory truncated at {lat:.2f},{lng:.2f}", file=sys.stderr)
        for row in rows:
            found[row["guid"]] = row
        time.sleep(0.25)
    print(f"directory: {len(found)} restaurants", file=sys.stderr)
    return found


def cents(v) -> int | None:
    if v is None:
        return None
    try:
        return int(round(float(v) * 100))
    except (TypeError, ValueError):
        return None


def martini_items(guid: str) -> list[dict]:
    """Espresso-martini items from a restaurant's online and register menus."""
    seen: dict[str, dict] = {}
    for visibility in (None, "POS"):
        vis = f',visibility:{visibility}' if visibility else ''
        q = ('{menusV3(input:{restaurantGuid:"%s"%s}){... on MenusResponse{menus{name groups{name '
             'items{name price prices}}}}}}' % (guid, vis))
        try:
            menus = (toast_query(q).get("menusV3") or {}).get("menus") or []
        except Exception as exc:
            print(f"menu {guid}: {exc}", file=sys.stderr)
            continue
        for menu in menus:
            for group in menu.get("groups") or []:
                for item in group.get("items") or []:
                    name = (item.get("name") or "").strip()
                    if not (MARTINI.search(name) and MARTINI_2.search(name)):
                        continue
                    prices = [c for c in (cents(p) for p in item.get("prices") or []) if c]
                    price = cents(item.get("price"))
                    if price is None and prices:
                        price = min(prices)
                    key = re.sub(r"\s+", " ", name.lower())
                    # Keep the cheapest listing of the same item across menus.
                    if key not in seen or (price and (seen[key]["price_cents"] is None or price < seen[key]["price_cents"])):
                        seen[key] = {"item": name, "price_cents": price}
        time.sleep(0.3)
    return list(seen.values())


def neighborhood(lat: float, lng: float) -> str | None:
    try:
        addr = get(NOMINATIM, params={"lat": lat, "lon": lng, "format": "jsonv2", "zoom": 16}).json().get("address") or {}
    except Exception:
        return None
    hood = addr.get("suburb") or addr.get("neighbourhood") or addr.get("quarter") or addr.get("city_district")
    if hood and len(hood) >= 3:
        return hood
    return addr.get("city") or addr.get("town") or addr.get("village") or hood


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="data/martinis.json")
    args = ap.parse_args()

    directory = toast_directory()
    guids = sorted(directory)
    if args.limit:
        guids = guids[: args.limit]
    hits = []
    for i, guid in enumerate(guids, 1):
        rest = directory[guid]
        items = martini_items(guid)
        if items:
            hits.append((rest, items))
        if i % 50 == 0:
            print(f"{i}/{len(guids)} scanned, {len(hits)} with espresso martinis", file=sys.stderr)

    out = []
    for rest, items in hits:
        loc = rest.get("location") or {}
        lat, lng = loc.get("latitude"), loc.get("longitude")
        hood = neighborhood(lat, lng) if lat and lng else None
        time.sleep(1.1)  # Nominatim courtesy pace
        addr = ", ".join(x for x in [loc.get("address1"), loc.get("city"), loc.get("state")] if x)
        cheapest = min((m["price_cents"] for m in items if m["price_cents"]), default=None)
        out.append({
            "name": re.sub(r"\s+", " ", rest.get("name") or "").strip(),
            "address": addr,
            "lat": lat, "lng": lng,
            "neighborhood": hood,
            "price_cents": cheapest,
            "items": sorted(items, key=lambda m: (m["price_cents"] is None, m["price_cents"] or 0)),
            "platform": "toast",
            "guid": rest["guid"],
        })
    out.sort(key=lambda r: (r["price_cents"] is None, r["price_cents"] or 0, r["name"]))

    doc = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "metro": "Milwaukee",
        "restaurants_scanned": len(guids),
        "count": len(out),
        "martinis": out,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(doc, indent=1))
    print(f"wrote {args.out}: {len(out)} restaurants with espresso martinis from {len(guids)} scanned", file=sys.stderr)


if __name__ == "__main__":
    main()
