# Experiment pipeline

This document describes how to run the offline recommendation experiments used in the dissertation evaluation. The pipeline is split into independent scripts that write results under `cache_experiments/`. More steps will be added later.

## Prerequisites

- **Python 3.11+** (the codebase uses modern type syntax such as `dict | None`)
- Project dependencies installed:

```powershell
pip install -r requirements.txt
```

- Input data present in `data/` (MAs, clients, distances, vertretungen, experience log, name mappings). The experiment scripts use the same data loaders as the API (`get_recommendations`, `get_vertretungen`, etc.).

- Run commands from the repository root:

```powershell
cd staff-planning-backend-v2
```

## Overview

| Step | Script | Input | Output |
|------|--------|-------|--------|
| 1 | `run_bfs_experiment.py` | Vertretung dates, optimizer | Recommendations + diffs |
| 2 | `calculate_complexity.py` | Cached diffs | Complexity scores |
| 3 | `calculate_silver_labels.py` | Cached diff stats | Silver labels |
| 4 | `balance_dataset.py` | Silver labels + complexity | Balanced diff-key manifest |
| 5 | `evaluate_experiment_diffs.py` | Cached diffs + simple diffs + balanced manifest | LLM assessments (3 modes) |
| 6 | `analyze_silver_label_deviation.py` | Balanced silver labels + evaluations | Alignment charts by setting |
| 7 | `analyze_silver_label_deviation_by_complexity.py` | Balanced silver labels + evaluations + complexity | Alignment charts by complexity |
| 8 | `analyze_divergence.py` | Balanced diffs + silver labels + full evaluations | LLM judge divergence analysis |
| 9 | `validate_experiment_outputs.py` | Cached diffs + evaluations (all modes) | LLM judge clarity/coherence validation |

Step 2 depends on step 1; step 3 depends on step 1 (`cache_diffs/` only). Step 4 depends on steps 2 and 3. Step 5 depends on steps 1 and 4 and requires API credentials. Steps 6 and 7 depend on steps 4 and 5; step 7 also depends on step 2. Step 8 depends on steps 1, 4, and 5 (`full` evaluations only) and requires API credentials. Step 9 depends on steps 1, 4, and 5 (all evaluation modes) and requires API credentials. All scripts are idempotent: re-running overwrites or skips existing files in `cache_experiments/`.

The optimizer also uses the shared runtime cache in `cache/` (SHA-256 keyed JSON files). Re-running experiments is faster when optimization results for the same settings already exist there.

## Step 1: BFS recommendation experiment

```powershell
py -3.11 run_bfs_experiment.py
```

### What it does

For each date **2025-03-17** through **2025-03-21**, the script:

1. Computes a **baseline** recommendation set (no forced assignment).
2. Explores **alternatives breadth-first**: from each set, it takes up to three alternative clients for the active MA row and re-runs the optimizer with that pair forced.
3. Stops after **21 recommendation sets** per date (`1 + 3 + 9 + 8`).
4. Computes **parent → child diffs** for every edge in the BFS tree (20 diffs per date).

### Output layout

```
cache_experiments/
  summary.json                          # BFS tree metadata per date
  cache_recommendations/
    {YYYY-MM-DD}/
      00.json … 20.json                 # raw + prepared recommendations
  cache_diffs/
    {YYYY-MM-DD}/
      {parent}_to_{child}.json          # full diff (calculate_diff format)
  cache_simple_diffs/
    {YYYY-MM-DD}/
      {parent}_to_{child}.json          # added/removed only (prepare_output shape)
```

Each recommendation file stores `index`, `parent_index`, `forced_ma`, `forced_client`, `prepared`, and `output`.

### Runtime

This step is CPU-heavy: up to **105 optimizer runs** (5 dates × 21 sets). Expect long runtimes on first execution; subsequent runs benefit from `cache/`.

## Step 2: Complexity scores

Run after step 1 has produced `cache_diffs/` and `cache_simple_diffs/`.

