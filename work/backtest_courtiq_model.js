#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const DATA_DIR = process.argv[2] ? path.resolve(process.argv[2]) : path.join(ROOT, 'work', 'tennis-data');
const OUT_DIR = path.join(ROOT, 'output', 'backtests');
const OUT_FILE = path.join(OUT_DIR, 'courtiq_backtest_report.json');
const FRONTEND_STATS_FILE = path.join(ROOT, 'outputs', 'tennis-ai-app', 'assets', 'player-stats.js');

const SURFACE_KEYS = {
  Hard: 'hard',
  Clay: 'clay',
  Grass: 'grass',
  Carpet: 'hard'
};

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function sigmoid(value) {
  return 1 / (1 + Math.exp(-value));
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = '';
  let quoted = false;

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];

    if (quoted) {
      if (char === '"' && next === '"') {
        cell += '"';
        i += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        cell += char;
      }
      continue;
    }

    if (char === '"') {
      quoted = true;
    } else if (char === ',') {
      row.push(cell);
      cell = '';
    } else if (char === '\n') {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = '';
    } else if (char !== '\r') {
      cell += char;
    }
  }

  if (cell.length || row.length) {
    row.push(cell);
    rows.push(row);
  }

  if (!rows.length) return [];
  const headers = rows.shift();
  return rows
    .filter(items => items.length === headers.length)
    .map(items => Object.fromEntries(headers.map((header, index) => [header, items[index]])));
}

function playerKey(name) {
  return String(name || '').trim();
}

function ratingFor(store, player) {
  const key = playerKey(player);
  if (!store.has(key)) {
    store.set(key, {
      global: 1500,
      hard: 1500,
      clay: 1500,
      grass: 1500,
      matches: 0,
      uncertainty: 85
    });
  }
  return store.get(key);
}

function expectedScore(aRating, bRating) {
  return 1 / (1 + 10 ** ((bRating - aRating) / 400));
}

function gameWinProbability(pointProbability) {
  const p = clamp(pointProbability, 0.01, 0.99);
  const q = 1 - p;
  const beforeDeuce = (p ** 4) * (1 + 4 * q + 10 * (q ** 2));
  const reachDeuce = 20 * (p ** 3) * (q ** 3);
  const winFromDeuce = (p ** 2) / ((p ** 2) + (q ** 2));
  return beforeDeuce + reachDeuce * winFromDeuce;
}

function matchWinFromSet(setProbability, bestOf) {
  const p = clamp(setProbability, 0.01, 0.99);
  if (Number(bestOf) === 5) {
    return (p ** 3) * (1 + 3 * (1 - p) + 6 * ((1 - p) ** 2));
  }
  return (p ** 2) * (3 - 2 * p);
}

function predictMatch(winnerRating, loserRating, surfaceKey, bestOf) {
  const surfaceA = winnerRating[surfaceKey] ?? winnerRating.global;
  const surfaceB = loserRating[surfaceKey] ?? loserRating.global;
  const blendedA = 0.58 * surfaceA + 0.32 * winnerRating.global - 0.10 * winnerRating.uncertainty;
  const blendedB = 0.58 * surfaceB + 0.32 * loserRating.global - 0.10 * loserRating.uncertainty;
  const prior = expectedScore(blendedA, blendedB);

  const pointEdge = clamp((blendedA - blendedB) / 1150, -0.11, 0.11);
  const pServeA = clamp(0.635 + pointEdge, 0.50, 0.78);
  const pServeB = clamp(0.635 - pointEdge, 0.50, 0.78);
  const holdA = gameWinProbability(pServeA);
  const holdB = gameWinProbability(pServeB);
  const setProb = sigmoid((holdA - holdB) * 3.4);
  const markov = matchWinFromSet(setProb, bestOf);

  return clamp(0.62 * markov + 0.38 * prior, 0.02, 0.98);
}

function updateRatings(a, b, surfaceKey, aWon, bestOf) {
  const surfaceA = a[surfaceKey] ?? a.global;
  const surfaceB = b[surfaceKey] ?? b.global;
  const expected = expectedScore(0.55 * surfaceA + 0.45 * a.global, 0.55 * surfaceB + 0.45 * b.global);
  const result = aWon ? 1 : 0;
  const importance = Number(bestOf) === 5 ? 1.08 : 1;
  const experienceDrag = 1 / (1 + Math.min(a.matches, b.matches) / 140);
  const k = (18 + 18 * experienceDrag) * importance;
  const delta = k * (result - expected);

  a.global += delta * 0.42;
  b.global -= delta * 0.42;
  a[surfaceKey] = surfaceA + delta * 0.72;
  b[surfaceKey] = surfaceB - delta * 0.72;
  a.matches += 1;
  b.matches += 1;
  a.uncertainty = Math.max(28, a.uncertainty * 0.992);
  b.uncertainty = Math.max(28, b.uncertainty * 0.992);
}

function scoreBucket(probability) {
  const lower = Math.floor(probability * 10) / 10;
  return `${Math.round(lower * 100)}-${Math.round((lower + 0.1) * 100)}%`;
}

function collectFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir)
    .filter(file => /^(atp|wta)_matches_\d{4}\.csv$/i.test(file))
    .map(file => path.join(dir, file))
    .sort();
}

function repoPath(filePath) {
  return path.relative(ROOT, filePath).replaceAll(path.sep, '/');
}

