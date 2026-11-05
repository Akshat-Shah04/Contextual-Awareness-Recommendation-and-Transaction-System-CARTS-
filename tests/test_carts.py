"""Tests for the CARTS engine, data loaders and web API.  Run: pytest -q"""

import importlib
import io
import math
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from carts_engine import CartsEngine, Config, evaluate, load_item_master, parse_transactions  # noqa: E402
from carts_engine.engine import squash  # noqa: E402

# Toy data from Table I / II of the CARTS paper
BASKETS = [
    ["Milk", "Bread", "Biscuits"], ["Tea", "Biscuits"], ["Rice", "Oil"], ["Juice", "Biscuits"],
    ["Milk", "Bread"], ["Tea", "Bread", "Biscuits"], ["Rice", "Oil", "Tea"], ["Juice", "Tea", "Biscuits"],
    ["Milk", "Rice"], ["Bread", "Tea", "Biscuits"],
]
ITEMS = pd.DataFrame({
    "item": ["Milk", "Bread", "Rice", "Oil", "Biscuits", "Tea", "Juice"],
    "cost_price": [40, 20, 60, 100, 15, 150, 30],
    "selling_price": [44, 25, 75, 120, 25, 180, 40],
})


@pytest.fixture()
def engine():
    return CartsEngine(BASKETS, load_item_master(io.StringIO(ITEMS.to_csv(index=False))),
                       Config(min_support=0.1, min_confidence=0.3)).fit()


# ------------------------------------------------------------------ data loading

def test_parse_headerless_baskets():
    assert parse_transactions("milk,bread\neggs\n\nmilk, milk ,jam\n") == [["milk", "bread"], ["eggs"], ["milk", "jam"]]


def test_parse_wide_table_drops_count_column():
    text = "Item(s),Item 1,Item 2,Item 3\n2,citrus fruit,margarine,\n1,whole milk,,\n"
    assert parse_transactions(text) == [["citrus fruit", "margarine"], ["whole milk"]]


def test_parse_kaggle_long_format_groups_by_member_and_date():
    text = ("Member_number,Date,itemDescription\n"
            "1,01-01-2015,milk\n1,01-01-2015,bread\n2,01-01-2015,eggs\n1,02-01-2015,jam\n1,01-01-2015,milk\n")
    assert sorted(parse_transactions(text)) == [["eggs"], ["jam"], ["milk", "bread"]]


def test_item_master_aliases_and_financials():
    df = load_item_master(io.StringIO("Item Names,Cost Price (C.P),Selling Price (S.P.)\nMilk,40,44\n"))
    row = df.iloc[0]
    assert row["profit_rs"] == 4
    assert row["profit_pct"] == 10.0          # on cost, as in the paper
    assert row["margin_pct"] == pytest.approx(9.09, abs=0.01)  # on selling price


def test_missing_prices_are_filled_and_flagged():
    im = load_item_master(io.StringIO("item,cp,sp\nMilk,40,44\n"))
    e = CartsEngine([["Milk", "Bread"], ["Milk"]], im, Config(min_support=0.5)).fit()
    bread = e.product("Bread")
    assert bread["estimated"] is True and bread["selling_price"] == 44


# ------------------------------------------------------------------ formula

def test_squash_is_zscore_through_logistic():
    s = squash(pd.Series([1.0, 2.0, 3.0]))
    assert s.iloc[1] == pytest.approx(0.5)
    assert s.iloc[2] == pytest.approx(1 / (1 + math.exp(-1.224744871)), rel=1e-6)
    assert squash(pd.Series([5.0, 5.0])).tolist() == [0.5, 0.5]


def test_carts_score_is_rule_strength_times_business_factor(engine):
    r = engine.rules
    assert len(r) > 0
    assert (r["carts_score"] - r["rule_strength"] * r["business_factor"]).abs().max() < 1e-12
    assert ((r["rule_strength"] > 0) & (r["rule_strength"] < 1)).all()
    assert (r["apriori_score"] == r["support"] * r["confidence"]).all()


def test_recommendation_sums_over_firing_rules(engine):
    recs = engine.recommend(["Tea", "Bread"], "carts", top_n=3)
    assert recs[0]["item"] == "Biscuits"   # paper: {Tea, Bread} -> Biscuits
    r = engine.rules
    fired = r[(r["consequent"] == "Biscuits") & r["antecedent_set"].map(lambda a: a <= {"Tea", "Bread"})]
    expected = fired["rule_strength"].sum() * engine.product("Biscuits")["business_factor"]
    assert recs[0]["score"] == pytest.approx(expected, abs=1e-4)
    assert recs[0]["rules_fired"] == len(fired)


