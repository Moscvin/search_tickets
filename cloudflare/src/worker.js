// Worker-ul Cloudflare al botului de Telegram.
//
// Telegram trimite fiecare mesaj și click aici (webhook). Meniul cu butoane (perioada → de unde → unde →
// câte zile → câte persoane) răspunde instant; când alegi tot, pornește căutarea pe GitHub Actions
// (.github/workflows/search_request.yml), care trimite rezultatul pe Telegram în 1–2 minute.
// Programările din wrangler.toml pornesc căutarea de luni și actualizarea zilnică a destinațiilor.
//
// Textele și datele butoanelor sunt aceleași ca în bot.py, ca să rămână compatibile.

const ORIGINS = ["RMO", "IAS", "OTP", "IST", "VRN", "BLQ", "BGY"];
const ORIGIN_NAMES = { RMO: "Chișinău", IAS: "Iași", OTP: "București", IST: "Istanbul", VRN: "Verona", BLQ: "Bologna", BGY: "Milano" };
const COUNTRIES = {
  TH: ["🇹🇭 Thailanda", ["BKK", "HKT"]],
  VN: ["🇻🇳 Vietnam", ["HAN", "SGN"]],
  ID: ["🇮🇩 Indonezia", ["CGK", "DPS"]],
  MY: ["🇲🇾 Malaezia", ["KUL"]],
  SG: ["🇸🇬 Singapore", ["SIN"]],
  PH: ["🇵🇭 Filipine", ["MNL"]],
  JP: ["🇯🇵 Japonia", ["NRT", "HND", "KIX"]],
  KR: ["🇰🇷 Coreea de Sud", ["ICN"]],
  CN: ["🇨🇳 China", ["PEK", "PVG", "CAN", "XIY"]],
  HK: ["🇭🇰 Hong Kong", ["HKG"]],
  TW: ["🇹🇼 Taiwan", ["TPE"]],
  IN: ["🇮🇳 India", ["DEL", "BOM"]],
  PK: ["🇵🇰 Pakistan", ["KHI", "LHE", "ISB"]],
  BD: ["🇧🇩 Bangladesh", ["DAC"]],
  LK: ["🇱🇰 Sri Lanka", ["CMB"]],
  NP: ["🇳🇵 Nepal", ["KTM"]],
  MV: ["🇲🇻 Maldive", ["MLE"]],
  AE: ["🇦🇪 Emiratele Arabe Unite", ["DXB", "AUH", "SHJ"]],
  QA: ["🇶🇦 Qatar", ["DOH"]],
  OM: ["🇴🇲 Oman", ["MCT"]],
  SA: ["🇸🇦 Arabia Saudită", ["RUH", "JED", "DMM", "MED"]],
  KW: ["🇰🇼 Kuweit", ["KWI"]],
  BH: ["🇧🇭 Bahrain", ["BAH"]],
  JO: ["🇯🇴 Iordania", ["AMM"]],
  LB: ["🇱🇧 Liban", ["BEY"]],
  IQ: ["🇮🇶 Irak", ["BGW", "EBL"]],
  EG: ["🇪🇬 Egipt", ["CAI", "HRG", "SSH"]],
  TN: ["🇹🇳 Tunisia", ["TUN"]],
  DZ: ["🇩🇿 Algeria", ["ALG", "ORN"]],
  MA: ["🇲🇦 Maroc", ["CMN", "RAK"]],
  ET: ["🇪🇹 Etiopia", ["ADD"]],
  KE: ["🇰🇪 Kenya", ["NBO", "MBA"]],
  TZ: ["🇹🇿 Tanzania", ["DAR", "JRO", "ZNZ"]],
  UG: ["🇺🇬 Uganda", ["EBB"]],
  NG: ["🇳🇬 Nigeria", ["LOS", "ABV"]],
  GH: ["🇬🇭 Ghana", ["ACC"]],
  SN: ["🇸🇳 Senegal", ["DSS"]],
  ZA: ["🇿🇦 Africa de Sud", ["JNB", "CPT"]],
  MU: ["🇲🇺 Mauritius", ["MRU"]],
  SC: ["🇸🇨 Seychelles", ["SEZ"]],
  AZ: ["🇦🇿 Azerbaidjan", ["GYD"]],
  GE: ["🇬🇪 Georgia", ["TBS", "BUS"]],
  AM: ["🇦🇲 Armenia", ["EVN"]],
  KZ: ["🇰🇿 Kazahstan", ["ALA", "NQZ"]],
  UZ: ["🇺🇿 Uzbekistan", ["TAS", "SKD"]],
  TM: ["🇹🇲 Turkmenistan", ["ASB"]],
  TJ: ["🇹🇯 Tadjikistan", ["DYU"]],
  GR: ["🇬🇷 Grecia", ["ATH", "SKG", "HER", "JTR"]],
  BG: ["🇧🇬 Bulgaria", ["SOF", "VAR"]],
  RO: ["🇷🇴 Romania", ["OTP", "CLJ", "TSR", "CND"]],
  RS: ["🇷🇸 Serbia", ["BEG", "INI"]],
  HR: ["🇭🇷 Croatia", ["ZAG", "SPU", "DBV"]],
  BA: ["🇧🇦 Bosnia", ["SJJ"]],
  MK: ["🇲🇰 Macedonia de Nord", ["SKP"]],
  AL: ["🇦🇱 Albania", ["TIA"]],
  ME: ["🇲🇪 Muntenegru", ["TIV"]],
  XK: ["🇽🇰 Kosovo", ["PRN"]],
  SI: ["🇸🇮 Slovenia", ["LJU"]],
  HU: ["🇭🇺 Ungaria", ["BUD"]],
  CZ: ["🇨🇿 Cehia", ["PRG"]],
  PL: ["🇵🇱 Polonia", ["WAW", "KRK", "GDN"]],
  DE: ["🇩🇪 Germania", ["BER", "FRA", "MUC", "DUS", "CGN", "HAM", "STR", "NUE"]],
  AT: ["🇦🇹 Austria", ["VIE", "SZG"]],
  CH: ["🇨🇭 Elveția", ["ZRH", "GVA", "BSL"]],
  IT: ["🇮🇹 Italia", ["FCO", "MXP", "VCE", "NAP", "BLQ", "PMO", "CTA", "TRN", "BRI"]],
  ES: ["🇪🇸 Spania", ["MAD", "BCN", "AGP", "VLC", "SVQ", "BIO"]],
  PT: ["🇵🇹 Portugalia", ["LIS", "OPO"]],
  FR: ["🇫🇷 Franța", ["CDG", "ORY", "NCE", "LYS", "MRS", "BOD", "TLS"]],
  BE: ["🇧🇪 Belgia", ["BRU"]],
  NL: ["🇳🇱 Olanda", ["AMS"]],
  LU: ["🇱🇺 Luxemburg", ["LUX"]],
  GB: ["🇬🇧 Regatul Unit", ["LHR", "LGW", "STN", "LTN", "MAN", "EDI", "BHX"]],
  IE: ["🇮🇪 Irlanda", ["DUB"]],
  DK: ["🇩🇰 Danemarca", ["CPH"]],
  SE: ["🇸🇪 Suedia", ["ARN", "GOT"]],
  NO: ["🇳🇴 Norvegia", ["OSL"]],
  FI: ["🇫🇮 Finlanda", ["HEL"]],
  EE: ["🇪🇪 Estonia", ["TLL"]],
  LV: ["🇱🇻 Letonia", ["RIX"]],
  LT: ["🇱🇹 Lituania", ["VNO"]],
  MT: ["🇲🇹 Malta", ["MLA"]],
  US: ["🇺🇸 Statele Unite", ["JFK", "EWR", "IAD", "ORD", "ATL", "LAX", "MIA", "BOS", "SFO", "DFW", "IAH"]],
  CA: ["🇨🇦 Canada", ["YYZ", "YUL", "YVR"]],
  MX: ["🇲🇽 Mexic", ["MEX", "CUN"]],
  BR: ["🇧🇷 Brazilia", ["GRU"]],
  VE: ["🇻🇪 Venezuela", ["CCS"]],
  AU: ["🇦🇺 Australia", ["SYD", "MEL"]],
};
const DAYS_AHEAD = 180; // perioada implicită pentru mesajele text
const MONTHS_AHEAD = 12;
const CITIES_PER_PAGE = 24;
const ANYWHERE = "ANY";
const MONTHS = ["ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", "iulie", "august", "septembrie",
  "octombrie", "noiembrie", "decembrie"];
