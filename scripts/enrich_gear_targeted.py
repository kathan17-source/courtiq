#!/usr/bin/env python3
"""Targeted exact enrichment for the remaining named major CourtIQ products."""

from __future__ import annotations

import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "outputs/tennis-ai-app/assets/gear/gear-index.json"
OUT = ROOT / "work/gear-sources/exact_targeted_enrichment_2026-08-10.json"
UA = "Mozilla/5.0 (compatible; CourtIQ exact product verifier/1.0)"


OFFICIAL = {
    "racket-babolat-pure-aero-98-gen9-unstrung": ("Pure Aero 98 Gen9 Unstrung", "https://www.babolat.com/gb/pure-aero-98-gen9-unstrung/100-101567.html"),
    "racket-babolat-pure-aero-gen9-unstrung": ("Pure Aero Gen9 Unstrung", "https://www.babolat.com/gb/pure-aero-gen9-unstrung/100-101569.html"),
    "racket-babolat-pure-aero-junior-25-gen9": ("Pure Aero Junior 25 Gen9", "https://www.babolat.com/gb/pure-aero-junior-25-gen9/100-140538.html"),
    "racket-babolat-pure-aero-junior-26-gen9": ("Pure Aero Junior 26 Gen9", "https://www.babolat.com/gb/pure-aero-junior-26-gen9/100-140520.html"),
    "racket-babolat-pure-aero-lite-gen9-unstrung": ("Pure Aero Lite Gen9 Unstrung", "https://www.babolat.com/gb/pure-aero-lite-gen9-unstrung/100-101572.html"),
    "racket-babolat-pure-aero-s-lite-gen9-unstrung": ("Pure Aero S Lite Gen9 Unstrung", "https://www.babolat.com/gb/pure-aero-s-lite-gen9-unstrung/100-101573.html"),
    "racket-babolat-pure-aero-team-gen9-unstrung": ("Pure Aero Team Gen9 Unstrung", "https://www.babolat.com/gb/pure-aero-team-gen9-unstrung/100-101571.html"),
    "racket-babolat-pure-drive-gen11-unstrung": ("Pure Drive + Gen11 Unstrung", "https://www.babolat.com/gb/pure-drive-gen11-unstrung/100-101553.html"),
    "racket-babolat-pure-drive-107-gen11-unstrung": ("Pure Drive 107 Gen11 Unstrung", "https://www.babolat.com/gb/pure-drive-107-gen11-unstrung/101557.html"),
    "racket-babolat-pure-drive-junior-25-gen11": ("Pure Drive Junior 25 Gen11", "https://www.babolat.com/gb/pure-drive-junior-25-gen11/100-140533.html"),
    "racket-babolat-pure-drive-junior-26-gen11": ("Pure Drive Junior 26 Gen11", "https://www.babolat.com/gb/pure-drive-junior-26-gen11/100-140530.html"),
    "racket-babolat-pure-drive-s-lite-gen11-unstrung": ("Pure Drive S Lite Gen11 Unstrung", "https://www.babolat.com/gb/pure-drive-s-lite-gen11-unstrung/100-101556.html"),
}

RETAILER_PAGES = {
    "racket-yonex-ezone-100-2025": ("Yonex EZONE 100 (2025)", "https://www.tennis-warehouse.com/descpage-EZ10BB.html", "Tennis Warehouse"),
    "racket-yonex-ezone-100l-2025": ("Yonex EZONE 100L (2025)", "https://www.tennis-warehouse.com/Yonex_EZONE_100L_2025/descpageRCYONEX-EZ1LBB.html", "Tennis Warehouse"),
    "racket-yonex-ezone-100sl-2025": ("Yonex EZONE 100 SL (2025)", "https://www.tennis-warehouse.com/Yonex_EZONE_100_SL_2025/descpage-EZ1SLB.html", "Tennis Warehouse"),
    "racket-yonex-ezone-105-2025": ("Yonex EZONE 105 (2025)", "https://www.tennis-warehouse.com/Yonex_EZONE_105_2025/descpageRCYONEX-EZ105B.html", "Tennis Warehouse"),
    "racket-yonex-ezone-98-2025": ("Yonex EZONE 98 (2025)", "https://www.tennis-warehouse.com/Yonex_EZONE_98_2025/descpageRCYONEX-EZ98BB.html", "Tennis Warehouse"),
    "racket-tecnifibre-tfight-300-isoflex": ("Tecnifibre TFight 300 Isoflex", "https://www.prodirectsport.com/products/tecnifibre-tfight-300-isoflex-unstrung-white-black-mens-rackets-271035/", "Pro:Direct Tennis"),
    "racket-tecnifibre-tfight-305-isoflex": ("Tecnifibre TFight 305 Isoflex", "https://www.prodirectsport.com/products/tecnifibre-tfight-305-isoflex-unstrung-white-black-mens-rackets-271034/", "Pro:Direct Tennis"),
    "racket-tecnifibre-tfight-315-isoflex": ("Tecnifibre TFight 315 Isoflex", "https://www.prodirectsport.com/products/tecnifibre-tfight-315-isoflex-unstrung-white-black-mens-rackets-271033/", "Pro:Direct Tennis"),
}

