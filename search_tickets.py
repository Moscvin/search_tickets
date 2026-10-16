#!/usr/bin/env python3
"""Caută bilete de avion ieftine dus-întors din Chișinău, Iași și București în orice direcție
și trimite un rezumat pe Telegram (câte o listă pentru fiecare oraș de plecare).

Surse: Wizz Air, Ryanair, FlyOne, HiSky, SkyUp (direct de pe site-urile lor), Kiwi.com pentru
celelalte companii (Turkish, Pegasus, LOT, Lufthansa, TAROM...) și opțional Aviasales/Travelpayouts.

Pentru fiecare destinație se caută cea mai ieftină combinație dus + întors, cu întoarcerea
la TRIP_MIN_DAYS..TRIP_MAX_DAYS zile după plecare. Se pot combina companii diferite și aeroporturi
diferite din același oraș (ex. dus Wizz Air la Bergamo, întors FlyOne din Malpensa).

Rulare:  .venv/bin/python search_tickets.py            # caută și trimite pe Telegram
         .venv/bin/python search_tickets.py --dry-run  # doar afișează în terminal
"""

import argparse
import datetime as dt
import html
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.parse import urlencode

from curl_cffi import requests

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "last_prices.json"

log = logging.getLogger("tickets")


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env(BASE_DIR / ".env")


def env_int(name: str, default: int) -> int:
    return int(os.environ.get(name) or default)


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TRAVELPAYOUTS_TOKEN = os.environ.get("TRAVELPAYOUTS_TOKEN", "")
# Orașele de plecare (coduri de aeroport), în ordinea în care apar în mesaj
ORIGINS = [o.strip().upper() for o in (os.environ.get("ORIGINS") or "RMO,IAS,OTP").split(",") if o.strip()]
DAYS_AHEAD = env_int("DAYS_AHEAD", 180)         # plecarea: în următoarele N zile
TRIP_MIN_DAYS = env_int("TRIP_MIN_DAYS", 2)     # întoarcerea: minim N zile după plecare
TRIP_MAX_DAYS = env_int("TRIP_MAX_DAYS", 7)     # întoarcerea: maxim N zile după plecare
MAX_PRICE_EUR = float(os.environ.get("MAX_PRICE_EUR") or 0)  # preț total maxim, 0 = fără limită
TOP_N = env_int("TOP_N", 15)                    # câte destinații pentru fiecare oraș de plecare
# Doar zboruri directe (fără escală); DIRECT_ONLY=false le include și pe cele cu escală
DIRECT_ONLY = (os.environ.get("DIRECT_ONLY") or "true").lower() not in ("0", "false", "nu", "no")

# Dacă e setat (de bot.py), sursele caută doar spre aceste aeroporturi
ROUTE_DESTINATIONS: set[str] | None = None


def wanted(airport: str) -> bool:
    return ROUTE_DESTINATIONS is None or airport in ROUTE_DESTINATIONS


TODAY = dt.date.today()
LAST_OUTBOUND = TODAY + dt.timedelta(days=DAYS_AHEAD)
LAST_DATE = LAST_OUTBOUND + dt.timedelta(days=TRIP_MAX_DAYS)  # orizontul de căutare pentru întoarceri

ORIGIN_NAMES = {"RMO": "Chișinău", "IAS": "Iași", "OTP": "București", "BBU": "București", "SCV": "Suceava"}

# Aeroporturi din același oraș: dus și întors se pot combina între ele
# (ex. dus la Milano Bergamo cu Wizz, întors din Milano Malpensa cu FlyOne).
CITY_AIRPORTS = {
    "MIL": ("Milano", ["BGY", "MXP", "LIN"]),
    "LON": ("Londra", ["LTN", "LGW", "STN", "LHR", "SEN", "LCY"]),
    "PAR": ("Paris", ["CDG", "ORY", "BVA"]),
    "ROM": ("Roma", ["FCO", "CIA"]),
    "IST": ("Istanbul", ["IST", "SAW"]),
    "BRU": ("Bruxelles", ["BRU", "CRL"]),
    "FRA": ("Frankfurt", ["FRA", "HHN"]),
    "MOW": ("Moscova", ["SVO", "DME", "VKO"]),
    "STO": ("Stockholm", ["ARN", "NYO", "BMA"]),
    "DXB": ("Dubai", ["DXB", "DWC"]),
    "VCE": ("Veneția", ["VCE", "TSF"]),
    "WAW": ("Varșovia", ["WAW", "WMI"]),
    "BCN": ("Barcelona", ["BCN", "GRO", "REU"]),
    "OSL": ("Oslo", ["OSL", "TRF", "RYG"]),
    "BUH": ("București", ["OTP"]),
    "EAP": ("Basel", ["BSL", "MLH"]),
}
AIRPORT_CITY = {airport: city for city, (_, airports) in CITY_AIRPORTS.items() for airport in airports}

