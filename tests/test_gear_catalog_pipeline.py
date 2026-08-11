import datetime as dt
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "update_gear_catalog.py"


spec = importlib.util.spec_from_file_location("gear_catalog", SCRIPT)
gear_catalog = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(gear_catalog)


def test_canonicalization_uses_required_product_schema():
    product = gear_catalog.canonicalize_record(
        {
            "brand": "Wilson",
            "name": "Blade 98",
            "type": "rackets",
            "specs": "98 in² · 305 g · 16×19",
            "product_url": "https://www.wilson.com/example-blade",
            "source": "unit fixture",
            "source_type": "official",
            "last_verified": "2026-08-01",
            "status": "current",
        }
    )

    for field in gear_catalog.CANONICAL_FIELDS:
        assert field in product
    assert product["category"] == "Racket"
    assert product["specs"]["head_size_sq_in"] == 98
    assert product["specs"]["unstrung_weight_g"] == 305
    assert product["specs"]["string_pattern"] == "16x19"
    assert product["product_url"] in product["source_links"]


def test_dedupe_merges_brand_model_variant_without_duplicate_cards():
    first = gear_catalog.canonicalize_record(
        {"brand": "HEAD", "name": "Speed MP", "type": "Racket", "specs": "100 in² · 300 g · 16×19"}
    )
    second = gear_catalog.canonicalize_record(
        {"brand": "HEAD", "model": "Speed MP", "category": "racquet", "product_url": "https://www.head.com/speed-mp"}
    )
    deduped = gear_catalog.dedupe_products([first, second])

    assert len(deduped) == 1
    assert deduped[0]["product_url"] == "https://www.head.com/speed-mp"


def test_search_exact_prefix_token_and_fuzzy_match():
    products = [
        gear_catalog.canonicalize_record({"brand": "Babolat", "name": "Pure Drive", "type": "Racket"}),
        gear_catalog.canonicalize_record({"brand": "ASICS", "name": "Gel Resolution", "type": "Shoes"}),
    ]

    assert gear_catalog.search_products(products, "Babolat Pure Drive")[0]["brand"] == "Babolat"
    assert gear_catalog.search_products(products, "Pure")[0]["model"] == "Pure Drive"
    assert gear_catalog.search_products(products, "gel shoes")[0]["brand"] == "ASICS"
    assert gear_catalog.search_products(products, "pur drve")[0]["brand"] == "Babolat"


def test_filters_and_pagination_do_not_load_entire_index_at_once():
    products = [
        gear_catalog.canonicalize_record({"brand": "Wilson", "name": f"Blade {idx}", "type": "Racket"})
        for idx in range(40)
    ]
    filtered = gear_catalog.filter_products(products, category="Racket", brand="Wilson")
    page = gear_catalog.paginate_products(filtered, page=1, page_size=24)

    assert len(filtered) == 40
    assert len(page["items"]) == 24
    assert page["has_more"] is True


def test_missing_images_and_stale_products_are_explicit():
    product = gear_catalog.canonicalize_record(
        {
            "brand": "Prince",
            "name": "Phantom 100",
            "type": "Racket",
            "image_url": "https://example.com/not-trusted.jpg",
            "status": "current",
            "last_verified": "2020-01-01",
        }
    )
    product = gear_catalog.mark_staleness(product, today=dt.date(2026, 8, 9))

    assert gear_catalog.image_is_usable(product) is False
    assert product["image_url"] == ""
    assert product["status"] == "unknown"
