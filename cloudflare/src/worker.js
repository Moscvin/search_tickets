// Worker-ul Cloudflare al botului de Telegram.
//
// Telegram trimite fiecare mesaj și click aici (webhook). Meniul cu butoane (perioada → de unde → unde →
// câte zile → câte persoane) răspunde instant; când alegi tot, pornește căutarea pe GitHub Actions
// (.github/workflows/search_request.yml), care trimite rezultatul pe Telegram în 1–2 minute.
// Programările din wrangler.toml pornesc căutarea de luni și actualizarea zilnică a destinațiilor.
//
// Textele și datele butoanelor sunt aceleași ca în bot.py, ca să rămână compatibile.

const ORIGINS = ["RMO", "IAS", "OTP"];
const ORIGIN_NAMES = { RMO: "Chișinău", IAS: "Iași", OTP: "București" };
const DAYS_AHEAD = 180; // perioada implicită pentru mesajele text
const MONTHS_AHEAD = 12;
const CITIES_PER_PAGE = 24;
const ANYWHERE = "ANY";
const MONTHS = ["ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie", "august", "septembrie",
  "octombrie", "noiembrie", "decembrie"];
const MONTHS_SHORT = ["ian", "feb", "mar", "apr", "mai", "iun", "iul", "aug", "sep", "oct", "noi", "dec"];
const DAY_OPTIONS = [["2", 2, 2], ["3", 3, 3], ["4", 4, 4], ["5", 5, 5], ["6", 6, 6], ["7", 7, 7],
  ["10", 10, 10], ["14", 14, 14], ["2–4", 2, 4], ["2–7", 2, 7], ["5–10", 5, 10]];
const PAX_OPTIONS = [["1 adult", 1, 0], ["2 adulți", 2, 0], ["3 adulți", 3, 0], ["4 adulți", 4, 0],
  ["1 adult + 1 copil", 1, 1], ["2 adulți + 1 copil", 2, 1], ["2 adulți + 2 copii", 2, 2],
  ["2 adulți + 3 copii", 2, 3]];

const HELP =
  "✈️ Apasă /start și alege din butoane: perioada, de unde, unde și câte zile.\n\n" +
  "Sau scrie direct ruta, de exemplu:\n" +
  "• <code>Chișinău - Dubai 7 zile</code>\n" +
  "• <code>Iași - Milano 3-5 zile 2 luni</code>\n" +
  "• <code>Chișinău - Roma 5 zile peste 6-12 luni</code>\n" +
  "• <code>Chișinău - oriunde weekend 2 persoane</code>\n\n" +
  "Caut doar zboruri directe, dus-întors, la toate companiile (Wizz Air, Ryanair, FlyOne, HiSky, SkyUp " +
  "și restul prin Kiwi.com).";

// --------------------------------------------------------------------------- date

function utcDate(y, m, d) { return new Date(Date.UTC(y, m, d)); }

function today() {
  const n = new Date();
  return utcDate(n.getUTCFullYear(), n.getUTCMonth(), n.getUTCDate());
}

function addDays(d, n) { return utcDate(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + n); }
function addMonths(d, n) { return utcDate(d.getUTCFullYear(), d.getUTCMonth() + n, 1); }
function monthEnd(d) { return addDays(addMonths(d, 1), -1); }
function same(a, b) { return a.getTime() === b.getTime(); }
function pad(n) { return String(n).padStart(2, "0"); }
function ymd(d) { return `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}`; }
function dmy(d) { return `${pad(d.getUTCDate())}.${pad(d.getUTCMonth() + 1)}.${d.getUTCFullYear()}`; }

function windowToken(start, end) { return ymd(start) + ymd(end); } // 16 cifre, ex. 2027040120271031

function parseWindow(token) {
  if (!/^\d{16}$/.test(token || "")) return null;
  const p = (s) => utcDate(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8));
  return [p(token.slice(0, 8)), p(token.slice(8))];
}

function defaultWindow() { const t = today(); return [t, addDays(t, DAYS_AHEAD)]; }