# Nume pentru aeroporturile pe care sursele le dau doar ca cod sau ca nume de aeroport
AIRPORT_NAMES = {
    "OMR": "Oradea", "CLJ": "Cluj-Napoca", "TSR": "Timișoara", "IAS": "Iași", "RMO": "Chișinău",
    "HAM": "Hamburg", "PMF": "Parma", "GYD": "Baku", "SSH": "Sharm El Sheikh", "BUS": "Batumi",
    "SBZ": "Sibiu", "CND": "Constanța", "SCV": "Suceava", "BCM": "Bacău", "CRA": "Craiova",
    "AYT": "Antalya", "BJV": "Bodrum", "ADB": "Izmir", "RIX": "Riga", "VNO": "Vilnius", "MUC": "München",
    "VIE": "Viena", "ZRH": "Zürich", "AMS": "Amsterdam", "HRG": "Hurghada", "ATH": "Atena", "CGN": "Köln",
    "STR": "Stuttgart", "TLV": "Tel Aviv", "JFK": "New York", "NBE": "Enfidha", "DWC": "Dubai",
}


def city_of(airport: str) -> str:
    return AIRPORT_CITY.get(airport, airport)


def city_name(city: str, names: dict) -> str:
    return CITY_AIRPORTS[city][0] if city in CITY_AIRPORTS else names.get(city, city)


@dataclass
class Flight:
    """Un zbor într-o direcție, între orașul de plecare `home` și o destinație."""
    airline: str
    origin: str
    destination: str
    date: str  # YYYY-MM-DD
    price_eur: float
    link: str
    home: str  # aeroportul de plecare al călătoriei (RMO / IAS / OTP)
    direct: bool = True
    return_date: str = ""  # setat doar pentru oferte dus-întors vândute împreună (Kiwi, Aviasales)

    @property
    def outbound(self) -> bool:
        return self.origin == self.home

    @property
    def airport(self) -> str:
        """Aeroportul de la celălalt capăt (destinația călătoriei)."""
        return self.destination if self.outbound else self.origin

    @property
    def place(self) -> str:
        return city_of(self.airport)


@dataclass
class Trip:
    home: str
    place: str
    place_name: str
    out: Flight
    back: Flight | None  # None când `out` e deja un bilet dus-întors
    total_eur: float
    link: str = ""  # link comun pentru dus-întors, dacă există


def new_session() -> requests.Session:
    return requests.Session(impersonate="chrome", timeout=30)


def eur_rates(s: requests.Session) -> dict:
    """Cursuri valutare față de EUR (câte unități dintr-o valută = 1 EUR)."""
    try:
        return s.get("https://open.er-api.com/v6/latest/EUR").json()["rates"]
    except Exception as e:  # noqa: BLE001
        log.warning("Nu am putut lua cursul valutar (%s), folosesc valori aproximative", e)
        return {"EUR": 1.0, "MDL": 20.0, "RON": 5.0, "USD": 1.1, "GBP": 0.85}


def to_eur(amount: float, currency: str, rates: dict) -> float:
    rate = rates.get(currency.upper())
    if not rate:
        raise ValueError(f"valută necunoscută: {currency}")
    return round(amount / rate, 2)


def in_range(date: str) -> bool:
    return TODAY.isoformat() <= date <= LAST_DATE.isoformat()


def month_starts(first: dt.date, last: dt.date) -> list[dt.date]:
    months, d = [], first.replace(day=1)
    while d <= last:
        months.append(d)
        d = (d + dt.timedelta(days=32)).replace(day=1)
    return months


def wizz_link(org: str, dst: str, date: str, ret: str = "null") -> str:
    return f"https://wizzair.com/en-gb/booking/select-flight/{org}/{dst}/{date}/{ret}/1/0/0/null"


# --------------------------------------------------------------------------- Wizz Air

def search_wizzair(s: requests.Session, rates: dict, names: dict) -> list[Flight]:
    home_page = s.get("https://wizzair.com/en-gb").text
    m = re.search(r"be\.wizzair\.com/([0-9.]+)/Api", home_page)
    if not m:
        raise RuntimeError("nu am găsit versiunea API Wizz Air")
    api = f"https://be.wizzair.com/{m.group(1)}/Api"
    headers = {"origin": "https://wizzair.com", "referer": "https://wizzair.com/"}

    cities = s.get(f"{api}/asset/map?languageCode=en-gb", headers=headers).json()["cities"]
    by_iata = {c["iata"]: c for c in cities}
    for c in cities:
        names.setdefault(c["iata"], c["shortName"].strip())

    def timetable(body: dict) -> dict:
        # Wizz răspunde cu 429/503 dacă facem cereri prea repede: așteptăm și reîncercăm
        for attempt in range(3):
            # după prima cerere Wizz setează cookie-ul RequestVerificationToken și îl cere înapoi ca header
            token = s.cookies.get("RequestVerificationToken", domain=".wizzair.com")
            req_headers = {**headers, "x-requestverificationtoken": token} if token else headers
            r = s.post(f"{api}/search/timetable", json=body, headers=req_headers)
            if r.status_code not in (429, 503):
                r.raise_for_status()
                return r.json()
            time.sleep(15 * (attempt + 1))
        r.raise_for_status()
        return {}

    flights = []
    for home in ORIGINS:
        if home not in by_iata:
            continue
        destinations = [
            c["iata"] for c in by_iata[home]["connections"]
            if not by_iata.get(c["iata"], {}).get("isFakeStation")  # sar peste "Londra (toate aeroporturile)" etc.
        ]
        destinations = [d for d in destinations if wanted(d)]
        log.info("Wizz Air: %d destinații din %s", len(destinations), home)
        consecutive_failures = 0
        for dest in destinations:
            if consecutive_failures >= 4:
                raise RuntimeError(f"Wizz Air blochează cererile ({consecutive_failures} eșecuri la rând)")
            start = TODAY
            while start <= LAST_DATE:
                end = min(start + dt.timedelta(days=41), LAST_DATE)  # Wizz acceptă maxim ~42 de zile pe cerere
                period = {"from": start.isoformat(), "to": end.isoformat()}
                body = {
                    "flightList": [{"departureStation": home, "arrivalStation": dest, **period},
                                   {"departureStation": dest, "arrivalStation": home, **period}],
                    "priceType": "regular", "adultCount": 1, "childCount": 0, "infantCount": 0,
                }
                try:
                    data = timetable(body)
                    consecutive_failures = 0
                    for f in (data.get("outboundFlights") or []) + (data.get("returnFlights") or []):
                        price = f.get("price") or {}
                        if not price.get("amount") or f.get("priceType") == "soldOut":
                            continue
                        date = f["departureDate"][:10]
                        org, dst = f["departureStation"], f["arrivalStation"]
                        flights.append(Flight(
                            airline="Wizz Air", origin=org, destination=dst, date=date, home=home,
                            price_eur=to_eur(price["amount"], price["currencyCode"], rates),
                            link=wizz_link(org, dst, date),
                        ))
                except Exception as e:  # noqa: BLE001
                    consecutive_failures += 1
                    log.warning("Wizz Air %s-%s: %s", home, dest, e)
                    break
                start = end + dt.timedelta(days=1)
                time.sleep(2)
    log.info("Wizz Air: %d prețuri", len(flights))
    return flights


