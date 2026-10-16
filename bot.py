#!/usr/bin/env python3
"""Răspunde la mesajele trimise botului de Telegram cu cele mai ieftine bilete pe o rută.

Exemple de mesaje:
    Chișinău - Dubai 7 zile
    Iași - Milano 3-5 zile
    București Londra 4
    RMO - IST

Rulează periodic (GitHub Actions la ~5 minute): citește mesajele noi, caută și răspunde.
Răspunde doar la chat-ul din TELEGRAM_CHAT_ID.

Rulare:  .venv/bin/python bot.py                          # răspunde la mesajele noi
         .venv/bin/python bot.py --query "Chișinău - Dubai 7"  # test local, fără Telegram
"""

import argparse
import datetime as dt
import html
import json
import logging
import re
import sys
import time
import unicodedata

import search_tickets as st

log = logging.getLogger("bot")

RESULTS = 8  # câte variante de date să trimită

HELP = (
    "✈️ Scrie-mi ruta și câte zile vrei să stai, de exemplu:\n"
    "• <code>Chișinău - Dubai 7 zile</code>\n"
    "• <code>Iași - Milano 3-5 zile</code>\n"
    "• <code>București Londra 4</code>\n\n"
    f"Caut dus-întors în următoarele {st.DAYS_AHEAD} de zile, la toate companiile "
    "(Wizz Air, Ryanair, FlyOne, HiSky, SkyUp și restul prin Kiwi.com), "
    "și îți trimit cele mai ieftine date, doar cu zboruri directe. Fără zile, caut "
    f"{st.TRIP_MIN_DAYS}–{st.TRIP_MAX_DAYS} zile."
)

# Denumiri românești pe care căutarea Kiwi nu le recunoaște sau le confundă
ALIASES = {
    "londra": "london", "roma": "rome", "viena": "vienna", "varsovia": "warsaw", "praga": "prague",
    "atena": "athens", "lisabona": "lisbon", "copenhaga": "copenhagen", "bruxel": "brussels",
    "bruxelles": "brussels", "venetia": "venice", "napoli": "naples", "florenta": "florence",
    "geneva": "geneva", "munchen": "munich", "koln": "cologne", "colonia": "cologne", "nisa": "nice",
    "salonic": "thessaloniki", "cipru": "larnaca", "tenerife": "tenerife south", "moscova": "moscow",
    "bucuresti": "bucharest", "chisinau": "chisinau", "iasi": "iasi", "cluj": "cluj-napoca",
    "dublin": "dublin", "edinburgh": "edinburgh", "stambul": "istanbul", "tel aviv": "tel aviv",
}


def plain(text: str) -> str:
    """Fără diacritice, litere mici: „Chișinău” → „chisinau”."""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).lower().strip()


# --------------------------------------------------------------------------- înțelegerea mesajului

def parse_query(text: str) -> tuple[str, str, int, int] | None:
    """„Chișinău - Dubai 7 zile” → ("Chișinău", "Dubai", 7, 7)."""
    text = text.strip()
    min_days, max_days = st.TRIP_MIN_DAYS, st.TRIP_MAX_DAYS
    m = re.search(r"(\d{1,2})\s*(?:-|–|—|\.\.)\s*(\d{1,2})\s*(?:zile|zi|nopti|nopți|nights|days|z)?\s*$", text, re.I)
    if m:
        min_days, max_days = sorted((int(m.group(1)), int(m.group(2))))
        text = text[:m.start()]
    else:
        m = re.search(r"(?:pe\s+)?(\d{1,2})\s*(?:zile|zi|nopti|nopți|nights|days|z)?\s*$", text, re.I)
        if m:
            min_days = max_days = int(m.group(1))
            text = text[:m.start()]
    text = text.strip(" ,.")
    parts = [p.strip() for p in re.split(r"\s*(?:-|–|—|→|->|>|/)\s*|\s+(?:spre|la|to|in|în)\s+", text) if p.strip()]
    if len(parts) != 2:
        words = text.split()
        if len(words) != 2:
            return None
        parts = words
    if not (1 <= min_days <= max_days <= 30):
        return None
    return parts[0], parts[1], min_days, max_days


