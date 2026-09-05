#!/usr/bin/env python3
"""Sweep Milwaukee ordering platforms for espresso martinis and write data/martinis.json."""
from __future__ import annotations

import argparse
import concurrent.futures
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
# Happy hour shows up as a menu or group named for it ("Happy Hour", "HH
# Specials") or in the item name itself ("HH Espresso Martini").
HAPPY = re.compile(r"happy\s*hour|\bhh\b", re.I)
# Toast location names routinely append the street address ("Von Trier 2235
# North Farwell Avenue") or repeat the whole name. Display cleanup only.
TRAILING_ADDR = re.compile(r"\s+\d+[\w.-]*\s+[A-Za-z0-9 .'&-]*?"
    r"(Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Blvd|Boulevard|Way|Highway|Hwy|Court|Ct|Place|Pl|Northway|Parkway|Pkwy|Terrace|Circle)\.?$", re.I)
MARTINI_2 = re.compile(r"martini|\btini\b", re.I)
# Downtown Milwaukee: Third Ward through Yankee Hill, river to the lake. User
# steering 2026-09-05: downtown gets read first and leads the site.
DT = (43.020, -87.930, 43.062, -87.870)
NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
# Clover online ordering: white-label, merchant's own prices, public JSON, no
# auth or bot wall (retested 2026-09-05). No public directory exists, so
# restaurants are found by scanning the websites OSM lists for Milwaukee
# bars/restaurants for ordering links, plus a hand-seeded slug list.
CLOVER_API = "https://www.clover.com/oloservice/v1/merchants"
CLOVER_LINK = re.compile(r"clover\.com/online-ordering/([A-Za-z0-9._~-]+)", re.I)
CLOVER_SEEDS = ["mke-fish--chicken-milwaukee", "mccocos-milwaukee", "aladdin-city-cafe-milwaukee",
                "your-in-luck-eats-milwaukee", "asianrican-foods-milwaukee"]
OVERPASS = ["https://overpass.kumi.systems/api/interpreter", "https://overpass-api.de/api/interpreter",
            "https://overpass.private.coffee/api/interpreter"]


def get(url, **kw):
    kw.setdefault("timeout", 30)
    r = requests.get(url, headers=UA, **kw)
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


def martini_items(guid: str) -> tuple[list[dict], bool]:
    """Espresso-martini items from a restaurant's online and register menus,
    plus whether the restaurant runs a happy hour at all. Regular-menu and
    happy-hour prices are kept apart: a spot's board price is its everyday
    price, the hh price only shows when the happy-hour toggle is on."""
    seen: dict[str, dict] = {}
    has_hh = False
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
            menu_hh = bool(HAPPY.search(menu.get("name") or ""))
            has_hh = has_hh or menu_hh
            for group in menu.get("groups") or []:
                group_hh = menu_hh or bool(HAPPY.search(group.get("name") or ""))
                has_hh = has_hh or group_hh
                for item in group.get("items") or []:
                    name = (item.get("name") or "").strip()
                    if not (MARTINI.search(name) and MARTINI_2.search(name)):
                        continue
                    # "SHOP ..." rows are retail shelf stock, not a poured drink.
                    if name.lower().startswith("shop "):
                        continue
                    item_hh = group_hh or bool(HAPPY.search(name))
                    prices = [c for c in (cents(p) for p in item.get("prices") or []) if c]
                    price = cents(item.get("price"))
                    if price is None and prices:
                        price = min(prices)
                    key = re.sub(r"\s+", " ", name.lower())
                    entry = seen.setdefault(key, {"item": name, "price_cents": None, "hh_price_cents": None})
                    # Keep the cheapest listing of the same item per price kind.
                    slot = "hh_price_cents" if item_hh else "price_cents"
                    if price and (entry[slot] is None or price < entry[slot]):
                        entry[slot] = price
        time.sleep(0.3)
    return list(seen.values()), has_hh


def neighborhood(lat: float, lng: float) -> str | None:
    try:
        addr = get(NOMINATIM, params={"lat": lat, "lon": lng, "format": "jsonv2", "zoom": 16}).json().get("address") or {}
    except Exception:
        return None
    hood = addr.get("suburb") or addr.get("neighbourhood") or addr.get("quarter") or addr.get("city_district")
    if hood and len(hood) >= 3:
        return hood
    return addr.get("city") or addr.get("town") or addr.get("village") or hood