# --------------------------------------------------------------------------- Ryanair

def ryanair_link(org: str, dst: str, date: str, back: str = "") -> str:
    return "https://www.ryanair.com/gb/en/trip/flights/select?" + urlencode({
        "adults": 1, "teens": 0, "children": 0, "infants": 0, "dateOut": date, "dateIn": back,
        "isConnectedFlight": "false", "isReturn": "true" if back else "false", "discount": 0,
        "originIata": org, "destinationIata": dst,
    })


def search_ryanair(s: requests.Session, rates: dict, names: dict) -> list[Flight]:
    flights = []
    for home in ORIGINS:
        r = s.get(f"https://www.ryanair.com/api/views/locate/searchWidget/routes/en/airport/{home}")
        if r.status_code == 404:  # Ryanair nu zboară din acest aeroport (ex. Chișinău)
            continue
        r.raise_for_status()
        routes = [rt["arrivalAirport"] for rt in r.json()
                  if rt.get("operator") == "FR" and wanted(rt["arrivalAirport"]["code"])]
        for a in routes:
            names.setdefault(a["code"], a["city"]["name"])
        log.info("Ryanair: %d destinații din %s", len(routes), home)
        for a in routes:
            dest = a["code"]
            # cel mai ieftin dus-întors de TRIP_MIN_DAYS..TRIP_MAX_DAYS zile pe această rută
            params = {
                "departureAirportIataCode": home, "arrivalAirportIataCode": dest,
                "outboundDepartureDateFrom": TODAY.isoformat(), "outboundDepartureDateTo": LAST_OUTBOUND.isoformat(),
                "inboundDepartureDateFrom": TODAY.isoformat(), "inboundDepartureDateTo": LAST_DATE.isoformat(),
                "durationFrom": TRIP_MIN_DAYS, "durationTo": TRIP_MAX_DAYS,
                "currency": "EUR", "market": "en-gb", "adultPaxCount": 1,
            }
            try:
                rr = s.get("https://services-api.ryanair.com/farfnd/v4/roundTripFares", params=params)
                rr.raise_for_status()
                fares = rr.json().get("fares") or []
            except Exception as e:  # noqa: BLE001
                log.warning("Ryanair %s-%s: %s", home, dest, e)
                continue
            # cele două zboruri intră separat, ca să poată fi combinate și cu alte companii
            for fare in fares:
                for leg in (fare["outbound"], fare["inbound"]):
                    org, dst = leg["departureAirport"]["iataCode"], leg["arrivalAirport"]["iataCode"]
                    date = leg["departureDate"][:10]
                    flights.append(Flight(
                        airline="Ryanair", origin=org, destination=dst, date=date, home=home,
                        price_eur=to_eur(leg["price"]["value"], leg["price"]["currencyCode"], rates),
                        link=ryanair_link(org, dst, date),
                    ))
            time.sleep(0.3)
    log.info("Ryanair: %d prețuri", len(flights))
    return flights


# --------------------------------------------------------------------------- FlyOne