PLACES_QUERY = """query UmbrellaPlacesQuery($search: PlacesSearchInput, $filter: PlacesFilterInput,
  $options: PlacesOptionsInput, $first: Int) {
  places(search: $search, filter: $filter, options: $options, first: $first) {
    ... on PlaceConnection { edges { node { __typename id legacyId name
      ... on Station { code type city { name legacyId } } ... on City { code } } } }
  }
}"""


def kiwi_places(s, term: str) -> list[dict]:
    variables = {"search": {"term": term}, "filter": {"onlyTypes": ["CITY", "AIRPORT"]},
                 "options": {"locale": "en"}, "first": 10}
    r = s.post("https://api.skypicker.com/umbrella/v2/graphql?featureName=UmbrellaPlacesQuery",
               json={"query": PLACES_QUERY, "variables": variables},
               headers={"origin": "https://www.kiwi.com", "referer": "https://www.kiwi.com/"})
    r.raise_for_status()
    return [e["node"] for e in (r.json()["data"]["places"].get("edges") or [])]


def resolve_city(s, name: str) -> tuple[str, list[str]] | None:
    """Numele orașului → (nume afișat, aeroporturile lui). Acceptă și coduri IATA (RMO, DXB)."""
    if re.fullmatch(r"[A-Z]{3}", name.strip()):  # cod IATA scris direct (RMO, DXB)
        code = name.strip()
        city = st.city_of(code)
        airports = st.CITY_AIRPORTS[city][1] if city in st.CITY_AIRPORTS else [code]
        return st.ORIGIN_NAMES.get(code) or st.AIRPORT_NAMES.get(code) or code, airports

    term = ALIASES.get(plain(name), name)
    nodes = kiwi_places(s, term)
    city = next((n for n in nodes if n["__typename"] == "City"), None)
    if city is None:
        station = next((n for n in nodes if n["__typename"] == "Station" and n.get("type") == "AIRPORT"), None)
        if station is None:
            return None
        city = {"name": station["city"]["name"], "legacyId": station["city"]["legacyId"], "code": station["code"]}
    # aeroporturile orașului: din căutarea după numele orașului, plus grupările cunoscute (ex. Milano)
    stations = kiwi_places(s, city["name"])
    airports = [n["code"] for n in stations if n["__typename"] == "Station" and n.get("type") == "AIRPORT"
                and n["city"]["legacyId"] == city["legacyId"]]
    known = st.CITY_AIRPORTS.get(st.city_of(airports[0]) if airports else city.get("code", ""))
    if known:  # grupările din search_tickets.py au doar aeroporturile cu zboruri comerciale
        airports = known[1]
    if not airports and city.get("code"):
        airports = [city["code"]]
    return (city["name"], airports) if airports else None


# --------------------------------------------------------------------------- căutarea

def search_route(s, origins: list[str], destinations: list[str], min_days: int, max_days: int) -> tuple[list, list, list]:
    """Toate sursele, limitate la o rută.

    Întoarce (variante directe, variante cu escală dacă nu există directe, erori), sortate după preț."""
    st.ORIGINS = origins
    st.ROUTE_DESTINATIONS = set(destinations)
    st.KIWI_DESTINATIONS = ",".join(destinations)
    st.TRIP_MIN_DAYS, st.TRIP_MAX_DAYS = min_days, max_days
    st.LAST_DATE = st.LAST_OUTBOUND + dt.timedelta(days=max_days)

    rates = st.eur_rates(s)
    names: dict[str, str] = dict(st.AIRPORT_NAMES)
    flights, errors = [], []

    def run(sources) -> None:
        for source in sources:
            try:
                flights.extend(source(s, rates, names))
            except Exception as e:  # noqa: BLE001
                log.exception("Sursa %s a eșuat", source.__name__)
                errors.append(f"{source.__name__.removeprefix('search_')}: {e}")

    st.DIRECT_ONLY = True
    run(st.SOURCES)
    direct = st.all_trips(flights, names, direct_only=True)
    if direct:
        return direct, [], errors
    # niciun zbor direct: căutăm și variantele cu escală (prin Kiwi), ca să le arătăm separat
    st.DIRECT_ONLY = False
    run([st.search_kiwi])
    return [], st.all_trips(flights, names, direct_only=False), errors


