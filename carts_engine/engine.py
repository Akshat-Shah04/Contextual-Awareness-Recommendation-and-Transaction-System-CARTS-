"""CARTS scoring engine: Apriori association rules re-ranked by business value.

CARTS score of a candidate item i (the formula in docs/images/carts_formula.png):

    Score(i) = [ sum over r in R(i) of (w_s*s_r + w_c*c_r + w_l*l_r + w_v*v_r) ]
               x (a_p*P_n + a_m*M_n + a_f*F_n + a_r*R_n)

  R(i)  rules A -> i that fire for the current cart (A is fully contained in the cart)
  s_r   support      c_r  confidence      l_r  lift      v_r  conviction
  P_n   profit per unit of i (SP - CP)    M_n  margin % of i ((SP - CP) / SP)
  F_n   frequency of i (share of baskets containing i)
  R_n   revenue of i (real sales revenue when the item master has it, else units x SP)

Every metric is Z-score normalised over all rules (rule metrics) or all items (item
metrics) and squashed to (0, 1) with the logistic function, x_n = 1 / (1 + e^-Z(x)).
The squash keeps both brackets positive, so a negative business factor can never flip
a strong rule's sign, and it limits the pull of extreme outliers (lift and conviction
are heavily skewed). Each weight group is rescaled to sum to 1.

The Apriori baseline ranks items by their best firing rule's Rs = support x confidence,
which is the frequency-only ranking CARTS is compared against.
"""

from __future__ import annotations

import random
import time
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules
from mlxtend.preprocessing import TransactionEncoder

from .data import Transactions, add_financials, align_item_master, item_frequencies

STRATEGIES = ("carts", "apriori")
RULE_COLUMNS = ["antecedent_set", "consequent", "support", "confidence", "lift", "conviction"]


@dataclass
class RuleWeights:
    support: float = 0.25     # w_s
    confidence: float = 0.35  # w_c
    lift: float = 0.25        # w_l
    conviction: float = 0.15  # w_v


@dataclass
class ItemWeights:
    profit: float = 0.35      # a_p
    margin: float = 0.25      # a_m
    frequency: float = 0.20   # a_f
    revenue: float = 0.20     # a_r


def _normalized(weights) -> dict[str, float]:
    d = {k: max(float(v), 0.0) for k, v in asdict(weights).items()}
    total = sum(d.values())
    return {k: v / total for k, v in d.items()} if total > 0 else {k: 1 / len(d) for k in d}


@dataclass
class Config:
    min_support: float = 0.01
    min_confidence: float = 0.2
    min_lift: float = 1.0
    max_len: int = 3
    rule_weights: RuleWeights = field(default_factory=RuleWeights)
    item_weights: ItemWeights = field(default_factory=ItemWeights)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        data = dict(data or {})
        rw = data.pop("rule_weights", None) or {}
        iw = data.pop("item_weights", None) or {}
        known = {k: v for k, v in data.items() if k in ("min_support", "min_confidence", "min_lift", "max_len")}
        cfg = cls(
            **known,
            rule_weights=RuleWeights(**{k: float(v) for k, v in rw.items() if k in RuleWeights.__dataclass_fields__}),
            item_weights=ItemWeights(**{k: float(v) for k, v in iw.items() if k in ItemWeights.__dataclass_fields__}),
        )
        cfg.min_support = min(max(float(cfg.min_support), 0.001), 1.0)
        cfg.min_confidence = min(max(float(cfg.min_confidence), 0.0), 1.0)
        cfg.min_lift = max(float(cfg.min_lift), 0.0)
        cfg.max_len = int(min(max(int(cfg.max_len), 2), 4))
        return cfg


def zscore(values: pd.Series) -> pd.Series:
    values = values.astype(float)
    std = values.std(ddof=0)
    if not np.isfinite(std) or std == 0:
        return pd.Series(0.0, index=values.index)
    return (values - values.mean()) / std


