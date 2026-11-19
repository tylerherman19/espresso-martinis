#!/usr/bin/env python3
"""Sweep Milwaukee ordering platforms for espresso martinis and write data/martinis.json."""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import itertools
import ipaddress
import json
import math
import os
import re
import socket
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

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
# A unit suffix sits after the street ("Aya 700 East Kilbourn Avenue, Suite 100")
# and has to come off first or the street match never reaches the end.
TRAILING_UNIT = re.compile(r"[,\s]+(Suite|Ste|Unit|Apt|Bldg|Building|#)\.?\s*[\w-]+$", re.I)
# Merchants mark a dead location in the name rather than delisting it.
CLOSED = re.compile(r"\b(closed|permanently closed|do not use|test store)\b", re.I)
MARTINI_2 = re.compile(r"martini|\btini\b", re.I)
NOT_COCKTAIL = re.compile(r"\b(?:na|n/a|non[\s-]*alcoholic|mocktails?|zero[\s-]*proof|"
                          r"chocolate\s+bars?|dessert\s+bars?|bars?\s+dessert|cakes?|cookies?|"
                          r"brownies?|desserts?|ice\s+cream|flights?|shop|retail|bottles?|"
                          r"pancakes?|waffles?|cupcakes?|candy|truffles?|canned|packs?|bars?$|"
                          r"six[\s-]*packs?|6[\s-]*packs?|liqueur)\b", re.I)
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
# A run that would shrink the list below this share of the last one is refused
# outright. The 2026-09-30 run wrote 2 spots over 98 when Toast started
# answering 403, and the site showed 2 until it was put back by hand.
MIN_KEEP = 0.5


def get(url, **kw):
    kw.setdefault("timeout", 30)
    r = requests.get(url, headers=UA, **kw)
    r.raise_for_status()
    return r


def toast_query(query: str) -> dict:
    payload = get(TOAST_API, params={"query": query}).json()
    errors = payload.get("errors") or []
    for err in errors:
        print(f"Toast GraphQL: {err.get('message')}", file=sys.stderr)
    if errors:
        raise RuntimeError(f"Toast GraphQL: {errors[0].get('message')}")
    if not isinstance(payload.get("data"), dict):
        raise ValueError("Toast response has no data object")
    return payload["data"]


def required_list(obj: dict, field: str) -> list:
    value = obj.get(field)
    if not isinstance(value, list):
        raise ValueError(f"missing or invalid {field}")
    return value


def is_martini(name: str) -> bool:
    return bool(MARTINI.search(name) and MARTINI_2.search(name) and not NOT_COCKTAIL.search(name))


def toast_directory() -> tuple[dict[str, dict], int, int]:
    """Every Toast restaurant in the box, plus how many grid cells failed out
    of how many were asked. A failed cell means its restaurants are unknown,
    not gone."""
    south, west, north, east = MKE
    when = f"{dt.date.today().isoformat()}T12:00:00.000Z"
    found: dict[str, dict] = {}
    lats = [south + i * GRID_LAT for i in range(int((north - south) / GRID_LAT) + 2)]
    lngs = [west + i * GRID_LNG for i in range(int((east - west) / GRID_LNG) + 2)]
    cells = list(itertools.product(lats, lngs))
    failed = 0
    for lat, lng in cells:
        q = ('{nearbyRestaurants(input:{diningOption:TAKE_OUT,fulfillmentDateTime:"%s",'
             "latitude:%.4f,longitude:%.4f,radius:%d}){guid name shortUrl "
             "location{address1 city state latitude longitude}}}" % (when, lat, lng, RADIUS_MI))
        try:
            rows = required_list(toast_query(q), "nearbyRestaurants")
            if any(not isinstance(row, dict) or not row.get("guid") for row in rows):
                raise ValueError("invalid restaurant row")
        except Exception as exc:
            print(f"directory {lat:.2f},{lng:.2f}: {exc}", file=sys.stderr)
            failed += 1
            continue
        if len(rows) >= PAGE_CAP:
            print(f"directory truncated at {lat:.2f},{lng:.2f}", file=sys.stderr)
            failed += 1
        for row in rows:
            found[row["guid"]] = row
        time.sleep(0.25)
    print(f"directory: {len(found)} restaurants, {failed}/{len(cells)} areas failed", file=sys.stderr)
    return found, failed, len(cells)


def cents(v) -> int | None:
    if v is None:
        return None
    try:
        return int(round(float(v) * 100))
    except (TypeError, ValueError):
        return None