def pick(trips: list, limit: int) -> list:
    """Cele mai ieftine variante, câte una pe pereche de date (lista e deja sortată după preț)."""
    seen, shown = set(), []
    for t in trips:
        key = (t.out.date, t.back.date if t.back else t.out.return_date)
        if key not in seen:
            seen.add(key)
            shown.append(t)
            if len(shown) == limit:
                break
    return shown


def format_reply(origin_name: str, dest_name: str, min_days: int, max_days: int,
                 direct: list, with_stops: list, errors: list) -> str:
    days = f"{min_days}" if min_days == max_days else f"{min_days}–{max_days}"
    route = f"{html.escape(origin_name)} → {html.escape(dest_name)}"
    lines = [f"✈️ <b>{route}</b>, dus-întors, {days} zile, doar zboruri directe\n"
             f"(plecare în următoarele {st.DAYS_AHEAD} zile)\n"]
    if direct:
        lines += [line.replace(" 🆕", "") for line in st.trip_lines(pick(direct, RESULTS), {})]
    else:
        lines.append(f"❌ <b>Nu există zboruri directe {route}</b> dus-întors de {days} zile "
                     f"în următoarele {st.DAYS_AHEAD} zile.")
        if with_stops:
            lines.append("Cele mai ieftine variante <b>cu escală</b>:")
            lines += [line.replace(" 🆕", "") for line in st.trip_lines(pick(with_stops, 3), {})]
        else:
            lines.append("Nu am găsit nici variante cu escală.")
    if errors:
        lines.append("⚠️ Unele surse n-au răspuns: " + html.escape("; ".join(errors)))
    return "\n\n".join(lines)


def answer(s, text: str) -> str:
    if plain(text) in ("/start", "/help", "help", "ajutor", "start"):
        return HELP
    parsed = parse_query(text)
    if not parsed:
        return "Nu am înțeles ruta. 🤔\n\n" + HELP
    origin, dest, min_days, max_days = parsed
    o = resolve_city(s, origin)
    d = resolve_city(s, dest)
    if not o:
        return f"Nu am găsit orașul „{html.escape(origin)}”."
    if not d:
        return f"Nu am găsit orașul „{html.escape(dest)}”."
    log.info("Caut %s %s → %s %s, %d-%d zile", o[0], o[1], d[0], d[1], min_days, max_days)
    return format_reply(o[0], d[0], min_days, max_days, *search_route(s, o[1], d[1], min_days, max_days))


# --------------------------------------------------------------------------- rutele directe (pentru meniu)

MENU_ORIGINS = list(st.ORIGINS)  # copiat înainte ca search_route să modifice st.ORIGINS