def test_never_recommends_items_already_in_cart(engine):
    for strategy in ("carts", "apriori"):
        names = [r["item"] for r in engine.recommend(["Tea", "Bread", "Biscuits"], strategy, top_n=7)]
        assert not {"Tea", "Bread", "Biscuits"} & set(names)
        assert len(names) == len(set(names)) == 4   # only 4 other products exist


def test_cold_start_and_unknown_items(engine):
    assert all(r["reason"] == "popular" for r in engine.recommend([], "carts", 3))
    assert len(engine.recommend(["does not exist"], "apriori", 3)) == 3


def test_price_change_rescores_rules(engine):
    before = engine.rules.set_index("consequent")["business_factor"].to_dict()
    engine.update_item("Juice", cost_price=5, selling_price=400)
    after = engine.rules.set_index("consequent")["business_factor"].to_dict()
    assert after["Juice"] > before["Juice"]


def test_weights_shift_ranking_towards_profit():
    im = load_item_master(io.StringIO(ITEMS.to_csv(index=False)))
    base = {"min_support": 0.1, "min_confidence": 0.3}
    a = CartsEngine(BASKETS, im, Config.from_dict(
        base | {"item_weights": {"profit": 0, "margin": 0, "frequency": 1, "revenue": 0}})).fit()
    b = CartsEngine(BASKETS, im, Config.from_dict(
        base | {"item_weights": {"profit": 1, "margin": 0, "frequency": 0, "revenue": 0}})).fit()
    # Tea has by far the highest profit per unit (Rs 30)
    assert b.product("Tea")["business_factor"] > a.product("Tea")["business_factor"]


def test_evaluate_runs(engine):
    out = evaluate(BASKETS * 20, engine.items, Config(min_support=0.1, min_confidence=0.3), max_cases=50)
    assert set(out["strategies"]) == {"carts", "apriori"}
    assert 0 <= out["strategies"]["carts"]["hit_rate"] <= 1


# ------------------------------------------------------------------ web API

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CARTS_INSTANCE", str(tmp_path))
    sys.modules.pop("app", None)
    app_module = importlib.import_module("app")
    return app_module.app.test_client()


def test_api_flow(client):
    stats = client.get("/api/stats").get_json()
    assert stats["transactions"] > 1000 and stats["rules"] > 0
    product = client.get("/api/products?sort=popular").get_json()["products"][0]["item"]

    recs = client.post("/api/recommend", json={"cart": [product], "strategy": "carts"}).get_json()["recommendations"]
    assert recs and product not in [r["item"] for r in recs]
    assert client.post("/api/recommend", json={"cart": [], "strategy": "nope"}).status_code == 400

    order = client.post("/api/checkout", json={"lines": [{"item": product, "qty": 2}, {"item": recs[0]["item"]}],
                                               "strategy": "carts", "recommended": [r["item"] for r in recs]}).get_json()
    assert order["accepted"] == [recs[0]["item"]]
    assert client.get("/api/stats").get_json()["orders"]["orders"] == 1
    assert client.post("/api/checkout", json={"lines": [{"item": "nope"}]}).status_code == 400

    s = client.post("/api/config", json={"min_support": 0.02, "item_weights": {"profit": 1}}).get_json()
    assert s["config"]["min_support"] == 0.02 and s["config"]["item_weights"]["profit"] == 1
    assert s["rules"] < stats["rules"]

    updated = client.put(f"/api/items/{product}", json={"cost_price": 0.1}).get_json()
    assert updated["cost_price"] == 0.1
    assert client.put(f"/api/items/{product}", json={"cost_price": -1}).status_code == 400

    rules = client.get("/api/rules?strategy=apriori&limit=5").get_json()
    assert len(rules) <= 5 and rules[0]["apriori_rank"] == 1


def test_upload_kaggle_long_format(client):
    csv = "Member_number,Date,itemDescription\n" + "".join(
        f"{i},01-01-2015,{a}\n{i},01-01-2015,{b}\n" for i in range(40) for a, b in [("milk", "bread")]
    ) + "".join(f"{100 + i},02-01-2015,eggs\n{100 + i},02-01-2015,milk\n" for i in range(20))
    res = client.post("/api/dataset", data={"transactions": (io.BytesIO(csv.encode()), "groceries.csv"), "currency": "$"},
                      content_type="multipart/form-data")
    body = res.get_json()
    assert res.status_code == 200, body
    assert body["transactions"] == 60 and body["dataset"]["currency"] == "$"
    assert client.post("/api/dataset/reset").get_json()["transactions"] > 1000