def search_flyone(s: requests.Session, rates: dict, names: dict) -> list[Flight]:
    page = s.get("https://bookings.flyone.eu/FareView").text
    m = re.search(r'"token":"([^"]+)"', page)
    if not m:
        raise RuntimeError("nu am găsit token-ul FlyOne")
    token = m.group(1)
    api = "https://api2.flyone.eu/api"
    headers = {"origin": "https://bookings.flyone.eu", "referer": "https://bookings.flyone.eu/",
               "authorization": f"Bearer {token}"}

    flyone_names: dict[str, str] = {}  # pagina FareCalendar nu se deschide fără numele orașelor
    try:
        routes = s.post(f"{api}/Routes/get-routes", json={}, headers=headers).json().get("routes") or []
        for rt in routes:
            flyone_names[rt["depCode"]] = rt["depAirportName"].strip()
            names.setdefault(rt["depCode"], rt["depAirportName"].strip())
    except Exception as e:  # noqa: BLE001
        log.warning("FlyOne: nu am putut lua lista de aeroporturi: %s", e)

    def link(org: str, dst: str, date: str) -> str:
        return "https://bookings.flyone.eu/FareCalendar?" + urlencode({
            "depCityName": flyone_names.get(org, org), "depCity": org,
            "arrCityName": flyone_names.get(dst, dst), "arrCity": dst,
            "startDate": date, "endDate": date,
        })

    months = month_starts(TODAY, LAST_DATE)
    flights = []
    for home in ORIGINS:
        # 1) destinațiile care au tarife (cel mai mic preț pe destinație, pe lună)
        destinations: dict[str, bool] = {}  # destinație -> zbor direct (connType 1 = cu escală, ex. Moscova)
        for month in months:
            body = {"token": token, "origin": home, "travelDate": max(month, TODAY).isoformat(), "currencyCode": "EUR"}
            r = s.post(f"{api}/search/get-route-fare", json=body, headers=headers)
            r.raise_for_status()
            for f in r.json().get("destinationFares") or []:
                if wanted(f["destination"]):
                    destinations.setdefault(f["destination"], f.get("connType") != 1)
            time.sleep(0.3)
        if not destinations:
            continue
        log.info("FlyOne: %d destinații din %s", len(destinations), home)

        # 2) calendarul de prețuri pe zile, dus și întors, pentru fiecare destinație și lună
        for dest, direct in destinations.items():
            for month in months:
                travel = max(month, TODAY).isoformat()
                body = {
                    "currencyCode": "EUR",
                    "searchCriteria": {
                        "paxInfo": [{"paxType": 1, "paxKey": "Adult1"}],
                        "journeyInfo": {"journeyType": 2, "routeInfo": [
                            {"depCity": home, "arrCity": dest, "travelDate": travel},
                            {"depCity": dest, "arrCity": home, "travelDate": travel},
                        ]},
                    },
                    "qsParams": [{"key": "", "value": ""}], "languageCode": "en-GB", "currency": "EUR",
                    "paxInfoId": 0, "reservationType": 0, "userAgent": "Mozilla/5.0", "personKey": "",
                }
                try:
                    r = s.post(f"{api}/search/fare-calendar-schedule", json=body, headers=headers)
                    r.raise_for_status()
                    schedule = r.json().get("flightSchedule") or []
                except Exception as e:  # noqa: BLE001
                    log.warning("FlyOne %s-%s %s: %s", home, dest, travel[:7], e)
                    continue
                for direction in schedule:
                    org, dst = (home, dest) if direction["direction"] == 1 else (dest, home)
                    for mon in direction["month"]:
                        for day in mon["days"]:
                            price = float(day.get("price") or 0)
                            if not day.get("isFlightAvailable") or day.get("isSoldOut") or price <= 0:
                                continue
                            date = f"{direction['year']}-{int(mon['month']):02d}-{int(day['date']):02d}"
                            if not in_range(date):
                                continue
                            flights.append(Flight(
                                airline="FlyOne", origin=org, destination=dst, date=date, home=home,
                                price_eur=to_eur(price, direction.get("currency") or "EUR", rates),
                                link=link(org, dst, date), direct=direct,
                            ))
                time.sleep(0.3)
    # răspunsurile pentru luni vecine se suprapun: păstrăm o singură intrare pe zbor
    flights = list({(f.origin, f.destination, f.date): f for f in flights}.values())
    log.info("FlyOne: %d prețuri", len(flights))
    return flights


# --------------------------------------------------------------------------- HiSky

def hisky_routes(s: requests.Session) -> dict[tuple[str, str], list[dict]]:
    """Pagina principală HiSky conține calendarul de prețuri: var prices_RMOSTN = JSON.parse(JSON.stringify([...]))."""
    page = s.get("https://hisky.aero/").text
    blocks = re.findall(r"var prices_([A-Z]{3})([A-Z]{3})\s*=\s*JSON\.parse\(\s*JSON\.stringify\((\[.*?\])\)\s*\)",
                        page, re.S)
    return {(org, dst): json.loads(raw) for org, dst, raw in blocks}


def hisky_connecting(routes: dict[tuple[str, str], list[dict]]) -> set[tuple[str, str]]:
    """Rutele HiSky care sunt de fapt cu escală (ex. Chișinău → Cluj prin București).

    Un bilet A → B cu escală în H pleacă la aceeași oră ca zborul A → H, în aceleași zile."""
    connecting = set()
    for (a, b), fares in routes.items():
        departures = {(f["date"], f["departure"]) for f in fares}
        for (a2, hub) in routes:
            if a2 != a or hub == b or (hub, b) not in routes:
                continue
            via_hub = {(f["date"], f["departure"]) for f in routes[(a, hub)]}
            if departures and len(departures & via_hub) > len(departures) / 2:
                connecting.add((a, b))
                break
    return connecting


