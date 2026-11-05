"""Loading and cleaning of transaction datasets and the item master.

Supported transaction formats (auto-detected):

* **Basket rows, no header** – one transaction per line, items comma separated
  (the classic Groceries dataset: ``citrus fruit,semi-finished bread,margarine``).
* **Wide table with header** – columns like ``Item(s), Item 1, Item 2, ...`` or
  ``Transaction_ID, Item_1, ...``. Id/count columns are dropped automatically.
* **Long table** – one row per purchased item, e.g. Kaggle's
  "Groceries dataset" (``Member_number, Date, itemDescription``). Rows are
  grouped into baskets by customer id + date (or by transaction id).
"""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from pathlib import Path
from typing import IO, Iterable

import pandas as pd

Transactions = list[list[str]]

_HEADER_HINT = re.compile(
    r"^(item\s*\(s\)|items?|item[\s_]*\d+|transaction([\s_]*id)?|tid|order[\s_]*id|"
    r"basket[\s_]*id|invoice(no)?|member[\s_]*number|customer[\s_]*id|user[\s_]*id|date|"
    r"item[\s_]*description|itemdescription|product([\s_]*name)?|description)$",
    re.IGNORECASE,
)
_ITEM_COL = re.compile(r"^(item[\s_]*description|itemdescription|product([\s_]*name)?|description|item(s)?|item[\s_]*name)$", re.I)
_ID_COL = re.compile(r"^(transaction([\s_]*id)?|tid|order[\s_]*id|basket[\s_]*id|invoice(no)?|member[\s_]*number|customer[\s_]*id|user[\s_]*id)$", re.I)
_DATE_COL = re.compile(r"^(date|order[\s_]*date|invoice[\s_]*date|timestamp)$", re.I)
_NUMERIC = re.compile(r"^\s*\d+(\.\d+)?\s*$")


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    return text


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _read_text(source: str | Path | IO) -> str:
    if hasattr(source, "read"):
        raw = source.read()
        return raw.decode("utf-8-sig", errors="replace") if isinstance(raw, bytes) else raw
    return Path(source).read_text(encoding="utf-8-sig", errors="replace")