```powershell
py -3.11 calculate_complexity.py
```

### What it does

For every diff file in `cache_experiments/cache_diffs/`, the script computes a complexity score for the **child** recommendation set:

```
complexity = number_added
           + |number_added - number_removed|
           + high_priority_clients_affected
           + priority_changes
```

| Component | Meaning |
|-----------|---------|
| `number_added` | Assignments added vs. parent (`hinzugefügt` from diff stats) |
| `added_removed_difference` | `abs(added − removed)` |
| `high_priority_clients_affected` | Distinct clients with priority `hoch` among added/removed |
| `priority_changes` | MAs present in both added and removed with a different client priority |

Counts come from `cache_diffs/`; priority details come from the matching file in `cache_simple_diffs/`.

The root recommendation set (index `00`) has no complexity entry because it has no parent diff.

### Output layout

```
cache_experiments/
  cache_complexity/
    summary.json                        # all scores aggregated by date
    {YYYY-MM-DD}/
      {parent}_to_{child}.json
```

Example entry (`cache_complexity/2025-03-17/00_to_01.json`):

```json
{
  "date": "2025-03-17",
  "recommendation_index": 1,
  "parent_index": 0,
  "diff_reference": "cache_experiments/cache_diffs/2025-03-17/00_to_01.json",
  "components": {
    "number_added": 4,
    "added_removed_difference": 0,
    "high_priority_clients_affected": 0,
    "priority_changes": 1
  },
  "complexity": 5
}
```

## Step 3: Silver labels

Run after step 1 has produced `cache_diffs/`.

```powershell
py -3.11 calculate_silver_labels.py
```

### What it does

For every diff in `cache_experiments/cache_diffs/`, the script assigns a **silver label** to the child recommendation set using statistics from `diff.stats`. Rules are evaluated in order; the first matching group wins.

**ablehnen**

| Rule | Condition (from diff stats) |
|------|----------------------------|
| High-priority client unassigned | More high-priority assignments removed than added (`hoch` → `Klienten-Priorität`) |
| Severe coverage loss | `hinzugefügt + 1 < entfernt` |

**eher ablehnen** (if not `ablehnen`)

| Rule | Condition |
|------|-----------|
| Experience drop | Client or school `durchschnittlich_erfahrung` drops by more than 2 (any priority bucket) |
| Long commute | Any added assignment has `Fahrtzeit in Minuten` max above 50 |
| Availability worsens | For high-priority changes, `durchschnittlich_früher` decreases (`Mitarbeiter muss früher gehen als der Klient`) |

**eher akzeptieren** — none of the above.

### Output layout

```
cache_experiments/
  cache_silver_labels/
    summary.json                        # label counts per date
    {YYYY-MM-DD}/
      {parent}_to_{child}.json
```

Example entry:

```json
{
  "date": "2025-03-18",
  "recommendation_index": 1,
  "parent_index": 0,
  "diff_reference": "cache_experiments/cache_diffs/2025-03-18/00_to_01.json",
  "silver_label": "eher ablehnen",
  "triggered_rules": ["experience_drop_substantial"],
  "metrics": {
    "number_added": 3,
    "number_removed": 3,
    "high_priority_removed": 2,
    "high_priority_added": 2,
    "severe_coverage_loss": false,
    "high_priority_client_unassigned": false,
    "client_experience_drop": 2.0,
    "school_experience_drop": null,
    "max_commute_minutes_added": 17,
    "high_priority_früher_removed": null,
    "high_priority_früher_added": null
  }
}
```

## Step 4: Balanced dataset manifest

Run after steps 2 and 3 have produced `cache_complexity/` and `cache_silver_labels/`.

```powershell
py -3.11 balance_dataset.py
```

Optional flags:

```powershell
py -3.11 balance_dataset.py --output cache_experiments/cache_balanced_sample.json
```

### What it does