def search_hisky(s: requests.Session, rates: dict, names: dict) -> list[Flight]:
    routes = hisky_routes(s)
    connecting = hisky_connecting(routes)
    flights = []
    for (org, dst), fares in routes.items():
        for home in ORIGINS:
            if home not in (org, dst) or not wanted(dst if org == home else org):
                continue
            for f in fares:
                price = float(str(f["price"]).replace(",", ""))
                date = dt.datetime.strptime(f["date"], "%d.%m.%Y").date()
                if price <= 0 or not in_range(date.isoformat()):
                    continue
                link = ("https://booking.hisky.aero/VARS/Public/deeplink.aspx?TripType=oneway&UserLanguage=ro"
                        f"&Adult=1&Child=0&InfantLap=0&UserCurrency=EUR&Origin1={org}&Destination1={dst}"
                        f"&DepartureDate1={date:%d.%m.%Y}")
                flights.append(Flight(
                    airline="HiSky", origin=org, destination=dst, date=date.isoformat(), home=home,
                    price_eur=to_eur(price, "EUR", rates), link=link, direct=(org, dst) not in connecting,
                ))
    log.info("HiSky: %d prețuri", len(flights))
    return flights


# --------------------------------------------------------------------------- SkyUp

def skyup_link(org: str, dst: str, date: str, back: str = "") -> str:
    params = {"departure_city": org, "arrival_city": dst, "date_forward": date}
    if back:
        params["date_backward"] = back
    return "https://skyup.aero/en/booking/flights?" + urlencode({**params, "adults": 1, "children": 0, "infants": 0})


def search_skyup(s: requests.Session, rates: dict, names: dict) -> list[Flight]:
    headers = {"origin": "https://skyup.aero", "referer": "https://skyup.aero/en"}
    connections = s.get("https://skyup.aero/api/v2/site/airport-connections?language=en&currency=EUR",
                        headers=headers).json()["connections"]
    flights = []
    for home in ORIGINS:
        destinations = []
        for c in connections:
            if c["originAirport"]["airportCode"] == home and wanted(c["destinationAirport"]["airportCode"]):
                dest = c["destinationAirport"]
                destinations.append(dest["airportCode"])
                names.setdefault(dest["airportCode"], dest["cityName"])
        if not destinations:
            continue
        log.info("SkyUp: %d destinații din %s", len(destinations), home)
        for dest in destinations:
            # un singur apel întoarce calendarul pe zile pentru ambele direcții
            body = {
                "AirlineCode": "U5", "OriginCityCode": home, "DestinationCityCode": dest,
                "Date": TODAY.isoformat(), "EndDate": LAST_DATE.isoformat(), "needReturnFlights": True,
                "originAndDestIsAirports": True, "TotalPaxCount": 1, "DayRange": 1,
                "PaxCountDetails": [{"PaxType": "ADULT", "PaxCount": 1}], "PointOfPurchase": "PL",
            }
            try:
                r = s.post("https://skyup.aero/api/site/calendar?language=en&currency=EUR", json=body, headers=headers)
                r.raise_for_status()
                data = r.json()
            except Exception as e:  # noqa: BLE001
                log.warning("SkyUp %s-%s: %s", home, dest, e)
                continue
            for key, org, dst in (("OnwardBestFareDetails", home, dest), ("ReturnBestFareDetails", dest, home)):
                for f in data.get(key) or []:
                    date = f["flight_date"][:10]
                    if f.get("is_sold_out") or not f.get("display_amount") or not in_range(date):
                        continue
                    flights.append(Flight(
                        airline="SkyUp", origin=org, destination=dst, date=date, home=home,
                        price_eur=to_eur(float(f["display_amount"]), f.get("currency_code") or "EUR", rates),
                        link=skyup_link(org, dst, date),
                    ))
            time.sleep(0.3)
    log.info("SkyUp: %d prețuri", len(flights))
    return flights


# --------------------------------------------------------------------------- Kiwi.com

# Orașe deservite de companiile fără scraper propriu: Turkish, Pegasus, SunExpress, LOT, Lufthansa,
# Austrian, airBaltic, Eurowings, Aegean, TAROM, Transavia, flydubai, AZAL, Israir...
# Kiwi caută acolo toate companiile, inclusiv combinații (ex. dus cu LOT, întors cu Wizz Air).
KIWI_DESTINATIONS = os.environ.get("KIWI_DESTINATIONS") or (
    "IST,SAW,AYT,BJV,ADB,WAW,FRA,MUC,VIE,RIX,VNO,GYD,DXB,ATH,OTP,ORY,CGN,STR,TLV,SSH,HRG,ZRH,AMS"
)

KIWI_QUERY = """query SearchReturnItinerariesQuery($search: SearchReturnInput, $filter: ItinerariesFilterInput,
  $options: ItinerariesOptionsInput) {
  returnItineraries(search: $search, filter: $filter, options: $options) {
    ... on Itineraries { itineraries { ... on ItineraryReturn {
      price { amount }
      outbound { sectorSegments { segment { source { localTime station { code } }
        destination { station { code city { name } } } carrier { name } } } }
      inbound { sectorSegments { segment { source { localTime station { code } } carrier { name } } } }
      bookingOptions { edges { node { bookingUrl } } }
    } } }
    ... on AppError { error: message }
  }
}"""