function windowLabel(start, end) {
  const wholeMonths = start.getUTCDate() === 1 || same(start, today());
  if (wholeMonths && same(end, monthEnd(end))) {
    const first = MONTHS[start.getUTCMonth()] +
      (start.getUTCFullYear() === end.getUTCFullYear() ? "" : ` ${start.getUTCFullYear()}`);
    const last = `${MONTHS[end.getUTCMonth()]} ${end.getUTCFullYear()}`;
    const oneMonth = start.getUTCFullYear() === end.getUTCFullYear() && start.getUTCMonth() === end.getUTCMonth();
    return oneMonth ? last : `${first} – ${last}`;
  }
  return `${dmy(start)} – ${dmy(end)}`;
}

// --------------------------------------------------------------------------- meniul

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const button = (text, data) => ({ text, callback_data: data }); // callback_data: maxim 64 de octeți
const rows = (list, n) => Array.from({ length: Math.ceil(list.length / n) }, (_, i) => list.slice(i * n, i * n + n));
const originName = (o) => ORIGIN_NAMES[o] || o;

function optionsFromCode(code) {
  return /^[01]\d\d$/.test(code || "")
    ? { weekend: code[0] === "1", adults: +code[1], children: +code[2] }
    : { weekend: false, adults: 1, children: 0 };
}

function people({ adults, children }) {
  let text = `${adults} ${adults === 1 ? "adult" : "adulți"}`;
  if (children) text += ` + ${children} ${children === 1 ? "copil" : "copii"}`;
  return text;
}

function describeDays(lo, hi, weekend) {
  if (weekend) return "weekend (Vi/Sâ → Du/Lu)";
  return lo === hi ? `${lo} zile` : `${lo}–${hi} zile`;
}

function monthButtons(first, last, data) {
  const list = [];
  for (let d = addMonths(first, 0); d <= last; d = addMonths(d, 1)) {
    list.push(button(`${MONTHS_SHORT[d.getUTCMonth()]} ${d.getUTCFullYear()}`, data(d)));
  }
  return rows(list, 3);
}

function menuFromMonth() {
  const t = today();
  const keyboard = monthButtons(t, addMonths(t, MONTHS_AHEAD), (d) => `F:${ymd(d).slice(0, 6)}`);
  return ["📅 <b>Din ce lună vrei să pleci?</b>\n" +
    "Apoi alegi până în ce lună. Poți scrie și numărul de zile de azi încolo (ex. <code>45</code>).", keyboard];
}

function menuToMonth(firstMonth) {
  const t = today();
  let start = utcDate(+firstMonth.slice(0, 4), +firstMonth.slice(4, 6) - 1, 1);
  if (start < t) start = t;
  const keyboard = monthButtons(start, addMonths(t, MONTHS_AHEAD), (d) => `W:${windowToken(start, monthEnd(d))}`);
  keyboard.push([button("◀️ Altă lună de început", "start")]);
  return [`📅 Plecare din <b>${MONTHS[start.getUTCMonth()]} ${start.getUTCFullYear()}</b>\n<b>Până în ce lună?</b>`,
    keyboard];
}

const windowHeader = (token) => `📅 Plecare: ${windowLabel(...parseWindow(token))}\n`;

function menuOrigins(token) {
  const keyboard = [ORIGINS.map((o) => button(originName(o), `o:${o}:${token}`)),
    [button("◀️ Altă perioadă", "start")]];
  return [windowHeader(token) + "✈️ <b>De unde zbori?</b>", keyboard];
}