This step creates a **balanced sampling manifest** without modifying the original experiment data. It keeps all cached diffs, labels, and evaluations unchanged and writes only the selected diff IDs (`diff_key`s) to a separate manifest file.

The balancing targets the three silver-label classes:

- `ablehnen`
- `eher ablehnen`
- `eher akzeptieren`

The smallest class size defines the target. In the current cache, that means:

- `ablehnen`: 50
- `eher ablehnen`: 851 -> downsampled to 50
- `eher akzeptieren`: 899 -> downsampled to 50

The sampler is **not random**. Selection is deterministic and uses sorted `diff_key`s after proportional allocation across these strata:

- `date`
- `complexity_quartile`
- `triggered_rules`

Complexity bins are no longer fixed. Instead, quartiles are computed from all cached complexity scores and stored in the manifest. With the current cache, the quartiles are:

| Quartile bin | Range |
|--------------|-------|
| `Q1` | `complexity <= 5` |
| `Q2` | `5 < complexity <= 6` |
| `Q3` | `6 < complexity <= 9` |
| `Q4` | `complexity > 9` |

### Output layout

```
cache_experiments/
  cache_balanced_sample.json
```

Example structure:

```json
{
  "strategy": "stratified_silver_balance",
  "stratify_by": ["date", "complexity_quartile", "triggered_rules"],
  "target_labels": ["ablehnen", "eher ablehnen", "eher akzeptieren"],
  "target_per_class": 50,
  "class_counts_before": {
    "ablehnen": 50,
    "eher ablehnen": 851,
    "eher akzeptieren": 899
  },
  "class_counts_after": {
    "ablehnen": 50,
    "eher ablehnen": 50,
    "eher akzeptieren": 50
  },
  "complexity_quartiles": {
    "q1": 5.0,
    "q2": 6.0,
    "q3": 9.0,
    "bin_keys": ["Q1", "Q2", "Q3", "Q4"]
  },
  "diff_keys": ["2025-03-17/00_to_01.json", "..."]
}
```

Downstream scripts use only the `diff_keys` listed in this manifest.

## Step 5: LLM evaluation

Run after steps 1 and 4 have produced `cache_diffs/`, `cache_simple_diffs/`, and `cache_balanced_sample.json`. Requires OpenAI API credentials (see `llm/helper/helper.py`) and makes live LLM calls unless results are already cached.

```powershell
py -3.11 evaluate_experiment_diffs.py
```

For self-hosted OpenAI-compatible endpoints (vLLM, Ollama, etc.):

```powershell
# via environment (.env)
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_API_KEY=your-key
MODEL_NAME=your-model

py -3.11 evaluate_experiment_diffs.py

# or via CLI flags
py -3.11 evaluate_experiment_diffs.py --base-url http://localhost:8000/v1 --model your-model
```

`OPENAI_BASE_URL` is also picked up by `evaluate_diff.py` and `chat.py` through the shared `init_phoenix` client.

### What it does

For every diff listed in `cache_experiments/cache_balanced_sample.json`, the script runs **three evaluation settings** (default model: `gpt-5.4`, overridable via `MODEL_NAME` or `--model`):

| Mode | Input | Pipeline |
|------|-------|----------|
| `full` | `cache_diffs` (`stats`, `vorher`, `nachher`) | StatisticsSummary + TabelleSummary → Assessment (same as `evaluate_diff`) |
| `simple` | Stats from `cache_diffs`, assignment tables from `cache_simple_diffs` | StatisticsSummary + TabelleSummary → Assessment |
| `simple_direct` | `cache_simple_diffs` only | Assessment directly (no intermediate summaries) |

Results are written to separate folders per mode; each folder name includes the model slug.

### Output layout

```
cache_experiments/
  cache_evaluations/
    summary.json
    full__gpt-5_4/
      {YYYY-MM-DD}/
        {parent}_to_{child}.json
    simple__gpt-5_4/
      {YYYY-MM-DD}/
        {parent}_to_{child}.json
    simple_direct__gpt-5_4/
      {YYYY-MM-DD}/
        {parent}_to_{child}.json
```