const MONTHS_SHORT = ["ian", "feb", "mar", "apr", "mai", "iun", "iul", "aug", "sep", "oct", "noi", "dec"];
const DAY_OPTIONS = [["2", 2, 2], ["3", 3, 3], ["4", 4, 4], ["5", 5, 5], ["6", 6, 6], ["7", 7, 7],
  ["10", 10, 10], ["14", 14, 14], ["2–4", 2, 4], ["2–7", 2, 7], ["5–10", 5, 10], ["11–20", 11, 20]];
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
  const keyboard = [...rows(ORIGINS.map((o) => button(originName(o), `o:${o}:${token}`)), 3),
    [button("◀️ Altă perioadă", "start")]];
  return [windowHeader(token) + "✈️ <b>De unde zbori?</b>", keyboard];
}

function menuDestinations(catalog, origin, page, token) {
  const cities = Object.entries(catalog[origin] || {});
  const pages = Math.max(1, Math.ceil(cities.length / CITIES_PER_PAGE));
  page = Math.min(Math.max(page, 0), pages - 1);
  const chunk = cities.slice(page * CITIES_PER_PAGE, (page + 1) * CITIES_PER_PAGE);
  const keyboard = rows(chunk.map(([place, info]) => button(info.name.slice(0, 20), `c:${origin}:${place}:${token}`)), 3);
  if (page === 0) {
    keyboard.unshift([button("🌍 Oriunde (cele mai ieftine)", `c:${origin}:${ANYWHERE}:${token}`)],
      [button("🗺 Țări", `k:${origin}:0:${token}`)]);
  }
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
  if (place.startsWith("@")) return COUNTRIES[place.slice(1)][0];
  return catalog[origin]?.[place]?.name || place;
}