function menuDestinations(catalog, origin, page, token) {
  const cities = Object.entries(catalog[origin] || {});
  const pages = Math.max(1, Math.ceil(cities.length / CITIES_PER_PAGE));
  page = Math.min(Math.max(page, 0), pages - 1);
  const chunk = cities.slice(page * CITIES_PER_PAGE, (page + 1) * CITIES_PER_PAGE);
  const keyboard = rows(chunk.map(([place, info]) => button(info.name.slice(0, 20), `c:${origin}:${place}:${token}`)), 3);
  if (page === 0) keyboard.unshift([button("🌍 Oriunde (cele mai ieftine)", `c:${origin}:${ANYWHERE}:${token}`)]);
  const nav = [];
  if (page > 0) nav.push(button("◀️ Înapoi", `p:${origin}:${page - 1}:${token}`));
  nav.push(button("🏠 Alt oraș", `W:${token}`));
  if (page < pages - 1) nav.push(button("Înainte ▶️", `p:${origin}:${page + 1}:${token}`));
  keyboard.push(nav);
  return [windowHeader(token) + `✈️ <b>${originName(origin)} → unde?</b>\n` +
    `${cities.length} destinații cu zboruri directe · pagina ${page + 1}/${pages}`, keyboard];
}

function placeName(catalog, origin, place) {
  if (place === ANYWHERE) return "🌍 Oriunde";
  return catalog[origin]?.[place]?.name || place;
}

function menuDays(catalog, origin, place, token) {
  const keyboard = rows(DAY_OPTIONS.map(([label, lo, hi]) => button(label, `x:${origin}:${place}:${lo}:${hi}:0:${token}`)), 4);
  keyboard.push([button("🏖 Weekend (Vi/Sâ → Du/Lu)", `x:${origin}:${place}:1:3:1:${token}`)]);
  keyboard.push([button("◀️ Alt oraș destinație", `o:${origin}:${token}`)]);
  return [windowHeader(token) +
    `✈️ <b>${originName(origin)} → ${esc(placeName(catalog, origin, place))}</b>\nCâte zile stai?`, keyboard];
}

function menuPassengers(catalog, origin, place, lo, hi, weekend, token) {
  const keyboard = rows(PAX_OPTIONS.map(([label, a, c]) =>
    button(label, `s:${origin}:${place}:${lo}:${hi}:${weekend ? 1 : 0}${a}${c}:${token}`)), 2);
  keyboard.push([button("◀️ Alte zile", `c:${origin}:${place}:${token}`)]);
  return [windowHeader(token) + `✈️ <b>${originName(origin)} → ${esc(placeName(catalog, origin, place))}</b>, ` +
    `${describeDays(lo, hi, weekend)}\nCâte persoane zboară?`, keyboard];
}

// --------------------------------------------------------------------------- servicii externe

async function telegram(env, method, params) {
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(params),
  });
  const data = await r.json();
  if (!data.ok && !String(data.description).includes("message is not modified")) {
    throw new Error(`Telegram ${method}: ${data.description}`);
  }
  return data.result;
}

const send = (env, text, keyboard) => telegram(env, "sendMessage", {
  chat_id: env.TELEGRAM_CHAT_ID, text, parse_mode: "HTML", disable_web_page_preview: true,
  ...(keyboard ? { reply_markup: { inline_keyboard: keyboard } } : {}),
});

const edit = (env, msg, text, keyboard) => telegram(env, "editMessageText", {
  chat_id: msg.chat.id, message_id: msg.message_id, text, parse_mode: "HTML", disable_web_page_preview: true,
  ...(keyboard ? { reply_markup: { inline_keyboard: keyboard } } : {}),
});

async function dispatch(env, workflow, inputs = {}) {
  const r = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/${workflow}/dispatches`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${env.GITHUB_TOKEN}`, accept: "application/vnd.github+json",
      "user-agent": "ticketplanebot-worker", "content-type": "application/json",
    },
    body: JSON.stringify({ ref: "main", inputs }),
  });
  if (!r.ok) throw new Error(`GitHub ${workflow}: ${r.status} ${await r.text()}`);
}

// Destinațiile cu zboruri directe, actualizate zilnic de .github/workflows/routes.yml
async function loadCatalog(env) {
  const r = await fetch(`https://raw.githubusercontent.com/${env.GITHUB_REPO}/main/routes.json`,
    { cf: { cacheTtl: 600, cacheEverything: true } });
  if (!r.ok) throw new Error(`routes.json: ${r.status}`);
  return (await r.json()).catalog;
}

// --------------------------------------------------------------------------- mesaje și butoane

