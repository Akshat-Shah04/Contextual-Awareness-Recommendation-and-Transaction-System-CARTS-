/* Dashboard: dataset KPIs, evaluation, rules explorer, model settings, item master, orders. */
(() => {
  const $ = id => document.getElementById(id);
  const charts = {};
  const GREEN = "#1f7a5c", BLUE = "#3d5a9e", GREY = "#c5cad3";
  const RULE_W = { support: "w_s · support", confidence: "w_c · confidence", lift: "w_l · lift", conviction: "w_v · conviction" };
  const ITEM_W = { profit: "α_p · profit / unit", margin: "α_m · margin %", frequency: "α_f · frequency", revenue: "α_r · revenue" };
  const DEFAULTS = {
    min_support: 0.01, min_confidence: 0.2, max_len: 3,
    rule_weights: { support: 0.25, confidence: 0.35, lift: 0.25, conviction: 0.15 },
    item_weights: { profit: 0.35, margin: 0.25, frequency: 0.2, revenue: 0.2 },
  };
  let stats, ruleStrategy = "carts", items = [];

  if (window.Chart) {
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.color = "#677285";
    Chart.defaults.plugins.legend.labels.boxWidth = 12;
  }

  function chart(id, config) {
    if (!window.Chart) { $(id).parentElement.innerHTML = `<div class="empty">Charts need internet access (Chart.js CDN).</div>`; return; }
    charts[id]?.destroy();
    charts[id] = new Chart($(id), { ...config, options: { responsive: true, maintainAspectRatio: false, ...config.options } });
  }

  // ------------------------------------------------------------------ KPIs & charts
  function renderStats() {
    CARTS.setDataset(stats.dataset);
    const o = stats.orders;
    const shown = Object.values(o.by_strategy).reduce((s, x) => s + x.shown, 0);
    const accepted = Object.values(o.by_strategy).reduce((s, x) => s + x.accepted, 0);
    const kpis = [
      ["Baskets", CARTS.num(stats.transactions), stats.order_transactions ? `incl. ${stats.order_transactions} shop orders` : "training transactions"],
      ["Products", CARTS.num(stats.products), stats.estimated_prices ? `${stats.estimated_prices} with fill-in prices` : "with prices"],
      ["Avg basket size", CARTS.num(stats.avg_basket, 1), "distinct items per basket"],
      ["Association rules", CARTS.num(stats.rules), `${CARTS.num(stats.frequent_itemsets)} frequent itemsets · ${stats.fit_seconds}s`],
      ["Shop orders", CARTS.num(o.orders), `${CARTS.money(o.revenue)} revenue`],
      ["Rec. acceptance", shown ? CARTS.pct(accepted / shown) : "–", `${accepted} of ${shown} suggestions bought`],
    ];
    $("kpis").innerHTML = kpis.map(([l, v, s]) =>
      `<div class="card kpi"><div class="label">${l}</div><div class="value num">${v}</div><div class="sub">${s}</div></div>`).join("");
    $("top20").textContent = `Only ${CARTS.pct(stats.top20_rule_overlap, 0)} of the top-20 rules are the same under both rankings.`;
    $("train-info").textContent = `${CARTS.num(stats.rules)} rules from ${CARTS.num(stats.transactions)} baskets`;

    chart("top-items", {
      type: "bar",
      data: { labels: stats.top_items.map(x => x.item), datasets: [{ data: stats.top_items.map(x => x.count), backgroundColor: GREEN, borderRadius: 4 }] },
      options: { indexAxis: "y", plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => `${CARTS.num(c.raw)} baskets` } } },
                 scales: { y: { ticks: { autoSkip: false, font: { size: 11 } } } } },
    });
    chart("categories", {
      type: "bar",
      data: {
        labels: stats.categories.map(c => c.category),
        datasets: [
          { label: "Revenue", data: stats.categories.map(c => c.revenue), backgroundColor: BLUE, borderRadius: 4 },
          { label: "Est. profit", data: stats.categories.map(c => c.profit), backgroundColor: GREEN, borderRadius: 4 },
        ],
      },
      options: { plugins: { tooltip: { callbacks: { label: c => `${c.dataset.label}: ${CARTS.money(c.raw)}` } } },
                 scales: { y: { ticks: { callback: v => CARTS.currency + Number(v).toLocaleString() } } } },
    });
    chart("basket-sizes", {
      type: "bar",
      data: { labels: stats.basket_sizes.labels, datasets: [{ data: stats.basket_sizes.counts, backgroundColor: BLUE, borderRadius: 3 }] },
      options: { plugins: { legend: { display: false } }, scales: { x: { title: { display: true, text: "items in basket" } } } },
    });
  }

  // ------------------------------------------------------------------ evaluation
  async function loadEvaluation(refresh = false) {
    $("eval-cards").innerHTML = `<div class="empty" style="grid-column:1/-1">Running evaluation…</div>`;
    try {
      const ev = await CARTS.api(`/api/evaluate${refresh ? "?refresh=1" : ""}`);
      const c = ev.strategies.carts, a = ev.strategies.apriori;
      const metrics = [
        ["Hit rate @5", "hit_rate", v => CARTS.pct(v)],
        ["Avg profit of suggestions", "avg_profit", v => CARTS.money(v)],
        ["Avg margin of suggestions", "avg_margin_pct", v => `${CARTS.num(v, 1)}%`],
        ["Profit of correct hits / 100 baskets", "profit_per_100_baskets", v => CARTS.money(v)],
      ];
      $("eval-cards").innerHTML = metrics.map(([label, key, fmt]) => {
        const diff = a[key] ? (c[key] - a[key]) / Math.abs(a[key]) : 0;
        const cls = diff > 0.005 ? "rank-up" : diff < -0.005 ? "rank-down" : "muted";
        return `<div class="card"><div class="small muted">${label}</div>
          <div><b style="color:${GREEN}">CARTS ${fmt(c[key])}</b> · <span style="color:${BLUE}">Apriori ${fmt(a[key])}</span></div>
          <div class="small ${cls}">${diff >= 0 ? "+" : ""}${(diff * 100).toFixed(1)}% vs Apriori</div></div>`;
      }).join("");
      // index chart: Apriori = 100 for every metric, so different units share one axis
      const idx = metrics.map(([, key]) => (a[key] ? (c[key] / a[key]) * 100 : 100));
      chart("eval-chart", {
        type: "bar",
        data: {
          labels: metrics.map(([label]) => label),
          datasets: [
            { label: "CARTS", backgroundColor: GREEN, borderRadius: 4, data: idx },
            { label: "Apriori (= 100)", backgroundColor: GREY, borderRadius: 4, data: metrics.map(() => 100) },
          ],
        },
        options: {
          plugins: { tooltip: { callbacks: { label: x => {
            const [, key, fmt] = metrics[x.dataIndex];
            const raw = x.datasetIndex === 0 ? c[key] : a[key];
            return `${x.dataset.label.split(" ")[0]}: ${fmt(raw)} (index ${Number(x.raw).toFixed(0)})`;
          } } } },
          scales: { y: { suggestedMin: 60, title: { display: true, text: "index, Apriori = 100" } } },
        },
      });
    } catch (e) {
      $("eval-cards").innerHTML = `<div class="empty" style="grid-column:1/-1">${CARTS.esc(e.message)}</div>`;
    }
  }

  // ------------------------------------------------------------------ rules
  async function loadRules() {
    const q = $("rule-q").value.trim();
    const rules = await CARTS.api(`/api/rules?strategy=${ruleStrategy}&limit=200&q=${encodeURIComponent(q)}`);
    $("rules").innerHTML = rules.length ? rules.map(r => {
      const delta = r.apriori_rank - r.carts_rank;
      const cls = delta > 0 ? "rank-up" : delta < 0 ? "rank-down" : "muted";
      return `<tr>
        <td>${r.antecedents.map(CARTS.esc).join(" + ")}<span class="arrow">→</span><b>${CARTS.esc(r.consequent)}</b></td>
        <td class="r num">${CARTS.pct(r.support, 2)}</td><td class="r num">${CARTS.pct(r.confidence)}</td>
        <td class="r num">${CARTS.num(r.lift, 2)}</td><td class="r num">${CARTS.num(r.rule_strength, 3)}</td>
        <td class="r num">${CARTS.num(r.business_factor, 3)}</td><td class="r num">${CARTS.money(r.profit_rs)}</td>
        <td class="r num">${CARTS.num(r.carts_score, 3)}</td>
        <td class="r num ${cls}" title="${delta > 0 ? "moved up" : delta < 0 ? "moved down" : "same"} vs Apriori">${r.carts_rank}</td>
        <td class="r num">${r.apriori_rank}</td></tr>`;
    }).join("") : `<tr><td colspan="10" class="empty">No rules. Try lowering min support or min confidence.</td></tr>`;
  }

  // ------------------------------------------------------------------ settings
  function slider(group, key, label, value) {
    return `<div class="field"><label>${label} <span id="v-${group}-${key}">${Number(value).toFixed(2)}</span></label>
      <input type="range" min="0" max="1" step="0.05" value="${value}" data-group="${group}" data-key="${key}"></div>`;
  }

  function renderSettings(cfg) {
    for (const k of ["min_support", "min_confidence", "max_len"]) {
      $(k).value = cfg[k];
      $(`v-${k}`).textContent = k === "max_len" ? cfg[k] : CARTS.pct(cfg[k], k === "min_support" ? 1 : 0);
    }
    $("include_orders").checked = stats.include_orders;
    $("rule-weights").innerHTML = Object.entries(RULE_W).map(([k, l]) => slider("rule_weights", k, l, cfg.rule_weights[k])).join("");
    $("item-weights").innerHTML = Object.entries(ITEM_W).map(([k, l]) => slider("item_weights", k, l, cfg.item_weights[k])).join("");
  }

  function readSettings() {
    const body = {
      min_support: +$("min_support").value, min_confidence: +$("min_confidence").value, max_len: +$("max_len").value,
      include_orders: $("include_orders").checked, rule_weights: {}, item_weights: {},
    };
    document.querySelectorAll("input[data-group]").forEach(i => { body[i.dataset.group][i.dataset.key] = +i.value; });
    return body;
  }

  async function retrain(body, button) {
    await CARTS.busy(button, async () => {
      try {
        stats = await CARTS.api("/api/config", { json: body });
        renderAll();
        CARTS.toast(`Retrained: ${CARTS.num(stats.rules)} rules`);
      } catch (e) { CARTS.toast(e.message, true); }
    });
  }

  // ------------------------------------------------------------------ dataset
  function renderDataset() {
    const d = stats.dataset || {};
    const s = d.stats || {};
    $("dataset-info").innerHTML = `
      <div><b>${CARTS.esc(d.name || "Custom dataset")}</b></div>
      ${d.source ? `<div class="muted" style="margin-top:4px">Source: ${CARTS.esc(d.source)}</div>` : ""}
      ${d.kaggle ? `<div><a href="${CARTS.esc(d.kaggle)}" target="_blank" rel="noopener">Kaggle mirror</a> · ${CARTS.esc(d.license || "")}</div>` : ""}
      ${s.period ? `<div class="muted">${CARTS.esc(s.period)} · ${CARTS.num(s.raw_lines)} raw invoice lines</div>` : ""}
      ${d.notes ? `<div style="margin-top:6px"><span class="pill warn">note</span> ${CARTS.esc(d.notes)}</div>` : ""}`;
  }

  // ------------------------------------------------------------------ orders
  async function loadOrders() {
    const orders = await CARTS.api("/api/orders?limit=50");
    const by = stats.orders.by_strategy;
    $("order-summary").innerHTML = Object.keys(by).length ? Object.entries(by).map(([s, x]) =>
      `<span class="pill ${s === "carts" ? "green" : "blue"}">${s.toUpperCase()}</span> ${x.orders} orders · ${CARTS.money(x.revenue)} ·
       acceptance ${CARTS.pct(x.acceptance_rate)} · profit from accepted recs ${CARTS.money(x.rec_profit)}`).join("<br>")
      : `<span class="muted">No orders yet. Place one from the Shop page.</span>`;
    $("orders").innerHTML = orders.map(o => `<tr>
      <td class="num">${o.id}</td>
      <td>${o.items.map(l => `${CARTS.esc(l.item)}${l.qty > 1 ? ` ×${l.qty}` : ""}`).join(", ")}</td>
      <td><span class="pill ${o.strategy === "carts" ? "green" : "blue"}">${o.strategy}</span></td>
      <td class="r num">${CARTS.money(o.total)}</td>
      <td class="r num">${o.accepted.length}/${o.recommended.length}</td></tr>`).join("") ||
      `<tr><td colspan="5" class="empty">–</td></tr>`;
  }

  // ------------------------------------------------------------------ item master
  async function loadItems() {
    items = await CARTS.api("/api/items");
    renderItems();
  }

  function renderItems() {
    const q = $("item-q").value.trim().toLowerCase();
    const list = items.filter(i => !q || i.item.toLowerCase().includes(q) || i.category.toLowerCase().includes(q))
      .sort((a, b) => b.times_sold - a.times_sold).slice(0, 300);
    $("item-note").textContent = `${items.length} products. Selling prices come from the data; cost prices are estimates `
      + `unless you edit them. Saving rescores every rule immediately.`;
    $("items").innerHTML = list.map(i => `<tr data-item="${CARTS.esc(i.item)}">
      <td>${CARTS.esc(i.item)} ${i.estimated ? '<span class="pill warn">fill-in price</span>' : ""}</td>
      <td class="small">${CARTS.esc(i.category)}</td>
      <td class="r"><input class="cell-input num" type="number" step="0.01" min="0.01" name="cost_price" value="${i.cost_price}" aria-label="Cost price"></td>
      <td class="r"><input class="cell-input num" type="number" step="0.01" min="0.01" name="selling_price" value="${i.selling_price}" aria-label="Selling price"></td>
      <td class="r num">${CARTS.money(i.profit_rs)}</td><td class="r num">${CARTS.num(i.margin_pct, 1)}%</td>
      <td class="r num">${CARTS.num(i.times_sold)}</td><td class="r num">${CARTS.num(i.business_factor, 3)}</td>
      <td><button class="btn small" data-save>Save</button></td></tr>`).join("");
  }

  // ------------------------------------------------------------------ wiring
  function renderAll() {
    renderStats(); renderSettings(stats.config); renderDataset();
    loadRules(); loadItems(); loadOrders(); loadEvaluation();
  }

  document.addEventListener("input", e => {
    const t = e.target;
    if (t.dataset.group) $(`v-${t.dataset.group}-${t.dataset.key}`).textContent = Number(t.value).toFixed(2);
    else if (["min_support", "min_confidence", "max_len"].includes(t.id))
      $(`v-${t.id}`).textContent = t.id === "max_len" ? t.value : CARTS.pct(t.value, t.id === "min_support" ? 1 : 0);
  });
  $("retrain").addEventListener("click", e => retrain(readSettings(), e.currentTarget));
  $("reset-settings").addEventListener("click", e => retrain({ ...DEFAULTS, include_orders: true }, e.currentTarget));
  $("eval-refresh").addEventListener("click", e => CARTS.busy(e.currentTarget, () => loadEvaluation(true)));
  let rq;
  $("rule-q").addEventListener("input", () => { clearTimeout(rq); rq = setTimeout(loadRules, 200); });
  $("rule-strategy").addEventListener("click", e => {
    const b = e.target.closest("[data-s]");
    if (!b) return;
    ruleStrategy = b.dataset.s;
    document.querySelectorAll("#rule-strategy button").forEach(x => x.classList.toggle("on", x === b));
    loadRules();
  });
  $("item-q").addEventListener("input", renderItems);
  $("items").addEventListener("click", async e => {
    const btn = e.target.closest("[data-save]");
    if (!btn) return;
    const row = btn.closest("tr");
    const body = {
      cost_price: +row.querySelector("[name=cost_price]").value,
      selling_price: +row.querySelector("[name=selling_price]").value,
    };
    await CARTS.busy(btn, async () => {
      try {
        await CARTS.api(`/api/items/${encodeURIComponent(row.dataset.item)}`, { method: "PUT", json: body });
        CARTS.toast(`Saved ${row.dataset.item}; rules rescored`);
        stats = await CARTS.api("/api/stats");
        renderStats(); loadRules(); loadItems(); loadEvaluation();
      } catch (err) { CARTS.toast(err.message, true); }
    });
  });
  $("upload").addEventListener("submit", async e => {
    e.preventDefault();
    const form = new FormData(e.target);
    if (!form.get("transactions").size && !form.get("item_master").size) { CARTS.toast("Choose a file first", true); return; }
    await CARTS.busy(e.submitter, async () => {
      try {
        stats = await CARTS.api("/api/dataset", { method: "POST", body: form });
        renderAll();
        CARTS.toast("Dataset loaded and model retrained");
        e.target.reset();
      } catch (err) { CARTS.toast(err.message, true); }
    });
  });
  $("reset-dataset").addEventListener("click", async e => {
    await CARTS.busy(e.currentTarget, async () => {
      stats = await CARTS.api("/api/dataset/reset", { method: "POST" });
      renderAll();
      CARTS.toast("Default dataset restored");
    });
  });
  $("clear-orders").addEventListener("click", async () => {
    if (!confirm("Delete all shop orders?")) return;
    await CARTS.api("/api/orders", { method: "DELETE" });
    stats = await CARTS.api("/api/stats");
    renderStats(); loadOrders();
  });

  (async () => {
    try { stats = await CARTS.api("/api/stats"); renderAll(); }
    catch (e) { CARTS.toast(e.message, true); }
  })();
})();
