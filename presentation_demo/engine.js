/* Pure, local replacement for evidence summarization and assessment.
   Input: the same {stats, vorher, nachher} diff consumed by evaluate_diff.py.
   No model output is read here. Policy v1 is deliberately small and explicit. */
(function (root) {
  'use strict';
  const HEADERS = ['Mitarbeiter', 'Klient', 'Priorität', 'Klient Tag bis', 'Mitarbeiter Tag bis', 'Quali-Fit', 'Fahrtzeit', 'Erfahrung (Klient)', 'Erfahrung (Schule)', 'Klient nicht vertreten bis', 'Mitarbeiter kann vertreten bis'];
  const LABELS = {accept: 'eher akzeptieren', caution: 'eher ablehnen', reject: 'ablehnen', review: 'manual review'};
  function time(value) {
    if (!/^\d{1,2}:\d{2}$/.test(value)) throw Error(`Invalid time: ${value}`);
    const [h, m] = value.split(':').map(Number);
    if (h > 23 || m > 59) throw Error(`Invalid time: ${value}`);
    return h * 60 + m;
  }
  function experience(value) {
    if (value === 'Keine') return 0;
    if (!/^\d+(?:\.\d+)? Tage$/.test(value)) throw Error(`Unknown experience: ${value}`);
    return parseFloat(value);
  }
  function parseTable(markdown) {
    if (typeof markdown !== 'string') throw Error('Missing assignment table');
    const cells = line => line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(x => x.trim());
    const lines = markdown.trim().split(/\r?\n/);
    if (JSON.stringify(cells(lines[0])) !== JSON.stringify(HEADERS)) throw Error('Unexpected table columns');
    const rows = lines.slice(2).filter(x => x.trim()).map(line => {
      const v = cells(line);
      if (v.length !== HEADERS.length) throw Error('Incomplete assignment row');
      if (!['hoch', 'mittel', 'niedrig'].includes(v[2])) throw Error('Unknown priority');
      if (!['✅', '❌'].includes(v[5])) throw Error('Unknown qualification fit');
      const travel = v[6].match(/^(\d+(?:\.\d+)?) min(?: [✅❌])?$/u);
      if (!travel) throw Error('Unknown travel time');
      for (const date of [v[9], v[10]]) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(Date.parse(date)) || new Date(date).toISOString().slice(0,10) !== date) throw Error('Unknown availability date');
      }
      return {employee: v[0], client: v[1], priority: v[2], clientEnd: time(v[3]), employeeEnd: time(v[4]), qualified: v[5] === '✅', travel: Number(travel[1]), clientExperience: experience(v[7]), schoolExperience: experience(v[8]), neededUntil: v[9], availableUntil: v[10], raw: v};
    });
    for (const key of ['employee', 'client']) {
      if (new Set(rows.map(r => r[key])).size !== rows.length) throw Error(`Ambiguous ${key} names; use IDs before generalizing this adapter`);
    }
    return rows;
  }
  const sum = (rows, test) => rows.filter(test).length;
  const maximum = rows => rows.length ? Math.max(...rows.map(r => r.travel)) : null;
  const format = n => n === null ? 'n/a' : String(n);
  function evaluateDiff(diff, policy = {}) {
    const threshold = policy.travelThreshold ?? 50;
    try {
      if (!Number.isFinite(threshold) || threshold < 0) throw Error('Invalid travel threshold');
      const before = parseTable(diff.vorher), after = parseTable(diff.nachher);
      const counts = diff.stats.anzahl;
      if (![counts.gesamt_vorher, counts.gesamt_nachher, counts.hinzugefügt, counts.entfernt].every(x => Number.isInteger(x) && x >= 0)
          || counts.hinzugefügt !== after.length || counts.entfernt !== before.length
          || counts.gesamt_nachher - counts.gesamt_vorher !== after.length - before.length
          || counts.gesamt_vorher < before.length || counts.gesamt_nachher < after.length) throw Error('Counts and changed-assignment tables disagree');
      const byEmployee = new Map(before.map(r => [r.employee, r]));
      const lostHigh = before.filter(r => r.priority === 'hoch' && !after.some(a => a.client === r.client));
      const lostClients = before.filter(r => !after.some(a => a.client === r.client));
      const gainedClients = after.filter(r => !before.some(b => b.client === r.client));
      const critical = after.filter(r => !r.qualified || (r.priority === 'hoch' && r.employeeEnd < r.clientEnd));
      const unfamiliar = after.filter(r => {
        const b = byEmployee.get(r.employee);
        return b && ((b.clientExperience > 0 && r.clientExperience === 0) || (b.schoolExperience > 0 && r.schoolExperience === 0));
      });
      const travel = after.filter(r => r.travel > threshold);
      const shortfall = after.filter(r => r.availableUntil < r.neededUntil || r.employeeEnd < r.clientEnd);
      const names = rows => rows.map(r => r.employee).join(', ');
      const trace = [
        {id: 'R1', title: 'Protect coverage', expression: 'lost high-priority clients > 0 OR total assignments fall by more than 1', hit: lostHigh.length > 0 || counts.gesamt_vorher - counts.gesamt_nachher > 1, level: 'reject', observation: `${lostHigh.length} high-priority client(s) lose assignment${lostHigh.length ? ': ' + lostHigh.map(r => r.client).join(', ') : ''}; total assignments ${counts.gesamt_vorher} → ${counts.gesamt_nachher}.`, source: 'before/after client sets; stats.anzahl'},
        {id: 'R2', title: 'Check assignment fit', expression: 'any added qualification mismatch OR high-priority daily end-time shortfall', hit: critical.length > 0, level: 'reject', observation: critical.length ? `${names(critical)}: qualification mismatch or high-priority end-time shortfall.` : 'No added qualification mismatch or high-priority end-time shortfall.', source: 'added: Quali-Fit, Priorität, client/employee end times'},
        {id: 'R3', title: 'Flag local risks', expression: `known → unknown client/school OR added commute > ${threshold} min OR added end-time/date shortfall`, hit: unfamiliar.length + travel.length + shortfall.length > 0, level: 'caution', observation: `${unfamiliar.length} employee(s) lose client or school familiarity${unfamiliar.length ? ' (' + names(unfamiliar) + ')' : ''}; ${travel.length} added commute(s) exceed ${threshold} min; ${shortfall.length} added assignment(s) have an end-time/date shortfall.`, source: 'employee-matched experience; added travel, end times and dates'},
        {id: 'R4', title: 'Otherwise, lean toward acceptance', expression: 'none of R1–R3 matches', hit: false, level: 'accept', observation: 'No rule-defined reason to reject; this is not a claim of optimality.', source: 'explicit policy fallback'},
      ];
      trace[3].hit = !trace.slice(0, 3).some(r => r.hit);
      const winner = trace.find(r => r.hit);
      for (const rule of trace) rule.deciding = rule.id === winner.id;
      const statistics = [
        {label: 'All assignments', before: counts.gesamt_vorher, after: counts.gesamt_nachher, scope: 'Whole plan', source: 'stats.anzahl.gesamt_vorher / gesamt_nachher'},
        {label: 'High-priority assignments', before: sum(before, r => r.priority === 'hoch'), after: sum(after, r => r.priority === 'hoch'), scope: 'Changed assignments only', source: 'tables: Priorität = hoch'},
        {label: 'Known client', before: sum(before, r => r.clientExperience > 0), after: sum(after, r => r.clientExperience > 0), scope: 'Changed assignments only', source: 'tables: Erfahrung (Klient) > 0'},
        {label: 'Known school', before: sum(before, r => r.schoolExperience > 0), after: sum(after, r => r.schoolExperience > 0), scope: 'Changed assignments only', source: 'tables: Erfahrung (Schule) > 0'},
        {label: 'Longest commute (min)', before: maximum(before), after: maximum(after), scope: 'Changed assignments only', source: 'tables: max(Fahrtzeit numeric minutes)'},
        {label: 'Daily end time covered', before: sum(before, r => r.employeeEnd >= r.clientEnd), after: sum(after, r => r.employeeEnd >= r.clientEnd), scope: 'Changed assignments only', source: 'tables: employee end ≥ client end'},
        {label: 'Required date covered', before: sum(before, r => r.availableUntil >= r.neededUntil), after: sum(after, r => r.availableUntil >= r.neededUntil), scope: 'Changed assignments only', source: 'tables: available until ≥ needed until'},
      ];
      const employees = [...new Set([...before, ...after].map(r => r.employee))].sort();
      const assignments = employees.map(employee => {
        const b = byEmployee.get(employee), a = after.find(r => r.employee === employee);
        const changes = [];
        if (!b || !a) changes.push(`${b ? 'Removed' : 'Added'} assignment for ${b?.client || a.client}.`);
        else {
          changes.push(`${b.client} → ${a.client}.`);
          for (const [field, label] of [['clientExperience', 'Client familiarity'], ['schoolExperience', 'School familiarity']]) {
            changes.push(`${label}: ${b[field] > 0 ? 'known' : 'unknown'} → ${a[field] > 0 ? 'known' : 'unknown'} (${b[field]} → ${a[field]} days).`);
          }
          changes.push(`Commute: ${b.travel} → ${a.travel} min${a.travel > threshold ? '; above threshold' : '; within threshold'}.`);
        }
        if (a && (!a.qualified || a.employeeEnd < a.clientEnd || a.availableUntil < a.neededUntil)) changes.push('Check qualification fit and end-time/date coverage in the evidence table.');
        return {employee, changes};
      });
      const actions = {R1: 'Restore high-priority coverage and review total coverage before accepting.', R2: 'Resolve the qualification or high-priority daily end-time shortfall before accepting.', R3: 'Review the flagged assignments with the planner before accepting.', R4: 'Proceed only if the planner’s additional context supports the change.'};
      return {status: 'ok', score: LABELS[winner.level], level: winner.level, threshold, before, after, counts, statistics, assignments, trace, lostClients, gainedClients,
        general_assessment: `${winner.observation} ${actions[winner.id]}`,
        statistics_summary: `Total assignments: ${counts.gesamt_vorher} → ${counts.gesamt_nachher}. In the changed subset, known-client assignments: ${statistics[2].before} → ${statistics[2].after}; longest commute: ${format(maximum(before))} → ${format(maximum(after))} min.`,
      };
    } catch (error) {
      return {status: 'review', score: LABELS.review, level: 'review', general_assessment: `Cannot evaluate safely: ${error.message}. Inspect the source evidence.`, trace: [], statistics: [], assignments: []};
    }
  }
  const api = {evaluateDiff, parseTable, HEADERS, LABELS};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Deterministic = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