def route_catalog(s) -> dict[str, dict[str, dict]]:
    """Destinațiile spre care există zboruri, pe oraș: {"RMO": {"MIL": {"name": "Milano", "airports": {...}}}}."""
    names: dict[str, str] = dict(st.AIRPORT_NAMES)
    found: dict[str, set[str]] = {o: set() for o in MENU_ORIGINS}

    def collect(label: str, fn) -> None:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            log.warning("Rute %s: %s", label, e)

    def wizz():
        page = s.get("https://wizzair.com/en-gb").text
        api = "https://be.wizzair.com/" + re.search(r"be\.wizzair\.com/([0-9.]+)/Api", page).group(1) + "/Api"
        cities = {c["iata"]: c for c in s.get(f"{api}/asset/map?languageCode=en-gb").json()["cities"]}
        for c in cities.values():
            names.setdefault(c["iata"], c["shortName"].strip())
        for o in MENU_ORIGINS:
            for c in (cities.get(o) or {}).get("connections", []):
                if not cities.get(c["iata"], {}).get("isFakeStation"):
                    found[o].add(c["iata"])

    def ryanair():
        for o in MENU_ORIGINS:
            r = s.get(f"https://www.ryanair.com/api/views/locate/searchWidget/routes/en/airport/{o}")
            if r.ok:
                for rt in r.json():
                    names.setdefault(rt["arrivalAirport"]["code"], rt["arrivalAirport"]["city"]["name"])
                    found[o].add(rt["arrivalAirport"]["code"])

    def flyone():
        page = s.get("https://bookings.flyone.eu/FareView").text
        token = re.search(r'"token":"([^"]+)"', page).group(1)
        routes = s.post("https://api2.flyone.eu/api/Routes/get-routes", json={},
                        headers={"authorization": f"Bearer {token}", "origin": "https://bookings.flyone.eu"}).json()["routes"]
        for rt in routes:
            names.setdefault(rt["depCode"], rt["depAirportName"].strip())
        if "RMO" not in found:  # FlyOne are tarife publicate doar din Chișinău
            return
        headers = {"authorization": f"Bearer {token}", "origin": "https://bookings.flyone.eu"}
        for month in st.month_starts(st.TODAY, st.LAST_OUTBOUND):
            fares = s.post("https://api2.flyone.eu/api/search/get-route-fare", headers=headers, json={
                "token": token, "origin": "RMO", "travelDate": max(month, st.TODAY).isoformat(), "currencyCode": "EUR",
            }).json().get("destinationFares") or []
            # connType 1 = cu escală (ex. Moscova prin Erevan): nu apar în meniu
            found["RMO"].update(f["destination"] for f in fares if f.get("connType") != 1)

    def hisky():
        routes = st.hisky_routes(s)
        connecting = st.hisky_connecting(routes)  # ex. Chișinău → Cluj prin București
        for org, dst in routes:
            if org in found and (org, dst) not in connecting:
                found[org].add(dst)

    def skyup():
        for c in s.get("https://skyup.aero/api/v2/site/airport-connections?language=en&currency=EUR").json()["connections"]:
            o, d = c["originAirport"]["airportCode"], c["destinationAirport"]
            names.setdefault(d["airportCode"], d["cityName"])
            if o in found:
                found[o].add(d["airportCode"])

    for label, fn in (("Wizz", wizz), ("Ryanair", ryanair), ("FlyOne", flyone), ("HiSky", hisky), ("SkyUp", skyup)):
        collect(label, fn)
    # companiile căutate prin Kiwi (Turkish, Pegasus, LOT, Lufthansa...): doar dacă Kiwi găsește un zbor direct
    for o in MENU_ORIGINS:
        for d in (d.strip() for d in st.KIWI_DESTINATIONS.split(",")):
            if not d or d in found[o] or st.city_of(d) == st.city_of(o):
                continue
            try:
                if st.kiwi_has_direct(s, o, d):
                    found[o].add(d)
            except Exception as e:  # noqa: BLE001
                log.warning("Kiwi %s-%s: %s", o, d, e)

    catalog: dict[str, dict[str, dict]] = {}
    for o, airports in found.items():
        cities: dict[str, dict] = {}
        for a in airports:
            if a in st.CITY_AIRPORTS and a not in st.CITY_AIRPORTS[a][1]:
                continue  # cod de oraș (LON, MOW), nu de aeroport
            place = st.city_of(a)
            if place == st.city_of(o):
                continue
            entry = cities.setdefault(place, {"name": st.city_name(place, names), "airports": set()})
            entry["airports"].add(a)
            if entry["name"] == place:  # numele vine uneori doar de la un alt aeroport al orașului
                entry["name"] = names.get(a, place)
        catalog[o] = dict(sorted(cities.items(), key=lambda kv: plain(kv[1]["name"])))
    return catalog


# --------------------------------------------------------------------------- Telegram

def tg(s, method: str, **params) -> dict:
    r = s.post(f"https://api.telegram.org/bot{st.TELEGRAM_BOT_TOKEN}/{method}", json=params, timeout=60)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method}: {data}")
    return data["result"]


def send(s, text: str, keyboard: list | None = None) -> None:
    # Telegram are o limită de 4096 caractere pe mesaj
    chunks, current = [], ""
    for block in text.split("\n\n"):
        if current and len(current) + len(block) > 3900:
            chunks.append(current)
            current = ""
        current += block + "\n\n"
    chunks.append(current)
    for i, chunk in enumerate(chunks):
        extra = {"reply_markup": {"inline_keyboard": keyboard}} if keyboard and i == len(chunks) - 1 else {}
        tg(s, "sendMessage", chat_id=st.TELEGRAM_CHAT_ID, text=chunk, parse_mode="HTML",
           disable_web_page_preview=True, **extra)


def button(text: str, data: str) -> dict:
    return {"text": text, "callback_data": data}  # callback_data: maxim 64 de octeți


CITIES_PER_PAGE = 24
DAY_OPTIONS = [("2", 2, 2), ("3", 3, 3), ("4", 4, 4), ("5", 5, 5), ("6", 6, 6), ("7", 7, 7),
               ("10", 10, 10), ("14", 14, 14), ("2–4", 2, 4), ("2–7", 2, 7), ("5–10", 5, 10)]