Each file contains `evaluation_mode`, `model`, `diff_reference`, `assessment`, and (for simple modes) `simple_diff_reference`. LLM responses are also deduplicated via `cache_llm/` using experiment-scoped cache keys.

Re-running the script skips diffs that already have an output file in the target folder.

### Runtime

With the current balanced sample (`150` diffs), this step issues up to **~750 LLM calls** on first run (150 diffs × up to 5 calls for `full`/`simple`, 1 call for `simple_direct`). Expect significant runtime and API cost.

## Step 6: Silver-label alignment by setting

Run after steps 4 and 5 have produced `cache_balanced_sample.json` and `cache_evaluations/`. Requires `matplotlib` and `seaborn` (included in `requirements.txt`). No LLM calls.

```powershell
py -3.11 analyze_silver_label_deviation.py
```

Optional flags:

```powershell
py -3.11 analyze_silver_label_deviation.py --model Qwen3.6-27B
py -3.11 analyze_silver_label_deviation.py --output-dir cache_experiments/analysis/silver_label_deviation
```

`--model` selects the evaluation cache folder (`{mode}__{model_slug}`). If omitted, the script auto-detects the first model slug that has all three evaluation modes.

### What it does

For each evaluation setting (`full`, `simple`, `simple_direct`), the script compares the **silver label** (step 3) with the LLM **assessment score** (step 5) for the balanced subset from step 4 and classifies the deviation:

| Category | Condition |
|----------|-----------|
| Übereinstimmend (aligned) | Silver label and assessment score are identical |
| Abweichend (unaligned) | Ordinal distance of 1 (e.g. `eher akzeptieren` vs. `eher ablehnen`) |
| Völlig abweichend (completely unaligned) | Ordinal distance of 2 (e.g. `eher akzeptieren` vs. `ablehnen`) |

Ordinal mapping: `eher akzeptieren` = 0, `eher ablehnen` = 1, `ablehnen` = 2.

### Output layout

```
cache_experiments/
  analysis/
    silver_label_deviation/
      summary.json
      heatmap_full.png
      heatmap_simple.png
      heatmap_simple_direct.png
      alignment_by_setting.png          # grouped bar chart (counts per setting)
```

- **Heatmaps** — confusion matrix per setting (silver label × assessment score, raw counts).
- **Bar chart** — three bars per evaluation setting showing aligned / unaligned / completely unaligned counts.

Shared alignment logic lives in `alignment_analysis.py`.

## Step 7: Silver-label alignment by complexity

Run after steps 2, 4, and 5 have produced `cache_complexity/`, `cache_balanced_sample.json`, and `cache_evaluations/`.

```powershell
py -3.11 analyze_silver_label_deviation_by_complexity.py
```

Optional flags match step 5 (`--model`, `--output-dir`).

### What it does

For **each evaluation setting**, the script groups the balanced subset by recommendation **complexity** (from step 2) and measures how well the LLM assessment aligns with the silver label within each group.

Complexity buckets are read from `cache_balanced_sample.json`, so the same quartile boundaries used during balancing are also used for analysis. With the current cache they are:

| Group | Range |
|-------|-------|
| `Q1` | `complexity <= 5` |
| `Q2` | `5 < complexity <= 6` |
| `Q3` | `6 < complexity <= 9` |
| `Q4` | `complexity > 9` |

For each bucket, the script reports the same three alignment categories as step 5. The bar charts show **percentages within each complexity group** (the three bars per group sum to 100%), so groups with different sample sizes are comparable.

### Output layout

```
cache_experiments/
  analysis/
    silver_label_deviation_by_complexity/
      summary.json
      alignment_by_complexity_full.png
      alignment_by_complexity_simple.png
      alignment_by_complexity_simple_direct.png
```