def parse_transactions(text: str) -> Transactions:
    """Parse CSV text in any supported format into a list of baskets."""
    rows = [row for row in csv.reader(io.StringIO(text)) if any(c.strip() for c in row)]
    if not rows:
        return []

    header = [c.strip() for c in rows[0]]
    has_header = sum(bool(_HEADER_HINT.match(h)) for h in header if h) >= max(1, len([h for h in header if h]) // 2)

    if has_header:
        item_cols = [i for i, h in enumerate(header) if _ITEM_COL.match(h)]
        id_cols = [i for i, h in enumerate(header) if _ID_COL.match(h)]
        date_cols = [i for i, h in enumerate(header) if _DATE_COL.match(h)]
        is_long = len(item_cols) == 1 and (id_cols or date_cols) and len(header) <= 6
        if is_long:
            item_i = item_cols[0]
            key_cols = id_cols + date_cols
            baskets: dict[tuple, list[str]] = {}
            for row in rows[1:]:
                if len(row) <= item_i:
                    continue
                item = _clean(row[item_i])
                if item is None:
                    continue
                key = tuple(row[i].strip() if i < len(row) else "" for i in key_cols)
                baskets.setdefault(key, []).append(item)
            return [_dedupe(b) for b in baskets.values() if b]

        # Wide table: drop id / count columns (e.g. "Item(s)" holds the basket size)
        drop = {i for i, h in enumerate(header) if _ID_COL.match(h) or re.match(r"^item\s*\(s\)$", h, re.I)}
        body = rows[1:]
    else:
        drop = set()
        body = rows

    transactions = []
    for row in body:
        items = [
            c for i, cell in enumerate(row)
            if i not in drop and (c := _clean(cell)) is not None and not _NUMERIC.match(c)
        ]
        if items:
            transactions.append(_dedupe(items))
    return transactions


def load_transactions(source: str | Path | IO) -> Transactions:
    return parse_transactions(_read_text(source))


def item_frequencies(transactions: Transactions) -> Counter:
    return Counter(item for basket in transactions for item in basket)


# --------------------------------------------------------------------------- item master

_ALIASES = {
    "item": ["item", "item name", "item names", "product", "name", "itemdescription"],
    "category": ["category", "department", "aisle"],
    "cost_price": ["cost_price", "cp", "cp (rs)", "cost price", "cost price (c.p)", "cost"],
    "selling_price": ["selling_price", "sp", "sp (rs)", "selling price", "selling price (s.p.)", "price", "mrp",
                      "unitprice", "unit price"],
    "units_sold": ["units_sold", "units sold", "quantity sold", "qty_sold"],
    "revenue": ["revenue", "sales", "sales_value", "total sales"],
}


def _find_col(columns: list[str], names: list[str]) -> str | None:
    lookup = {c.strip().lower(): c for c in columns}
    for name in names:
        if name in lookup:
            return lookup[name]
    return None


def normalize_item_master(df: pd.DataFrame) -> pd.DataFrame:
    """Map an item master with any of the known column spellings to the canonical schema
    ``item, category, cost_price, selling_price, profit_pct, margin_pct, profit_rs``."""
    cols = {key: _find_col(list(df.columns), names) for key, names in _ALIASES.items()}
    if cols["item"] is None or cols["cost_price"] is None or cols["selling_price"] is None:
        raise ValueError(
            "Item master needs item, cost price and selling price columns "
            f"(found: {', '.join(map(str, df.columns))})"
        )
    out = pd.DataFrame({
        "item": df[cols["item"]].astype(str).str.strip(),
        "category": df[cols["category"]].astype(str).str.strip() if cols["category"] else "Uncategorized",
        "cost_price": pd.to_numeric(df[cols["cost_price"]], errors="coerce"),
        "selling_price": pd.to_numeric(df[cols["selling_price"]], errors="coerce"),
    })
    for key in ("units_sold", "revenue"):  # optional real sales figures
        col = _find_col(list(df.columns), _ALIASES[key])
        if col is not None:
            out[key] = pd.to_numeric(df[col], errors="coerce")
    out = out.dropna(subset=["cost_price", "selling_price"])
    out = out[out["item"] != ""].drop_duplicates("item", keep="last")
    return add_financials(out.reset_index(drop=True))


def add_financials(df: pd.DataFrame) -> pd.DataFrame:
    """Profit % is on cost, margin % is on selling price (as defined in the CARTS paper)."""
    df = df.copy()
    df["profit_rs"] = (df["selling_price"] - df["cost_price"]).round(2)
    df["profit_pct"] = (df["profit_rs"] / df["cost_price"].where(df["cost_price"] != 0) * 100).fillna(0).round(2)
    df["margin_pct"] = (df["profit_rs"] / df["selling_price"].where(df["selling_price"] != 0) * 100).fillna(0).round(2)
    return df


def load_item_master(source: str | Path | IO) -> pd.DataFrame:
    name = getattr(source, "filename", None) or getattr(source, "name", None) or str(source)
    if str(name).lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(source)
    else:
        df = pd.read_csv(io.StringIO(_read_text(source)))
    return normalize_item_master(df)


def align_item_master(item_master: pd.DataFrame, transactions: Transactions) -> pd.DataFrame:
    """Match item names case-insensitively to the transaction vocabulary and fill in
    products that have no price with the median of the catalogue (flagged ``estimated``)."""
    freq = item_frequencies(transactions)
    canonical = {name.lower(): name for name in freq}
    im = item_master.copy()
    im["item"] = im["item"].map(lambda n: canonical.get(n.lower(), n))
    im = im[im["item"].isin(freq)].drop_duplicates("item", keep="last")
    im["estimated"] = False

    missing = [name for name in freq if name not in set(im["item"])]
    if missing:
        cp = float(item_master["cost_price"].median()) if len(item_master) else 50.0
        sp = float(item_master["selling_price"].median()) if len(item_master) else 60.0
        filler = pd.DataFrame({
            "item": missing, "category": "Uncategorized",
            "cost_price": cp, "selling_price": sp, "estimated": True,
        })
        im = pd.concat([im, add_financials(filler)], ignore_index=True)

    im["times_sold"] = im["item"].map(freq).astype(int)
    return add_financials(im).sort_values("item", key=lambda s: s.str.lower()).reset_index(drop=True)
