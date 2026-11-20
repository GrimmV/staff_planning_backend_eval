'use strict';
const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
let selected = 0, stage = 'recommendation', threshold = 50;
let designScenario = 'exploration';
const english = {'eher akzeptieren':'Lean toward acceptance','eher ablehnen':'Lean toward rejection','ablehnen':'Reject the change','manual review':'Manual review'};
const level = score => ({'eher akzeptieren':'accept','eher ablehnen':'caution','ablehnen':'reject'}[score] || 'review');
const sourceName = path => path.split('/').slice(-2).join('/');
function lens(title, tag, content, generative = false) {
  return `<article class="lens ${generative ? 'generative' : ''}"><header class="lens-header"><span>${title}</span><span class="tag">${tag}</span></header><div class="lens-body">${content}</div></article>`;
}
function renderCases() {
  $('cases').innerHTML = EXAMPLES.map((x, i) => `<button class="case ${selected === i ? 'active' : ''}" data-case="${i}" aria-pressed="${selected === i}"><span class="case-number">${x.number}</span><span><strong>${escapeHTML(x.title)}</strong><small>${escapeHTML(x.date)} · state ${escapeHTML(x.edge.replace('_to_', ' → '))}</small></span></button>`).join('');
}
function renderTrace(result) {
  $('trace').innerHTML = result.trace.map(r => `<div class="rule ${r.deciding ? 'deciding' : ''}"><div class="rule-top"><span class="rule-id">${r.id}</span><strong>${r.title}</strong><span class="state">${r.deciding ? 'DECIDES' : r.hit ? 'MATCH' : 'NO MATCH'}</span></div><p>${escapeHTML(r.expression)}</p><details><summary>Inspect evidence</summary><p>${escapeHTML(r.observation)}</p><p class="expression">${escapeHTML(r.source)}</p></details></div>`).join('');
}
function metrics(r) {
  return `<div class="metrics"><div class="metric"><span>Total plan assignments</span><strong>${r.counts.gesamt_vorher} → ${r.counts.gesamt_nachher}</strong><small>Whole plan</small></div><div class="metric"><span>High-priority assignments</span><strong>${r.statistics[1].before} → ${r.statistics[1].after}</strong><small>Removed → added subset</small></div><div class="metric"><span>Longest commute</span><strong>${r.statistics[4].before ?? '—'} → ${r.statistics[4].after ?? '—'}</strong><small>Minutes · removed → added subset</small></div></div>`;
}
function recommendation(x, r) {
  const a = x.assessment, deciding = r.trace.find(t => t.deciding);
  const deterministic = `<div class="decision-label ${r.level}">Policy v1 · ${deciding.id}</div><h3>${english[r.score]}</h3><p class="original-label">${escapeHTML(r.score)}</p><p class="recommendation-text">${escapeHTML(r.general_assessment)}</p><p class="mini-note">Every sentence comes from a fixed template. Trace the decision through the rules on the right.</p>`;
  const generated = `<div class="decision-label ${level(a.score)}">Recorded model assessment</div><h3>${english[a.score]}</h3><p class="original-label">Original label: ${escapeHTML(a.score)}</p><p class="recommendation-text" lang="de">${escapeHTML(a.general_assessment)}</p><p class="mini-note">Verbatim cached text · ${escapeHTML(x.model)} · full pipeline. English heading translates the label only.</p><details><summary>Show both detailed assessments</summary><p lang="de">${escapeHTML(a.detail_level_1_assessment)}</p><p lang="de">${escapeHTML(a.detail_level_2_assessment)}</p></details>`;
  return `<div class="compare">${lens('Deterministic', 'RULES + TEMPLATES', deterministic)}${lens('Generative', 'CACHE REPLAY', generated, true)}</div>${metrics(r)}<p class="small-source">Shared evidence: ${escapeHTML(x.sources[0].path)} · Original LLM result: ${escapeHTML(sourceName(x.sources[1].path))}</p>`;
}
function summaries(x, r) {
  const stats = `<p class="mini-note">${escapeHTML(r.statistics_summary)}</p><ul class="summary-list">${r.statistics.map(s => `<li><strong>${escapeHTML(s.label)}: ${s.before ?? 'n/a'} → ${s.after ?? 'n/a'}</strong><span>${s.scope}</span><details><summary>Source field</summary><p><code>${escapeHTML(s.source)}</code></p></details></li>`).join('')}</ul>`;
  const llmStats = `<p class="mini-note">Original selected statistics; wording and effect labels are unedited.</p><ul class="summary-list" lang="de">${x.assessment.statistiken.relevant_changes.map(s => `<li><strong>${escapeHTML(s.relevant_feature)}</strong><p>${escapeHTML(s.änderung)}</p><span class="effect">Model effect: ${escapeHTML(s.effect)}</span></li>`).join('')}</ul>`;
  const assignments = `<ul class="summary-list">${r.assignments.map(a => `<li><strong>${escapeHTML(a.employee)}</strong>${a.changes.map(c => `<p>${escapeHTML(c)}</p>`).join('')}</li>`).join('')}</ul>`;
  const llmAssignments = `<ul class="summary-list" lang="de">${x.assessment.änderungen.map(a => `<li><strong>${escapeHTML(a.ma)}</strong>${a.relevant_changes.map(c => `<p>${escapeHTML(c.relevant_spalte)}: ${escapeHTML(c.änderung)} <span class="effect">(${escapeHTML(c.effect)})</span></p>`).join('')}<span class="effect">Overall model effect: ${escapeHTML(a.effect)}</span></li>`).join('')}</ul>`;
  return `<div class="compare">${lens('Statistics · deterministic', 'FIXED METRICS', stats)}${lens('Statistics · generative', 'CACHE REPLAY', llmStats, true)}</div><h3>Assignment comparison</h3><p class="small-source">Employee-matched rows compare different assignments where clients change; these are not longitudinal experience changes for the same pair.</p><div class="compare">${lens('Deterministic', 'FIXED SENTENCES', assignments)}${lens('Generative', 'SELECTED CHANGES', llmAssignments, true)}</div>`;
}
function rawTable(rows) {
  return `<div class="table-scroll"><table class="raw-table"><thead><tr>${Deterministic.HEADERS.map(h => `<th>${escapeHTML(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr>${r.raw.map((c, i) => `<td class="${(i === 6 && r.travel > threshold) || (i === 5 && !r.qualified) ? 'attention' : ''}">${escapeHTML(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function evidence(x, r) {
  return `${metrics(r)}<div class="data-panel"><h3>What changed in coverage?</h3><p>Clients no longer assigned: <strong>${escapeHTML(r.lostClients.map(c => `${c.client} (${c.priority})`).join(', ') || 'None')}</strong><br>Newly assigned clients: <strong>${escapeHTML(r.gainedClients.map(c => `${c.client} (${c.priority})`).join(', ') || 'None')}</strong></p><p>Calculated from client names in the complete removed/added set. Unchanged assignments are absent from these tables.</p></div><div class="data-panel"><h3>Before · removed assignments</h3>${rawTable(r.before)}</div><div class="data-panel"><h3>After · added assignments</h3>${rawTable(r.after)}<p>Cells above the current travel threshold are highlighted. The original ✓/✗ icons are preserved: their travel cutoff is 60 minutes in <code>assignment_simple.py</code>, separate from this policy’s ${threshold}-minute warning cutoff.</p></div><div class="data-panel"><h3>Provenance & original input</h3><p>The evidence and generative assessment are paired by date and parent/child state indices. No optimizer or LLM is run in this demonstration.</p>${x.sources.map(s => `<p class="small-source"><strong>${escapeHTML(s.path)}</strong><br>SHA-256: ${s.sha256}</p>`).join('')}<details><summary>Inspect the original diff JSON</summary><pre>${escapeHTML(JSON.stringify(x.diff, null, 2))}</pre></details><details><summary>Inspect the original cached assessment</summary><pre>${escapeHTML(JSON.stringify(x.assessment, null, 2))}</pre></details></div>`;
}
const scenarios = {
  operations: {title: 'Stable daily operation', need: 'A planner needs the same checks and concise output for a repeated, well-specified decision.', fit: 'Rules + templates are a strong starting point.', reason: 'The evidence schema is fixed, the policy can be enumerated, and repeatable wording is sufficient. An LLM adds little if it merely restates a few numbers.', architecture: 'Compute facts → explicit policy → fixed templates', question: 'Would natural-language flexibility change a real user decision, or just make the output sound better?'},
  exploration: {title: 'Complex what-if exploration', need: 'A planner explores many interacting changes and asks different follow-up questions about the consequences.', fit: 'LLM-assisted interpretation becomes more reasonable.', reason: 'The benefit is selecting and connecting relevant evidence across varied questions and tradeoffs. Encoding every useful explanatory combination can become costly. This benefit still needs testing on real planning tasks.', architecture: 'Verified facts + policy checks → LLM synthesis with evidence references → planner review', question: 'Does the model expose a consequential interaction the fixed summary misses, without inventing or misrepresenting evidence?'},
  communication: {title: 'Different audiences, same decision', need: 'The label is fixed, but a planner, manager and nontechnical stakeholder need different levels of detail or languages.', fit: 'Keep the decision deterministic; use an LLM for expression.', reason: 'Audience adaptation is a distinct reason to use generation. It does not require delegating policy enforcement or arithmetic to the model. Invariant facts and the decision can remain locked.', architecture: 'Verified facts + fixed label → LLM wording → factual consistency check', question: 'Can the generated explanation improve comprehension while preserving the same facts, caveats and label?'}
};
function discussion(x) {
  const s = scenarios[designScenario];
  const prompts = [
    'Example 01: should 6 → 1 experience days matter beyond the known/unknown distinction? A rule makes that value choice explicit; an LLM can discuss it, but may also overstate it. What evidence would justify either interpretation?',
    'Example 02: should losing a high-priority client always veto a change, even if qualification fit improves elsewhere? If yes, enforce the veto deterministically and let the LLM explain the conflict.',
    'Example 03: both labels agree. Is the LLM explanation more useful for deciding what to do next? Agreement alone does not show that generation adds value.'
  ];
  return `<section class="discussion-lead"><p class="eyebrow">THE DESIGN QUESTION</p><h3>Use generation where interpretation<br>or communication earns its cost.</h3><p>Rules are compelling when the relevant facts, priorities and output can be specified in advance. An LLM becomes more compelling when useful explanations must adapt to combinations, questions or audiences that are difficult to enumerate.</p><p class="discussion-caveat">These are design hypotheses to discuss and test, not advantages established by three selected outputs.</p></section>
  <div class="data-panel"><h3>What makes an LLM worth considering here?</h3><div class="table-scroll"><table class="factor-table"><thead><tr><th>Factor</th><th>Why rules may be sufficient</th><th>When an LLM may add value</th></tr></thead><tbody>
  <tr><th>Evidence variety</th><td>The same typed fields and a small set of facts matter each day.</td><td>Planning diffs must be explained alongside varied, supplied notes or exceptions. The model can connect heterogeneous evidence; each claim still needs a source.</td></tr>
  <tr><th>Interacting tradeoffs</th><td>Priority and veto rules settle the decision.</td><td>Many weak signals interact and there is no agreed total ordering. A model can articulate competing considerations for a human, without making them objective.</td></tr>
  <tr><th>Long-tail explanations</th><td>Repeated cases fit a manageable template library.</td><td>Many combinations need different emphasis. Generation can reduce hand-authored phrasing and selection logic; evaluation and maintenance work remain.</td></tr>
  <tr><th>Changing needs</th><td>The criteria and requested explanation stay stable.</td><td>Users frequently ask for different perspectives or new forms of explanation. Prompt changes can support exploration; changed policies still need versioning and validation.</td></tr>
  <tr><th>Audience & dialogue</th><td>One fixed table and short recommendation are enough.</td><td>Users need plain language, multiple languages, drill-down or “why this rather than that?” questions grounded in the evidence.</td></tr>
  <tr><th>Operational constraints</th><td>Strict reproducibility, low runtime overhead and an auditable policy are central.</td><td>The communication benefit justifies inference cost, response time, data handling and output review. This cache replay measures none of those costs.</td></tr>
  </tbody></table></div></div>
  <div class="data-panel scenario-panel"><p class="eyebrow">CHANGE THE USE CASE, NOT THE EVIDENCE</p><h3>Which part should be generative?</h3><div class="scenario-choices" role="group" aria-label="Choose a design scenario">${Object.entries(scenarios).map(([key, value]) => `<button data-scenario="${key}" aria-pressed="${key === designScenario}" class="${key === designScenario ? 'selected' : ''}">${value.title}</button>`).join('')}</div><p>${s.need}</p><div class="scenario-result"><h4>${s.fit}</h4><p>${s.reason}</p><div class="architecture">${s.architecture}</div><p><strong>Question to test:</strong> ${s.question}</p></div><p class="small-source">Illustrative design scenarios, not a scored selection algorithm. The current cached experiment uses structured tables; varied notes, audience adaptation and dialogue are extensions, not demonstrated capabilities of these recordings.</p></div>
  <div class="compare discussion-cards"><article class="data-panel"><h3>Keep these responsibilities explicit</h3><ul><li><strong>Facts:</strong> compute counts, deltas and identity matches in code.</li><li><strong>Policy:</strong> version any non-negotiable constraints and vetoes.</li><li><strong>Expression:</strong> allow an LLM to adapt wording if it helps users.</li><li><strong>Interpretation:</strong> expose assumptions and cite evidence if the LLM weighs tradeoffs.</li><li><strong>Decision:</strong> preserve the planner’s ability to inspect, contest and override guidance.</li></ul></article><article class="data-panel"><h3>Test value, not just fluent text</h3><ul><li>Are important risks preserved, especially high-priority coverage?</li><li>Are numeric claims and client/employee identities correct?</li><li>Do planners understand the tradeoff and make a better-informed choice?</li><li>Does wording vary without changing facts or policy?</li><li>Is the benefit worth runtime cost, latency and review effort?</li></ul><p>Compare rules-only, rules + LLM wording, and LLM-assisted interpretation on the same held-out cases and user tasks.</p></article></div>
  <div class="discussion-prompt"><p class="eyebrow">BRING IT BACK TO THIS CASE</p><p>${prompts[selected]}</p></div>
  <p class="discussion-bottom">Determinism does not make a policy correct. Fluency does not make an interpretation faithful. This comparison separates the XAI seeking structure from the choice of mechanism used to mediate evidence; both approaches still need inspectable evidence and assumptions.</p>`;
}
function render() {
  const x = EXAMPLES[selected], r = Deterministic.evaluateDiff(x.diff, {travelThreshold: threshold});
  renderCases();
  document.querySelectorAll('[data-stage]').forEach(b => { b.classList.toggle('active', b.dataset.stage === stage); b.setAttribute('aria-pressed', b.dataset.stage === stage); });
  $('case-meta').textContent = `EXAMPLE ${x.number} / 03 · ${x.date} · ${stage.toUpperCase()}`;
  $('case-title').textContent = stage === 'discussion' ? 'Where does an LLM earn its place?' : x.title; $('case-subtitle').textContent = stage === 'discussion' ? 'Separate factual computation, policy enforcement, interpretation and expression.' : x.subtitle;
  $('case-note').textContent = threshold === 50 ? x.note : 'Policy sensitivity experiment: only the deterministic commute cutoff has changed. Inspect which flags change and whether a higher-priority rule or another risk still determines the recommendation. The recorded model response is not a response to this modified policy.';
  const agrees = r.score === x.assessment.score;
  $('agreement').textContent = agrees ? 'Same recommendation' : 'Different recommendations';
  $('agreement').className = `badge ${agrees ? '' : 'diff'}`;
  $('threshold-value').textContent = `${threshold} min`;
  $('policy-state').textContent = threshold === 50 ? 'Default policy · examples selected at this setting' : 'Modified policy · cached LLM unchanged';
  renderTrace(r);
  $('stage').innerHTML = r.status !== 'ok' ? `<div class="data-panel"><h3>Manual review</h3><p>${escapeHTML(r.general_assessment)}</p></div>` : ({recommendation, summaries, evidence, discussion}[stage])(x, r);
}
$('cases').addEventListener('click', event => { const b = event.target.closest('[data-case]'); if (!b) return; selected = Number(b.dataset.case); render(); document.querySelector(`[data-case="${selected}"]`).focus(); });
document.querySelector('.pipeline').addEventListener('click', event => { const b = event.target.closest('[data-stage]'); if (!b) return; stage = b.dataset.stage; render(); });
$('stage').addEventListener('click', event => { const b = event.target.closest('[data-scenario]'); if (!b) return; designScenario = b.dataset.scenario; render(); document.querySelector(`[data-scenario="${designScenario}"]`).focus(); });
$('threshold').addEventListener('input', event => { threshold = Number(event.target.value); render(); });
$('reset').addEventListener('click', () => { threshold = 50; $('threshold').value = 50; render(); });
$('focus').addEventListener('click', () => { const active = document.body.classList.toggle('focus'); $('focus').setAttribute('aria-pressed', active); $('focus').textContent = active ? 'Exit presentation view' : 'Presentation view'; });
$('print').addEventListener('click', () => window.print());
$('method-button').addEventListener('click', () => { $('method').hidden = !$('method').hidden; $('method-button').setAttribute('aria-expanded', !$('method').hidden); if (!$('method').hidden) $('method').scrollIntoView({behavior:'smooth',block:'start'}); });
$('export').addEventListener('click', () => {
  const x = EXAMPLES[selected];
  const payload = {policy: {version: 'demo-v1', travelThreshold: threshold}, example: x, deterministic: Deterministic.evaluateDiff(x.diff, {travelThreshold: threshold})};
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], {type:'application/json'}));
  const a = document.createElement('a'); a.href = url; a.download = `xai-seeking-${x.date}-${x.edge}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
render();