def squash(values: pd.Series) -> pd.Series:
    """Z-score then logistic: maps any metric onto (0, 1) with 0.5 = average."""
    return 1.0 / (1.0 + np.exp(-zscore(values)))


class CartsEngine:
    def __init__(self, transactions: Transactions, item_master: pd.DataFrame, config: Config | None = None):
        if not transactions:
            raise ValueError("No transactions to learn from")
        self.transactions = transactions
        self.config = config or Config()
        self.items = align_item_master(item_master, transactions)
        self._lookup = {name.lower(): name for name in self.items["item"]}
        self.rules = pd.DataFrame(columns=RULE_COLUMNS)
        self.frequent_itemsets = pd.DataFrame()
        self.fit_seconds = 0.0

    # ------------------------------------------------------------------ training
    def fit(self) -> "CartsEngine":
        start = time.perf_counter()
        encoder = TransactionEncoder()
        onehot = pd.DataFrame(encoder.fit(self.transactions).transform(self.transactions), columns=encoder.columns_)
        self.item_support = onehot.mean()

        freq = apriori(onehot, min_support=self.config.min_support, use_colnames=True,
                       max_len=self.config.max_len, low_memory=True)
        self.frequent_itemsets = freq
        rules = pd.DataFrame()
        if len(freq) and (freq["itemsets"].map(len) > 1).any():
            rules = association_rules(freq, metric="confidence", min_threshold=self.config.min_confidence)
            rules = rules[(rules["lift"] >= self.config.min_lift) & (rules["consequents"].map(len) == 1)]
        if len(rules):
            rules = rules.assign(
                antecedent_set=rules["antecedents"].map(frozenset),
                consequent=rules["consequents"].map(lambda s: next(iter(s))),
            )[RULE_COLUMNS].copy()
            conv = rules["conviction"].replace([np.inf, -np.inf], np.nan)
            cap = conv.max() if conv.notna().any() else 1.0
            rules["conviction"] = conv.fillna(cap)  # confidence = 1 -> infinite conviction
        else:
            rules = pd.DataFrame(columns=RULE_COLUMNS)
        self.rules = rules.reset_index(drop=True)
        self.rescore()
        self.fit_seconds = time.perf_counter() - start
        return self

    def rescore(self) -> None:
        """Recompute both brackets of the formula — cheap; call after prices or weights change."""
        iw = _normalized(self.config.item_weights)
        rw = _normalized(self.config.rule_weights)

        items = self.items
        support = items["item"].map(self.item_support).fillna(0.0)
        revenue = items["revenue"] if "revenue" in items and items["revenue"].notna().all() \
            else items["times_sold"] * items["selling_price"]
        items["support"] = support.round(5)
        items["P_n"] = squash(items["profit_rs"])
        items["M_n"] = squash(items["margin_pct"])
        items["F_n"] = squash(support)
        items["R_n"] = squash(revenue)
        items["business_factor"] = (iw["profit"] * items["P_n"] + iw["margin"] * items["M_n"]
                                    + iw["frequency"] * items["F_n"] + iw["revenue"] * items["R_n"])

        r = self.rules
        if r.empty:
            for col in ("rule_strength", "business_factor", "profit_rs", "margin_pct", "rs",
                        "carts_score", "apriori_score", "carts_rank", "apriori_rank"):
                r[col] = pd.Series(dtype=float)
        else:
            factor = items.set_index("item")
            r["rule_strength"] = (rw["support"] * squash(r["support"]) + rw["confidence"] * squash(r["confidence"])
                                  + rw["lift"] * squash(r["lift"]) + rw["conviction"] * squash(r["conviction"]))
            r["business_factor"] = r["consequent"].map(factor["business_factor"])
            r["profit_rs"] = r["consequent"].map(factor["profit_rs"])
            r["margin_pct"] = r["consequent"].map(factor["margin_pct"])
            r["rs"] = r["support"] * r["confidence"]
            r["carts_score"] = r["rule_strength"] * r["business_factor"]
            r["apriori_score"] = r["rs"]
            r["carts_rank"] = r["carts_score"].rank(ascending=False, method="min").astype(int)
            r["apriori_rank"] = r["apriori_score"].rank(ascending=False, method="min").astype(int)
        self._build_matrix()

    def update_item(self, item: str, cost_price: float | None = None, selling_price: float | None = None,
                    category: str | None = None) -> dict:
        name = self.resolve(item)
        if name is None:
            raise KeyError(item)
        idx = self.items.index[self.items["item"] == name][0]
        if cost_price is not None:
            self.items.at[idx, "cost_price"] = float(cost_price)
        if selling_price is not None:
            self.items.at[idx, "selling_price"] = float(selling_price)
        if category:
            self.items.at[idx, "category"] = category
        self.items.at[idx, "estimated"] = False
        self.items = add_financials(self.items)
        self.rescore()
        return self.product(name)

    # ------------------------------------------------------------------ queries
    def resolve(self, name: str) -> str | None:
        return self._lookup.get(str(name).strip().lower())

    def product(self, name: str) -> dict:
        return _clean_record(self.items[self.items["item"] == name].iloc[0].to_dict())

    def recommend(self, cart: list[str], strategy: str = "carts", top_n: int = 5) -> list[dict]:
        """Top-N items for a cart. CARTS sums (rule strength) over all firing rules and multiplies
        by the item's business factor; Apriori takes the best firing rule's support x confidence.
        If too few rules fire, partially matching rules (down-weighted by overlap) and then the
        best items overall fill the list."""
        if strategy not in STRATEGIES:
            raise ValueError(f"strategy must be one of {STRATEGIES}")
        m = self._matrix
        n_items = len(m["vocab"])
        cart_set = {n for n in (self.resolve(c) for c in cart) if n}
        cart_vec = np.zeros(n_items, dtype=np.float32)
        cart_vec[[m["index"][i] for i in cart_set]] = 1
        picks: dict[str, dict] = {}

        if cart_set and m["n_rules"]:
            overlap = (m["antecedents"] @ cart_vec) / m["ante_len"]
            open_rules = cart_vec[m["consequent_idx"]] == 0
            for reason, mask, weight in (
                ("rule", open_rules & (overlap >= 1), np.ones_like(overlap)),
                ("partial rule", open_rules & (overlap > 0) & (overlap < 1), 0.5 * overlap),
            ):
                idx = np.flatnonzero(mask)
                if not idx.size:
                    continue
                cons = m["consequent_idx"][idx]
                if strategy == "carts":
                    contrib = m["rule_strength"][idx] * weight[idx]
                    totals = np.bincount(cons, weights=contrib, minlength=n_items)
                    scores = totals * m["business_factor"]
                else:
                    contrib = m["rs"][idx] * weight[idx]
                    scores = np.zeros(n_items)
                    np.maximum.at(scores, cons, contrib)
                # strongest rule behind each item, for the explanation
                best_rule = {}
                for j, c, v in sorted(zip(idx, cons, contrib), key=lambda t: -t[2]):
                    best_rule.setdefault(c, j)
                fired = np.bincount(cons, minlength=n_items)
                for c in np.argsort(-scores, kind="stable"):
                    if len(picks) >= top_n or scores[c] <= 0:
                        break
                    name = m["vocab"][c]
                    if name in picks:
                        continue
                    row = self._rule_rows[best_rule[c]]
                    picks[name] = {"item": name, "score": round(float(scores[c]), 4), "reason": reason,
                                   "because": row["because"], "rules_fired": int(fired[c]),
                                   "support": row["support"], "confidence": row["confidence"], "lift": row["lift"]}
                if len(picks) >= top_n:
                    break

        if len(picks) < top_n:  # cold start / nothing fired: best items overall
            for name, score, support in m["popular"][strategy]:
                if len(picks) >= top_n:
                    break
                if name in cart_set or name in picks:
                    continue
                picks[name] = {"item": name, "score": score, "reason": "popular", "because": [], "rules_fired": 0,
                               "support": support, "confidence": None, "lift": None}

        return [{**rec, **self._item_info[rec["item"]]} for rec in picks.values()]

    def _build_matrix(self) -> None:
        """Precompute dense rule x item arrays so recommend() is a handful of numpy ops."""
        vocab = list(self.items["item"])
        index = {name: i for i, name in enumerate(vocab)}
        r = self.rules
        ante = np.zeros((len(r), len(vocab)), dtype=np.float32)
        for row_i, a in enumerate(r["antecedent_set"]):
            ante[row_i, [index[x] for x in a]] = 1
        ordering = {"apriori": "support", "carts": "business_factor"}
        self._matrix = {
            "vocab": vocab, "index": index, "n_rules": len(r), "antecedents": ante,
            "ante_len": np.maximum(ante.sum(axis=1), 1),
            "consequent_idx": np.array([index[c] for c in r["consequent"]], dtype=int),
            "rule_strength": r["rule_strength"].to_numpy(dtype=float),
            "rs": r["rs"].to_numpy(dtype=float),
            "business_factor": self.items["business_factor"].to_numpy(dtype=float),
            "popular": {
                s: [(n, round(float(v), 4), round(float(sp), 4)) for n, v, sp in
                    self.items.sort_values(col, ascending=False)[["item", col, "support"]].itertuples(index=False)]
                for s, col in ordering.items()
            },
        }
        self._rule_rows = [
            {"because": sorted(a), "support": round(float(s), 4), "confidence": round(float(cf), 4),
             "lift": round(float(l), 3)}
            for a, s, cf, l in zip(r["antecedent_set"], r["support"], r["confidence"], r["lift"])
        ]
        self._item_info = {
            row["item"]: {"category": row["category"], "selling_price": float(row["selling_price"]),
                          "profit_rs": float(row["profit_rs"]), "profit_pct": float(row["profit_pct"]),
                          "margin_pct": float(row["margin_pct"]),
                          "business_factor": round(float(row["business_factor"]), 4)}
            for row in self.items.to_dict("records")
        }

    def rules_table(self, strategy: str = "carts", query: str = "", limit: int = 100) -> list[dict]:
        if self.rules.empty:
            return []
        r = self.rules
        if query:
            q = query.lower()
            r = r[r["consequent"].str.lower().str.contains(q, regex=False)
                  | r["antecedent_set"].map(lambda a: any(q in x.lower() for x in a))]
        r = r.sort_values(f"{strategy}_score", ascending=False).head(limit)
        cols = ["consequent", "support", "confidence", "lift", "conviction", "rule_strength", "business_factor",
                "profit_rs", "margin_pct", "carts_score", "apriori_score", "carts_rank", "apriori_rank"]
        out = []
        for ant, rec in zip(r["antecedent_set"], r[cols].to_dict("records")):
            rec = _clean_record(rec)
            rec["antecedents"] = sorted(ant)
            out.append(rec)
        return out

    def stats(self) -> dict:
        sizes = pd.Series([len(t) for t in self.transactions])
        freq = item_frequencies(self.transactions)
        items = self.items
        revenue = items["revenue"] if "revenue" in items and items["revenue"].notna().all() \
            else items["times_sold"] * items["selling_price"]
        units = items["units_sold"] if "units_sold" in items and items["units_sold"].notna().all() else items["times_sold"]
        by_cat = (items.assign(revenue_=revenue, profit_=units * items["profit_rs"])
                  .groupby("category").agg(products=("item", "count"), revenue=("revenue_", "sum"),
                                           profit=("profit_", "sum"))
                  .sort_values("revenue", ascending=False))
        hist = sizes.clip(upper=30).value_counts().sort_index()
        overlap = 0.0
        if len(self.rules):
            k = min(20, len(self.rules))
            overlap = len(set(self.rules.nsmallest(k, "apriori_rank").index)
                          & set(self.rules.nsmallest(k, "carts_rank").index)) / k
        return {
            "transactions": len(self.transactions),
            "products": len(items),
            "estimated_prices": int(items["estimated"].sum()),
            "avg_basket": round(float(sizes.mean()), 2),
            "frequent_itemsets": len(self.frequent_itemsets),
            "rules": len(self.rules),
            "fit_seconds": round(self.fit_seconds, 2),
            "top_items": [{"item": i, "count": c} for i, c in freq.most_common(15)],
            "basket_sizes": {"labels": [f"{i}+" if i == 30 else str(i) for i in hist.index], "counts": hist.tolist()},
            "categories": [{"category": c, "products": int(row["products"]), "revenue": round(float(row["revenue"]), 2),
                            "profit": round(float(row["profit"]), 2)} for c, row in by_cat.iterrows()],
            "top20_rule_overlap": round(overlap, 2),
            "config": self.config.to_dict(),
        }

    def catalog(self) -> list[dict]:
        cols = ["item", "category", "cost_price", "selling_price", "profit_rs", "profit_pct", "margin_pct",
                "times_sold", "support", "business_factor", "estimated"]
        return [_clean_record(r) for r in self.items[cols].to_dict("records")]


