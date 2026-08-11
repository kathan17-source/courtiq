from __future__ import annotations

from pathlib import Path
import subprocess
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class StaticQualityTests(unittest.TestCase):
    def test_gear_images_do_not_hotlink_unverified_products(self) -> None:
        app_js = (ROOT / "outputs/tennis-ai-app/app.js").read_text(encoding="utf-8")
        router_js = (ROOT / "outputs/tennis-ai-app/js/router.js").read_text(encoding="utf-8")
        self.assertNotIn("VERIFIED_GEAR_IMAGES", app_js)
        self.assertNotIn("tennis-warehouse.com", app_js)
        self.assertNotIn("PRODUCT IMAGE PENDING", app_js)

    def test_no_duplicate_old_export_folder(self) -> None:
        self.assertFalse((ROOT / "outputs/CourtIQ_Tennis_App 2").exists())

    def test_brand_does_not_claim_ai_badge_in_nav(self) -> None:
        index_html = (ROOT / "outputs/tennis-ai-app/index.html").read_text(encoding="utf-8")
        self.assertNotIn("<em>AI</em>", index_html)

    def test_upload_jobs_have_lifecycle_constraints(self) -> None:
        schema = (ROOT / "backend/database/schema.sql").read_text(encoding="utf-8")
        self.assertIn("status TEXT NOT NULL CHECK", schema)
        self.assertIn("idx_uploaded_jobs_expires_at", schema)

    def test_interview_docs_exist(self) -> None:
        for relative_path in ("DEMO.md", "INTERVIEW_NOTES.md", "ALGORITHMS.md", "docs/interview_architecture.md"):
            self.assertTrue((ROOT / relative_path).exists(), relative_path)

    def test_production_prediction_does_not_use_placeholder_rating(self) -> None:
        service = (ROOT / "backend/app/services/prediction_service.py").read_text(encoding="utf-8")
        self.assertNotIn("placeholder_rating", service)
        self.assertIn("load_tour_model", service)
        self.assertIn("request.tour", service)

    def test_frontend_video_uses_backend_analyzer(self) -> None:
        app_js = (ROOT / "outputs/tennis-ai-app/app.js").read_text(encoding="utf-8")
        self.assertIn("/api/video/analyze", app_js)
        self.assertIn("analyzeUploadedVideo", app_js)
        self.assertIn('id="video-upload"', app_js)
        self.assertIn('accept="video/*,.mp4,.mov,.m4v,.webm"', app_js)
        self.assertIn("form.append('file', file)", app_js)
        self.assertNotIn("headers: { 'Content-Type': 'multipart/form-data'", app_js)
        self.assertNotIn("addEventListener('click', buildLocalVideoReport)", app_js)

    def test_video_picker_is_native_visible_and_preview_is_persistent(self) -> None:
        app_js = (ROOT / "outputs/tennis-ai-app/app.js").read_text(encoding="utf-8")
        css = (ROOT / "outputs/tennis-ai-app/styles.css").read_text(encoding="utf-8")
        self.assertIn("native-video-upload", app_js)
        self.assertIn("controls playsinline preload=\"metadata\"", app_js)
        self.assertIn("URL.createObjectURL(file)", app_js)
        self.assertIn("URL.revokeObjectURL(state.selectedVideoUrl)", app_js)
        self.assertIn("button.disabled = !file || Boolean(validationError)", app_js)
        self.assertIn(".native-video-upload::file-selector-button", css)
        self.assertNotIn('id="video-input"', app_js)

    def test_puzzle_board_uses_tactical_geometry_not_placeholder_primitives(self) -> None:
        app_js = (ROOT / "outputs/tennis-ai-app/app.js").read_text(encoding="utf-8")
        css = (ROOT / "outputs/tennis-ai-app/styles.css").read_text(encoding="utf-8")
        for expected in ("function puzzleGeometry", "puzzleTargetForOption", "court-tactical-svg", "incoming-trajectory", "preferred-trajectory", "recovery-trajectory", "decision-target", "athlete-marker", "precise-ball", "tactical-context"):
            self.assertIn(expected, app_js + css)
        board_source = app_js.split("function rallyCourtMarkup", 1)[1].split("function puzzlesPage", 1)[0]
        for removed in ("court-label", "ball-dot", "shot-line", "you-dot", "opponent-dot", "last-choice"):
            self.assertNotIn(removed, board_source)
            self.assertNotIn(f".{removed}", css)
        self.assertIn("const complete = Boolean(state.puzzleFeedback)", app_js)

    def test_analyze_flow_has_no_manual_focus_gate(self) -> None:
        app_js = (ROOT / "outputs/tennis-ai-app/app.js").read_text(encoding="utf-8")
        self.assertNotIn("Choose what should be checked first", app_js)
        self.assertNotIn("data-focus", app_js)
        self.assertNotIn("state.analyzeFocus", app_js)
        self.assertNotIn("Select focus", app_js)
        self.assertIn("browser-detectable metadata", app_js)
        self.assertIn("Automatic video report", app_js)
        self.assertIn("videoDetectionCardsMarkup", app_js)
        self.assertIn("videoLimitationsMarkup", app_js)
        self.assertIn("Detecting strokes and movement", app_js)

    def test_train_side_uses_real_analysis_workflow(self) -> None:
        app_js = (ROOT / "outputs/tennis-ai-app/app.js").read_text(encoding="utf-8")
        self.assertIn("Analysis workflow", app_js)
        self.assertIn("OpenCV + MediaPipe body landmarks", app_js)
        self.assertIn("persistAnalysisRecord", app_js)
        self.assertIn("Add to training plan", app_js)
        self.assertNotIn("Local sample report", app_js)
        self.assertNotIn("Demo fallback report", app_js)

    def test_train_copy_stays_professional(self) -> None:
        app_js = (ROOT / "outputs/tennis-ai-app/app.js").read_text(encoding="utf-8")
        banned = [
            "random chest-day nonsense",
            "mirror muscles",
            "bullshit",
            "fake percentages",
        ]
        for phrase in banned:
            self.assertNotIn(phrase, app_js)

    def test_train_interactions_are_wired(self) -> None:
        app_js = (ROOT / "outputs/tennis-ai-app/app.js").read_text(encoding="utf-8")
        for expected in (
            "handleVideoInput",
            "data-video-time",
            "startTrainingSession",
            "completeTrainingSession",
            "updatePlanCompletion",
        ):
            self.assertIn(expected, app_js)

    def test_match_predictor_uses_real_directory_and_health_check(self) -> None:
        app_js = (ROOT / "outputs/tennis-ai-app/app.js").read_text(encoding="utf-8")
        self.assertIn("COURTIQ_PLAYER_DIRECTORY", app_js)
        self.assertIn("state.selectedTour", app_js)
        self.assertIn("tourSelectorMarkup", app_js)
        self.assertIn("abbreviatedNameCandidates", app_js)
        self.assertIn("/api/health", app_js)
        self.assertIn("prediction service is temporarily unavailable", app_js)
        self.assertNotIn("Prediction service is unavailable</h2>", app_js)

    def test_frontend_player_asset_contains_separate_tours(self) -> None:
        asset = (ROOT / "outputs/tennis-ai-app/assets/player-stats.js").read_text(encoding="utf-8")
        self.assertIn('"tour":"ATP"', asset)
        self.assertIn('"tour":"WTA"', asset)
        self.assertIn("window.COURTIQ_PLAYER_DIRECTORY", asset)

    def test_wta_ingestion_location_is_documented(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("work/tennis-data/wta/", readme)
        self.assertIn("python scripts/train_models.py --tour wta", readme)
        self.assertTrue((ROOT / "scripts/run_courtiq.py").exists())
        self.assertTrue((ROOT / "scripts/train_models.py").exists())

    def test_atp_training_routes_to_round_safe_pipeline(self) -> None:
        train_models = (ROOT / "scripts/train_models.py").read_text(encoding="utf-8")
        self.assertIn("train_atp_round_safe", train_models)
        self.assertIn("final_modeling_pass", train_models)
        self.assertIn("round_safe", train_models)
        self.assertIn("train_basic_tour", train_models)

    def test_prediction_feed_only_uses_verified_schedule_rows(self) -> None:
        app_js = (ROOT / "outputs/tennis-ai-app/app.js").read_text(encoding="utf-8")
        self.assertIn("UPCOMING_PREDICTIONS", app_js)
        self.assertIn("verified_schedule === true", app_js)
        self.assertIn("groupedUpcomingPredictions", app_js)
        self.assertIn("No verified upcoming", app_js)

    def test_prediction_feed_has_no_tournament_finder_state(self) -> None:
        app_js = (ROOT / "outputs/tennis-ai-app/app.js").read_text(encoding="utf-8")
        for removed in (
            "tournamentLocation",
            "tournamentCountry",
            "tournamentSurface",
            "tournamentDateRange",
            "tournamentResultsOpen",
            "function updateTournamentFilter",
            "function refreshTournamentResults",
            "filteredTournamentEvents",
            "tournamentResultsMarkup",
            "tournament-country",
            "tournament-surface",
            "tournament-date-range",
            "find-tournaments')?.addEventListener('click', buildTournamentOutput)",
        ):
            self.assertNotIn(removed, app_js)

    def test_frontend_contrast_guardrails_exist(self) -> None:
        css = (ROOT / "outputs/tennis-ai-app/styles.css").read_text(encoding="utf-8")
        for expected in (
            "--bg-app",
            "--bg-surface",
            "--bg-surface-raised",
            "--bg-surface-interactive",
            "--accent-text",
            "--accent-foreground",
            "--text-primary",
            "--text-secondary",
            "--text-muted",
            "--border-subtle",
            "--accent-lime",
            "--accent-cyan",
            "button:disabled",
            ".primary-action:hover",
            "select option",
            ".angle-hints b",
            ".detected-grid",
            ".tournament-cards article",
            ".puzzle-options button.correct",
            ".security-row",
        ):
            self.assertIn(expected, css)
        self.assertNotIn("background: var(--accent);\n  color: var(--ink);", css)

    def test_puzzle_court_is_procedural_and_interactive(self) -> None:
        app_js = (ROOT / "outputs/tennis-ai-app/app.js").read_text(encoding="utf-8")
        for expected in (
            "PUZZLE_CATEGORIES",
            "PUZZLE_DIFFICULTIES",
            "PUZZLE_SURFACES",
            "PUZZLE_ARCHETYPES",
            "PUZZLE_SCENARIO_SPACE_ESTIMATE",
            "function generatePuzzleScenario",
            "function tacticalStateFromSeed",
            "function legalPuzzleOptions",
            "function nextPuzzleSeed",
            "nextPuzzleId",
            "puzzleStats",
            "puzzleSeed",
            "puzzle-category",
            "puzzle-difficulty",
            "puzzle-surface",
            "start-puzzle-training",
        ):
            self.assertIn(expected, app_js)
        self.assertNotIn("const PUZZLE_LIBRARY", app_js)
        self.assertNotIn("buildProceduralPuzzleLibrary", app_js)
        self.assertNotIn("Choose a rally type", app_js)
        self.assertNotIn("data-puzzle-id", app_js)

    def test_puzzle_generator_samples_diverse_valid_scenarios(self) -> None:
        app_js = (ROOT / "outputs/tennis-ai-app/app.js").read_text(encoding="utf-8")
        start = app_js.index("const PUZZLE_CATEGORIES")
        end = app_js.index("const COMPETE_ROWS", start)
        generator_source = app_js[start:end]
        script = textwrap.dedent(
            f"""
            {generator_source}
            const signatures = new Set();
            for (let i = 1; i <= 1000; i += 1) {{
              const scenario = generatePuzzleScenario(i * 7919, {{
                category: i % 2 ? 'Return' : 'Attack',
                difficulty: i % 3 ? 'Advanced' : 'Elite',
                surface: i % 5 ? 'Hard court' : 'Clay court'
              }});
              if (!scenario.signature) throw new Error('missing signature');
              if (scenario.category !== 'Return' && scenario.category !== 'Attack') throw new Error('category mismatch');
              if (scenario.difficulty !== 'Advanced' && scenario.difficulty !== 'Elite') throw new Error('difficulty mismatch');
              if (!scenario.steps?.[0]?.[3] || new Set(scenario.steps[0][3]).size !== scenario.steps[0][3].length) throw new Error('duplicate options');
              if (typeof scenario.steps[0][4] !== 'number') throw new Error('missing preferred option');
              signatures.add(scenario.signature);
            }}
            if (signatures.size < 600) throw new Error(`low scenario diversity: ${{signatures.size}}`);
            """
        )
        subprocess.run(["node", "-e", script], cwd=ROOT, check=True)

    def test_gear_is_hidden_but_catalog_assets_are_preserved(self) -> None:
        app_js = (ROOT / "outputs/tennis-ai-app/app.js").read_text(encoding="utf-8")
        router_js = (ROOT / "outputs/tennis-ai-app/js/router.js").read_text(encoding="utf-8")
        index_html = (ROOT / "outputs/tennis-ai-app/index.html").read_text(encoding="utf-8")
        gear_index = (ROOT / "outputs/tennis-ai-app/assets/gear/gear-index.js").read_text(encoding="utf-8")
        self.assertNotIn("assets/gear/gear-index.js", index_html)
        self.assertIn("window.COURTIQ_GEAR_INDEX", gear_index)
        self.assertIn("bootstrap_seed.json", gear_index)
        self.assertNotIn("['train/gear', 'gear'", app_js)
        self.assertNotIn('data-page="train/gear"', index_html)
        self.assertIn("raw === 'gear' || raw === 'train/gear'", router_js)

    def test_profile_security_is_dark_compact_not_fake_settings(self) -> None:
        app_js = (ROOT / "outputs/tennis-ai-app/app.js").read_text(encoding="utf-8")
        css = (ROOT / "outputs/tennis-ai-app/styles.css").read_text(encoding="utf-8")
        self.assertIn("SECURITY & PRIVACY", app_js)
        self.assertIn("security-row", app_js)
        self.assertIn("local-profile-reset", app_js)
        self.assertNotIn("blocked users", app_js.lower())
        self.assertNotIn("Tournament wins, upload streaks", app_js)
        self.assertIn(".security-panel", css)
        self.assertIn(".security-row", css)


if __name__ == "__main__":
    unittest.main()