def kiwi_has_direct(s: requests.Session, home: str, dest: str) -> bool:
    """Există vreun zbor direct dus-întors home ↔ dest (orice companie) în următoarele DAYS_AHEAD zile?"""
    variables = {
        "search": {
            "itinerary": {
                "source": {"ids": [f"Station:airport:{home}"]},
                "destination": {"ids": [f"Station:airport:{dest}"]},
                "outboundDepartureDate": {"start": f"{TODAY + dt.timedelta(days=1)}T00:00:00",
                                          "end": f"{LAST_OUTBOUND}T23:59:59"},
                "inboundDepartureDate": {"start": f"{TODAY + dt.timedelta(days=1)}T00:00:00",
                                         "end": f"{LAST_OUTBOUND + dt.timedelta(days=30)}T23:59:59"},
            },
            "passengers": {"adults": 1, "children": 0, "infants": 0, "adultsHoldBags": [0],
                           "adultsHandBags": [0], "childrenHoldBags": [], "childrenHandBags": []},
            "cabinClass": {"cabinClass": "ECONOMY", "applyMixedClasses": False},
        },
        "filter": {"transportTypes": ["FLIGHT"], "contentProviders": ["KIWI"], "limit": 1, "maxStopsCount": 0},
        "options": {"sortBy": "PRICE", "currency": "eur", "locale": "en", "market": "md", "partner": "skypicker",
                    "partnerMarket": "md", "storeSearch": False, "searchStrategy": "REDUCED", "abTestInput": {}},
    }
    r = s.post("https://api.skypicker.com/umbrella/v2/graphql?featureName=SearchReturnItinerariesQuery",
               json={"query": KIWI_QUERY, "variables": variables},
               headers={"origin": "https://www.kiwi.com", "referer": "https://www.kiwi.com/"}, timeout=60)
    r.raise_for_status()
    result = (r.json().get("data") or {}).get("returnItineraries") or {}
    return bool(result.get("itineraries"))


def search_kiwi(s: requests.Session, rates: dict, names: dict) -> list[Flight]:
    headers = {"origin": "https://www.kiwi.com", "referer": "https://www.kiwi.com/"}
    destinations = [d.strip() for d in KIWI_DESTINATIONS.split(",") if d.strip()]
    flights = []
    for home in ORIGINS:
        for dest in destinations:
            if city_of(dest) == city_of(home):
                continue
            variables = {
                "search": {
                    "itinerary": {
                        "source": {"ids": [f"Station:airport:{home}"]},
                        "destination": {"ids": [f"Station:airport:{dest}"]},
                        "outboundDepartureDate": {"start": f"{TODAY + dt.timedelta(days=1)}T00:00:00",
                                                  "end": f"{LAST_OUTBOUND}T23:59:59"},
                        "inboundDepartureDate": {"start": f"{TODAY + dt.timedelta(days=1)}T00:00:00",
                                                 "end": f"{LAST_DATE}T23:59:59"},
                        "nightsCount": {"start": TRIP_MIN_DAYS, "end": TRIP_MAX_DAYS},
                    },
                    "passengers": {"adults": 1, "children": 0, "infants": 0, "adultsHoldBags": [0],
                                   "adultsHandBags": [0], "childrenHoldBags": [], "childrenHandBags": []},
                    "cabinClass": {"cabinClass": "ECONOMY", "applyMixedClasses": False},
                },
                "filter": {"allowDifferentStationConnection": True, "enableSelfTransfer": True,
                           "enableThrowAwayTicketing": False, "enableTrueHiddenCity": False,
                           "transportTypes": ["FLIGHT"], "contentProviders": ["KIWI"], "limit": 10,
                           **({"maxStopsCount": 0} if DIRECT_ONLY else {})},
                "options": {"sortBy": "PRICE", "mergePriceDiffRule": "INCREASED", "currency": "eur",
                            "locale": "en", "market": "md", "partner": "skypicker", "partnerMarket": "md",
                            "storeSearch": False, "searchStrategy": "REDUCED", "abTestInput": {}},
            }
            try:
                r = s.post("https://api.skypicker.com/umbrella/v2/graphql?featureName=SearchReturnItinerariesQuery",
                           json={"query": KIWI_QUERY, "variables": variables}, headers=headers, timeout=60)
                r.raise_for_status()
                result = (r.json().get("data") or {}).get("returnItineraries") or {}
                if result.get("error"):
                    raise RuntimeError(result["error"])
            except Exception as e:  # noqa: BLE001
                log.warning("Kiwi %s-%s: %s", home, dest, e)
                continue
            for it in result.get("itineraries") or []:
                out = [x["segment"] for x in it["outbound"]["sectorSegments"]]
                back = [x["segment"] for x in it["inbound"]["sectorSegments"]]
                edges = it["bookingOptions"]["edges"]
                if not out or not back or not edges:
                    continue
                arrival = out[-1]["destination"]["station"]
                names.setdefault(arrival["code"], arrival["city"]["name"])
                carriers = list(dict.fromkeys(seg["carrier"]["name"] for seg in out + back))
                flights.append(Flight(
                    airline=" + ".join(carriers) + " (Kiwi)", origin=home, destination=arrival["code"],
                    date=out[0]["source"]["localTime"][:10], home=home,
                    price_eur=to_eur(float(it["price"]["amount"]), "EUR", rates),
                    link="https://www.kiwi.com" + edges[0]["node"]["bookingUrl"],
                    direct=len(out) == 1 and len(back) == 1,
                    return_date=back[0]["source"]["localTime"][:10],
                ))
            time.sleep(0.5)
    log.info("Kiwi: %d oferte dus-întors", len(flights))
    return flights