def menu_origins() -> tuple[str, list]:
    keyboard = [[button(st.ORIGIN_NAMES.get(o, o), f"o:{o}") for o in MENU_ORIGINS]]
    return "✈️ <b>De unde zbori?</b>", keyboard


def menu_destinations(catalog: dict, origin: str, page: int) -> tuple[str, list]:
    cities = list(catalog.get(origin, {}).items())
    pages = max(1, -(-len(cities) // CITIES_PER_PAGE))
    page = min(max(page, 0), pages - 1)
    chunk = cities[page * CITIES_PER_PAGE:(page + 1) * CITIES_PER_PAGE]
    keyboard = [[button(info["name"][:20], f"c:{origin}:{place}") for place, info in chunk[i:i + 3]]
                for i in range(0, len(chunk), 3)]
    nav = []
    if page > 0:
        nav.append(button("◀️ Înapoi", f"p:{origin}:{page - 1}"))
    nav.append(button("🏠 Alt oraș", "start"))
    if page < pages - 1:
        nav.append(button("Înainte ▶️", f"p:{origin}:{page + 1}"))
    keyboard.append(nav)
    text = (f"✈️ <b>{st.ORIGIN_NAMES.get(origin, origin)} → unde?</b>\n"
            f"{len(cities)} destinații cu zboruri directe · pagina {page + 1}/{pages}")
    return text, keyboard


def menu_days(catalog: dict, origin: str, place: str) -> tuple[str, list]:
    name = catalog.get(origin, {}).get(place, {}).get("name", place)
    row = [button(label, f"s:{origin}:{place}:{lo}:{hi}") for label, lo, hi in DAY_OPTIONS]
    keyboard = [row[i:i + 4] for i in range(0, len(row), 4)]
    keyboard.append([button("◀️ Alt oraș destinație", f"o:{origin}")])
    return f"✈️ <b>{st.ORIGIN_NAMES.get(origin, origin)} → {html.escape(name)}</b>\nCâte zile stai?", keyboard


def search_from_menu(s, catalog: dict, origin: str, place: str, lo: int, hi: int) -> str:
    info = catalog.get(origin, {}).get(place)
    if not info:
        return "Nu mai găsesc această rută. Încearcă din nou cu /start."
    airports = sorted(info["airports"] | set(st.CITY_AIRPORTS.get(place, ("", []))[1]))
    return format_reply(st.ORIGIN_NAMES.get(origin, origin), info["name"], lo, hi,
                        *search_route(s, [origin], airports, lo, hi))


CATALOG_FILE = st.BASE_DIR / "routes_cache.json"


def load_catalog(s) -> dict:
    """Catalogul de rute, recalculat o dată pe zi (durează ~40 s) și păstrat în routes_cache.json."""
    try:
        cached = json.loads(CATALOG_FILE.read_text())
        if cached.get("date") == st.TODAY.isoformat():
            return {o: {p: {"name": v["name"], "airports": set(v["airports"])} for p, v in cities.items()}
                    for o, cities in cached["catalog"].items()}
    except Exception:  # noqa: BLE001
        pass
    catalog = route_catalog(s)
    CATALOG_FILE.write_text(json.dumps({"date": st.TODAY.isoformat(), "catalog": {
        o: {p: {"name": v["name"], "airports": sorted(v["airports"])} for p, v in cities.items()}
        for o, cities in catalog.items()}}, ensure_ascii=False))
    return catalog


class Session:
    """Ține catalogul de rute încărcat cât timp botul e activ."""

    def __init__(self, s):
        self.s = s
        self._catalog = None

    @property
    def catalog(self) -> dict:
        if self._catalog is None:
            self._catalog = load_catalog(self.s)
        return self._catalog

    def edit(self, msg: dict, text: str, keyboard: list | None = None) -> None:
        extra = {"reply_markup": {"inline_keyboard": keyboard}} if keyboard else {}
        tg(self.s, "editMessageText", chat_id=msg["chat"]["id"], message_id=msg["message_id"], text=text,
           parse_mode="HTML", **extra)

    def on_message(self, text: str) -> None:
        if parse_query(text):
            tg(self.s, "sendMessage", chat_id=st.TELEGRAM_CHAT_ID, text="🔎 Caut, durează 1–2 minute...")
            send(self.s, answer(self.s, text))
        else:  # /start, salut sau orice altceva: meniul cu butoane
            send(self.s, *menu_origins())

    def on_callback(self, cb: dict) -> None:
        data, msg = cb.get("data", ""), cb["message"]
        tg(self.s, "answerCallbackQuery", callback_query_id=cb["id"])
        parts = data.split(":")
        if data == "start":
            self.edit(msg, *menu_origins())
        elif parts[0] == "o":
            if self._catalog is None and not CATALOG_FILE.exists():
                self.edit(msg, "⏳ Verific ce zboruri directe există... (~1 minut, doar prima dată azi)")
            self.edit(msg, *menu_destinations(self.catalog, parts[1], 0))
        elif parts[0] == "p":
            self.edit(msg, *menu_destinations(self.catalog, parts[1], int(parts[2])))
        elif parts[0] == "c":
            self.edit(msg, *menu_days(self.catalog, parts[1], parts[2]))
        elif parts[0] == "s":
            origin, place, lo, hi = parts[1], parts[2], int(parts[3]), int(parts[4])
            name = self.catalog.get(origin, {}).get(place, {}).get("name", place)
            days = f"{lo}" if lo == hi else f"{lo}–{hi}"
            self.edit(msg, f"🔎 Caut <b>{st.ORIGIN_NAMES.get(origin, origin)} → {html.escape(name)}</b>, "
                           f"{days} zile... durează 1–2 minute.")
            send(self.s, search_from_menu(self.s, self.catalog, origin, place, lo, hi),
                 [[button("🔁 Altă căutare", "start")]])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--query", help="caută o rută și afișează rezultatul, fără Telegram")
    parser.add_argument("--menu", action="store_true", help="afișează destinațiile din meniu, fără Telegram")
    parser.add_argument("--idle-minutes", type=float, default=10,
                        help="cât rămâne activ după ultimul mesaj, ca să răspundă instant la butoane")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    s = st.new_session()

    if args.query:
        print(re.sub(r"<[^>]+>", "", html.unescape(answer(s, args.query))))
        return 0
    if args.menu:
        for o, cities in route_catalog(s).items():
            print(o, len(cities), ", ".join(f"{info['name']} ({','.join(sorted(info['airports']))})"
                                            for info in cities.values()))
        return 0

    if not (st.TELEGRAM_BOT_TOKEN and st.TELEGRAM_CHAT_ID):
        log.error("Setează TELEGRAM_BOT_TOKEN și TELEGRAM_CHAT_ID")
        return 1

    session = Session(s)
    offset = None
    last_activity = None
    started = time.monotonic()
    while True:
        # prima verificare e instantanee; dacă a fost activitate, așteptăm mesaje noi (long polling)
        wait = 0 if last_activity is None else 25
        params = {"timeout": wait, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            params["offset"] = offset
        updates = tg(s, "getUpdates", **params)
        if updates:
            offset = updates[-1]["update_id"] + 1
            # confirmăm imediat, ca o eroare să nu proceseze aceleași mesaje la nesfârșit
            tg(s, "getUpdates", offset=offset, timeout=0)
        for update in updates:
            msg = update.get("message") or {}
            cb = update.get("callback_query")
            chat_id = (cb["message"]["chat"]["id"] if cb else msg.get("chat", {}).get("id"))
            if str(chat_id) != str(st.TELEGRAM_CHAT_ID):
                continue  # botul răspunde doar proprietarului
            last_activity = time.monotonic()
            try:
                if cb:
                    log.info("Buton: %s", cb.get("data"))
                    session.on_callback(cb)
                elif msg.get("text"):
                    log.info("Mesaj: %s", msg["text"])
                    session.on_message(msg["text"])
            except Exception as e:  # noqa: BLE001
                log.exception("Eroare")
                send(s, f"⚠️ A apărut o eroare: {html.escape(str(e))}")
        if last_activity is None:
            log.info("Niciun mesaj nou")
            return 0
        idle = time.monotonic() - last_activity
        if idle > args.idle_minutes * 60 or time.monotonic() - started > 50 * 60:
            log.info("Închid sesiunea (inactiv %.0f s)", idle)
            return 0


if __name__ == "__main__":
    sys.exit(main())
