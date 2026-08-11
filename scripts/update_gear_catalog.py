#!/usr/bin/env python3
"""Build CourtIQ's canonical gear product index.

The app can still fall back to its legacy seed list, but this script is the
refresh point for real source files placed in work/gear-sources.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = ROOT / "work" / "gear-sources"
DEFAULT_APP_JS = ROOT / "outputs" / "tennis-ai-app" / "app.js"
DEFAULT_OUTPUT_JSON = ROOT / "outputs" / "tennis-ai-app" / "assets" / "gear" / "gear-index.json"
DEFAULT_OUTPUT_JS = ROOT / "outputs" / "tennis-ai-app" / "assets" / "gear" / "gear-index.js"
DEFAULT_BOOTSTRAP = DEFAULT_SOURCE_DIR / "bootstrap_seed.json"

CATEGORY_ALIASES = {
    "racket": "Racket",
    "rackets": "Racket",
    "racquet": "Racket",
    "racquets": "Racket",
    "shoe": "Shoes",
    "shoes": "Shoes",
    "ball": "Ball",
    "balls": "Ball",
    "string": "String",
    "strings": "String",
    "bag": "Bag",
    "bags": "Bag",
    "grip": "Grip",
    "grips": "Grip",
    "overgrip": "Grip",
    "overgrips": "Grip",
    "dampener": "Dampener",
    "dampeners": "Dampener",
    "accessory": "Accessory",
    "accessories": "Accessory",
}

BRAND_OFFICIAL_URLS = {
    "Babolat": "https://www.babolat.com/",
    "Wilson": "https://www.wilson.com/en-us/tennis",
    "HEAD": "https://www.head.com/en/tennis",
    "Yonex": "https://www.yonex.com/tennis",
    "Tecnifibre": "https://www.tecnifibre.com/",
    "Dunlop": "https://dunlopsports.com/tennis/",
    "Prince": "https://princetennis.com/",
    "ASICS": "https://www.asics.com/",
    "Nike": "https://www.nike.com/tennis",
    "Adidas": "https://www.adidas.com/tennis",
    "Puma": "https://us.puma.com/us/en/sports/tennis",
    "New Balance": "https://www.newbalance.com/tennis/",
    "K-Swiss": "https://kswiss.com/",
    "On": "https://www.on.com/",
    "Solinco": "https://www.solincosports.com/",
    "Luxilon": "https://www.luxilon.com/",
    "Volkl": "https://www.volkltennis.com/",
    "ProKennex": "https://prokennex.com/",
    "Artengo": "https://www.decathlon.com/",
    "Diadem": "https://diademsports.com/",
    "Lacoste": "https://www.lacoste.com/",
    "Gamma": "https://www.gammasports.com/",
}

CANONICAL_FIELDS = (
    "id",
    "brand",
    "model",
    "variant",
    "category",
    "subcategory",
    "gender",
    "image_url",
    "image_local_path",
    "image_verified",
    "product_url",
    "official_url",
    "retailer_url",
    "price",
    "currency",
    "availability",
    "status",
    "active",
    "specs",
    "style",
    "game_impact",
    "best_for",
    "source",
    "source_type",
    "source_links",
    "last_verified",
)


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", normalize_text(value).lower()).strip()


def slugify(value: Any) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", normalize_key(value)).strip("-")
    return slug or "unknown"


def category_for(value: Any) -> str:
    key = normalize_key(value)
    return CATEGORY_ALIASES.get(key, normalize_text(value) or "Accessory")


def split_model_variant(name: str) -> tuple[str, str]:
    clean = normalize_text(name)
    match = re.match(r"^(.+?)\s+(gen\s*\d+|v\d+|team|lite|tour|pro|mp|ls|l|ul|plus|junior\s*\d+)$", clean, re.I)
    if match:
      return match.group(1).strip(), match.group(2).strip()
    return clean, ""


def parse_specs(specs: Any) -> dict[str, Any]:
    if isinstance(specs, dict):
        return {str(k): v for k, v in specs.items() if v not in ("", None)}
    text = normalize_text(specs)
    out: dict[str, Any] = {}
    head = re.search(r"(\d{2,3})\s*in", text, re.I)
    weight = re.search(r"(\d{3})\s*g", text, re.I)
    pattern = re.search(r"(\d{2})\s*[×x]\s*(\d{2})", text)
    gauge = re.search(r"(\d{2}L?|\d{2})\s*gauge", text, re.I)
    if head:
        out["head_size_sq_in"] = int(head.group(1))
    if weight:
        out["unstrung_weight_g"] = int(weight.group(1))
    if pattern:
        out["string_pattern"] = f"{pattern.group(1)}x{pattern.group(2)}"
    if gauge:
        out["gauge"] = gauge.group(1)
    if text:
        out["summary"] = text
    return out


def product_identity(record: dict[str, Any]) -> str:
    return "|".join(
        normalize_key(record.get(field))
        for field in ("brand", "model", "variant", "category")
    )


def canonical_product_id(record: dict[str, Any]) -> str:
    return "-".join(
        part
        for part in (
            slugify(record.get("category")),
            slugify(record.get("brand")),
            slugify(record.get("model")),
            slugify(record.get("variant")),
        )
        if part and part != "unknown"
    )


def image_is_usable(record: dict[str, Any]) -> bool:
    local = normalize_text(record.get("image_local_path"))
    remote = normalize_text(record.get("image_url"))
    if local and (ROOT / local).exists():
        return True
    if remote and record.get("image_verified") is True:
        return True
    return False


def source_links(record: dict[str, Any]) -> list[str]:
    links: list[str] = []
    for key in ("product_url", "official_url", "retailer_url"):
        value = normalize_text(record.get(key))
        if value and value.startswith(("https://", "http://")) and value not in links:
            links.append(value)
    for value in record.get("source_links") or []:
        value = normalize_text(value)
        if value and value.startswith(("https://", "http://")) and value not in links:
            links.append(value)
    return links


def mark_staleness(record: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    status = normalize_text(record.get("status")).lower()
    if status in {"current", "archived", "discontinued", "unknown"}:
        record["status"] = "archived" if status == "discontinued" else status
    else:
        record["status"] = "unknown"
    verified = normalize_text(record.get("last_verified"))
    if verified:
        try:
            age = (today - date.fromisoformat(verified[:10])).days
            if age > 540 and record["status"] == "current":
                record["status"] = "unknown"
        except ValueError:
            record["last_verified"] = None
    return record


def canonicalize_record(raw: dict[str, Any], *, default_source: str = "") -> dict[str, Any]:
    brand = normalize_text(raw.get("brand"))
    raw_name = normalize_text(raw.get("model") or raw.get("name") or raw.get("product_name"))
    model, variant = split_model_variant(raw_name)
    variant = normalize_text(raw.get("variant")) or variant
    category = category_for(raw.get("category") or raw.get("type"))
    official_url = normalize_text(raw.get("official_url"))
    price = raw.get("price")
    if raw.get("source_type") == "bootstrap_seed":
        price = None
    record = {
        "id": "",
        "brand": brand,
        "model": model,
        "variant": variant,
        "category": category,
        "subcategory": normalize_text(raw.get("subcategory") or raw.get("style")),
        "gender": normalize_text(raw.get("gender") or raw.get("sex") or "unisex").lower(),
        "image_url": normalize_text(raw.get("image_url") or raw.get("imageUrl")),
        "image_local_path": normalize_text(raw.get("image_local_path") or raw.get("imageLocalPath")),
        "image_verified": bool(raw.get("image_verified") or raw.get("imageVerified")),
        "product_url": normalize_text(raw.get("product_url") or raw.get("productUrl")),
        "official_url": official_url,
        "retailer_url": normalize_text(raw.get("retailer_url") or raw.get("retailerUrl")),
        "price": price if price not in ("", None) else None,
        "currency": normalize_text(raw.get("currency")),
        "availability": normalize_text(raw.get("availability") or "unknown").lower(),
        "status": normalize_text(raw.get("status") or "unknown").lower(),
        "active": raw.get("active", True) is not False,
        "specs": parse_specs(raw.get("specs")),
        "style": normalize_text(raw.get("style")),
        "game_impact": normalize_text(raw.get("game_impact") or raw.get("impact")),
        "best_for": normalize_text(raw.get("best_for") or raw.get("pro")),
        "source": normalize_text(raw.get("source") or default_source),
        "source_type": normalize_text(raw.get("source_type") or raw.get("sourceType") or "provided_source"),
        "source_links": list(raw.get("source_links") or []),
        "last_verified": normalize_text(raw.get("last_verified") or raw.get("lastVerified")) or None,
    }
    if record["image_url"] and not record["image_verified"]:
        record["image_url"] = ""
    record["source_links"] = source_links(record)
    record["id"] = normalize_text(raw.get("id")) or canonical_product_id(record)
    return mark_staleness(record)


def merge_records(primary: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(primary)
    for field in CANONICAL_FIELDS:
        if field in {"id", "source_links"}:
            continue
        existing = merged.get(field)
        value = incoming.get(field)
        if existing in ("", None, [], {}) and value not in ("", None, [], {}):
            merged[field] = value
        elif field == "status" and existing == "unknown" and value == "current":
            merged[field] = "current"
        elif field == "image_verified" and value is True:
            merged[field] = True
    merged["source_links"] = source_links({**merged, "source_links": (merged.get("source_links") or []) + (incoming.get("source_links") or [])})
    return merged


def dedupe_products(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for record in records:
        key = product_identity(record)
        if not key.replace("|", ""):
            continue
        deduped[key] = merge_records(deduped[key], record) if key in deduped else record
    return sorted(deduped.values(), key=lambda item: (item["category"], item["brand"], item["model"], item["variant"]))


def product_text(record: dict[str, Any]) -> str:
    return normalize_key(" ".join(
        str(record.get(key) or "")
        for key in ("brand", "model", "variant", "category", "subcategory", "style", "game_impact", "best_for")
    ))


def search_score(record: dict[str, Any], query: str) -> int:
    q = normalize_key(query)
    if not q:
        return 1
    name = normalize_key(f"{record.get('brand')} {record.get('model')} {record.get('variant')}")
    text = product_text(record)
    tokens = [token for token in q.split() if token]
    if q == name:
        return 1000
    if name.startswith(q):
        return 800
    if all(token in text.split() or token in text for token in tokens):
        return 600 + sum(text.count(token) for token in tokens)
    if q in text:
        return 400
    text_tokens = text.split()
    if tokens and all(min((levenshtein(token, candidate) for candidate in text_tokens), default=99) <= 2 for token in tokens):
        return 220
    if min((levenshtein(q, token) for token in text.split()), default=99) <= 2:
        return 150
    return 0


def search_products(products: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    scored = [(search_score(product, query), product) for product in products]
    return [product for score, product in sorted(scored, key=lambda pair: (-pair[0], pair[1]["brand"], pair[1]["model"])) if score > 0]


def filter_products(
    products: list[dict[str, Any]],
    *,
    category: str = "All",
    brand: str = "All brands",
    status: str = "active",
) -> list[dict[str, Any]]:
    wanted_category = category_for(category) if category not in {"All", "All categories"} else "All"
    filtered = []
    for product in products:
        if wanted_category != "All" and product.get("category") != wanted_category:
            continue
        if brand != "All brands" and product.get("brand") != brand:
            continue
        if status == "active" and product.get("active") is False:
            continue
        if status == "current" and product.get("status") != "current":
            continue
        filtered.append(product)
    return filtered


def paginate_products(products: list[dict[str, Any]], page: int = 1, page_size: int = 24) -> dict[str, Any]:
    page = max(1, int(page or 1))
    page_size = min(96, max(1, int(page_size or 24)))
    start = (page - 1) * page_size
    return {
        "page": page,
        "page_size": page_size,
        "total": len(products),
        "items": products[start:start + page_size],
        "has_more": start + page_size < len(products),
    }


def levenshtein(a: str, b: str) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def read_source_file(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("products") or data.get("items") or []
        return [dict(item) for item in data]
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    return []


def extract_bootstrap_from_app_js(app_js: Path) -> list[dict[str, Any]]:
    script = r"""
