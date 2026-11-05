"""Command-line interface for CARTS (the web app is in app.py).

Examples:
    python carts_apriori.py recommend "Jumbo Bag Red Retrospot" "Lunch Bag Red Retrospot"
    python carts_apriori.py recommend --strategy apriori --top 10 "Party Bunting"
    python carts_apriori.py rules --top 15
    python carts_apriori.py evaluate
    python carts_apriori.py products --search heart
    python carts_apriori.py recommend --transactions my_baskets.csv --item-master my_prices.csv milk bread
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from carts_engine import STRATEGIES, CartsEngine, Config, evaluate, load_item_master, load_transactions

DATA = Path(__file__).resolve().parent / "data"


def build_engine(args: argparse.Namespace) -> CartsEngine:
    meta_path = DATA / "dataset.json"
    defaults = json.loads(meta_path.read_text(encoding="utf-8")).get("defaults", {}) if meta_path.exists() else {}
    config = Config.from_dict({
        **defaults,
        **{k: v for k, v in {"min_support": args.min_support, "min_confidence": args.min_confidence}.items()
           if v is not None},
    })
    transactions = load_transactions(args.transactions)
    return CartsEngine(transactions, load_item_master(args.item_master), config).fit()


def table(rows: list[list], headers: list[str]) -> str:
    cells = [headers] + [[str(c) for c in r] for r in rows]
    widths = [max(len(r[i]) for r in cells) for i in range(len(headers))]
    line = "  ".join("-" * w for w in widths)
    out = ["  ".join(h.ljust(w) for h, w in zip(headers, widths)), line]
    out += ["  ".join(c.ljust(w) for c, w in zip(r, widths)) for r in cells[1:]]
    return "\n".join(out)


def cmd_recommend(engine: CartsEngine, args: argparse.Namespace) -> None:
    unknown = [c for c in args.cart if engine.resolve(c) is None]
    if unknown:
        print(f"Not in catalogue (ignored): {', '.join(unknown)}")
    strategies = STRATEGIES if args.strategy == "both" else [args.strategy]
    for s in strategies:
        recs = engine.recommend(args.cart, s, args.top)
        print(f"\n{s.upper()} recommendations for: {', '.join(args.cart) or '(empty cart)'}")
        print(table([[i + 1, r["item"], f"{r['score']:.3f}", f"{r['profit_rs']:.2f}", f"{r['margin_pct']:.1f}%",
                      r["reason"] + (f" ({' + '.join(r['because'])})" if r["because"] else "")]
                     for i, r in enumerate(recs)],
                    ["#", "item", "score", "profit/unit", "margin", "why"]))


def cmd_rules(engine: CartsEngine, args: argparse.Namespace) -> None:
    rules = engine.rules_table(args.strategy if args.strategy != "both" else "carts", args.search or "", args.top)
    print(table([[" + ".join(r["antecedents"]) + " -> " + r["consequent"], f"{r['support']:.3f}",
                  f"{r['confidence']:.2f}", f"{r['lift']:.2f}", f"{r['carts_score']:.3f}", r["carts_rank"], r["apriori_rank"]]
                 for r in rules],
                ["rule", "support", "conf", "lift", "CARTS", "CARTS rank", "Apriori rank"]))


def cmd_products(engine: CartsEngine, args: argparse.Namespace) -> None:
    q = (args.search or "").lower()
    items = [i for i in engine.catalog() if q in i["item"].lower()]
    items.sort(key=lambda i: -i["times_sold"])
    print(table([[i["item"], i["category"], f"{i['selling_price']:.2f}", f"{i['margin_pct']:.1f}%", i["times_sold"]]
                 for i in items[: args.top]], ["item", "category", "price", "margin", "baskets"]))


def cmd_evaluate(engine: CartsEngine, args: argparse.Namespace) -> None:
    result = evaluate(engine.transactions, engine.items, engine.config, top_n=args.top)
    print(f"Hold-out evaluation: {result['cases']} test baskets, trained on {result['train_size']}")
    rows = [[s, f"{m['hit_rate']:.1%}", f"{m['avg_profit']:.2f}", f"{m['avg_margin_pct']:.1f}%", f"{m['profit_per_100_baskets']:.2f}"]
            for s, m in result["strategies"].items()]
    print(table(rows, ["strategy", f"hit rate@{args.top}", "avg profit/suggestion", "avg margin", "profit of hits/100 baskets"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["recommend", "rules", "products", "evaluate"])
    parser.add_argument("cart", nargs="*", help="items in the cart (for 'recommend')")
    parser.add_argument("--strategy", choices=[*STRATEGIES, "both"], default="both")
    parser.add_argument("--top", type=int, help="rows to show (default 5 for recommend/evaluate, 20 otherwise)")
    parser.add_argument("--search")
    parser.add_argument("--min-support", type=float)
    parser.add_argument("--min-confidence", type=float)
    parser.add_argument("--transactions", default=DATA / "transactions.csv")
    parser.add_argument("--item-master", default=DATA / "item_master.csv")
    args = parser.parse_args()
    if args.top is None:
        args.top = 20 if args.command in ("rules", "products") else 5

    engine = build_engine(args)
    {"recommend": cmd_recommend, "rules": cmd_rules, "products": cmd_products, "evaluate": cmd_evaluate}[args.command](engine, args)


if __name__ == "__main__":
    main()
