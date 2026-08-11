from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "outputs" / "tennis-ai-app" / "app.js"


def learn_source():
    return APP_JS.read_text()


def test_three_distinct_curriculum_levels_exist():
    source = learn_source()
    assert "const LEARN_CURRICULUM" in source
    for level in ("Beginner", "Intermediate", "Advanced"):
        assert f"  {level}: [" in source

    for beginner_topic in ("Ready position", "Tennis scoring", "Contact in front"):
        assert beginner_topic in source
    for intermediate_topic in ("Serve +1 patterns", "Blocking big serves", "Changing direction safely"):
        assert intermediate_topic in source
    for advanced_topic in ("Serve disguise", "Creating court asymmetry", "Scoreboard-aware risk"):
        assert advanced_topic in source


def test_curriculum_controls_are_real_and_bound():
    source = learn_source()
    for control in (
        "data-learn-level",
        "data-learn-category",
        "data-learn-open",
        "data-learn-related",
        "data-learn-back",
    ):
        assert control in source

    assert "updateLearnView({ learnLevel:" in source
    assert "updateLearnView({ learnCategory:" in source
    assert "updateLearnView({ learnOpenLesson:" in source
    assert "button[data-learn-open], button[data-learn-related]" in source


def test_learn_history_and_local_level_persistence():
    source = learn_source()
    assert "localStorage.cqLearnLevel" in source
    assert "history.pushState" in source
    assert "window.addEventListener('popstate'" in source
    assert "event.state?.courtiqLearn" in source


def test_puzzle_links_use_central_router():
    source = learn_source()
    learn_page = source.split("function learnPage()", 1)[1].split("function currentPuzzle()", 1)[0]
    assert "actionButton('Open Puzzle Court', 'train/puzzles')" in learn_page
    assert 'data-page="train/puzzles"' in source
    assert "document.addEventListener('click', handleRouteIntent);" in source


def test_old_dead_lesson_tiles_are_removed():
    source = learn_source()
    learn_page = source.split("function learnPage()", 1)[1].split("function currentPuzzle()", 1)[0]
    for dead_markup in ("lesson-steps", "intro-lesson", "LEARN_MODULES", "mini-module"):
        assert dead_markup not in learn_page
    assert "Ready position" in source
    assert "data-learn-open" in learn_page


def test_no_gamification_added_to_learn():
    source = learn_source()
    learn_section = source.split("const LEARN_CURRICULUM", 1)[1].split("const PUZZLE_CATEGORIES", 1)[0]
    for term in ("XP", "badge", "streak", "mastery", "completion bar"):
        assert term not in learn_section