def martini_items(guid: str) -> tuple[list[dict], bool, bool]:
    """Espresso-martini items from a restaurant's online and register menus,
    whether the restaurant runs a happy hour at all, and whether both menus
    were actually read. Regular-menu and happy-hour prices are kept apart: a
    spot's board price is its everyday price, the hh price only shows when the
    happy-hour toggle is on."""
    seen: dict[str, dict] = {}
    has_hh = False
    read = True
    for visibility in (None, "POS"):
        vis = f',visibility:{visibility}' if visibility else ''
        q = ('{menusV3(input:{restaurantGuid:"%s"%s}){... on MenusResponse{menus{name groups{name '
             'items{name price prices}}}}}}' % (guid, vis))
        try:
            result = toast_query(q).get("menusV3")
            if not isinstance(result, dict):
                raise ValueError("missing or invalid menusV3")
            menus = required_list(result, "menus")
            for menu in menus:
                for group in required_list(menu, "groups"):
                    required_list(group, "items")
        except Exception as exc:
            print(f"menu {guid}: {exc}", file=sys.stderr)
            read = False
            continue
        for menu in menus:
            menu_hh = bool(HAPPY.search(menu.get("name") or ""))
            has_hh = has_hh or menu_hh
            for group in menu.get("groups") or []:
                group_hh = menu_hh or bool(HAPPY.search(group.get("name") or ""))
                has_hh = has_hh or group_hh
                for item in group.get("items") or []:
                    name = (item.get("name") or "").strip()
                    if not is_martini(name):
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
    return list(seen.values()), has_hh, read


# Subdivision names OSM returns that locate nothing for a reader. Outside the
# city of Milwaukee the municipality is the useful label anyway; inside it,
# these few are replaced by the city.
OBSCURE_HOODS = {
    "Park Place", "Honey Creek Manor", "Bluemound Heights", "Conrad Gardens",
    "Whitnall Oaks", "Downtown District", "Village Center District",
    "Southridge Commercial District", "Underwood Parkway", "Inglewood",
    "Lowell Damon Woods", "Pabst Park", "Six Points", "Forest Home Corridor",
    "Tosa Village",
}


def neighborhood(lat: float, lng: float) -> str | None:
    """The label a Milwaukeean would use for where a spot is: the real
    neighborhood inside the city, the municipality everywhere else."""
    try:
        addr = get(NOMINATIM, params={"lat": lat, "lon": lng, "format": "jsonv2", "zoom": 16}).json().get("address") or {}
    except Exception:
        return None
    city = addr.get("city") or addr.get("town") or addr.get("village")
    hood = addr.get("suburb") or addr.get("neighbourhood") or addr.get("quarter") or addr.get("city_district")
    if city and city.strip().lower() != "milwaukee":
        return city
    if hood and len(hood) >= 3 and hood not in OBSCURE_HOODS:
        return hood
    return city or hood


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
    name = TRAILING_UNIT.sub("", name)
    return TRAILING_ADDR.sub("", name).strip().rstrip(",")


def is_downtown(lat, lng) -> bool:
    return lat is not None and lng is not None and DT[0] <= lat <= DT[2] and DT[1] <= lng <= DT[3]


def osm_websites() -> list[str] | None:
    """Bar and restaurant websites OSM knows in the box, or None when no
    Overpass mirror answered."""
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
                raise ValueError(f"overpass remark: {payload['remark'][:160]}")
            els = required_list(payload, "elements")
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
    return None


def public_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("website must be a public HTTP(S) URL")
    addresses = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80),
                                   type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("website resolves to a non-public address")
    return addresses[0][4][0]


class WebsiteAdapter(requests.adapters.HTTPAdapter):
    def __init__(self, hostname):
        self.hostname = hostname
        super().__init__()

    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, server_hostname=self.hostname, assert_hostname=self.hostname, **kwargs)


def website_html(url: str) -> str:
    for _ in range(6):
        ip = public_url(url)
        parts = urlsplit(url)
        host = f"[{ip}]" if ":" in ip else ip
        port = parts.port or (443 if parts.scheme == "https" else 80)
        pinned = urlunsplit((parts.scheme, f"{host}:{port}", parts.path, parts.query, ""))
        with requests.Session() as session:
            session.trust_env = False
            session.mount("https://", WebsiteAdapter(parts.hostname))
            with session.get(pinned, headers={**UA, "Host": parts.netloc}, timeout=12,
                             allow_redirects=False, stream=True) as response:
                response.raise_for_status()
                if response.is_redirect:
                    url = urljoin(url, response.headers["Location"])
                    continue
                body = bytearray()
                for chunk in response.iter_content(chunk_size=16384):
                    if len(body) + len(chunk) > 400000:
                        raise ValueError("website exceeds 400000 bytes")
                    body.extend(chunk)
                return body.decode(response.encoding or "utf-8", errors="replace")
    raise ValueError("too many website redirects")


