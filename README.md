# Bilete ieftine din Chișinău → Telegram

Caută zilnic cele mai ieftine bilete **dus-întors** din Chișinău (RMO) în orice direcție și trimite pe Telegram
top destinații cu preț total, datele dus/întors, companie și link de rezervare.
Plecarea în următoarele 180 de zile, întoarcerea după 2–7 zile.

Surse:
- **Wizz Air**: API-ul site-ului (toate rutele din RMO)
- **FlyOne**: calendarul de tarife
- **HiSky**: prețurile de pe pagina principală
- **SkyUp**: calendarul de tarife
- **Kiwi.com**: restul companiilor (Turkish, Pegasus, AJet, SunExpress, LOT, Lufthansa, Austrian, airBaltic,
  Eurowings, Aegean, TAROM, Transavia, flydubai, AZAL...) pentru orașele din `KIWI_DESTINATIONS`
- **Aviasales** (opțional, cu `TRAVELPAYOUTS_TOKEN` gratuit)

Dusul și întorsul se pot combina între companii și între aeroporturile aceluiași oraș
(ex. dus cu Wizz Air la Milano Bergamo, întors cu FlyOne din Milano Malpensa).

## 1. Bot Telegram
1. Scrie lui [@BotFather](https://t.me/BotFather) → `/newbot` → primești **token-ul**.
2. Scrie-i ceva botului tău, apoi deschide `https://api.telegram.org/bot<TOKEN>/getUpdates`
   și ia `"chat":{"id": ...}` → acesta e **chat id-ul**.

## 2. GitHub Actions (rulează zilnic, gratuit)
1. Urcă proiectul într-un repo pe GitHub.
2. **Settings → Secrets and variables → Actions → New repository secret**:
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (și opțional `TRAVELPAYOUTS_TOKEN`).
3. Opțional, la tab-ul **Variables**: `DAYS_AHEAD`, `TRIP_MIN_DAYS`, `TRIP_MAX_DAYS`, `MAX_PRICE_EUR`, `TOP_N`, `KIWI_DESTINATIONS`.
4. **Actions → Bilete ieftine din Chișinău → Run workflow** ca să testezi imediat.

Ora rulării se schimbă în [.github/workflows/search_tickets.yml](.github/workflows/search_tickets.yml) (`cron`, în UTC).

## Rulare locală
```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # completează token-ul și chat id-ul
.venv/bin/python search_tickets.py --dry-run   # doar afișează
.venv/bin/python search_tickets.py             # trimite pe Telegram
```