def clean_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name or "").strip()
    half = len(name) // 2
    if len(name) % 2 == 0 and name[:half] == name[half:]:
        name = name[:half].rstrip()
    words = name.split(" ")
    if len(words) % 2 == 0:
        n = len(words) // 2
        if words[:n] == words[n:]:
            name = " ".join(words[:n])
    return TRAILING_ADDR.sub("", name).strip()


def is_downtown(lat, lng) -> bool:
    return lat is not None and lng is not None and DT[0] <= lat <= DT[2] and DT[1] <= lng <= DT[3]


def osm_websites() -> list[str]:
    # Simple equality filters only: the regex alternation form 400s on some
    # Overpass backends. Same shape as the coffee collector's discovery.
    b = f"{MKE[0]},{MKE[1]},{MKE[2]},{MKE[3]}"
    parts = [f'nwr["amenity"="{a}"]["{t}"]({b});' for a in ("bar", "pub", "restaurant")
             for t in ("website", "contact:website")]
    query = "[out:json][timeout:120];(" + "".join(parts) + ");out tags;"
    for host in OVERPASS:
        try:
            payload = get(host, params={"data": query}, timeout=180).json()
            if payload.get("remark"):
                print(f"overpass remark: {payload['remark'][:160]}", file=sys.stderr)
            els = payload.get("elements") or []
        except Exception as exc:
            print(f"overpass {host}: {exc}", file=sys.stderr)
            continue
        urls = set()
        for el in els:
            tags = el.get("tags") or {}
            url = tags.get("website") or tags.get("contact:website")
            if url and url.startswith("http"):
                urls.add(url)
        return sorted(urls)
    return []


def clover_slugs() -> dict[str, str]:
    """slug -> website it was found on, seeds plus OSM website link scan."""
    found = {slug: "seed" for slug in CLOVER_SEEDS}
    urls = osm_websites()
    print(f"osm: {len(urls)} bar/restaurant websites to scan for Clover links", file=sys.stderr)
    def probe(url):
        try:
            html = requests.get(url, headers=UA, timeout=12).text[:400000]
        except Exception:
            return []
        return CLOVER_LINK.findall(html)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for url, slugs in zip(urls, pool.map(probe, urls)):
            for slug in slugs:
                found.setdefault(slug, url)
    print(f"clover: {len(found)} ordering pages found", file=sys.stderr)
    return found


def geocode(address: str):
    try:
        rows = get(NOMINATIM.replace("reverse", "search"),
                   params={"q": address, "format": "jsonv2", "limit": 1, "countrycodes": "us"}).json()
    except Exception:
        return None, None
    if not rows:
        return None, None
    return float(rows[0]["lat"]), float(rows[0]["lon"])


