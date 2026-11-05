/* Shop page: browse, build a cart, get live CARTS / Apriori recommendations, check out. */
(() => {
  const PAGE = 60;
  const state = {
    products: [], byName: new Map(), category: "", query: "", sort: "popular", shown: PAGE,
    cart: JSON.parse(localStorage.getItem("carts.cart") || "[]"),   // [{item, qty}]
    strategy: localStorage.getItem("carts.strategy") || "carts",
    bestsellerCut: Infinity,
    shownRecs: new Set(),   // every item recommended during this shopping session
    recs: [],
  };
  const $ = id => document.getElementById(id);

  async function loadProducts() {
    const params = new URLSearchParams({ q: state.query, category: state.category, sort: state.sort });
    const data = await CARTS.api(`/api/products?${params}`);
    state.products = data.products;
    renderCategories(data.categories);
    renderProducts();
  }

  function renderCategories(categories) {
    const el = $("categories");
    el.innerHTML = ["", ...categories].map(c =>
      `<button class="chip ${c === state.category ? "on" : ""}" data-c="${CARTS.esc(c)}">`
      + `<span class="chip-icon" aria-hidden="true">${c ? CARTS.CATEGORY_ICONS[c] || "🛒" : "🛒"}</span>${c ? CARTS.esc(c) : "All"}</button>`).join("");
  }

  function renderProducts() {
    const list = state.products.slice(0, state.shown);
    const topSeller = state.bestsellerCut;
    $("products").innerHTML = list.length ? list.map(p => `
      <div class="card product">
        <div class="thumb" style="--tint:${CARTS.colorFor(p.category)}">
          <span class="thumb-icon" aria-hidden="true">${CARTS.iconFor(p.item, p.category)}</span>
          ${p.times_sold >= topSeller ? '<span class="badge-hot">Bestseller</span>' : ""}
        </div>
        <div class="name">${CARTS.esc(p.item)}</div>
        <div class="cat" style="--tint:${CARTS.colorFor(p.category)}">${CARTS.esc(p.category)}</div>
        <div class="meta">
          <span class="price num">${CARTS.money(p.selling_price)}</span>
          <button class="btn small primary" data-add="${CARTS.esc(p.item)}">Add</button>
        </div>
      </div>`).join("") : `<div class="empty">No products match.</div>`;
    $("more").hidden = state.products.length <= state.shown;
  }

  function saveCart() {
    localStorage.setItem("carts.cart", JSON.stringify(state.cart));
  }

  function addToCart(item, fromRec = false) {
    const line = state.cart.find(l => l.item === item);
    if (line) line.qty += 1; else state.cart.push({ item, qty: 1, fromRec });
    saveCart();
    renderCart();
    refreshRecs();
    CARTS.toast(`Added ${item}`);
  }

  function renderCart() {
    const el = $("cart");
    if (!state.cart.length) {
      el.innerHTML = `<div class="empty">Your cart is empty.</div>`;
    } else {
      el.innerHTML = state.cart.map((l, i) => {
        const p = state.byName.get(l.item);
        return `<div class="cart-line">
          <div class="line-main"><span class="mini-icon" style="--tint:${CARTS.colorFor(p?.category || "")}" aria-hidden="true">${CARTS.iconFor(l.item, p?.category)}</span><div><div>${CARTS.esc(l.item)}</div>
            <div class="small muted">${p ? CARTS.money(p.selling_price) : ""} ${l.fromRec ? '<span class="pill green">recommended</span>' : ""}</div></div></div>
          <div class="qty">
            <button data-dec="${i}" aria-label="Decrease">−</button><span class="num">${l.qty}</span><button data-inc="${i}" aria-label="Increase">+</button>
          </div>
          <div class="num">${p ? CARTS.money(p.selling_price * l.qty) : ""}</div>
        </div>`;
      }).join("");
    }
    const total = state.cart.reduce((s, l) => s + (state.byName.get(l.item)?.selling_price || 0) * l.qty, 0);
    $("cart-total").textContent = state.cart.length ? CARTS.money(total) : "–";
    $("checkout").disabled = !state.cart.length;
  }

  let recTimer;
  function refreshRecs() {
    clearTimeout(recTimer);
    recTimer = setTimeout(loadRecs, 120);
  }

  async function loadRecs() {
    const cart = state.cart.map(l => l.item);
    try {
      const data = await CARTS.api("/api/recommend", { json: { cart, strategy: state.strategy, top_n: 6 } });
      state.recs = data.recommendations;
      if (cart.length) state.recs.forEach(r => state.shownRecs.add(r.item));
      renderRecs(!cart.length);
    } catch (e) { CARTS.toast(e.message, true); }
  }

  function renderRecs(coldStart) {
    const el = $("recs");
    const head = coldStart ? `<div class="small muted" style="margin-bottom:4px">Popular picks to get you started:</div>` : "";
    el.innerHTML = head + state.recs.map(r => {
      let why;
      if (r.reason === "popular") why = "Popular across all baskets";
      else {
        const base = `${r.reason === "partial rule" ? "Partly matches" : "Bought with"} ${r.because.map(CARTS.esc).join(" + ")}`;
        why = `${base} · confidence ${CARTS.pct(r.confidence, 0)} · lift ${CARTS.num(r.lift, 1)}` +
              (r.rules_fired > 1 ? ` · ${r.rules_fired} rules agree` : "");
      }
      return `<div class="rec flash">
        <div class="line-main"><span class="mini-icon" style="--tint:${CARTS.colorFor(r.category)}" aria-hidden="true">${CARTS.iconFor(r.item, r.category)}</span>
          <div><strong>${CARTS.esc(r.item)}</strong> <span class="small muted">${CARTS.money(r.selling_price)}</span></div></div>
        <button class="btn small" data-add-rec="${CARTS.esc(r.item)}">Add</button>
        <div class="why">${why}</div>
      </div>`;
    }).join("");
  }

  async function checkout() {
    const btn = $("checkout");
    await CARTS.busy(btn, async () => {
      try {
        const res = await CARTS.api("/api/checkout", {
          json: { lines: state.cart, strategy: state.strategy, recommended: [...state.shownRecs] },
        });
        const n = res.accepted.length;
        CARTS.toast(`Order #${res.order.id} placed: ${CARTS.money(res.order.total)}` +
                    (n ? ` (${n} recommended item${n > 1 ? "s" : ""} bought)` : ""));
        state.cart = []; state.shownRecs.clear();
        saveCart(); renderCart(); loadRecs();
      } catch (e) { CARTS.toast(e.message, true); }
    });
  }

  // ------------------------------------------------------------------ events
  let searchTimer;
  $("search").addEventListener("input", e => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { state.query = e.target.value.trim(); state.shown = PAGE; loadProducts(); }, 200);
  });
  $("sort").addEventListener("change", e => { state.sort = e.target.value; loadProducts(); });
  $("categories").addEventListener("click", e => {
    const c = e.target.closest("[data-c]");
    if (!c) return;
    state.category = c.dataset.c; state.shown = PAGE; loadProducts();
  });
  $("more").addEventListener("click", () => { state.shown += PAGE; renderProducts(); });
  $("products").addEventListener("click", e => {
    const b = e.target.closest("[data-add]");
    if (b) addToCart(b.dataset.add);
  });
  $("recs").addEventListener("click", e => {
    const b = e.target.closest("[data-add-rec]");
    if (b) addToCart(b.dataset.addRec, true);
  });
  $("cart").addEventListener("click", e => {
    const inc = e.target.closest("[data-inc]"), dec = e.target.closest("[data-dec]");
    if (inc) state.cart[+inc.dataset.inc].qty += 1;
    else if (dec) {
      const i = +dec.dataset.dec;
      state.cart[i].qty -= 1;
      if (state.cart[i].qty <= 0) { state.cart.splice(i, 1); refreshRecs(); }
    } else return;
    saveCart(); renderCart();
  });
  $("clear-cart").addEventListener("click", () => { state.cart = []; saveCart(); renderCart(); refreshRecs(); });
  $("checkout").addEventListener("click", checkout);
  $("strategy").addEventListener("click", e => {
    const b = e.target.closest("[data-s]");
    if (!b) return;
    state.strategy = b.dataset.s;
    localStorage.setItem("carts.strategy", state.strategy);
    document.querySelectorAll("#strategy button").forEach(x => x.classList.toggle("on", x === b));
    loadRecs();
  });
  document.querySelectorAll("#strategy button").forEach(x => x.classList.toggle("on", x.dataset.s === state.strategy));

  // ------------------------------------------------------------------ boot
  (async () => {
    try {
      const stats = await CARTS.api("/api/stats");
      CARTS.setDataset(stats.dataset);
      const all = await CARTS.api("/api/products");
      all.products.forEach(p => state.byName.set(p.item, p));
      const sold = all.products.map(p => p.times_sold).sort((a, b) => b - a);
      state.bestsellerCut = sold[Math.max(0, Math.floor(sold.length * 0.05) - 1)] ?? Infinity;
      await loadProducts();
      // drop cart lines for products that no longer exist (e.g. after a dataset change)
      state.cart = state.cart.filter(l => state.byName.has(l.item));
      saveCart(); renderCart(); loadRecs();
    } catch (e) { CARTS.toast(e.message, true); }
  })();
})();