RACQUET_GUYS = {
    "racket-head-extreme-mp-2024": ("Head Extreme MP (2024)", "https://racquetguys.ca/products/head-extreme-mp-2024-draft-specs-needs-update-descrp-is-ok"),
    "racket-head-extreme-pro-2024": ("Head Extreme Pro (2024)", "https://racquetguys.ca/products/head-extreme-pro-2024-draft-specs-need-update-description-good"),
    "racket-head-speed-team-2024": ("Head Speed Team (2024)", "https://racquetguys.ca/products/head-speed-team-2024"),
    "racket-wilson-blade-100-v9": ("Wilson Blade 100 V9", "https://racquetguys.ca/products/wilson-blade-100-v9"),
    "racket-wilson-blade-98-v9-16x19": ("Wilson Blade 98 16x19 V9", "https://racquetguys.ca/products/wilson-blade-98-16x19-v9"),
    "racket-wilson-blade-98-v9-18x20": ("Wilson Blade 98 18x20 V9", "https://racquetguys.ca/products/wilson-blade-98-18x20-v9"),
    "racket-wilson-shift-99-v1": ("Wilson Shift 99 V1", "https://racquetguys.ca/products/wilson-shift-99-v1"),
    "racket-wilson-shift-99-pro-v1": ("Wilson Shift 99 Pro V1", "https://racquetguys.ca/products/wilson-shift-99-pro-v1"),
    "shoes-asics-court-ff-3-novak": ("Asics Court FF 3 Novak Men's Tennis Shoe (Blue/White)", "https://racquetguys.ca/products/asics-court-ff-3-novak-mens-tennis-shoe-blue-white-1041a363-400"),
    "shoes-new-balance-fuelcell-996v6": ("New Balance FuelCell 996v6 Women's Tennis Shoe (White)", "https://racquetguys.ca/products/new-balance-fuelcell-996v6-womens-tennis-shoe-white-wch996v6-w6"),
    "shoes-nike-court-lite-4": ("Nike Court Lite 4 Women's Tennis Shoe (Apricot Agate/Volt)", "https://racquetguys.ca/products/nike-court-lite-4-womens-tennis-shoe-apricot-agate-volt"),
    "shoes-nike-zoom-vapor-cage-4-rafa": ("Nike Zoom Vapor Cage 4 Rafa Men's Tennis Shoe (LT Photo Blue/LT Armonry Blue)", "https://racquetguys.ca/products/nike-zoom-vapor-cage-4-rafa-mens-tennis-shoe-lt-photo-blue-lt-armonry-blue"),
}


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", html.unescape(value).lower()).strip()


def fetch(url: str) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=35) as response:
        return response.read(), response.headers.get_content_type()


