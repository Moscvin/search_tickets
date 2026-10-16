# Instalare și întreținere

Botul rulează pe **Cloudflare Worker** (meniul, 24/7) și pe **GitHub Actions** (căutările).
Calculatorul nu trebuie să fie pornit.

```
Telegram ──webhook──▶ Cloudflare Worker ──menu instant
                          │
                          └─ workflow_dispatch ──▶ GitHub Actions ──▶ căutare ──▶ Telegram
Cron (Worker) ─▶ căutarea de luni (search_tickets.yml)
              ─▶ actualizarea destinațiilor (routes.yml → routes.json)
```

## 1. Ce e în repo

| Fișier | Rol |
|---|---|
| `cloudflare/src/worker.js` | meniul cu butoane, webhook-ul Telegram, programările |
| `cloudflare/wrangler.toml` | numele Worker-ului, programările (cron), variabile |
| `bot.py` | căutarea și formatarea rezultatelor (rulează pe GitHub Actions) |
| `search_tickets.py` | sursele de zboruri (Wizz, Ryanair, FlyOne, HiSky, SkyUp, Kiwi) |
| `routes.json` | destinațiile cu zboruri directe, pentru meniu (actualizat zilnic) |
| `.github/workflows/search_request.yml` | căutarea pornită din meniu |
| `.github/workflows/search_tickets.yml` | căutarea săptămânală (luni) |
| `.github/workflows/routes.yml` | recalcularea `routes.json` |

## 2. Secrete și variabile

**GitHub** (Settings → Secrets and variables → Actions → *Secrets*):

- `TELEGRAM_BOT_TOKEN`: tokenul botului de la @BotFather.
- `TELEGRAM_CHAT_ID`: ID-ul tău de chat. Botul răspunde doar acestui chat.
- `TRAVELPAYOUTS_TOKEN` (opțional): pentru Aviasales.

**GitHub, variabile** (tab *Variables*, opționale): `ORIGINS`, `DAYS_AHEAD`, `TRIP_MIN_DAYS`,
`TRIP_MAX_DAYS`, `MAX_PRICE_EUR`, `TOP_N`, `DIRECT_ONLY`, `KIWI_DESTINATIONS`.

**Cloudflare Worker** (`cd cloudflare && npx wrangler secret put NUME`):

| Nume | Ce conține |
|---|---|
| `TELEGRAM_BOT_TOKEN` | același token ca pe GitHub |
| `TELEGRAM_CHAT_ID` | același ID ca pe GitHub |
| `WEBHOOK_SECRET` | un șir aleator; Telegram îl trimite la fiecare mesaj, Worker-ul refuză cererile fără el |
| `GITHUB_TOKEN` | token GitHub *fine-grained*, doar pentru `Moscvin/search_tickets`, cu **Actions: Read and write** |

Verifică ce secrete există: `npx wrangler secret list`.

## 3. Instalare de la zero

1. Cont gratuit pe [cloudflare.com](https://dash.cloudflare.com/sign-up).
2. Token GitHub: [creează-l aici](https://github.com/settings/personal-access-tokens/new), cu
   *Only select repositories* → `search_tickets`, permisiunea **Actions: Read and write**
   și **Expiration: No expiration**.
3. În `cloudflare/`:
   ```
   npm install
   npx wrangler login
   npx wrangler deploy
   ```
4. Setează cele patru secrete din tabelul de mai sus.
5. Setează webhook-ul Telegram (înlocuiește `<TOKEN>` și `<SECRET>`):
   ```
   https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://ticketplanebot.moscvin-2002.workers.dev&secret_token=<SECRET>
   ```
   Verificare: `https://api.telegram.org/bot<TOKEN>/getWebhookInfo` trebuie să arate URL-ul și `last_error_message` gol.
6. Scrie-i botului `/start`.

## 4. Cum se folosește

- `/start` deschide meniul: perioada → de unde → unde (sau 🌍 Oriunde) → zile (sau 🏖 Weekend) → persoane.
- Mesaje text: `Chișinău - Dubai 7 zile`, `Iași - Milano 3-5 zile 2 luni`, `Chișinău - Roma 5 zile peste 6-12 luni`,
  `Chișinău - oriunde weekend 2 persoane`.
- Doar zboruri **directe**. Dacă nu există, botul arată cele mai ieftine variante cu escală.
- Căutarea durează 1–2 minute (3–10 pentru „Oriunde”).

## 5. Programări

| Când | Ce pornește | Unde e configurat |
|---|---|---|
| luni 06:00 UTC | căutarea săptămânală | `cloudflare/wrangler.toml` (`crons`) și `search_tickets.py` |
| zilnic 03:00 UTC | `routes.json` | `cloudflare/wrangler.toml` |

De ce Worker-ul și nu GitHub: programările GitHub (`schedule`) nu au pornit deloc în testele noastre.

## 6. Întreținere

**Actualizarea codului Worker-ului**, după fiecare modificare în `cloudflare/src/worker.js`:
```
cd cloudflare && npx wrangler deploy
```

**Schimbarea unui secret** (de exemplu la rotația tokenului GitHub):
```
cd cloudflare && npx wrangler secret put GITHUB_TOKEN
```
Lipești valoarea când îți cere terminalul. Nu o pune în chat, în fișiere sau în commit-uri.

**Rotația tokenului GitHub:** creează un token nou cu aceleași setări, actualizează secretul `GITHUB_TOKEN`
și șterge tokenul vechi din [setările GitHub](https://github.com/settings/personal-access-tokens).

**Schimbarea orei programărilor:** editează `crons` din `cloudflare/wrangler.toml` (format UTC), apoi `npx wrangler deploy`.

## 7. Dacă ceva nu merge

| Simptom | Cauza probabilă | Ce faci |
|---|---|---|
| Botul nu răspunde deloc | webhook-ul nu e setat sau e pe alt URL | `getWebhookInfo` și reface pasul 5 din instalare |
| Meniul merge, căutarea nu | `GITHUB_TOKEN` expirat sau fără permisiune | rotește tokenul (secțiunea 6) |
| „Nu am găsit orașul” | numele nu e recunoscut | scrie orașul în română sau cu codul IATA (ex. `OTP`) |
| Meniul nu are destinații | `routes.json` lipsește sau e vechi | rulează manual `routes.yml` din tab-ul Actions |
| Rezultat cu o sursă lipsă | o companie a schimbat site-ul sau blochează cererile | mesajul arată sursa; alte surse merg în continuare |
| Wizz Air blochează | prea multe cereri într-un timp scurt | așteaptă câteva ore; căutarea reîncearcă singură |

Log-urile căutărilor sunt în tab-ul **Actions** al repo-ului, la fiecare rulare.
