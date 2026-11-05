"""CARTS web app: a shop page that recommends while you fill your cart, and an analytics dashboard.

Run:
    pip install -r requirements.txt
    python app.py            # http://127.0.0.1:5000
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from carts_engine import (STRATEGIES, CartsEngine, Config, OrderStore, evaluate,
                          load_item_master, load_transactions)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
INSTANCE = Path(os.environ.get("CARTS_INSTANCE", ROOT / "instance"))
DEFAULT_TRANSACTIONS = DATA / "transactions.csv"
DEFAULT_ITEM_MASTER = DATA / "item_master.csv"
STATE_FILE = INSTANCE / "state.json"
DEFAULT_META = json.loads((DATA / "dataset.json").read_text(encoding="utf-8")) if (DATA / "dataset.json").exists() else {}


class State:
    """Holds the trained engine; retraining swaps it atomically under a lock."""

    def __init__(self) -> None:
        INSTANCE.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.store = OrderStore(INSTANCE / "carts.db")
        saved = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
        self.config = Config.from_dict(saved.get("config") or DEFAULT_META.get("defaults", {}))
        self.include_orders = bool(saved.get("include_orders", True))
        self.meta = saved.get("meta") or DEFAULT_META
        tx_path = INSTANCE / "transactions.csv"
        im_path = INSTANCE / "item_master.csv"
        self.transactions_path = tx_path if tx_path.exists() else DEFAULT_TRANSACTIONS
        self.item_master_path = im_path if im_path.exists() else DEFAULT_ITEM_MASTER
        self.evaluation = None
        self.train()

    def train(self) -> None:
        with self.lock:
            base = load_transactions(self.transactions_path)
            extra = self.store.baskets() if self.include_orders else []
            item_master = load_item_master(self.item_master_path)
            self.engine = CartsEngine(base + extra, item_master, self.config).fit()
            self.base_size, self.order_baskets = len(base), len(extra)
            self.evaluation = None

    def save(self) -> None:
        STATE_FILE.write_text(json.dumps({
            "config": self.config.to_dict(),
            "include_orders": self.include_orders,
            "meta": self.meta,
        }, indent=2))

    def persist_prices(self) -> None:
        cols = [c for c in ("item", "category", "cost_price", "selling_price", "units_sold", "revenue")
                if c in self.engine.items]
        self.engine.items[cols].to_csv(INSTANCE / "item_master.csv", index=False)
        self.item_master_path = INSTANCE / "item_master.csv"


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
state = State()


def _error(message: str, status: int = 400):
    return jsonify({"error": message}), status


# ------------------------------------------------------------------------- pages

@app.get("/")
def shop():
    return render_template("shop.html", active="shop")


@app.get("/dashboard")
def dashboard():
    return render_template("dashboard.html", active="dashboard")


# ------------------------------------------------------------------------- shop API

@app.get("/api/products")
def products():
    items = state.engine.catalog()
    q = request.args.get("q", "").strip().lower()
    category = request.args.get("category", "")
    if q:
        items = [i for i in items if q in i["item"].lower()]
    if category:
        items = [i for i in items if i["category"] == category]
    sort = request.args.get("sort", "popular")
    keys = {"popular": lambda i: -i["times_sold"], "name": lambda i: i["item"].lower(),
            "price": lambda i: i["selling_price"], "margin": lambda i: -i["margin_pct"]}
    items.sort(key=keys.get(sort, keys["popular"]))
    categories = sorted({i["category"] for i in state.engine.catalog()})
    return jsonify({"products": items, "categories": categories})


@app.post("/api/recommend")
def recommend():
    body = request.get_json(silent=True) or {}
    cart = body.get("cart", [])
    strategy = body.get("strategy", "carts")
    if strategy not in STRATEGIES:
        return _error(f"strategy must be one of {list(STRATEGIES)}")
    top_n = int(min(max(int(body.get("top_n", 5)), 1), 20))
    with state.lock:
        return jsonify({"strategy": strategy, "recommendations": state.engine.recommend(cart, strategy, top_n)})


@app.post("/api/compare")
def compare():
    body = request.get_json(silent=True) or {}
    cart = body.get("cart", [])
    with state.lock:
        return jsonify({s: state.engine.recommend(cart, s, 5) for s in STRATEGIES})


@app.post("/api/checkout")
def checkout():
    body = request.get_json(silent=True) or {}
    lines_in = body.get("lines", [])
    if not lines_in:
        return _error("Cart is empty")
    strategy = body.get("strategy", "carts")
    recommended = [str(x) for x in body.get("recommended", [])]
    with state.lock:
        lines = []
        for line in lines_in:
            name = state.engine.resolve(line.get("item", ""))
            if not name:
                return _error(f"Unknown product: {line.get('item')}")
            qty = int(min(max(int(line.get("qty", 1)), 1), 99))
            p = state.engine.product(name)
            lines.append({"item": name, "qty": qty, "price": p["selling_price"], "profit": p["profit_rs"]})
        bought = {l["item"] for l in lines}
        accepted = [r for r in recommended if r in bought]
        order = state.store.add(lines, strategy if strategy in STRATEGIES else "carts", recommended, accepted)
    return jsonify({"order": order, "accepted": accepted})


# ------------------------------------------------------------------------- dashboard API

@app.get("/api/stats")
def stats():
    with state.lock:
        s = state.engine.stats()
        s.update(dataset=state.meta, base_transactions=state.base_size,
                 order_transactions=state.order_baskets, include_orders=state.include_orders,
                 orders=state.store.summary())
    return jsonify(s)


@app.get("/api/rules")
def rules():
    strategy = request.args.get("strategy", "carts")
    if strategy not in STRATEGIES:
        return _error("bad strategy")
    limit = int(min(max(int(request.args.get("limit", 50)), 1), 1000))
    with state.lock:
        return jsonify(state.engine.rules_table(strategy, request.args.get("q", ""), limit))


@app.get("/api/items")
def items():
    with state.lock:
        return jsonify(state.engine.catalog())


@app.put("/api/items/<path:name>")
def update_item(name: str):
    body = request.get_json(silent=True) or {}
    try:
        cp = float(body["cost_price"]) if "cost_price" in body else None
        sp = float(body["selling_price"]) if "selling_price" in body else None
    except (TypeError, ValueError):
        return _error("Prices must be numbers")
    if (cp is not None and cp <= 0) or (sp is not None and sp <= 0):
        return _error("Prices must be positive")
    with state.lock:
        try:
            item = state.engine.update_item(name, cp, sp, body.get("category"))
        except KeyError:
            return _error("Unknown product", 404)
        state.persist_prices()
        state.evaluation = None
    return jsonify(item)


@app.get("/api/evaluate")
def run_evaluation():
    with state.lock:
        if state.evaluation is not None and not request.args.get("refresh"):
            return jsonify(state.evaluation)
        engine, config = state.engine, state.config
        transactions, items = engine.transactions, engine.items.copy()
    # runs outside the lock (a few seconds) so the shop stays responsive
    result = evaluate(transactions, items, config)
    with state.lock:
        if state.engine is engine:
            state.evaluation = result
    return jsonify(result)


@app.get("/api/orders")
def orders():
    return jsonify(state.store.list(limit=int(request.args.get("limit", 25))))


@app.delete("/api/orders")
def clear_orders():
    state.store.clear()
    state.train()
    return jsonify({"ok": True})


@app.post("/api/config")
def update_config():
    body = request.get_json(silent=True) or {}
    try:
        current = state.config.to_dict()
        merged = {**current, **{k: v for k, v in body.items() if k not in ("include_orders", "rule_weights", "item_weights")}}
        for group in ("rule_weights", "item_weights"):
            merged[group] = {**current[group], **(body.get(group) or {})}
        new_config = Config.from_dict(merged)
    except (TypeError, ValueError) as exc:
        return _error(f"Invalid config: {exc}")
    with state.lock:
        old = state.config
        state.config = new_config
        if "include_orders" in body:
            state.include_orders = bool(body["include_orders"])
        try:
            state.train()
        except Exception as exc:  # e.g. support too low -> memory blow-up
            state.config = old
            state.train()
            return _error(f"Training failed: {exc}")
        state.save()
    return stats()


@app.post("/api/dataset")
def upload_dataset():
    tx_file = request.files.get("transactions")
    im_file = request.files.get("item_master")
    if not tx_file and not im_file:
        return _error("Upload a transactions file and/or an item master")
    with state.lock:
        old = (state.transactions_path, state.item_master_path, state.meta)
        try:
            if tx_file:
                transactions = load_transactions(tx_file)
                if len(transactions) < 10:
                    return _error("Found fewer than 10 transactions in that file")
                path = INSTANCE / "transactions.csv"
                import csv
                with path.open("w", newline="", encoding="utf-8") as fh:
                    csv.writer(fh).writerows(transactions)
                state.transactions_path = path
                state.meta = {"name": f"{tx_file.filename} ({len(transactions):,} baskets)",
                              "currency": request.form.get("currency") or state.meta.get("currency", ""),
                              "source": "Uploaded by user", "notes": ""}
            if im_file:
                im = load_item_master(im_file)
                im[[c for c in ("item", "category", "cost_price", "selling_price", "units_sold", "revenue") if c in im]].to_csv(INSTANCE / "item_master.csv", index=False)
                state.item_master_path = INSTANCE / "item_master.csv"
            state.train()
        except Exception as exc:
            state.transactions_path, state.item_master_path, state.meta = old
            state.train()
            return _error(f"Could not load dataset: {exc}")
        state.save()
    return stats()


@app.post("/api/dataset/reset")
def reset_dataset():
    with state.lock:
        for f in ("transactions.csv", "item_master.csv"):
            (INSTANCE / f).unlink(missing_ok=True)
        state.transactions_path, state.item_master_path = DEFAULT_TRANSACTIONS, DEFAULT_ITEM_MASTER
        state.meta = DEFAULT_META
        state.config = Config.from_dict(DEFAULT_META.get("defaults", {}))
        state.train()
        state.save()
    return stats()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=bool(os.environ.get("FLASK_DEBUG")))
