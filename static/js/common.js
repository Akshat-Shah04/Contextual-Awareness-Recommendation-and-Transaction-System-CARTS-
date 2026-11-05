/* Shared helpers for the CARTS pages. */
const CARTS = {
  currency: "",

  async api(path, options = {}) {
    const opts = { ...options };
    if (opts.json !== undefined) {
      opts.method = opts.method || "POST";
      opts.headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
      opts.body = JSON.stringify(opts.json);
      delete opts.json;
    }
    const res = await fetch(path, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
    return data;
  },

  money(v) {
    if (v === null || v === undefined || Number.isNaN(v)) return "–";
    return `${this.currency}${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  },
  pct(v, digits = 1) {
    return v === null || v === undefined ? "–" : `${(Number(v) * 100).toFixed(digits)}%`;
  },
  num(v, digits = 0) {
    return v === null || v === undefined ? "–" : Number(v).toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
  },
  esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  },

  toast(message, isError = false) {
    const el = document.getElementById("toast");
    el.textContent = message;
    el.classList.toggle("error", isError);
    el.classList.add("show");
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => el.classList.remove("show"), 3500);
  },

  setDataset(meta) {
    if (!meta) return;
    this.currency = meta.currency || "";
    const el = document.getElementById("dataset-badge");
    el.textContent = `Dataset: ${meta.name || "custom"}`;
    el.title = [meta.source, meta.notes].filter(Boolean).join("\n");
  },

  /* Product icon from keywords in the name (first match wins), falling back to the category.
     Only emoji available in the Windows 10 / older macOS emoji fonts are used. */
  ICON_RULES: [
    [/hot water bottle|hand warmer/, "🔥"], [/alarm clock|clock/, "⏰"], [/t-light|tlight|candle/, "🕯️"],
    [/lantern/, "🏮"], [/light|lamp|bulb/, "💡"], [/cases|cupcake|baking/, "🧁"], [/bread/, "🍞"], [/sewing|pegs|knitting|thread/, "🧵"],
    [/parasol|umbrella/, "☂️"], [/sleigh bell|bell/, "🔔"], [/ruler/, "📏"], [/paint|clay|colouring/, "🎨"],
    [/spinning top|skipping|snakes|ladders|bingo/, "🎲"], [/mice|mouse/, "🐭"], [/pear|apple|fruit/, "🍐"],
    [/fan/, "🎐"], [/cabinet|coat rack|black ?board|shelf/, "🗄️"], [/stationery/, "✏️"],
    [/cake ?stand|cake tin|birthday|cake/, "🎂"], [/cookie/, "🍪"], [/jam|honey|jar/, "🍯"],
    [/lunch box|lunch bag/, "🍱"], [/charlotte|purse|tote|handbag/, "👜"], [/jumbo|shopper|bag/, "🛍️"],
    [/teacup|tea ?cup|mug|cup|coffee/, "☕"], [/tea/, "🍵"], [/plate|bowl|cutlery|dinner|kitchen|oven/, "🍽️"],
    [/spoon|fork/, "🥄"], [/apron|pantry|chef/, "🍳"], [/bottle|glass|jug|milk/, "🥛"],
    [/tin|storage|box|drawer|trinket/, "📦"], [/basket|picnic|wicker/, "🧺"], [/napkin|tissue/, "🧻"],
    [/plaster/, "🩹"], [/christmas|xmas|advent|santa|reindeer|snowflake|bauble/, "🎄"],
    [/bunting|party|confetti|garland/, "🎉"], [/balloon/, "🎈"], [/ribbon|bow\b/, "🎀"],
    [/wrap|gift/, "🎁"], [/card|envelope|love letter/, "💌"], [/notebook|book|journal|calendar/, "📓"],
    [/pen\b|pencil|crayon|chalk/, "✏️"], [/sticker|tape|paper chain|paper/, "📜"],
    [/doormat|door|knob|hook|key/, "🔑"], [/sign|keep calm|plaque/, "🏷️"], [/frame|picture|mirror/, "🖼️"],
    [/cushion|sofa|chair/, "🛋️"], [/spaceboy|rocket|space/, "🚀"], [/fairy/, "🧚"], [/skull/, "💀"],
    [/dolly|doll|teddy|toy|childrens|kids/, "🧸"], [/game|domino|skittles|jigsaw|playhouse/, "🎲"],
    [/strawberry/, "🍓"], [/rose|flower|floral|garden|plant/, "🌷"], [/bird|owl|robin/, "🐦"],
    [/woodland|fox|rabbit|bunny|animal/, "🦊"], [/cat\b|kitty/, "🐱"], [/dog\b|puppy/, "🐶"],
    [/umbrella/, "☂️"], [/necklace|bracelet|earring|ring\b|jewel/, "💍"], [/scarf|gloves|slipper/, "🧣"],
    [/chocolate|sweet|candy/, "🍫"], [/popcorn/, "🍿"], [/london|bus/, "🚌"], [/star/, "⭐"],
    [/heart|sweetheart|love/, "❤️"], [/ornament|decoration|hanging/, "✨"], [/home|house/, "🏠"],
  ],
  CATEGORY_ICONS: {
    "Christmas": "🎄", "Bags": "👜", "Kitchen & Dining": "🍽️", "Candles & Lighting": "🕯️",
    "Stationery & Wrap": "✏️", "Party": "🎉", "Home Decor": "🏠", "Kids & Toys": "🧸",
    "Fashion & Accessories": "💍", "Other": "🎁",
  },
  iconFor(name, category) {
    const n = String(name).toLowerCase();
    // keywords must start a word, so "tin" does not match "bunting"
    this._iconRules ||= this.ICON_RULES.map(([re, icon]) => [new RegExp("\\b(?:" + re.source + ")"), icon]);
    for (const [re, icon] of this._iconRules) if (re.test(n)) return icon;
    return this.CATEGORY_ICONS[category] || "🛒";
  },

  /* deterministic colour per category */
  colorFor(key) {
    const palette = ["#1f7a5c", "#3d5a9e", "#b5651d", "#8a4fa3", "#2b8a9e", "#a3485f", "#5b7f2a", "#6d6a2f", "#47607a", "#9a5b2d", "#7a4b8c"];
    let h = 0;
    for (const ch of String(key)) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    return palette[h % palette.length];
  },

  async busy(button, fn) {
    const label = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `<span class="spinner"></span> ${label}`;
    try { return await fn(); }
    finally { button.disabled = false; button.innerHTML = label; }
  },
};
