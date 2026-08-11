from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "outputs" / "tennis-ai-app" / "app.js"


def generated_plan_counts() -> list[dict[str, object]]:
    script = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('const TRAINING_GOALS');
const end = source.indexOf('function defaultPlanItems');
if (start < 0 || end < 0) throw new Error('Plan generator source was not found');
const planSource = source.slice(start, end);
const cases = [
  { name: 'single', goal: 'Footwork', level: 'Advanced', days: 4, duration: 45, weeks: 0 },
  { name: 'one-week', goal: 'Footwork', level: 'Advanced', days: 4, duration: 45, weeks: 1 },
  { name: 'two-week', goal: 'Footwork', level: 'Advanced', days: 4, duration: 45, weeks: 2 },
  { name: 'four-week', goal: 'Footwork', level: 'Advanced', days: 4, duration: 45, weeks: 4 },
  { name: 'six-week', goal: 'Footwork', level: 'Advanced', days: 5, duration: 45, weeks: 6 },
  { name: 'eight-week-four-days', goal: 'Footwork', level: 'Advanced', days: 4, duration: 45, weeks: 8 },
  { name: 'eight-week-three-days', goal: 'Footwork', level: 'Advanced', days: 3, duration: 45, weeks: 8 }
];
const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(`${planSource}\n;globalThis.makePlan = generateTrainingPlan;`, sandbox);
const result = cases.map(input => {
  const plan = sandbox.makePlan(input);
  const persisted = JSON.parse(JSON.stringify({ ...plan, selectedSessionId: plan.sessions.at(-1).id }));
  return {
    name: input.name,
    sessions: plan.sessions.length,
    weeks: [...new Set(plan.sessions.map(session => session.week))],
    lastId: plan.sessions.at(-1).id,
    persistedSessions: persisted.sessions.length,
    persistedSelection: persisted.selectedSessionId
  };
});
process.stdout.write(JSON.stringify(result));
"""
    completed = subprocess.run(
        ["node", "-e", script, str(APP_JS)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_supported_plan_lengths_generate_exact_session_counts() -> None:
    results = {item["name"]: item for item in generated_plan_counts()}
    expected = {
        "single": 1,
        "one-week": 4,
        "two-week": 8,
        "four-week": 16,
        "six-week": 30,
        "eight-week-four-days": 32,
        "eight-week-three-days": 24,
    }
    for name, count in expected.items():
        assert results[name]["sessions"] == count
        assert results[name]["persistedSessions"] == count

    eight_week = results["eight-week-four-days"]
    assert eight_week["weeks"] == list(range(1, 9))
    assert eight_week["lastId"] == "week-8-day-4"
    assert eight_week["persistedSelection"] == "week-8-day-4"


def test_plan_ui_exposes_all_sessions_without_completion_gates() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    assert "sessions.slice(1, 9)" not in source
    assert 'data-plan-session="${escapeHtml(item.id)}"' in source
    assert "function selectPlanSession" in source
    assert "activePlan.selectedSessionId = sessionId" in source
    assert "item.status === 'completed' ? 'Completed'" in source
    assert "data-session-complete" in source
