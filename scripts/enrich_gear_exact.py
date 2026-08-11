#!/usr/bin/env python3
"""Enrich existing CourtIQ gear identities from exact, structured web sources.

The matcher deliberately assigns each source product to the longest matching
catalog identity. This prevents a specific product (for example Pure Aero 98)
from being attached to a broader family record (Pure Aero).
"""

from __future__ import annotations

import json
import html as html_lib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "outputs/tennis-ai-app/assets/gear/gear-index.json"
ASSET_DIR = ROOT / "outputs/tennis-ai-app/assets/gear"
OUTPUT = ROOT / "work/gear-sources/exact_product_enrichment_2026-08-10.json"
USER_AGENT = "Mozilla/5.0 (compatible; CourtIQ exact product verifier/1.0)"


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def fetch(url: str) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=35) as response:
        return response.read(), response.headers.get_content_type()


def catalog_products() -> list[dict]:
    return json.loads(INDEX.read_text(encoding="utf-8"))["products"]


def identity(product: dict) -> str:
    return norm(" ".join(filter(None, (product["brand"], product["model"], product["variant"]))))


def cache_image(product: dict, image_url: str) -> str:
    body, content_type = fetch(image_url)
    extensions = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    extension = extensions.get(content_type)
    if not extension or len(body) < 4_000:
        raise ValueError(f"unusable image response: {content_type}, {len(body)} bytes")
    relative = Path("outputs/tennis-ai-app/assets/gear") / f"{product['id']}{extension}"
    destination = ROOT / relative
    destination.write_bytes(body)
    return relative.as_posix()


def holabird_entries() -> list[dict]:
    parent, _ = fetch("https://www.holabirdsports.com/sitemap.xml")
    root = ET.fromstring(parent)
    namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    sitemap_urls = [node.text for node in root.findall("s:sitemap/s:loc", namespace) if node.text and "sitemap_products_" in node.text]
    entries: list[dict] = []
    image_ns = {
        "s": "http://www.sitemaps.org/schemas/sitemap/0.9",
        "i": "http://www.google.com/schemas/sitemap-image/1.1",
    }
    for sitemap_url in sitemap_urls:
        body, _ = fetch(sitemap_url)
        child = ET.fromstring(body)
        for url_node in child.findall("s:url", image_ns):
            page_url = url_node.findtext("s:loc", default="", namespaces=image_ns)
            image_node = url_node.find("i:image", image_ns)
            if image_node is None:
                continue
            title = image_node.findtext("i:title", default="", namespaces=image_ns)
            image_url = image_node.findtext("i:loc", default="", namespaces=image_ns)
            if page_url and title and image_url:
                entries.append({"title": title, "page_url": page_url, "image_url": image_url})
    return entries


def exact_longest_matches(products: list[dict], entries: list[dict]) -> list[tuple[dict, dict]]:
    targets = [(identity(product), product) for product in products]
    matched: dict[str, tuple[dict, dict]] = {}
    for entry in entries:
        source_name = norm(entry["title"])
        candidates = [(name, product) for name, product in targets if source_name == name or source_name.startswith(name + " ")]
        if not candidates:
            continue
        longest = max(len(name.split()) for name, _ in candidates)
        winners = [(name, product) for name, product in candidates if len(name.split()) == longest]
        if len(winners) != 1:
            continue
        _, product = winners[0]
        current = matched.get(product["id"])
        # Prefer the least embellished exact title (typically the base colorway).
        if current is None or len(norm(entry["title"]).split()) < len(norm(current[1]["title"]).split()):
            matched[product["id"]] = (product, entry)
    return list(matched.values())


def yonex_official_matches(products: list[dict]) -> list[tuple[dict, dict]]:
    def inspect(product: dict) -> tuple[dict, dict] | None:
        product_name = " ".join(filter(None, (product["model"], product["variant"])))
        slug = re.sub(r"[^a-z0-9]+", "-", product_name.lower()).strip("-")
        page_url = f"https://us.yonex.com/products/{slug}"
        try:
            body, _ = fetch(page_url)
        except Exception:
            return None
        html = body.decode("utf-8", "ignore")
        title_match = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
        image_match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', html, re.I)
        if not title_match or not image_match:
            return None
        page_name = html_lib.unescape(re.sub(r"<.*?>", "", title_match.group(1))).split("–", 1)[0].strip()
        # Parenthetical merchandising notes such as “(STRUNG)” do not change
        # the named catalog model, but generation numbers must match literally.
        comparable = norm(re.sub(r"\([^)]*\)", "", page_name))
        if comparable != norm(product_name):
            return None
        image_url = urllib.parse.urljoin(page_url, image_match.group(1).replace("&amp;", "&"))
        if image_url.startswith("http://"):
            image_url = "https://" + image_url.removeprefix("http://")
        return product, {"title": page_name, "page_url": page_url, "image_url": image_url}

    yonex_products = [product for product in products if product["brand"] == "Yonex"]
    with ThreadPoolExecutor(max_workers=12) as pool:
        return [match for match in pool.map(inspect, yonex_products) if match is not None]


def main() -> None:
    products = catalog_products()
    pairs = exact_longest_matches(products, holabird_entries())
    official_pairs = yonex_official_matches(products)
    by_id: dict[str, dict] = {}

    for product, entry in pairs:
        try:
            local_path = cache_image(product, entry["image_url"])
        except Exception as exc:
            print(f"SKIP IMAGE {product['id']}: {exc}")
            continue
        by_id[product["id"]] = {
            "id": product["id"],
            "brand": product["brand"],
            "model": product["model"],
            "variant": product["variant"],
            "category": product["category"],
            "image_url": entry["image_url"],
            "image_local_path": local_path,
            "image_verified": True,
            "product_url": entry["page_url"],
            "retailer_url": entry["page_url"],
            "source": f"Holabird Sports exact product sitemap title: {entry['title']}",
            "source_type": "exact_retailer_product",
            "source_links": [entry["page_url"], entry["image_url"]],
            "last_verified": date.today().isoformat(),
        }

    # Official exact matches take precedence over retailer matches.
    for product, entry in official_pairs:
        try:
            local_path = cache_image(product, entry["image_url"])
        except Exception as exc:
            print(f"SKIP IMAGE {product['id']}: {exc}")
            continue
        by_id[product["id"]] = {
            "id": product["id"],
            "brand": product["brand"],
            "model": product["model"],
            "variant": product["variant"],
            "category": product["category"],
            "image_url": entry["image_url"],
            "image_local_path": local_path,
            "image_verified": True,
            "product_url": entry["page_url"],
            "official_url": entry["page_url"],
            "source": f"Yonex USA exact official product page: {entry['title']}",
            "source_type": "exact_official_product",
            "source_links": [entry["page_url"], entry["image_url"]],
            "last_verified": date.today().isoformat(),
        }

    payload = {"metadata": {"verified_at": date.today().isoformat(), "matching_policy": "exact longest brand + model + variant/generation"}, "products": sorted(by_id.values(), key=lambda item: item["id"])}
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"verified_products": len(by_id), "official": sum(bool(item.get("official_url")) for item in by_id.values()), "retailer": sum(bool(item.get("retailer_url")) for item in by_id.values()), "output": str(OUTPUT)}, indent=2))


if __name__ == "__main__":
    main()
