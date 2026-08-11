#!/usr/bin/env node

const fs = require('fs');
const https = require('https');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const DATA_DIR = path.join(ROOT, 'work', 'tennis-data');
const CURRENT_YEAR = 2026;
const START_YEAR = Number(process.argv.find(arg => arg.startsWith('--from='))?.split('=')[1] || 2000);
const END_YEAR = Number(process.argv.find(arg => arg.startsWith('--to='))?.split('=')[1] || CURRENT_YEAR);
const TOURS = process.argv.includes('--atp-only') ? ['atp'] : process.argv.includes('--wta-only') ? ['wta'] : ['atp', 'wta'];

const SOURCES = {
  atp: {
    repo: 'JeffSackmann/tennis_atp',
    raw: year => `https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/atp_matches_${year}.csv`
  },
  wta: {
    repo: 'JeffSackmann/tennis_wta',
    raw: year => `https://raw.githubusercontent.com/JeffSackmann/tennis_wta/master/wta_matches_${year}.csv`
  }
};

function download(url, destination) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(destination);
    https.get(url, response => {
      if (response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
        file.close();
        fs.unlinkSync(destination);
        download(response.headers.location, destination).then(resolve, reject);
        return;
      }

      if (response.statusCode !== 200) {
        file.close();
        fs.unlinkSync(destination);
        reject(new Error(`HTTP ${response.statusCode} for ${url}`));
        return;
      }

      response.pipe(file);
      file.on('finish', () => {
        file.close();
        resolve();
      });
    }).on('error', error => {
      file.close();
      if (fs.existsSync(destination)) fs.unlinkSync(destination);
      reject(error);
    });
  });
}

async function main() {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  const results = [];

  for (const tour of TOURS) {
    for (let year = START_YEAR; year <= END_YEAR; year += 1) {
      const filename = `${tour}_matches_${year}.csv`;
      const destination = path.join(DATA_DIR, filename);
      const url = SOURCES[tour].raw(year);

      if (fs.existsSync(destination) && fs.statSync(destination).size > 1000) {
        results.push({ tour, year, status: 'exists', filename });
        continue;
      }

      try {
        await download(url, destination);
        results.push({ tour, year, status: 'downloaded', filename });
      } catch (error) {
        results.push({ tour, year, status: 'failed', reason: error.message, filename });
      }
    }
  }

  const manifest = {
    source: 'Jeff Sackmann tennis_atp / tennis_wta yearly match CSV files',
    dataDirectory: DATA_DIR,
    generatedAt: new Date().toISOString(),
    startYear: START_YEAR,
    endYear: END_YEAR,
    tours: TOURS,
    results
  };

  fs.writeFileSync(path.join(DATA_DIR, 'source_manifest.json'), JSON.stringify(manifest, null, 2));
  console.log(JSON.stringify(manifest, null, 2));
}

main();