async function onMessage(env, text) {
  const clean = text.trim();
  const days = clean.match(/^(\d{1,3})\s*(zile|z)?$/i);
  if (days) { // perioada scrisă de mână: „45” de zile de azi
    const n = +days[1];
    if (n >= 7 && n <= 365) return send(env, ...menuOrigins(windowToken(today(), addDays(today(), n))));
    const [t, k] = menuFromMonth();
    return send(env, "Perioada trebuie să fie între 7 și 365 de zile.\n\n" + t, k);
  }
  if (/^\/?(help|ajutor)$/i.test(clean)) return send(env, HELP);
  // o rută scrisă de mână („Chișinău - Dubai 7 zile”): o înțelege și o caută bot.py
  if (!clean.startsWith("/") && (clean.includes("-") || clean.includes("→") || clean.split(/\s+/).length >= 2)) {
    await send(env, "🔎 Caut, durează 1–2 minute...");
    return dispatch(env, "search_request.yml", { text: clean });
  }
  return send(env, ...menuFromMonth()); // /start, salut sau orice altceva
}

async function onCallback(env, cb) {
  const data = cb.data || "";
  const msg = cb.message;
  await telegram(env, "answerCallbackQuery", { callback_query_id: cb.id });
  const parts = data.split(":");
  const token = parseWindow(parts[parts.length - 1]) ? parts[parts.length - 1] : windowToken(...defaultWindow());
  if (data === "start") return edit(env, msg, ...menuFromMonth());
  if (parts[0] === "F") return edit(env, msg, ...menuToMonth(parts[1]));
  if (parts[0] === "W") return edit(env, msg, ...menuOrigins(token));

  const catalog = await loadCatalog(env);
  if (parts[0] === "o") return edit(env, msg, ...menuDestinations(catalog, parts[1], 0, token));
  if (parts[0] === "p") return edit(env, msg, ...menuDestinations(catalog, parts[1], +parts[2], token));
  if (parts[0] === "c") return edit(env, msg, ...menuDays(catalog, parts[1], parts[2], token));
  if (parts[0] === "x") {
    return edit(env, msg, ...menuPassengers(catalog, parts[1], parts[2], +parts[3], +parts[4], parts[5] === "1", token));
  }
  if (parts[0] === "s") {
    const [, origin, place, lo, hi] = parts;
    const opts = parts.length > 6 ? optionsFromCode(parts[5]) : optionsFromCode("");
    const wait = place === ANYWHERE ? "3–10 minute" : "1–2 minute";
    await edit(env, msg, `🔎 Caut <b>${originName(origin)} → ${esc(placeName(catalog, origin, place))}</b>, ` +
      `${describeDays(+lo, +hi, opts.weekend)}, ${people(opts)}, plecare ${windowLabel(...parseWindow(token))}... ` +
      `durează ${wait}.`);
    return dispatch(env, "search_request.yml", { button: data });
  }
}

export default {
  async fetch(request, env) {
    if (request.method !== "POST") return new Response("ticketplanebot ok");
    // doar Telegram cunoaște secretul setat la înregistrarea webhook-ului
    if (request.headers.get("x-telegram-bot-api-secret-token") !== env.WEBHOOK_SECRET) {
      return new Response("forbidden", { status: 403 });
    }
    const update = await request.json();
    const cb = update.callback_query;
    const msg = update.message;
    const chatId = cb ? cb.message?.chat?.id : msg?.chat?.id;
    if (String(chatId) !== String(env.TELEGRAM_CHAT_ID)) return new Response("ok"); // doar proprietarul
    try {
      if (cb) await onCallback(env, cb);
      else if (msg?.text) await onMessage(env, msg.text);
    } catch (e) {
      console.error(e);
      await send(env, `⚠️ A apărut o eroare: ${esc(e.message)}`).catch(() => {});
    }
    return new Response("ok"); // mereu 200, altfel Telegram retrimite același mesaj
  },

  async scheduled(event, env) {
    if (event.cron === "0 6 * * 1") await dispatch(env, "search_tickets.yml"); // căutarea de luni
    else await dispatch(env, "routes.yml"); // destinațiile din meniu, zilnic
  },
};
