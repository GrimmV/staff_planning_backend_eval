'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {evaluateDiff, parseTable} = require('./engine.js');
const examples = require('./examples.js');
const clone = x => JSON.parse(JSON.stringify(x));

test('three cached examples span all decision labels without reading LLM results', () => {
  assert.deepEqual(examples.map(x => evaluateDiff(x.diff).score), ['eher akzeptieren', 'ablehnen', 'eher ablehnen']);
  for (const x of examples) {
    const before = JSON.stringify(x.diff);
    assert.deepEqual(evaluateDiff(x.diff), evaluateDiff(clone(x.diff)));
    assert.equal(JSON.stringify(x.diff), before, 'input is not mutated');
  }
});

test('bundled sources are exact, correctly paired copies when the cache is available', () => {
  for (const x of examples) {
    for (const source of x.sources) {
      const file = path.resolve(__dirname, '..', source.path);
      if (fs.existsSync(file)) assert.equal(crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'), source.sha256);
    }
    const diffFile = path.resolve(__dirname, '..', x.sources[0].path);
    const evalFile = path.resolve(__dirname, '..', x.sources[1].path);
    if (fs.existsSync(diffFile)) assert.deepEqual(x.diff, JSON.parse(fs.readFileSync(diffFile, 'utf8')).diff);
    if (fs.existsSync(evalFile)) assert.deepEqual(x.assessment, JSON.parse(fs.readFileSync(evalFile, 'utf8')).assessment);
  }
});

test('commute threshold is strict; changing it can change the label', () => {
  assert.equal(evaluateDiff(examples[0].diff, {travelThreshold: 27}).score, 'eher ablehnen');
  assert.equal(evaluateDiff(examples[0].diff, {travelThreshold: 28}).score, 'eher akzeptieren');
  const r = evaluateDiff(examples[2].diff, {travelThreshold: 51});
  assert.equal(r.score, 'eher ablehnen', 'familiarity loss still applies at 51');
  assert.match(r.trace[2].observation, /0 added commute/);
});

test('binary familiarity treats 6 to 1 days as retained, but 6 to zero as loss', () => {
  const diff = clone(examples[0].diff);
  assert.equal(evaluateDiff(diff).trace[2].hit, false);
  diff.nachher = diff.nachher.replace('15 min ✅ | 1 Tage | 1 Tage', '15 min ✅ | Keine | 1 Tage');
  assert.equal(evaluateDiff(diff).score, 'eher ablehnen');
});

test('coverage veto wins even when a lower rule also triggers', () => {
  const r = evaluateDiff(examples[1].diff, {travelThreshold: 0});
  assert.equal(r.trace[0].deciding, true);
  assert.equal(r.trace[2].hit, true);
  assert.equal(r.trace[2].deciding, false);
  assert.deepEqual(r.lostClients.map(x => x.client), ['Max Bauer']);
  assert.equal(r.score, 'ablehnen');
});

test('an individual lost high-priority client cannot be hidden by an equal count', () => {
  const diff = clone(examples[1].diff);
  diff.nachher = diff.nachher.replace('Lena Richter | niedrig', 'Lena Richter | hoch');
  assert.equal(evaluateDiff(diff).score, 'ablehnen');
  assert.equal(evaluateDiff(diff).statistics[1].before, evaluateDiff(diff).statistics[1].after);
});

test('qualification mismatch is a veto and missing dates require review', () => {
  const diff = clone(examples[0].diff);
  diff.nachher = diff.nachher.replace('✅', '❌');
  assert.equal(evaluateDiff(diff).score, 'ablehnen');
  assert.equal(evaluateDiff(diff).trace[1].deciding, true);
  diff.nachher = diff.nachher.replace('2025-03-17', 'unknown');
  assert.equal(evaluateDiff(diff).status, 'review');
});

test('daily equality is covered; a high-priority shortfall is a veto', () => {
  const diff = clone(examples[2].diff);
  diff.nachher = diff.nachher.replace('13:00 | 13:00', '13:00 | 12:59');
  assert.match(evaluateDiff(diff).trace[2].observation, /1 added assignment\(s\) have/);
  diff.nachher = diff.nachher.replace('Niklas Koch | mittel', 'Niklas Koch | hoch');
  assert.equal(evaluateDiff(diff).score, 'ablehnen');
});

test('date shortfall flags risk even when daily end times fit', () => {
  const diff = clone(examples[0].diff);
  diff.nachher = diff.nachher.replace('2025-03-17 | 2025-03-17', '2025-03-17 | 2025-03-16');
  assert.equal(evaluateDiff(diff).score, 'eher ablehnen');
});

test('malformed or ambiguous evidence never silently becomes acceptance', () => {
  for (const diff of [null, {}, {vorher: 'broken'}, {...examples[0].diff, stats: {}}]) assert.equal(evaluateDiff(diff).status, 'review');
  const diff = clone(examples[0].diff);
  diff.stats.anzahl.hinzugefügt += 1;
  assert.equal(evaluateDiff(diff).status, 'review');
  assert.equal(evaluateDiff(examples[0].diff, {travelThreshold: NaN}).status, 'review');
  assert.throws(() => parseTable(examples[0].diff.vorher.replace('Marie Schröder', 'Tom Werner')), /Ambiguous/);
});
