import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "outputs" / "tennis-ai-app" / "app.js"
INDEX_HTML = ROOT / "outputs" / "tennis-ai-app" / "index.html"
ROUTER_JS = ROOT / "outputs" / "tennis-ai-app" / "js" / "router.js"


EXPECTED_ROUTES = {
    "train/overview": "trainhome",
    "train/analyze": "analyze",
    "train/plan": "train",
    "train/learn": "learn",
    "train/puzzles": "puzzles",
    "train/profile": "profile",
    "predict/overview": "predict",
    "predict/match": "quant",
    "predict/players": "players",
    "predict/compare": "compare",
    "predict/tournaments": "compete",
    "predict/simulation": "simulation",
    "predict/model-lab": "model",
}


def test_frontend_has_canonical_route_model():
    source = APP_JS.read_text()
    router = ROUTER_JS.read_text()

    assert "const ROUTE_DEFINITIONS" in router
    assert "function normalizeRoute" in router
    assert "function applyRoute" in source
    assert "function goToPage" in source

    for route, page in EXPECTED_ROUTES.items():
        assert f"['{route}', '{page}'" in router


def test_sidebar_uses_canonical_deep_links():
    html = INDEX_HTML.read_text()

    for route in EXPECTED_ROUTES:
        assert f'data-page="{route}"' in html


def test_old_one_word_routes_still_have_aliases():
    source = ROUTER_JS.read_text()
    legacy_aliases = [
        "trainhome",
        "today",
        "analyze",
        "train",
        "learn",
        "puzzles",
        "profile",
        "predict",
        "quant",
        "players",
        "compare",
        "compete",
        "simulation",
        "model",
    ]

    for alias in legacy_aliases:
        assert f"'{alias}'" in source


def test_render_active_state_uses_normalized_routes_not_raw_page_ids():
    source = APP_JS.read_text()

    assert "normalizeRoute(button.dataset.page).id === state.route" in source
    assert "button.dataset.page === state.page" not in source


def test_product_switch_restores_last_product_route():
    source = APP_JS.read_text()

    assert "cqLastTrainRoute" in source
    assert "cqLastPredictRoute" in source
    assert "savedRouteForProduct(nextProduct)" in source
    assert "setProduct(target.dataset.product, target.dataset.route)" in source


def test_landing_entries_open_product_overviews():
    source = APP_JS.read_text()

    assert 'data-product="train" data-route="train/overview"' in source
    assert 'data-product="predict" data-route="predict/overview"' in source
    for route in (
        "train/analyze",
        "train/plan",
        "train/puzzles",
        "predict/match",
        "predict/compare",
        "predict/simulation",
        "predict/model-lab",
    ):
        assert f'data-page="{route}"' in source


def test_entry_sidebar_and_history_use_stable_delegated_routing():
    source = APP_JS.read_text()

    assert "function handleRouteIntent(event)" in source
    assert "document.addEventListener('click', handleRouteIntent);" in source
    assert "target.dataset.route" in source
    assert "goToPage(target.dataset.page)" in source
    assert "window.addEventListener('hashchange'" in source
    assert "location.hash = route.id" in source
    assert "history.replaceState" in source

    bind_source = source.split("function bindPageEvents()", 1)[1].split("function render()", 1)[0]
    assert "$$('button[data-product]')" not in bind_source
    assert "$$('[data-page]')" not in bind_source


def test_internal_ctas_use_canonical_routes():
    source = APP_JS.read_text()
    html = INDEX_HTML.read_text()
    allowed = set(EXPECTED_ROUTES) | {"entry"}
    legacy_pages = {
        "analyze",
        "train",
        "learn",
        "puzzles",
        "gear",
        "profile",
        "quant",
        "players",
        "compare",
        "compete",
        "simulation",
        "model",
    }

    data_pages = {
        page
        for page in re.findall(r'data-page="([^"]+)"', source + html)
        if not page.startswith("${")
    }
    assert data_pages <= allowed
    assert not (data_pages & legacy_pages)

    action_pages = set(re.findall(r"actionButton\('[^']+', '([^']+)'\)", source))
    assert action_pages <= allowed
    assert not (action_pages & legacy_pages)


def test_analyze_and_prediction_feed_routes_render_current_controls():
    source = APP_JS.read_text()
    analyze_function = source.split("function analyzePage()", 1)[1].split("function", 1)[0]
    compete_function = source.split("function competePage()", 1)[1].split("function", 1)[0]

    assert "video-upload" in analyze_function
    assert 'accept="video/*,.mp4,.mov,.m4v,.webm"' in analyze_function
    assert "analyze-btn" in analyze_function
    assert "Choose what should be checked first" not in analyze_function
    assert "focus-pill" not in analyze_function

    for expected in ("prediction-tournament", "prediction-line", "groupedUpcomingPredictions"):
        assert expected in compete_function
    for removed in ("tournament-location", "tournament-country", "tournament-surface", "tournament-date-range"):
        assert removed not in compete_function


def test_puzzle_route_remains_and_gear_route_is_removed():
    source = APP_JS.read_text()
    puzzle_function = source.split("function puzzlesPage()", 1)[1].split("function analyzePage()", 1)[0]

    for expected in ("puzzle-category", "puzzle-difficulty", "puzzle-surface", "start-puzzle-training", "data-puzzle-answer"):
        assert expected in puzzle_function
    assert "Choose a rally type" not in puzzle_function

    assert "['train/gear', 'gear'" not in source
    assert "raw === 'gear' || raw === 'train/gear'" in ROUTER_JS.read_text()
    assert 'data-page="train/gear"' not in INDEX_HTML.read_text()


def test_plan_native_selects_survive_route_navigation_regression():
    source = APP_JS.read_text()
    plan_source = source.split("function trainPage()", 1)[1].split("function competePage()", 1)[0]

    for control_id in ("plan-goal", "plan-level", "plan-days", "plan-duration", "plan-weeks"):
        assert f'<select id="{control_id}"' in plan_source

    assert "const renderPendingFromHashChange = syncHash" in source
    assert "if (!renderPendingFromHashChange) render();" in source
    assert "location.hash = route.id;\n  return true;" in source
    assert "document.addEventListener('click', handleRouteIntent);" in source
    bind_source = source.split("function bindPageEvents()", 1)[1].split("function render()", 1)[0]
    assert "$$('[data-product]')" not in bind_source
    assert "route.id === state.route" in source
    assert "generatedPlanBuilder.replaceWith(existingPlanBuilder)" in source