def clover_martini_items(slug: str) -> tuple[dict, list[dict]] | None:
    merchant = get(CLOVER_API + f"/{slug}", params={"slug": "true"}).json()
    if not merchant.get("merchantUuid"):
        return None
    menu = get(CLOVER_API + f"/{merchant['merchantUuid']}/menu").json()
    categories = menu.get("categories") or {}
    seen: dict[str, dict] = {}
    for node in menu.get("items") or []:
        name = (node.get("name") or "").strip()
        if not (MARTINI.search(name) and MARTINI_2.search(name)):
            continue
        price = node.get("price")
        if not isinstance(price, (int, float)) or price <= 0:
            price = None
        price = int(price) if price else None
        key = re.sub(r"\s+", " ", name.lower())
        entry = seen.setdefault(key, {"item": name, "price_cents": None, "hh_price_cents": None})
        slot = "hh_price_cents" if HAPPY.search(name) else "price_cents"
        if price and (entry[slot] is None or price < entry[slot]):
            entry[slot] = price
    return merchant, list(seen.values())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="data/martinis.json")
    args = ap.parse_args()

    directory = toast_directory()
    guids = sorted(directory, key=lambda g: (
        not is_downtown((directory[g].get("location") or {}).get("latitude"),
                        (directory[g].get("location") or {}).get("longitude")), g))
    n_dt = sum(1 for g in guids if is_downtown((directory[g].get("location") or {}).get("latitude"),
                                               (directory[g].get("location") or {}).get("longitude")))
    print(f"{n_dt} downtown restaurants scanned first", file=sys.stderr)
    if args.limit:
        guids = guids[: args.limit]
    hits = []
    for i, guid in enumerate(guids, 1):
        rest = directory[guid]
        items, has_hh = martini_items(guid)
        if items or has_hh:
            hits.append((rest, items, has_hh))
        if i % 50 == 0:
            print(f"{i}/{len(guids)} scanned, {len(hits)} with espresso martinis", file=sys.stderr)

    out = []
    for rest, items, has_hh in hits:
        if not items:
            continue
        loc = rest.get("location") or {}
        lat, lng = loc.get("latitude"), loc.get("longitude")
        hood = neighborhood(lat, lng) if lat and lng else None
        time.sleep(1.1)  # Nominatim courtesy pace
        addr = ", ".join(x for x in [loc.get("address1"), loc.get("city"), loc.get("state")] if x)
        hh_prices = [m["hh_price_cents"] for m in items if m.get("hh_price_cents")]
        regular = [m["price_cents"] for m in items if m["price_cents"]]
        # Board price is the everyday price; a happy-hour-only listing still
        # gets the spot on the board at its hh price.
        cheapest = min(regular) if regular else min(hh_prices, default=None)
        out.append({
            "name": clean_name(rest.get("name")),
            "address": addr,
            "lat": lat, "lng": lng,
            "neighborhood": hood,
            "downtown": is_downtown(lat, lng),
            "price_cents": cheapest,
            "items": sorted(items, key=lambda m: (m["price_cents"] is None, m["price_cents"] or 0)),
            "happy_hour": has_hh or bool(hh_prices),
            "hh_price_cents": min(hh_prices) if hh_prices else None,
            "platform": "toast",
            "guid": rest["guid"],
        })
    out.sort(key=lambda r: (r["price_cents"] is None, r["price_cents"] or 0, r["name"]))

    for slug, found_on in clover_slugs().items():
        try:
            result = clover_martini_items(slug)
        except Exception as exc:
            print(f"clover {slug}: {exc}", file=sys.stderr)
            continue
        if not result:
            continue
        merchant, items = result
        if not items:
            continue
        addr = merchant.get("address") or {}
        lat = lng = None
        loc = merchant.get("location") or {}
        if isinstance(loc.get("latitude"), (int, float)):
            lat, lng = loc["latitude"], loc["longitude"]
        name = clean_name(merchant.get("name"))
        dupe = any(name.lower() == r["name"].lower() for r in out)
        if dupe:
            continue
        address = ", ".join(x for x in [addr.get("address1"), addr.get("city"), addr.get("state")] if x)
        if lat is None and address:
            lat, lng = geocode(address)
            time.sleep(1.1)  # Nominatim courtesy pace
        hood = neighborhood(lat, lng) if lat and lng else None
        if lat and lng:
            time.sleep(1.1)
        hh_prices = [m["hh_price_cents"] for m in items if m.get("hh_price_cents")]
        regular = [m["price_cents"] for m in items if m["price_cents"]]
        out.append({
            "name": name,
            "address": address,
            "lat": lat, "lng": lng,
            "neighborhood": hood,
            "downtown": is_downtown(lat, lng),
            "price_cents": min(regular) if regular else min(hh_prices, default=None),
            "items": sorted(items, key=lambda m: (m["price_cents"] is None, m["price_cents"] or 0)),
            "happy_hour": bool(hh_prices),
            "hh_price_cents": min(hh_prices) if hh_prices else None,
            "platform": "clover",
            "guid": slug,
        })
        print(f"clover hit: {name} ({len(items)} items)", file=sys.stderr)
    out.sort(key=lambda r: (r["price_cents"] is None, r["price_cents"] or 0, r["name"]))

    # Hand-verified spots the platforms cannot see (no online ordering,
    # website-only menus). A live platform hit for the same name wins.
    manual_path = Path(__file__).resolve().parent.parent / "data" / "manual.json"
    if manual_path.exists():
        manual = json.loads(manual_path.read_text()).get("entries") or []
        live_names = {r["name"].lower() for r in out}
        added = 0
        for entry in manual:
            if entry["name"].lower() in live_names:
                print(f"manual: {entry['name']} also on a platform now, keeping the live one", file=sys.stderr)
                continue
            out.append(entry)
            added += 1
        if added:
            out.sort(key=lambda r: (r["price_cents"] is None, r["price_cents"] or 0, r["name"]))
            print(f"manual: {added} hand-verified spots merged", file=sys.stderr)

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