def clover_slugs() -> tuple[dict[str, str], list[str]]:
    """Seed and discovered slugs, plus discovery failures."""
    found = {slug: "seed" for slug in CLOVER_SEEDS}
    urls = osm_websites()
    if urls is None:
        print("osm: no Overpass mirror answered, seeds only", file=sys.stderr)
        return found, ["Overpass: no mirror answered, so Clover discovery used its seed list only"]
    print(f"osm: {len(urls)} bar/restaurant websites to scan for Clover links", file=sys.stderr)
    def probe(url):
        try:
            return CLOVER_LINK.findall(website_html(url)), None
        except Exception as exc:
            return [], f"Clover discovery {url}: {exc}"
    problems = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for url, (slugs, problem) in zip(urls, pool.map(probe, urls)):
            if problem:
                problems.append(problem)
            for slug in slugs:
                found.setdefault(slug, url)
    print(f"clover: {len(found)} ordering pages found", file=sys.stderr)
    return found, problems


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
        raise ValueError("Clover response has no merchantUuid")
    menu = get(CLOVER_API + f"/{merchant['merchantUuid']}/menu").json()
    seen: dict[str, dict] = {}
    for node in required_list(menu, "items"):
        name = (node.get("name") or "").strip()
        if not is_martini(name):
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


def load_previous(path: Path) -> dict:
    try:
        doc = json.loads(path.read_text())
    except FileNotFoundError:
        if not path.exists() and not path.is_symlink():
            return {}
        raise
    if not isinstance(doc, dict) or not isinstance(doc.get("martinis"), list):
        raise ValueError(f"{path}: invalid previous directory")
    for row in doc["martinis"]:
        if not isinstance(row, dict) or not row.get("guid") or not row.get("name") or "price_cents" not in row:
            raise ValueError(f"{path}: invalid previous venue")
    return doc


def write_atomic(path: Path, doc: dict) -> None:
    body = json.dumps(doc, indent=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=f".{path.name}.",
                                         encoding="utf-8", delete=False) as fh:
            temporary = Path(fh.name)
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def normalized(text: str) -> str:
    return re.sub(r"[^\w]+", " ", text.casefold()).strip()


def same_venue(a: dict, b: dict) -> bool:
    if normalized(a["name"]) != normalized(b["name"]):
        return False
    if a.get("address") and b.get("address") and normalized(a["address"]) == normalized(b["address"]):
        return True
    coords = [r.get(k) for r in (a, b) for k in ("lat", "lng")]
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in coords):
        return False
    lat1, lng1, lat2, lng2 = map(math.radians, coords)
    distance = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(min(1, distance))) <= 100


def by_price(rows: list[dict]) -> None:
    rows.sort(key=lambda r: (r["price_cents"] is None, r["price_cents"] or 0, r["name"]))


def assemble(fresh: list[dict], carried: list[dict], manual: list[dict]) -> list[dict]:
    """Live readings beat hand-checks, which beat carried readings of the
    same venue. A shared name without a matching location is not a duplicate."""
    out = []
    for r in fresh + manual + carried:
        if any(r["guid"] == other["guid"] or same_venue(r, other) for other in out):
            continue
        out.append(r)
    by_price(out)
    return out


def collapsed(new: int, old: int) -> bool:
    """True when a run would throw away too much of the last list to trust."""
    return old >= 10 and new < old * MIN_KEEP