def meta(html_text: str, key: str) -> str:
    patterns = [
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(key)}["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text, re.I)
        if match:
            return html.unescape(match.group(1))
    return ""


def cache(product_id: str, image_url: str) -> str:
    body, content_type = fetch(image_url)
    extensions = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    extension = extensions.get(content_type)
    if not extension or len(body) < 4_000:
        raise ValueError(f"bad image: {content_type}, {len(body)} bytes")
    relative = Path("outputs/tennis-ai-app/assets/gear") / f"{product_id}{extension}"
    (ROOT / relative).write_bytes(body)
    return relative.as_posix()


def product_record(product: dict, expected: str, page_url: str, source_name: str, source_type: str) -> dict:
    body, _ = fetch(page_url)
    page = body.decode("utf-8", "ignore")
    title = meta(page, "og:title") or re.search(r"<title>(.*?)</title>", page, re.I | re.S).group(1)
    image_url = meta(page, "og:image:secure_url") or meta(page, "og:image") or meta(page, "twitter:image")
    if not image_url and "tennis-warehouse.com" in page_url:
        match = re.search(r'https://img\.tennis-warehouse\.com/watermark/rs\.php\?path=[^"\']+?&(?:amp;)?nw=455', page, re.I)
        image_url = html.unescape(match.group(0)) if match else ""
    if not image_url and "babolat.com" in page_url:
        match = re.search(r'"image":\["(https://media\.babolat\.com/[^ "\']+)', page, re.I)
        image_url = html.unescape(match.group(1)) if match else ""
    if norm(expected) not in norm(title) or not image_url:
        raise ValueError(f"identity/image check failed: expected={expected!r}, title={title!r}")
    if image_url.startswith("//"):
        image_url = "https:" + image_url
    if image_url.startswith("http://"):
        image_url = "https://" + image_url.removeprefix("http://")
    local = cache(product["id"], image_url)
    record = {
        "id": product["id"], "brand": product["brand"], "model": product["model"], "variant": product["variant"], "category": product["category"],
        "image_url": image_url, "image_local_path": local, "image_verified": True,
        "product_url": page_url, "source": f"{source_name} exact product page: {expected}", "source_type": source_type,
        "source_links": [page_url, image_url], "last_verified": date.today().isoformat(),
    }
    record["official_url" if source_type == "exact_official_product" else "retailer_url"] = page_url
    return record


def racquet_guys_images() -> dict[str, tuple[str, str]]:
    parent, _ = fetch("https://racquetguys.ca/sitemap.xml")
    root = ET.fromstring(parent)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9", "i": "http://www.google.com/schemas/sitemap-image/1.1"}
    urls = [node.text for node in root.findall("s:sitemap/s:loc", ns) if node.text and "sitemap_products_" in node.text and "/en-us/" not in node.text and "/en-eu/" not in node.text and "/fr/" not in node.text]
    wanted = {url: (product_id, expected) for product_id, (expected, url) in RACQUET_GUYS.items()}
    found: dict[str, tuple[str, str]] = {}
    for sitemap_url in urls:
        body, _ = fetch(sitemap_url)
        child = ET.fromstring(body)
        for node in child.findall("s:url", ns):
            url = node.findtext("s:loc", "", ns)
            if url not in wanted:
                continue
            image = node.find("i:image", ns)
            title = image.findtext("i:title", "", ns) if image is not None else ""
            image_url = image.findtext("i:loc", "", ns) if image is not None else ""
            product_id, expected = wanted[url]
            if norm(title) == norm(expected) and image_url:
                found[product_id] = (title, image_url)
    return found


def main() -> None:
    products = {item["id"]: item for item in json.loads(INDEX.read_text(encoding="utf-8"))["products"]}
    records: list[dict] = []
    jobs = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        for product_id, (expected, url) in OFFICIAL.items():
            jobs.append((product_id, pool.submit(product_record, products[product_id], expected, url, "Babolat", "exact_official_product")))
        for product_id, (expected, url, retailer) in RETAILER_PAGES.items():
            jobs.append((product_id, pool.submit(product_record, products[product_id], expected, url, retailer, "exact_retailer_product")))
        for product_id, future in jobs:
            try:
                records.append(future.result())
            except Exception as exc:
                print(f"SKIP {product_id}: {exc}")
    found = racquet_guys_images()
    for product_id, (expected, url) in RACQUET_GUYS.items():
        if product_id not in found:
            print(f"SKIP {product_id}: exact sitemap entry not found")
            continue
        title, image_url = found[product_id]
        try:
            local = cache(product_id, image_url)
        except Exception as exc:
            print(f"SKIP {product_id}: {exc}")
            continue
        product = products[product_id]
        records.append({
            "id": product_id, "brand": product["brand"], "model": product["model"], "variant": product["variant"], "category": product["category"],
            "image_url": image_url, "image_local_path": local, "image_verified": True, "product_url": url, "retailer_url": url,
            "source": f"RacquetGuys exact product sitemap title: {title}", "source_type": "exact_retailer_product",
            "source_links": [url, image_url], "last_verified": date.today().isoformat(),
        })
    # The canonical importer recognizes trailing “Junior 25/26” as a variant.
    # Keep the generation in the raw model for these four records so a rebuild
    # preserves the existing model + generation identity instead of stripping
    # the junior size on a second normalization pass.
    for record in records:
        if re.search(r"(?:Team|Lite|Tour|Pro|MP|LS|L|UL|Plus|Junior\s+\d+)$", record["model"], re.I) and record["variant"]:
            record["model"] = f"{record['model']} {record['variant']}"
            record["variant"] = ""
    OUT.write_text(json.dumps({"metadata": {"verified_at": date.today().isoformat(), "scope": "targeted unresolved major/current products only"}, "products": sorted(records, key=lambda item: item["id"])}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verified": len(records), "official": sum(bool(item.get("official_url")) for item in records), "retailer": sum(bool(item.get("retailer_url")) for item in records), "output": str(OUT)}, indent=2))


if __name__ == "__main__":
    main()