`summary.json` is structured as `modes.{setting}.groups.{complexity}` with raw counts and percentages per alignment category.

## Step 8: Divergence analysis (LLM-as-a-judge)

Run after steps 1, 4, and 5 have produced `cache_diffs/`, `cache_balanced_sample.json`, and `full` evaluations in `cache_evaluations/`. Requires OpenAI API credentials (or a compatible endpoint via `OPENAI_BASE_URL`).

```powershell
py -3.11 analyze_divergence.py
```

Optional flags:

```powershell
py -3.11 analyze_divergence.py --model Qwen3.6-27B
py -3.11 analyze_divergence.py --judge-model gpt-5.4 --base-url http://localhost:8000/v1
py -3.11 analyze_divergence.py --output-dir cache_experiments/analysis/divergence_analysis
```

`--model` selects the evaluation cache folder (`full__{model_slug}`). `--judge-model` overrides the judge LLM (default: `MODEL_NAME` env or `gpt-5.4`).

### What it does

For the **`full` evaluation setting only**, the script selects balanced-subset diffs where the LLM **assessment score** does not match the **silver label** (ordinal deviation > 0). For each misaligned case, a separate LLM judge compares:

| Input | Role |
|-------|------|
| `cache_diffs/` (stats, `vorher`, `nachher`) | Ground truth |
| `cache_silver_labels/` | Reference policy |
| `cache_evaluations/full__{model}/` | Generated LLM assessment (incl. intermediate summaries) |

The judge classifies the likely cause(s) of the deviation using a structured response model (`llm/response_models/DivergenceAnalysis.py`):

| Divergence type | Meaning |
|-----------------|---------|
| `critical_omission` | A high-priority or coverage-critical effect is not mentioned |
| `harmful_optimism` | The score is too positive relative to the reference policy |
| `over_caution` | The score is too negative despite no critical risk |
| `abstraction_drift` | Intermediate summaries lose decisive evidence |
| `count_level_misinterpretation` | Added/removed counts are interpreted without checking affected clients |
| `priority_miscalibration` | Priority effects are over- or under-weighted |
| `experience_over_weighting` | Familiarity dominates despite stronger coverage evidence |
| `distance_over_weighting` | Commute dominates despite weak practical relevance |
| `context_overload` | Many changes cause relevant facts to be ignored |
| `unsupported_hallucinated_claim` | The explanation mentions facts not present in the data |
| `no_reason_found` | No clear divergence pattern can be identified |
| `other` | Divergence present but does not fit predefined categories |

Each case receives a **primary** and **secondary** divergence type plus a short explanation. Judge prompts live in `llm/prompts/DivergenceJudgePrompt.py`.

### Output layout

```
cache_experiments/
  analysis/
    divergence_analysis/
      summary.json
      {YYYY-MM-DD}/
        {parent}_to_{child}.json
```

Example entry:

```json
{
  "diff_key": "2025-03-17/00_to_01.json",
  "evaluation_mode": "full",
  "silver_label": "eher ablehnen",
  "assessment_score": "eher akzeptieren",
  "ordinal_deviation": 1,
  "triggered_rules": ["experience_drop_substantial"],
  "divergence": {
    "primary_divergence_type": "harmful_optimism",
    "secondary_divergence_type": "experience_over_weighting",
    "explanation": "..."
  }
}
```

`summary.json` aggregates `primary_divergence_type_counts` across all misaligned cases in the balanced subset. Judge responses are deduplicated via `cache_llm/`. Re-running skips cases that already have an output file.

### Runtime

One LLM call per misaligned `full` evaluation (typically ~40 cases for 100 diffs). Expect API cost proportional to the number of misaligned cases.

## Step 9: Output validation (LLM-as-a-judge)

Run after steps 1, 4, and 5 have produced `cache_diffs/`, `cache_simple_diffs/`, `cache_balanced_sample.json`, and evaluations in `cache_evaluations/`. Requires OpenAI API credentials (or a compatible endpoint via `OPENAI_BASE_URL`).