def report(problems: list[str]) -> None:
    """Hand the workflow what went wrong so the run goes red and says why."""
    for p in problems:
        print(f"problem: {p}", file=sys.stderr)
    if not problems:
        return
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
            fh.write("degraded=true\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write("### Sources that did not answer\n\n")
            fh.write("".join(f"- {p}\n" for p in problems))
            fh.write("\nSpots behind them kept their last reading and its date.\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--output", "--out", dest="out", default="data/martinis.json")
    ap.add_argument("--force", action="store_true",
                    help="write even when the list shrinks past MIN_KEEP of the last one")
    args = ap.parse_args()
    out_path = Path(args.out)
    production = Path(__file__).resolve().parent.parent / "data" / "martinis.json"
    if args.limit < 0:
        ap.error("--limit must not be negative")
    if args.limit and out_path.resolve() == production.resolve():
        ap.error("--limit requires --output pointing somewhere other than data/martinis.json")
    today = dt.date.today().isoformat()

    # Last run's swept spots, so a source that does not answer this time costs
    # a fresh reading, not the spot.
    previous = load_previous(out_path)
    prev_date = (previous.get("generated_at") or "")[:10] or None
    prev_rows = {r["guid"]: r for r in previous.get("martinis") or []
                 if r.get("platform") in ("toast", "clover") and r.get("guid")}
    unread: set[str] = set()
    problems: list[str] = []

    directory, failed, cells = toast_directory()
    if failed:
        problems.append(f"Toast directory: {failed} of {cells} areas did not answer")
        unread |= {g for g, r in prev_rows.items() if r["platform"] == "toast" and g not in directory}
    guids = sorted(directory, key=lambda g: (
        not is_downtown((directory[g].get("location") or {}).get("latitude"),
                        (directory[g].get("location") or {}).get("longitude")), g))
    n_dt = sum(1 for g in guids if is_downtown((directory[g].get("location") or {}).get("latitude"),
                                               (directory[g].get("location") or {}).get("longitude")))
    print(f"{n_dt} downtown restaurants scanned first", file=sys.stderr)
    if args.limit:
        guids = guids[: args.limit]
    hits = []
    menu_failed = 0
    for i, guid in enumerate(guids, 1):
        rest = directory[guid]
        items, has_hh, read = martini_items(guid)
        if not read:
            menu_failed += 1
            unread.add(guid)
            continue
        if items or has_hh:
            hits.append((rest, items, has_hh))
        if i % 50 == 0:
            print(f"{i}/{len(guids)} scanned, {len(hits)} with espresso martinis", file=sys.stderr)
    if menu_failed:
        problems.append(f"Toast menus: {menu_failed} of {len(guids)} did not answer")

    out = []
    for rest, items, has_hh in hits:
        if not items:
            continue
        if CLOSED.search(rest.get("name") or ""):
            print(f"skipping closed location: {rest.get('name')}", file=sys.stderr)
            continue
        loc = rest.get("location") or {}
        lat, lng = loc.get("latitude"), loc.get("longitude")
        hood = neighborhood(lat, lng) if lat and lng else None
        time.sleep(1.1)  # Nominatim courtesy pace
        addr = ", ".join(x for x in [loc.get("address1"), loc.get("city"), loc.get("state")] if x)
        hh_prices = [m["hh_price_cents"] for m in items if m.get("hh_price_cents")]
        regular = [m["price_cents"] for m in items if m["price_cents"]]
        cheapest = min(regular, default=None)
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
            "seen_at": today,
        })

    slugs, discovery_problems = clover_slugs()
    problems.extend(discovery_problems)
    for g, r in prev_rows.items():
        if r["platform"] == "clover":
            slugs.setdefault(g, "previous")
    for slug, found_on in slugs.items():
        try:
            result = clover_martini_items(slug)
        except requests.HTTPError as exc:
            print(f"clover {slug}: {exc}", file=sys.stderr)
            problems.append(f"Clover {slug}: {exc}")
            # A 404 is a merchant that left Clover; anything else is Clover
            # not answering, and the last reading stands.
            if exc.response is None or exc.response.status_code != 404:
                unread.add(slug)
            continue
        except Exception as exc:
            print(f"clover {slug}: {exc}", file=sys.stderr)
            problems.append(f"Clover {slug}: {exc}")
            unread.add(slug)
            continue
        if not result:
            unread.add(slug)
            problems.append(f"Clover {slug}: missing menu response")
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
            "price_cents": min(regular, default=None),
            "items": sorted(items, key=lambda m: (m["price_cents"] is None, m["price_cents"] or 0)),
            "happy_hour": bool(hh_prices),
            "hh_price_cents": min(hh_prices) if hh_prices else None,
            "platform": "clover",
            "guid": slug,
            "seen_at": today,
        })
        print(f"clover hit: {name} ({len(items)} items)", file=sys.stderr)

    # Spots whose source did not answer keep their last reading, dated, so the
    # site can say how old it is instead of dropping the bar.
    carried = []
    for g in sorted(unread):
        if g in prev_rows:
            row = dict(prev_rows[g])
            row.setdefault("seen_at", prev_date)
            carried.append(row)

    # Hand-verified spots the platforms cannot see (no online ordering,
    # website-only menus).
    manual_path = Path(__file__).resolve().parent.parent / "data" / "manual.json"
    manual = []
    if manual_path.exists():
        manual = json.loads(manual_path.read_text()).get("entries") or []

    out_rows = assemble(out, carried, manual)
    kept = sum(1 for r in out_rows if any(r is c for c in carried))
    print(f"live: {len(out)}, carried from the last reading: {kept}, hand-verified: "
          f"{sum(1 for r in out_rows if r.get('platform') == 'website')}", file=sys.stderr)

    old_count = len(previous.get("martinis") or [])
    if collapsed(len(out_rows), old_count) and not args.force:
        problems.append(f"refused to write {len(out_rows)} spots over the last run's {old_count}")
        report(problems)
        print("Nothing was written. Rerun with --force if the drop is real.", file=sys.stderr)
        sys.exit(1)

    doc = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "metro": "Milwaukee",
        "restaurants_scanned": len(guids),
        "count": len(out_rows),
        "carried_forward": kept,
        "problems": problems,
        "martinis": out_rows,
    }
    write_atomic(out_path, doc)
    print(f"wrote {args.out}: {len(out_rows)} restaurants with espresso martinis from {len(guids)} scanned", file=sys.stderr)
    report(problems)


if __name__ == "__main__":
    main()