function summarize(matches) {
  const ratings = new Map();
  const summary = {
    matches: 0,
    correct: 0,
    brierSum: 0,
    logLossSum: 0,
    byTour: {},
    bySurface: {},
    calibration: {}
  };

  for (const match of matches) {
    const surfaceKey = SURFACE_KEYS[match.surface] || 'hard';
    const winner = playerKey(match.winner_name);
    const loser = playerKey(match.loser_name);
    if (!winner || !loser || winner === loser) continue;

    const winnerRating = ratingFor(ratings, winner);
    const loserRating = ratingFor(ratings, loser);
    const pWinner = predictMatch(winnerRating, loserRating, surfaceKey, match.best_of);
    const modelCorrect = pWinner >= 0.5;
    const confidence = Math.max(pWinner, 1 - pWinner);
    const brier = (1 - pWinner) ** 2;
    const logLoss = -Math.log(clamp(pWinner, 0.001, 0.999));
    const bucket = scoreBucket(confidence);

    summary.matches += 1;
    summary.correct += modelCorrect ? 1 : 0;
    summary.brierSum += brier;
    summary.logLossSum += logLoss;

    const tour = match.tour || 'unknown';
    summary.byTour[tour] ||= { matches: 0, correct: 0 };
    summary.byTour[tour].matches += 1;
    summary.byTour[tour].correct += modelCorrect ? 1 : 0;

    summary.bySurface[surfaceKey] ||= { matches: 0, correct: 0 };
    summary.bySurface[surfaceKey].matches += 1;
    summary.bySurface[surfaceKey].correct += modelCorrect ? 1 : 0;

    summary.calibration[bucket] ||= { matches: 0, observedWins: 0, averageConfidence: 0 };
    summary.calibration[bucket].matches += 1;
    summary.calibration[bucket].observedWins += modelCorrect ? 1 : 0;
    summary.calibration[bucket].averageConfidence += confidence;

    updateRatings(winnerRating, loserRating, surfaceKey, true, match.best_of);
  }

  const finishGroup = group => Object.fromEntries(Object.entries(group).map(([key, value]) => [
    key,
    {
      matches: value.matches,
      accuracy: +(value.correct / Math.max(1, value.matches) * 100).toFixed(2)
    }
  ]));

  const playerStats = Object.fromEntries([...ratings.entries()]
    .filter(([, value]) => value.matches >= 5)
    .sort((a, b) => b[1].matches - a[1].matches)
    .map(([name, value]) => [
      name,
      {
        global: +value.global.toFixed(1),
        hard: +(value.hard ?? value.global).toFixed(1),
        clay: +(value.clay ?? value.global).toFixed(1),
        grass: +(value.grass ?? value.global).toFixed(1),
        form: 50,
        pressure: 50,
        fatigue: Math.max(4, Math.round(value.uncertainty / 12)),
        matches: value.matches
      }
    ]));

  return {
    matches: summary.matches,
    accuracy: +(summary.correct / Math.max(1, summary.matches) * 100).toFixed(2),
    brier: +(summary.brierSum / Math.max(1, summary.matches)).toFixed(4),
    logLoss: +(summary.logLossSum / Math.max(1, summary.matches)).toFixed(4),
    byTour: finishGroup(summary.byTour),
    bySurface: finishGroup(summary.bySurface),
    playerStatProfiles: Object.keys(playerStats).length,
    playerStats,
    calibration: Object.fromEntries(Object.entries(summary.calibration).map(([key, value]) => [
      key,
      {
        matches: value.matches,
        averageConfidence: +(value.averageConfidence / value.matches * 100).toFixed(2),
        observedAccuracy: +(value.observedWins / value.matches * 100).toFixed(2)
      }
    ]))
  };
}

function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const files = collectFiles(DATA_DIR);

  if (!files.length) {
    const report = {
      status: 'no_data',
      message: 'No real ATP/WTA match CSV files found. Add Jeff Sackmann style files such as atp_matches_2025.csv and wta_matches_2025.csv to work/tennis-data, then rerun this script.',
      expectedDirectory: repoPath(DATA_DIR),
      expectedFilePattern: '(atp|wta)_matches_YYYY.csv',
      output: repoPath(OUT_FILE)
    };
    fs.writeFileSync(OUT_FILE, JSON.stringify(report, null, 2));
    fs.mkdirSync(path.dirname(FRONTEND_STATS_FILE), { recursive: true });
    fs.writeFileSync(FRONTEND_STATS_FILE, 'window.COURTIQ_PLAYER_STATS = {};\n');
    console.log(JSON.stringify(report, null, 2));
    return;
  }

  const matches = [];
  for (const file of files) {
    const tour = path.basename(file).startsWith('wta') ? 'wta' : 'atp';
    const rows = parseCsv(fs.readFileSync(file, 'utf8'));
    for (const row of rows) {
      if (!row.winner_name || !row.loser_name || !row.surface) continue;
      matches.push({ ...row, tour });
    }
  }

  matches.sort((a, b) => String(a.tourney_date || '').localeCompare(String(b.tourney_date || '')));
  const report = {
    status: 'ok',
    dataDirectory: repoPath(DATA_DIR),
    files: files.map(file => path.basename(file)),
    ...summarize(matches)
  };

  fs.writeFileSync(OUT_FILE, JSON.stringify(report, null, 2));
  fs.mkdirSync(path.dirname(FRONTEND_STATS_FILE), { recursive: true });
  fs.writeFileSync(
    FRONTEND_STATS_FILE,
    `window.COURTIQ_PLAYER_STATS = ${JSON.stringify(report.playerStats || {}, null, 2)};\n`
  );
  console.log(JSON.stringify(report, null, 2));
}

main();