# ---------------------------------------------------------------------- evaluation

def evaluate(transactions: Transactions, item_master: pd.DataFrame, config: Config,
             test_fraction: float = 0.2, max_cases: int = 1500, top_n: int = 5, seed: int = 7) -> dict:
    """Hold-out evaluation. Train on 80% of baskets; for each sampled test basket hide one
    item and recommend top-N from the rest. Reports, per strategy:
      hit_rate               share of cases where the hidden item was recommended
      avg_margin_pct/profit  what the strategy tends to recommend
      profit_per_100_baskets profit of correctly predicted (i.e. actually bought) items"""
    rng = random.Random(seed)
    data = list(transactions)
    rng.shuffle(data)
    cut = int(len(data) * (1 - test_fraction))
    train, test = data[:cut], [t for t in data[cut:] if len(t) >= 2]
    engine = CartsEngine(train, item_master, config).fit()
    cases = [(b, rng.choice(b)) for b in rng.sample(test, min(max_cases, len(test)))]
    profit = engine.items.set_index("item")["profit_rs"]

    results = {}
    for strategy in STRATEGIES:
        hits, hit_profit, margins, profits = 0, 0.0, [], []
        for basket, hidden in cases:
            recs = engine.recommend([i for i in basket if i != hidden], strategy, top_n)
            margins += [r["margin_pct"] for r in recs]
            profits += [r["profit_rs"] for r in recs]
            if hidden in {r["item"] for r in recs}:
                hits += 1
                hit_profit += float(profit.get(hidden, 0.0))
        n = max(len(cases), 1)
        results[strategy] = {
            "hit_rate": round(hits / n, 4),
            "avg_margin_pct": round(float(np.mean(margins)) if margins else 0.0, 2),
            "avg_profit": round(float(np.mean(profits)) if profits else 0.0, 3),
            "profit_per_100_baskets": round(hit_profit / n * 100, 2),
        }
    return {"cases": len(cases), "train_size": len(train), "top_n": top_n, "strategies": results}


def _clean_record(rec: dict) -> dict:
    out = {}
    for k, v in rec.items():
        if isinstance(v, np.integer):
            v = int(v)
        elif isinstance(v, (np.floating, float)):
            v = None if not np.isfinite(v) else round(float(v), 4)
        elif isinstance(v, np.bool_):
            v = bool(v)
        out[k] = v
    return out
