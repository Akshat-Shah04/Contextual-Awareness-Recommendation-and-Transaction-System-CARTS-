"""Prepare the UCI "Online Retail" dataset for CARTS.

Source (real data):
    Chen, D. (2015). Online Retail [Dataset]. UCI Machine Learning Repository.
    https://doi.org/10.24432/C5BW33  (CC BY 4.0)
    Mirrored on Kaggle as "E-Commerce Data" (carrie1/ecommerce-data).

All transactions of a UK-based, non-store online gift retailer between
2010-12-01 and 2011-12-09 (541,909 invoice lines).

What this script does:
  1. Drops cancelled invoices (InvoiceNo starting with "C"), returns (Quantity <= 0),
     zero-priced lines and non-product codes (POST, DOT, M, BANK CHARGES, gift vouchers...).
  2. Keeps the TOP_N products ordered on the most invoices (keeps the shop catalogue and
     Apriori tractable) and writes one basket per invoice -> data/transactions.csv
  3. Builds data/item_master.csv with, per product:
       selling_price  REAL   - median unit price actually charged (GBP)
       units_sold     REAL   - total quantity sold
       revenue        REAL   - total Quantity x UnitPrice
       category       DERIVED - keyword rules on the product description
       cost_price     ESTIMATED - the dataset has no costs; see estimate_margin()

Usage:
    python scripts/prepare_online_retail.py "path/to/Online Retail.xlsx"
Download: https://archive.ics.uci.edu/static/public/352/online+retail.zip
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TOP_N = 500

# Keyword -> category (first match wins). Derived from product descriptions.
CATEGORY_RULES: list[tuple[str, str]] = [
    (r"CHRISTMAS|XMAS|ADVENT|SANTA|REINDEER|SNOWFLAKE|BAUBLE", "Christmas"),
    (r"BAG|TOTE|SHOPPER|PURSE", "Bags"),
    (r"CAKE|CAKESTAND|BAKING|TEA ?CUP|MUG|CUP|PLATE|BOWL|JUG|TEAPOT|CUTLERY|SPOON|NAPKIN|LUNCH BOX|"
     r"TIN|JAR|BOTTLE|TRAY|COASTER|KITCHEN|APRON|OVEN|EGG|CHOPSTICK|DOILY|STRAW", "Kitchen & Dining"),
    (r"CANDLE|T-LIGHT|TLIGHT|LANTERN|LIGHT|LAMP|HOLDER", "Candles & Lighting"),
    (r"CARD|WRAP|PAPER|NOTEBOOK|PEN|PENCIL|STICKER|STATIONERY|CALENDAR|ENVELOPE|TAPE|BOOK", "Stationery & Wrap"),
    (r"BUNTING|PARTY|BALLOON|BIRTHDAY|GARLAND|DECORATION|CONFETTI", "Party"),
    (r"FRAME|CLOCK|SIGN|CUSHION|DOORMAT|HOOK|HANGER|DRAWER|MIRROR|CHALKBOARD|WALL|DOOR|"
     r"STORAGE|BOX|BASKET|VASE|ORNAMENT|HEART|PLANT|GARDEN", "Home Decor"),
    (r"TOY|GAME|DOLL|SPACEBOY|DOLLY|JIGSAW|PLAYHOUSE|SKITTLES|DOMINO|CHILDREN|CHILDS|KIDS|BABY", "Kids & Toys"),
    (r"NECKLACE|BRACELET|EARRING|RING|HAIR|SCARF|UMBRELLA|HAND WARMER|SLIPPER|GLOVES", "Fashion & Accessories"),
]

# Assumed gross margin (on selling price) by category, based on typical gift/homeware
# retail margins. These are ASSUMPTIONS, not data: replace with real costs if you have them.
CATEGORY_MARGIN = {
    "Christmas": 0.55, "Bags": 0.45, "Kitchen & Dining": 0.40, "Candles & Lighting": 0.50,
    "Stationery & Wrap": 0.60, "Party": 0.55, "Home Decor": 0.48, "Kids & Toys": 0.42,
    "Fashion & Accessories": 0.58, "Other": 0.45,
}

NON_PRODUCT = re.compile(r"^(POST|DOT|M|C2|S|B|PADS|AMAZONFEE|BANK CHARGES|CRUK|DCGS.*|gift_.*)$", re.I)

DATASET_META = {
    "name": "Online Retail (UCI / Kaggle) - real invoices 2010-2011",
    "currency": "£",
    "source": "Chen, D. (2015). Online Retail. UCI Machine Learning Repository. https://doi.org/10.24432/C5BW33",
    "kaggle": "https://www.kaggle.com/datasets/carrie1/ecommerce-data",
    "license": "CC BY 4.0",
    "notes": "Selling prices, quantities and baskets are real. Categories are derived from "
             "descriptions; cost prices are estimated from assumed category margins.",
    "defaults": {"min_support": 0.01, "min_confidence": 0.2, "min_lift": 1.0, "max_len": 3},
}


def categorize(description: str) -> str:
    for pattern, category in CATEGORY_RULES:
        if re.search(r"\b(?:" + pattern + r")(?:S|ES)?\b", description):
            return category
    return "Other"


def estimate_margin(category: str) -> float:
    """Assumed gross margin for a category (no per-item invention beyond that)."""
    return CATEGORY_MARGIN.get(category, CATEGORY_MARGIN["Other"])


def display_name(description: str) -> str:
    text = re.sub(r"\s+", " ", description).strip().rstrip(".")
    words = []
    for w in text.split(" "):
        words.append(w if re.fullmatch(r"[0-9]+[A-Z]*|[A-Z]{1,2}\d*", w) and len(w) <= 2 else w.capitalize())
    return " ".join(words)


def prepare(xlsx: Path) -> None:
    raw = pd.read_excel(xlsx, dtype={"InvoiceNo": str, "StockCode": str})
    df = raw.dropna(subset=["Description"])
    df = df[~df["InvoiceNo"].str.startswith("C") & (df["Quantity"] > 0) & (df["UnitPrice"] > 0)]
    df = df[~df["StockCode"].str.match(NON_PRODUCT)]
    # One name per stock code (descriptions vary slightly between invoices)
    names = df.groupby("StockCode")["Description"].agg(lambda s: s.str.strip().mode().iat[0])
    df = df.assign(item=df["StockCode"].map(names).map(display_name))

    top = df.groupby("item")["InvoiceNo"].nunique().nlargest(TOP_N).index
    df = df[df["item"].isin(top)]

    baskets = df.groupby("InvoiceNo")["item"].agg(lambda s: list(dict.fromkeys(s)))
    DATA.mkdir(exist_ok=True)
    with (DATA / "transactions.csv").open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(baskets.tolist())

    df = df.assign(line_revenue=df["Quantity"] * df["UnitPrice"])
    agg = df.groupby("item").agg(
        selling_price=("UnitPrice", "median"),
        units_sold=("Quantity", "sum"),
        revenue=("line_revenue", "sum"),
        invoices=("InvoiceNo", "nunique"),
        stock_code=("StockCode", "first"),
    ).reset_index()
    agg["category"] = agg["item"].str.upper().map(categorize)
    agg["est_margin"] = agg["category"].map(estimate_margin)
    agg["cost_price"] = (agg["selling_price"] * (1 - agg["est_margin"])).round(2)
    agg["selling_price"] = agg["selling_price"].round(2)
    agg["revenue"] = agg["revenue"].round(2)
    cols = ["item", "stock_code", "category", "cost_price", "selling_price", "units_sold", "revenue", "invoices"]
    agg.sort_values("invoices", ascending=False)[cols].to_csv(DATA / "item_master.csv", index=False)

    meta = dict(DATASET_META, stats={
        "raw_lines": int(len(raw)), "invoices": int(len(baskets)), "products": int(len(agg)),
        "period": f"{raw['InvoiceDate'].min():%Y-%m-%d} to {raw['InvoiceDate'].max():%Y-%m-%d}",
    })
    (DATA / "dataset.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"{len(baskets):,} baskets, {len(agg)} products -> {DATA}")
    print(agg["category"].value_counts().to_string())


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    prepare(Path(sys.argv[1]))