# --------------------------------------------------------------------------- Aviasales (opțional)

def search_aviasales(s: requests.Session, rates: dict, names: dict) -> list[Flight]:
    """Necesită TRAVELPAYOUTS_TOKEN gratuit. Întoarce oferte dus-întors deja combinate."""
    if not TRAVELPAYOUTS_TOKEN:
        log.info("Aviasales: sărit (nu e setat TRAVELPAYOUTS_TOKEN)")
        return []
    flights = []
    for home in ORIGINS:
        for month in month_starts(TODAY, LAST_OUTBOUND):
            r = s.get("https://api.travelpayouts.com/aviasales/v3/prices_for_dates", params={
                "origin": home, "departure_at": month.strftime("%Y-%m"), "one_way": "false", "direct": "false",
                "sorting": "price", "currency": "eur", "limit": 1000, "token": TRAVELPAYOUTS_TOKEN,
            })
            r.raise_for_status()
            for f in r.json().get("data") or []:
                date = f["departure_at"][:10]
                ret = (f.get("return_at") or "")[:10]
                if not ret or not in_range(date) or not wanted(f.get("destination_airport") or f["destination"]):
                    continue
                flights.append(Flight(
                    airline=f"Aviasales ({f.get('airline', '?')})", origin=home,
                    destination=f.get("destination_airport") or f["destination"], date=date, home=home,
                    price_eur=to_eur(float(f["price"]), "EUR", rates),
                    link="https://www.aviasales.com" + f["link"] if f.get("link") else "https://www.aviasales.com",
                    direct=f.get("transfers", 0) == 0 and f.get("return_transfers", 0) == 0,
                    return_date=ret,
                ))
            time.sleep(0.4)
    log.info("Aviasales: %d oferte dus-întors", len(flights))
    return flights


SOURCES = [search_wizzair, search_ryanair, search_flyone, search_hisky, search_skyup, search_kiwi, search_aviasales]


# --------------------------------------------------------------------------- combinare dus + întors

def stay_ok(out_date: str, back_date: str) -> bool:
    days = (dt.date.fromisoformat(back_date) - dt.date.fromisoformat(out_date)).days
    return TRIP_MIN_DAYS <= days <= TRIP_MAX_DAYS


def all_trips(flights: list[Flight], names: dict, direct_only: bool | None = None) -> list[Trip]:
    """Toate combinațiile dus + întors valide, de la cea mai ieftină.

    Dusul și întorsul pot fi cu companii diferite și pe aeroporturi diferite din același oraș."""
    # cel mai ieftin zbor pe (plecare, oraș, direcție, aeroport, zi) - reduce mult numărul de combinații
    cheapest: dict[tuple, Flight] = {}
    trips: list[Trip] = []

    def add(trip: Trip) -> None:
        if not MAX_PRICE_EUR or trip.total_eur <= MAX_PRICE_EUR:
            trips.append(trip)

    if direct_only is None:
        direct_only = DIRECT_ONLY
    for f in flights:
        if f.place == city_of(f.home):  # ex. Otopeni → Băneasa
            continue
        if direct_only and not f.direct:
            continue
        if f.return_date:  # ofertă dus-întors gata făcută
            if f.date <= LAST_OUTBOUND.isoformat() and stay_ok(f.date, f.return_date):
                add(Trip(f.home, f.place, city_name(f.place, names), f, None, f.price_eur))
            continue
        if f.outbound and f.date > LAST_OUTBOUND.isoformat():
            continue
        key = (f.home, f.place, f.outbound, f.airport, f.date)
        if key not in cheapest or f.price_eur < cheapest[key].price_eur:
            cheapest[key] = f

    outbound: dict[tuple, list[Flight]] = {}
    inbound: dict[tuple, list[Flight]] = {}
    for (home, place, is_out, _, _), f in cheapest.items():
        (outbound if is_out else inbound).setdefault((home, place), []).append(f)

    for (home, place), outs in outbound.items():
        backs = inbound.get((home, place), [])
        for out in outs:
            for back in backs:
                if not stay_ok(out.date, back.date):
                    continue
                link = ""
                if out.airline == back.airline and out.airport == back.airport:
                    if out.airline == "Wizz Air":
                        link = wizz_link(home, out.airport, out.date, back.date)
                    elif out.airline == "SkyUp":
                        link = skyup_link(home, out.airport, out.date, back.date)
                    elif out.airline == "Ryanair":
                        link = ryanair_link(home, out.airport, out.date, back.date)
                add(Trip(home, place, city_name(place, names), out, back,
                         round(out.price_eur + back.price_eur, 2), link))
    return sorted(trips, key=lambda t: t.total_eur)


def cheapest_trips(flights: list[Flight], names: dict) -> list[Trip]:
    """Cea mai ieftină combinație dus + întors pentru fiecare (oraș de plecare, oraș destinație)."""
    best: dict[tuple, Trip] = {}
    for trip in all_trips(flights, names):
        best.setdefault((trip.home, trip.place), trip)  # lista e deja sortată după preț
    return sorted(best.values(), key=lambda t: t.total_eur)