```powershell
py -3.11 validate_experiment_outputs.py
```

Optional flags:

```powershell
py -3.11 validate_experiment_outputs.py --model Qwen3.6-27B
py -3.11 validate_experiment_outputs.py --judge-model gpt-5.4 --base-url http://localhost:8000/v1
py -3.11 validate_experiment_outputs.py --mode full --mode simple
py -3.11 validate_experiment_outputs.py --output-dir cache_experiments/cache_validations
```

`--model` selects the evaluation cache folder (`{mode}__{model_slug}`). `--judge-model` overrides the judge LLM (default: `MODEL_NAME` env or `gpt-5.4`). `--mode` can be repeated to validate specific settings only.

### What it does

For each evaluation case in the balanced subset, an LLM judge scores every pipeline input/output pair on two dimensions (integer 0–10, each with a short explanation):

| Dimension | Meaning |
|-----------|---------|
| **Clarity** | How clear and well-structured the generated output is for domain experts |
| **Coherence** | How faithfully and logically the output follows from the input |

Input/output pairs per evaluation mode:

| Mode | Pairs | Input source |
|------|-------|--------------|
| `simple_direct` | 1 (`direct_assessment`) | `cache_simple_diffs/` assignment tables |
| `simple` | 3 (`assignments_summary`, `statistics_summary`, `assessment`) | Simple diffs + `cache_diffs/` stats + combined intermediate outputs |
| `full` | 3 (same steps) | `cache_diffs/` vorher/nachher + stats + combined intermediate outputs |

Response models: `llm/response_models/OutputValidation.py` (`ClarityJudgment`, `CoherenceJudgment`). Prompts: `llm/prompts/OutputValidationPrompt.py`. Pair extraction: `experiment_validation_pairs.py`.

### Output layout

```
cache_experiments/
  cache_validations/
    summary.json
    full/
      {YYYY-MM-DD}/
        {parent}_to_{child}.json
    simple/
      ...
    simple_direct/
      ...
```

Example entry (per step):

```json
{
  "diff_key": "2025-03-17/00_to_01.json",
  "evaluation_mode": "full",
  "judge_model": "gpt-5.4",
  "steps": {
    "assignments_summary": {
      "clarity": { "score": 8, "explanation": "..." },
      "coherence": { "score": 7, "explanation": "..." }
    }
  }
}
```

`summary.json` reports mean clarity and coherence per mode and per pipeline step. Judge responses are deduplicated via `cache_llm/`. Re-running skips cases that already have an output file.

### Runtime

Two LLM calls per input/output pair (clarity + coherence, run in parallel). Expect ~800 judge calls for 100 balanced diffs across all three modes (100 × 1 + 100 × 3 + 100 × 3 pairs × 2 judgments).

## Quick start (full pipeline)

```powershell
pip install -r requirements.txt
py -3.11 run_bfs_experiment.py
py -3.11 calculate_complexity.py
py -3.11 calculate_silver_labels.py
py -3.11 balance_dataset.py
py -3.11 evaluate_experiment_diffs.py
py -3.11 analyze_silver_label_deviation.py
py -3.11 analyze_silver_label_deviation_by_complexity.py
py -3.11 analyze_divergence.py
py -3.11 validate_experiment_outputs.py
```

## Notes

- Experiment artifacts live only under `cache_experiments/` and are separate from the API runtime cache in `cache/`.
- `cache_experiments/` is generated output; add it to `.gitignore` if you do not want to version large result files.
- `cache_experiments/cache_balanced_sample.json` is the only balancing artifact; it stores selected IDs, not copied data.
- Analysis charts and judge results (steps 6–8) are written under `cache_experiments/analysis/` and can be regenerated at any time from cached labels and evaluations.
- Output validation results (step 9) are written under `cache_experiments/cache_validations/` and can be regenerated from cached diffs and evaluations.
