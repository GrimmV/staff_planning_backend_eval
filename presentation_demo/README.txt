XAI SEEKING — OFFLINE PRESENTATION DEMO

Open index.html directly in Chrome, Edge or Firefox. No install, server, API key,
network connection or LLM is required. Keep the five UI files together:
index.html, styles.css, app.js, engine.js and examples.js.

Suggested 5-minute walkthrough
1. Start with example 01 and Recommendation. Compare the two top-level labels.
2. Open Summaries: Tom's client experience falls from 6 to 1 days, but he still
   knows the new client. The deterministic policy encodes familiarity as binary.
3. Open Evidence to inspect the exact removed/added rows and provenance.
4. Lower the commute threshold from 50 to 27 minutes: example 01 now cautions.
   At 28 minutes it provisionally accepts again. Reset before switching cases.
5. Example 02 shows a coverage veto: Max Bauer disappears from the assignments.
6. Example 03 shows agreement despite different mechanisms. At a 51-minute
   cutoff the commute flag disappears, but lost familiarity still triggers R3.
7. Open Method & limitations for the tradeoff discussion. Use Presentation view
   for a cleaner screen, Print / PDF for the selected layer, or JSON export for
   the complete case, policy, derived outputs and source references.
8. Open Discuss the approach for general selection factors. Switch between
   stable daily operation, complex what-if exploration and different audiences.
   Discuss whether generation belongs in interpretation, expression, both or
   neither. Each case has a question tying that discussion to actual evidence.

The original LLM prose is German and is preserved exactly. English headings
translate its label, not its justification. The deterministic templates are
English. Cached model: Qwen3.6-27B, full pipeline. These are selected examples,
not a representative evaluation or an accuracy comparison.

Architecture
- build_examples.py copies three paired cache records and hashes source files.
  Run `python presentation_demo/build_examples.py` from the repository root
  only when deliberately refreshing the bundled fixtures. It does not run the
  solver, import evaluate_diff.py, or call a model.
- engine.js exports evaluateDiff(diff, {travelThreshold: 50}), a pure function.
  It receives only the diff used by evaluate_diff.py, never an LLM response.
- app.js renders both independent paths. All HTML from cache is escaped.
  Output is generated locally on each input change; the cached LLM stays fixed.
- Production API, solver, prompts, silver labels and caches are unchanged.

Policy v1 (first match decides)
R1 Reject: a high-priority client loses assignment OR net coverage falls by >1.
R2 Reject: an added qualification mismatch OR high-priority end-time shortfall.
R3 Lean reject: an employee changes from known to unknown client/school OR an
   added commute exceeds the cutoff OR added end-time/date coverage is short.
R4 Otherwise lean accept, subject to the planner's additional context.

The commute default and coverage cutoff borrow from calculate_silver_labels.py.
Familiarity and availability follow llm/prompts/general_guidance.py. This policy
is NOT the existing silver-label implementation: it uses individual client
sets, binary familiarity, and explicit per-assignment fit checks. In particular
it does not penalize the size of an experience decline while familiarity remains.
The strict >50 interpretation is a design choice for “well above 45 minutes”.
R2 rejects equality only if the employee ends BEFORE the client; equal end times
count as covered. Thresholds, precedence and this boundary need domain validation.

Interpretation limits
- This demonstrates all three mediation replacements (statistics, assignments,
  assessment), not a drop-in Python API replacement. To integrate, port the pure
  rules to Python, adapt to the response schemas, and use stable IDs from the
  structured changed_assignments data before replacing evaluate_diff calls.
- Metrics except total plan counts describe the removed/added subset. Do not
  present them as overall plan statistics. Unknown, inconsistent or ambiguous
  tables return manual review instead of guessing. This is a small adapter for
  the current table format, not a general Markdown parser or schema validator.
- The source tables use names; duplicate names in a table are rejected. Across
  states they are assumed to identify the same person. Use IDs in production.
- Commute is parsed from numeric table minutes. Aggregate cached travel strings
  were produced by float_to_time even for minute values; they are left untouched
  in provenance and cached prose, and not interpreted as HH:MM by the engine.
- The source's travel checkmark uses a 60-minute cutoff, distinct from the demo.
- Date and end-time checks do not establish full feasibility. Start times and
  other constraints are outside the LLM tables. This demo does not rerun CP.
- An assignment exchange compares an employee's old and new clients; this is
  not a time-series change of experience with the same client.
- Rule counts overlap; warning counts must not be added as unique assignments.
- The policy cannot weigh every tradeoff. A single medium/low-priority coverage
  loss does not independently trigger rejection. No encoded warning is not the
  same as optimal, safe, or approved by a planner.
- Fixed templates can omit useful nuance; generative summaries can omit facts
  or interpret them differently. Disagreement alone establishes neither error
  nor superiority. The recording does not test variability across generations.

Checks (Node.js, built-in modules only)
  node --test presentation_demo/engine.test.js
  node --check presentation_demo/app.js
  node presentation_demo/browser_check.cjs

If the environment blocks Node test subprocesses, use:
  node --test --test-isolation=none presentation_demo/engine.test.js

The optional browser check uses an installed Chrome (or a browser executable
passed as its first argument), local DevTools and Node built-ins. It checks all
views, design scenarios, threshold changes, mobile overflow and PDF rendering.
Screenshots and a sample PDF are written to the ignored qa-output directory.

The test suite covers real fixture outputs, source integrity, strict threshold
boundaries, rule precedence, per-client coverage, familiarity, fit/availability
checks, malformed inputs and repeatability.