# --------------------------------------------------------------------------- mesaj Telegram

WEEKDAYS = ["Lu", "Ma", "Mi", "Jo", "Vi", "Sâ", "Du"]


def fmt_date(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d:%d.%m} ({WEEKDAYS[d.weekday()]})"


def leg_line(arrow: str, f: Flight) -> str:
    stop = "" if f.direct else " · cu escală"
    return (f"   {arrow} {fmt_date(f.date)} · {f.origin} → {f.destination} · {html.escape(f.airline)}{stop} · "
            f"€{f.price_eur:.0f} · "
            f"<a href=\"{html.escape(f.link)}\">bilet</a>")


def trip_lines(top: list[Trip], previous: dict) -> list[str]:
    lines = []
    for i, t in enumerate(top, 1):
        old = previous.get(f"{t.home}:{t.place}")
        trend = ""
        if old is None:
            trend = " 🆕"
        elif t.total_eur < old - 0.5:
            trend = f" 🔻 (era €{old:.0f})"
        nights = (dt.date.fromisoformat(t.back.date if t.back else t.out.return_date)
                  - dt.date.fromisoformat(t.out.date)).days
        home_name = html.escape(ORIGIN_NAMES.get(t.home, t.home))
        line = (f"{i}. <b>{home_name} → {html.escape(t.place_name)}</b> — "
                f"<b>€{t.total_eur:.0f} dus-întors</b>{trend} · {nights} nopți\n")
        if t.back:
            line += leg_line("🛫", t.out) + "\n" + leg_line("🛬", t.back)
            if t.link:
                line += f"\n   🔗 <a href=\"{html.escape(t.link)}\">Rezervă dus-întors</a>"
        else:
            stop = "" if t.out.direct else " · cu escală"
            line += (f"   🛫 {fmt_date(t.out.date)} · {t.home} → {t.out.airport}\n"
                     f"   🛬 {fmt_date(t.out.return_date)} · {t.out.airport} → {t.home}\n"
                     f"   ✈️ {html.escape(t.out.airline)}{stop}\n"
                     f"   🔗 <a href=\"{html.escape(t.out.link)}\">Rezervă</a>")
        lines.append(line)
    return lines


def format_messages(trips: list[Trip], previous: dict, errors: list[str]) -> list[str]:
    """Câte o listă pentru fiecare oraș de plecare; mesajele sunt împărțite la limita Telegram."""
    blocks = [f"✈️ <b>Bilete ieftine dus-întors</b> — {TODAY:%d.%m.%Y}\n"
              f"(plecare în următoarele {DAYS_AHEAD} zile, întoarcere după {TRIP_MIN_DAYS}–{TRIP_MAX_DAYS} zile"
              f"{', doar zboruri directe' if DIRECT_ONLY else ''})\n"]
    for home in ORIGINS:
        top = [t for t in trips if t.home == home][:TOP_N]
        blocks.append(f"\n🏠 <b>Din {html.escape(ORIGIN_NAMES.get(home, home))} ({home})</b>\n")
        lines = trip_lines(top, previous)
        blocks += ["\n" + line + "\n" for line in lines] or ["\nNu am găsit zboruri în criteriile setate.\n"]
    if errors:
        blocks.append("\n⚠️ Erori: " + html.escape("; ".join(errors)))

    # Telegram are o limită de 4096 caractere pe mesaj
    messages, current = [], ""
    for block in blocks:
        if current and len(current) + len(block) > 3900:
            messages.append(current)
            current = ""
        current += block
    messages.append(current)
    return messages


def send_telegram(s: requests.Session, text: str) -> None:
    r = s.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
        "chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True,
    })
    if not r.ok:
        raise RuntimeError(f"Telegram a răspuns {r.status_code}: {r.text}")


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:  # noqa: BLE001
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="nu trimite pe Telegram, doar afișează")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not args.dry_run and not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        log.error("Setează TELEGRAM_BOT_TOKEN și TELEGRAM_CHAT_ID în .env (sau rulează cu --dry-run)")
        return 1

    s = new_session()
    rates = eur_rates(s)
    names: dict[str, str] = dict(AIRPORT_NAMES)
    flights: list[Flight] = []
    errors: list[str] = []
    for source in SOURCES:
        name = source.__name__.removeprefix("search_")
        try:
            flights += source(s, rates, names)
        except Exception as e:  # noqa: BLE001
            log.exception("Sursa %s a eșuat", name)
            errors.append(f"{name}: {e}")

    ranked = cheapest_trips(flights, names)
    previous = load_state()
    messages = format_messages(ranked, previous, errors)

    if args.dry_run:
        for msg in messages:
            print(re.sub(r"<[^>]+>", "", html.unescape(msg)))
    else:
        for msg in messages:
            send_telegram(s, msg)
        log.info("Trimis pe Telegram (%d mesaje)", len(messages))
        STATE_FILE.write_text(json.dumps({f"{t.home}:{t.place}": t.total_eur for t in ranked}, indent=1))

    (BASE_DIR / "last_results.json").write_text(json.dumps([asdict(t) for t in ranked], indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