function menuCountries(catalog, origin, page, token) {
  const reachable = new Set(Object.values(catalog[origin] || {}).flatMap((info) => info.airports));
  const countries = Object.entries(COUNTRIES).filter(([, [, airports]]) => airports.some((a) => reachable.has(a)));
  const perPage = 15;
  const pages = Math.max(1, Math.ceil(countries.length / perPage));
  page = Math.min(Math.max(page, 0), pages - 1);
  const chunk = countries.slice(page * perPage, (page + 1) * perPage);
  const keyboard = rows(chunk.map(([code, [label]]) => button(label, `c:${origin}:@${code}:${token}`)), 3);
  const nav = [button("◀️ Înapoi", `p:${origin}:0:${token}`)];
  if (page > 0) nav.push(button("◀️ Pagina anterioară", `k:${origin}:${page - 1}:${token}`));
  if (page < pages - 1) nav.push(button("Pagina următoare ▶️", `k:${origin}:${page + 1}:${token}`));
  keyboard.push(nav);
  return [windowHeader(token) + `🗺 <b>Țări din ${originName(origin)}</b>\n` +
    `${countries.length} țări cu zboruri directe · pagina ${page + 1}/${pages}`, keyboard];
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
  if (workflow === "search_request.yml") inputs = { ...inputs, chat: String(env.TELEGRAM_CHAT_ID) };
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
  if (parts[0] === "k") return edit(env, msg, ...menuCountries(catalog, parts[1], +parts[2], token));
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

// --------------------------------------------------------------------------- acces

const isAdmin = (env, chatId) => String(chatId) === String(env.ADMIN_CHAT_ID || env.TELEGRAM_CHAT_ID);

async function allowedUser(env, chatId) {
  return (await env.USERS.get("allowed:" + chatId)) !== null;
}

// Cine a scris botului: reținem username-ul, ca adminul să poată adăuga pe @username
async function rememberUser(env, chatId, from) {
  const username = from?.username ? from.username.toLowerCase() : "";
  const name = [from?.first_name, from?.last_name].filter(Boolean).join(" ") || "fără nume";
  if (username) await env.USERS.put("name:" + username, String(chatId));
  return { username, name };
}

async function onAdminCommand(env, text) {
  const [cmd, rawUser] = text.trim().split(/\s+/);
  const username = (rawUser || "").replace(/^@/, "").toLowerCase();
  if (cmd === "/utilizatori") {
    const lines = async (prefix) => {
      const { keys } = await env.USERS.list({ prefix });
      const out = [];
      for (const k of keys) {
        const info = JSON.parse((await env.USERS.get(k.name)) || "{}");
        out.push("• " + esc(info.label || k.name) + " (" + k.name.split(":")[1] + ")");
      }
      return out.join("\n");
    };
    return send(env, "👥 <b>Utilizatori cu acces</b>\n" + ((await lines("allowed:")) || "(niciunul)") +
      "\n\n⏳ <b>Cereri în așteptare</b>\n" + ((await lines("pending:")) || "(niciuna)"));
  }
  if (cmd === "/adauga" || cmd === "/sterge") {
    if (!username) return send(env, "Scrie: <code>" + cmd + " @username</code>");
    const chatId = await env.USERS.get("name:" + username);
    if (!chatId) return send(env, `Nu cunosc pe @${esc(username)}. Trebuie să-i scrie botului întâi.`);
    if (cmd === "/adauga") {
      const pending = await env.USERS.get("pending:" + chatId);
      const label = pending ? JSON.parse(pending).label : "@" + username;
      await env.USERS.put("allowed:" + chatId, JSON.stringify({ label }));
      await env.USERS.delete("pending:" + chatId);
      await send({ ...env, TELEGRAM_CHAT_ID: chatId }, "✅ Ai acces acum. Scrie /start ca să cauți bilete.");
      return send(env, `✅ @${esc(username)} are acces acum.`);
    }
    await env.USERS.delete("allowed:" + chatId);
    return send(env, `🚫 @${esc(username)} nu mai are acces.`);
  }
  return send(env, "Comenzi admin:\n" +
    "• <code>/adauga @username</code> – dă acces (utilizatorul trebuie să fi scris botului)\n" +
    "• <code>/sterge @username</code> – scoate accesul\n" +
    "• <code>/utilizatori</code> – lista cu cine are acces și cererile în așteptare");
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
    if (!msg?.text && !cb) return new Response("ok");
    const chatId = String(cb ? cb.message?.chat?.id : msg?.chat?.id);
    const from = cb ? cb.from : msg.from;
    const { username, name } = await rememberUser(env, chatId, from);

    // ctx: răspunsurile merg la chat-ul celui care a scris (la admin, la același chat)
    const ctx = { ...env, TELEGRAM_CHAT_ID: chatId };
    try {
      if (isAdmin(env, chatId)) {
        if (msg?.text?.startsWith("/adauga") || msg?.text?.startsWith("/sterge") || msg?.text?.startsWith("/utilizatori") || msg?.text === "/comenzi") {
          await onAdminCommand(env, msg.text);
        } else if (cb) await onCallback(ctx, cb);
        else if (msg?.text) await onMessage(ctx, msg.text);
      } else if (await allowedUser(env, chatId)) {
        if (cb) await onCallback(ctx, cb);
        else if (msg?.text) await onMessage(ctx, msg.text);
      } else {
        // utilizator nou: îi cerem adminului accesul, o singură notificare
        const label = `@${username || "fără username"} (${name})`;
        if (!(await env.USERS.get("pending:" + chatId))) {
          await env.USERS.put("pending:" + chatId, JSON.stringify({ label }));
          await send(env, `👤 Cerere de acces: ${esc(label)}\nCa să-i dai acces scrie: <code>/adauga @${esc(username)}</code>`).catch(() => {});
        }
        await send(ctx, "🔒 Nu ai acces încă. Am trimis cererea administratorului; îți scriu când ai acces.").catch(() => {});
      }
    } catch (e) {
      console.error(e);
      await send(ctx, `⚠️ A apărut o eroare: ${esc(e.message)}`).catch(() => {});
    }
    return new Response("ok"); // mereu 200, altfel Telegram retrimite același mesaj
  },

  async scheduled(event, env) {
    if (event.cron === "0 6 * * 1") await dispatch(env, "search_tickets.yml"); // căutarea de luni
    else await dispatch(env, "routes.yml"); // destinațiile din meniu, zilnic
  },
};
