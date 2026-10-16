# Bilete ieftine din Chișinău, Iași și București → Telegram

Caută săptămânal (lunea, pornit de Worker-ul Cloudflare) cele mai ieftine bilete **dus-întors** din Chișinău (RMO), Iași (IAS) și București (OTP) în orice direcție și trimite pe Telegram
top destinații cu preț total, datele dus/întors, companie și link de rezervare.
Plecarea în următoarele 180 de zile, întoarcerea după 2–7 zile, doar zboruri directe (`DIRECT_ONLY=false` le include și pe cele cu escală).

Surse:
- **Wizz Air**: API-ul site-ului (toate rutele)
- **Ryanair**: cel mai ieftin dus-întors pe fiecare rută (zboară din Iași și București, nu din Chișinău)
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

## 2. GitHub Actions (rulează în fiecare luni, gratuit)
1. Urcă proiectul într-un repo pe GitHub.
2. **Settings → Secrets and variables → Actions → New repository secret**:
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (și opțional `TRAVELPAYOUTS_TOKEN`).
3. Opțional, la tab-ul **Variables**: `ORIGINS`, `DAYS_AHEAD`, `TRIP_MIN_DAYS`, `TRIP_MAX_DAYS`, `MAX_PRICE_EUR`, `TOP_N`, `DIRECT_ONLY`, `KIWI_DESTINATIONS`.
4. **Actions → Bilete ieftine din Chișinău, Iași, București → Run workflow** ca să testezi imediat.

Ora rulării se schimbă în [.github/workflows/search_tickets.yml](.github/workflows/search_tickets.yml) (`cron`, în UTC).

## 3. Întreabă botul o rută
Scrie-i botului `/start` (sau orice mesaj) și alege din butoane: **din ce lună** → **până în ce lună** pleci
(ex. aprilie – octombrie 2027) → **de unde** (Chișinău / Iași / București) → **unde** (doar orașele cu zboruri directe)
(sau **🌍 Oriunde** – cele mai ieftine destinații) → **câte zile** (sau **🏖 Weekend**: Vi/Sâ → Du/Lu)
→ **câte persoane** (adulți, copii). Botul trimite cele mai ieftine date dus-întors cu zboruri directe din intervalul ales,
cu prețul total pentru toți pasagerii;
dacă pe rută nu există zbor direct, îți scrie asta și îți arată cele mai ieftine variante cu escală.
Poți scrie și direct, de exemplu `Chișinău - Dubai 7 zile`, `Iași - Milano 3-5 zile 2 luni` sau
`Chișinău - Roma 5 zile peste 6-12 luni`, `Chișinău - oriunde weekend 2 persoane`.

### Cum funcționează (gratuit, 24/7, fără calculator pornit)
- **Cloudflare Worker** ([cloudflare/src/worker.js](cloudflare/src/worker.js)): Telegram îi trimite fiecare mesaj și click;
  meniul răspunde instant. Planul Free (100.000 de cereri/zi) e de ajuns.
- **GitHub Actions** ([search_request.yml](.github/workflows/search_request.yml)): Worker-ul pornește căutarea când alegi ruta;
  rezultatul vine pe Telegram în 1–2 minute (3–10 pentru „Oriunde”).
- **Programările** Worker-ului pornesc căutarea de luni ([search_tickets.yml](.github/workflows/search_tickets.yml))
  și actualizarea zilnică a destinațiilor din meniu ([routes.yml](.github/workflows/routes.yml) → `routes.json`).

### Instalarea Worker-ului
1. Cont gratuit pe [cloudflare.com](https://dash.cloudflare.com/sign-up), apoi în `cloudflare/`: `npx wrangler login`.
2. Un token GitHub *fine-grained* doar pentru acest repo, cu permisiunea **Actions: Read and write**
   ([creează-l aici](https://github.com/settings/personal-access-tokens/new)).
3. În `cloudflare/`: `npx wrangler deploy`, apoi `npx wrangler secret put` pentru `TELEGRAM_BOT_TOKEN`,
   `TELEGRAM_CHAT_ID`, `GITHUB_TOKEN` și `WEBHOOK_SECRET` (un șir aleator).
4. Webhook-ul Telegram: `https://api.telegram.org/bot<TOKEN>/setWebhook?url=<adresa Worker-ului>&secret_token=<WEBHOOK_SECRET>`.

Răspunde doar la chat-ul din `TELEGRAM_CHAT_ID`.

## Rulare locală
```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # completează token-ul și chat id-ul
.venv/bin/python search_tickets.py --dry-run   # doar afișează
.venv/bin/python bot.py --query "Chișinău - Dubai 7"   # o rută, fără Telegram
.venv/bin/python search_tickets.py             # trimite pe Telegram
```