const fs = require('fs');
const path = process.argv[1];
const text = fs.readFileSync(path, 'utf8');
const start = text.indexOf('const GEAR_ITEMS = [');
const end = text.indexOf('];', start);
if (start < 0 || end < 0) throw new Error('GEAR_ITEMS not found');
const arrayText = text.slice(text.indexOf('[', start), end + 1);
const items = Function(`"use strict"; return (${arrayText});`)();
console.log(JSON.stringify(items));
"""
    result = subprocess.run(["node", "-e", script, str(app_js)], check=True, text=True, capture_output=True)
    return json.loads(result.stdout)


def ensure_bootstrap_seed(source_dir: Path, app_js: Path) -> None:
    source_dir.mkdir(parents=True, exist_ok=True)
    if DEFAULT_BOOTSTRAP.exists():
        return
    seed = []
    for raw in extract_bootstrap_from_app_js(app_js):
        item = dict(raw)
        item["source"] = "CourtIQ legacy bootstrap seed"
        item["source_type"] = "bootstrap_seed"
        item["status"] = "unknown"
        item["availability"] = "unknown"
        item["last_verified"] = None
        seed.append(item)
    DEFAULT_BOOTSTRAP.write_text(json.dumps(seed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_index(source_dir: Path, app_js: Path) -> dict[str, Any]:
    ensure_bootstrap_seed(source_dir, app_js)
    raw_records: list[dict[str, Any]] = []
    source_files = sorted(path for path in source_dir.iterdir() if path.suffix.lower() in {".json", ".csv"})
    for source_file in source_files:
        for raw in read_source_file(source_file):
            raw_records.append(canonicalize_record(raw, default_source=source_file.name))
    products = dedupe_products(raw_records)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    counts_by_category: dict[str, int] = {}
    counts_by_brand: dict[str, int] = {}
    for product in products:
        counts_by_category[product["category"]] = counts_by_category.get(product["category"], 0) + 1
        counts_by_brand[product["brand"]] = counts_by_brand.get(product["brand"], 0) + 1
    return {
        "metadata": {
            "generated_at": now,
            "raw_records": len(raw_records),
            "total_products": len(products),
            "duplicates_merged": max(0, len(raw_records) - len(products)),
            "counts_by_category": counts_by_category,
            "counts_by_brand": counts_by_brand,
            "source_files": [str(path.relative_to(ROOT)) for path in source_files],
            "products_with_real_images": sum(1 for product in products if image_is_usable(product)),
            "products_with_exact_product_urls": sum(1 for product in products if product.get("product_url")),
            "products_with_exact_official_urls": sum(1 for product in products if product.get("official_url")),
            "products_with_exact_retailer_urls": sum(1 for product in products if product.get("retailer_url")),
            "products_with_retailer_urls": sum(1 for product in products if product.get("retailer_url")),
            "current_count": sum(1 for product in products if product.get("status") == "current"),
            "archived_count": sum(1 for product in products if product.get("status") == "archived"),
            "unknown_status_count": sum(1 for product in products if product.get("status") == "unknown"),
        },
        "products": products,
    }


def write_outputs(index: dict[str, Any], output_json: Path, output_js: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(index, indent=2, ensure_ascii=False)
    output_json.write_text(payload + "\n", encoding="utf-8")
    output_js.write_text(
        "window.COURTIQ_GEAR_INDEX = "
        + json.dumps(index, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the CourtIQ gear product index.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--app-js", type=Path, default=DEFAULT_APP_JS)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-js", type=Path, default=DEFAULT_OUTPUT_JS)
    args = parser.parse_args()
    index = build_index(args.source_dir, args.app_js)
    write_outputs(index, args.output_json, args.output_js)
    meta = index["metadata"]
    print(json.dumps({
        "total_products": meta["total_products"],
        "counts_by_category": meta["counts_by_category"],
        "products_with_real_images": meta["products_with_real_images"],
        "products_with_exact_product_urls": meta["products_with_exact_product_urls"],
        "source_files": meta["source_files"],
        "output_json": str(args.output_json),
        "output_js": str(args.output_js),
    }, indent=2))


if __name__ == "__main__":
    main()
