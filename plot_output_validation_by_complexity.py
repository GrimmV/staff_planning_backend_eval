"""
Generate dissertation-ready validation figures and statistical tests.

Produces:
1. Main figure comparing prompting settings overall (Friedman/Wilcoxon support).
2. Exploratory heatmaps by merged complexity group (Q2+Q3 combined).

Reads metadata from summary_output_validation.json and rebuilds per-case scores
from the validation cache.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from alignment_analysis import (
    CACHE_COMPLEXITY,
    EVALUATION_MODES,
    load_balanced_diff_keys,
    load_complexity_by_diff,
    load_json,
    save_json,
)
from analyze_experiment_validations import build_records, records_to_dataframe
from dissertation_figure_style import (
    MODE_COLORS, MODE_ORDER, WIDTH, apply_style, export_figure,
)

DEFAULT_SUMMARY = "cache_experiments/analysis/output_validation/summary_output_validation.json"
DEFAULT_OUTPUT = (
    "cache_experiments/analysis/output_validation/"
    "validation_scores_by_setting.png"
)
DEFAULT_HEATMAP_OUTPUT = (
    "cache_experiments/analysis/output_validation/"
    "validation_scores_by_complexity_heatmap.png"
)
DEFAULT_STATS_TABLE = (
    "cache_experiments/analysis/output_validation/"
    "validation_statistics_table.csv"
)
DEFAULT_STATS_JSON = (
    "cache_experiments/analysis/output_validation/"
    "validation_statistics.json"
)

PROMPTING_LABELS: Dict[str, str] = {
    "full": "Full evidence",
    "simple": "Condensed evidence",
    "simple_direct": "Direct summary",
}

SETTING_TABLE_LABELS: Dict[str, str] = {
    "full": "Full",
    "simple": "Simple",
    "simple_direct": "Simple direct",
}

CLARITY_QUALITY_THRESHOLD = 8.0

MERGED_COMPLEXITY_ORDER: Tuple[str, ...] = ("low", "medium", "high")
MERGED_COMPLEXITY_LABELS: Dict[str, str] = {
    "low": "Low complexity",
    "medium": "Medium complexity",
    "high": "High complexity",
}
MERGED_COMPLEXITY_SOURCES: Dict[str, Tuple[str, ...]] = {
    "low": ("Q1",),
    "medium": ("Q2", "Q3"),
    "high": ("Q4",),
}

METRICS: Tuple[str, ...] = ("clarity", "coherence")

PAIRWISE_COMPARISONS: Tuple[Tuple[str, str], ...] = (
    ("full", "simple"),
    ("full", "simple_direct"),
    ("simple", "simple_direct"),
)


@dataclass
class SettingSummary:
    mode: str
    median: float
    q25: float
    q75: float


@dataclass
class PostHocResult:
    mode_a: str
    mode_b: str
    p_raw: float
    p_holm: float
    median_paired_diff: float
    rank_biserial: float
    significant: bool


@dataclass
class MetricAnalysis:
    metric: str
    n_cases: int
    setting_summaries: List[SettingSummary]
    friedman_stat: float
    friedman_p: float
    kendalls_w: float
    post_hoc: List[PostHocResult] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot LLM validation scores by prompting setting, run repeated-measures "
            "statistical tests, and generate exploratory complexity heatmaps."
        )
    )
    parser.add_argument(
        "--summary",
        default=DEFAULT_SUMMARY,
        help="Path to summary_output_validation.json produced by analyze_experiment_validations.py.",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="Output path for the main setting-comparison figure (PNG).",
    )
    parser.add_argument(
        "--heatmap-output",
        default=DEFAULT_HEATMAP_OUTPUT,
        help="Output path for the exploratory complexity heatmap figure (PNG).",
    )
    parser.add_argument(
        "--stats-table",
        default=DEFAULT_STATS_TABLE,
        help="Output path for the compact statistical results table (CSV).",
    )
    parser.add_argument(
        "--stats-json",
        default=DEFAULT_STATS_JSON,
        help="Output path for detailed statistical results (JSON).",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="Figure resolution in dots per inch.",
    )
    parser.add_argument(
        "--skip-mixed-model",
        action="store_true",
        help="Skip the exploratory mixed-effects robustness check.",
    )
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="Run statistics only without generating the figure.",
    )
    return parser.parse_args()


def format_model_slug(model_slug: str) -> str:
    return model_slug.replace("_", ".")


def load_plot_data(summary_path: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    summary = load_json(summary_path)
    allowed_diff_keys = load_balanced_diff_keys()
    complexities = {
        key: value
        for key, value in load_complexity_by_diff().items()
        if key in allowed_diff_keys
    }
    if not complexities:
        raise FileNotFoundError(f"No complexity scores found in {CACHE_COMPLEXITY}")

    from alignment_analysis import load_complexity_quartile_config

    complexity_group_keys, _, quartile_breakpoints = load_complexity_quartile_config()
    records = build_records(
        summary["model_slug"],
        summary["validation_dir"],
        allowed_diff_keys,
        complexities,
        quartile_breakpoints,
    )
    if not records:
        raise FileNotFoundError(
            f"No validation records found for model {summary['model_slug']} "
            f"in {summary['validation_dir']}."
        )

    df = records_to_dataframe(records).dropna(subset=["complexity_group"])
    if df.empty:
        raise ValueError("No validation records with complexity scores found.")

    return df, summary


def aggregate_case_level(df: pd.DataFrame, modes: Sequence[str]) -> pd.DataFrame:
    """Aggregate to one score per planning case and setting to avoid pseudo-replication."""
    aggregated = (
        df.groupby(["diff_key", "mode"], as_index=False)
        .agg(
            clarity=("clarity", "median"),
            coherence=("coherence", "median"),
            complexity=("complexity", "first"),
            complexity_group=("complexity_group", "first"),
        )
        .query("mode in @modes")
    )
    return aggregated


def add_merged_complexity_group(case_df: pd.DataFrame) -> pd.DataFrame:
    source_to_merged = {
        source: merged
        for merged, sources in MERGED_COMPLEXITY_SOURCES.items()
        for source in sources
    }
    enriched = case_df.copy()
    enriched["complexity_group_merged"] = enriched["complexity_group"].map(source_to_merged)
    return enriched.dropna(subset=["complexity_group_merged"])


def median_iqr(values: pd.Series) -> Tuple[float, float, float]:
    if values.empty:
        return float("nan"), float("nan"), float("nan")
    q25, median, q75 = np.percentile(values, [25, 50, 75])
    return float(median), float(q25), float(q75)


def format_iqr(q25: float, q75: float) -> str:
    return f"{q25:.2f}-{q75:.2f}"


def holm_adjust(p_values: Dict[str, float]) -> Dict[str, float]:
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    adjusted: Dict[str, float] = {}
    previous = 0.0
    m = len(ordered)
    for index, (name, p_value) in enumerate(ordered):
        corrected = min(1.0, p_value * (m - index))
        corrected = max(corrected, previous)
        adjusted[name] = corrected
        previous = corrected
    return adjusted


def kendalls_w(chi_square: float, n_cases: int, n_conditions: int) -> float:
    if n_cases == 0 or n_conditions <= 1:
        return float("nan")
    return chi_square / (n_cases * (n_conditions - 1))


def matched_pairs_rank_biserial(differences: np.ndarray, wilcoxon_statistic: float) -> float:
    nonzero = differences[differences != 0]
    n = len(nonzero)
    if n == 0:
        return float("nan")
    return 1.0 - (2.0 * wilcoxon_statistic) / (n * (n + 1))


def pairwise_label(mode_a: str, mode_b: str) -> str:
    return f"{SETTING_TABLE_LABELS[mode_a]} vs. {SETTING_TABLE_LABELS[mode_b]}"


def wide_metric_matrix(case_df: pd.DataFrame, metric: str, modes: Sequence[str]) -> pd.DataFrame:
    wide = case_df.pivot(index="diff_key", columns="mode", values=metric)
    return wide[list(modes)].dropna()


def analyze_metric(case_df: pd.DataFrame, metric: str, modes: Sequence[str]) -> MetricAnalysis:
    wide = wide_metric_matrix(case_df, metric, modes)
    n_cases = len(wide)
    if n_cases == 0:
        raise ValueError(f"No complete case-level observations for metric '{metric}'.")

    setting_summaries = []
    for mode in modes:
        median, q25, q75 = median_iqr(wide[mode])
        setting_summaries.append(SettingSummary(mode=mode, median=median, q25=q25, q75=q75))

    samples = [wide[mode].to_numpy() for mode in modes]
    friedman_stat, friedman_p = stats.friedmanchisquare(*samples)
    effect_w = kendalls_w(float(friedman_stat), n_cases, len(modes))

    raw_p_values: Dict[str, float] = {}
    post_hoc_details: Dict[str, Dict[str, float]] = {}
    for mode_a, mode_b in PAIRWISE_COMPARISONS:
        differences = (wide[mode_a] - wide[mode_b]).to_numpy()
        if np.all(differences == 0):
            raw_p = 1.0
            wilcoxon_stat = 0.0
        else:
            wilcoxon_result = stats.wilcoxon(
                wide[mode_a],
                wide[mode_b],
                zero_method="wilcox",
                alternative="two-sided",
                method="auto",
            )
            raw_p = float(wilcoxon_result.pvalue)
            wilcoxon_stat = float(wilcoxon_result.statistic)

        pair_name = f"{mode_a}_vs_{mode_b}"
        raw_p_values[pair_name] = raw_p
        post_hoc_details[pair_name] = {
            "median_paired_diff": float(np.median(wide[mode_a] - wide[mode_b])),
            "rank_biserial": matched_pairs_rank_biserial(differences, wilcoxon_stat),
        }

    adjusted_p_values = holm_adjust(raw_p_values) if friedman_p < 0.05 else {
        pair_name: 1.0 for pair_name in raw_p_values
    }
    post_hoc: List[PostHocResult] = []
    for mode_a, mode_b in PAIRWISE_COMPARISONS:
        pair_name = f"{mode_a}_vs_{mode_b}"
        holm_p = adjusted_p_values[pair_name]
        post_hoc.append(
            PostHocResult(
                mode_a=mode_a,
                mode_b=mode_b,
                p_raw=raw_p_values[pair_name],
                p_holm=holm_p,
                median_paired_diff=post_hoc_details[pair_name]["median_paired_diff"],
                rank_biserial=post_hoc_details[pair_name]["rank_biserial"],
                significant=friedman_p < 0.05 and holm_p < 0.05,
            )
        )

    return MetricAnalysis(
        metric=metric,
        n_cases=n_cases,
        setting_summaries=setting_summaries,
        friedman_stat=float(friedman_stat),
        friedman_p=float(friedman_p),
        kendalls_w=effect_w,
        post_hoc=post_hoc,
    )


def significant_post_hoc_summary(
    post_hoc: Sequence[PostHocResult],
    friedman_p: float,
) -> str:
    if friedman_p >= 0.05:
        return "-"
    significant = [pairwise_label(result.mode_a, result.mode_b) for result in post_hoc if result.significant]
    return "; ".join(significant) if significant else "-"


def build_results_table(analyses: Sequence[MetricAnalysis]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for analysis in analyses:
        post_hoc_summary = significant_post_hoc_summary(analysis.post_hoc, analysis.friedman_p)
        metric_label = analysis.metric.capitalize()
        for index, setting in enumerate(analysis.setting_summaries):
            row = {
                "Metric": metric_label,
                "Setting": SETTING_TABLE_LABELS[setting.mode],
                "Median": round(setting.median, 2),
                "IQR": format_iqr(setting.q25, setting.q75),
                "Friedman p": "",
                "Kendall's W": "",
                "Significant post-hoc differences": "",
            }
            if index == 0:
                row["Friedman p"] = f"{analysis.friedman_p:.4f}"
                row["Kendall's W"] = f"{analysis.kendalls_w:.3f}"
                row["Significant post-hoc differences"] = post_hoc_summary
            rows.append(row)
    return pd.DataFrame(rows)


def build_post_hoc_table(analyses: Sequence[MetricAnalysis]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for analysis in analyses:
        for result in analysis.post_hoc:
            rows.append(
                {
                    "Metric": analysis.metric.capitalize(),
                    "Comparison": pairwise_label(result.mode_a, result.mode_b),
                    "Median paired difference": round(result.median_paired_diff, 2),
                    "Rank-biserial r": round(result.rank_biserial, 3),
                    "p (raw)": round(result.p_raw, 4),
                    "p (Holm)": round(result.p_holm, 4) if analysis.friedman_p < 0.05 else "",
                    "Significant": "yes" if result.significant else "no",
                    "Reported": "yes" if analysis.friedman_p < 0.05 else "no (Friedman n.s.)",
                }
            )
    return pd.DataFrame(rows)


def run_mixed_model(case_df: pd.DataFrame, metric: str) -> Dict[str, Any]:
    import statsmodels.formula.api as smf

    model_df = case_df[["diff_key", "mode", metric, "complexity"]].dropna().copy()
    model_df["mode"] = pd.Categorical(model_df["mode"], categories=list(EVALUATION_MODES), ordered=True)
    complexity_std = model_df["complexity"].std()
    if complexity_std == 0:
        return {
            "metric": metric,
            "formula": f"{metric} ~ C(mode, Treatment(reference='full')) * complexity",
            "n_observations": int(len(model_df)),
            "n_cases": int(model_df["diff_key"].nunique()),
            "converged": False,
            "error": "Complexity has zero variance; mixed model not estimable.",
            "coefficients": [],
        }

    model_df["complexity_c"] = (model_df["complexity"] - model_df["complexity"].mean()) / complexity_std
    formula = f"{metric} ~ C(mode, Treatment(reference='full')) * complexity_c"
    model = smf.mixedlm(formula, model_df, groups=model_df["diff_key"])

    fit = None
    fit_errors: List[str] = []
    for reml, method in ((True, "lbfgs"), (False, "lbfgs"), (False, "powell"), (False, "nm")):
        try:
            candidate = model.fit(reml=reml, method=method, maxiter=300, disp=False)
            fit = candidate
            if candidate.converged:
                break
        except Exception as exc:
            fit_errors.append(f"reml={reml}, method={method}: {exc}")

    if fit is None:
        return {
            "metric": metric,
            "formula": formula,
            "n_observations": int(len(model_df)),
            "n_cases": int(model_df["diff_key"].nunique()),
            "converged": False,
            "error": "; ".join(fit_errors) if fit_errors else "Mixed model did not converge.",
            "coefficients": [],
        }

    coefficients: List[Dict[str, Any]] = []
    for term in fit.params.index:
        coefficients.append(
            {
                "term": term,
                "coef": float(fit.params[term]),
                "std_err": float(fit.bse[term]),
                "z": float(fit.tvalues[term]),
                "p": float(fit.pvalues[term]),
            }
        )

    return {
        "metric": metric,
        "formula": formula,
        "n_observations": int(len(model_df)),
        "n_cases": int(model_df["diff_key"].nunique()),
        "converged": bool(fit.converged),
        "warning": fit_errors[-1] if fit_errors and not fit.converged else None,
        "coefficients": coefficients,
    }


def analysis_to_dict(analysis: MetricAnalysis) -> Dict[str, Any]:
    return {
        "metric": analysis.metric,
        "n_cases": analysis.n_cases,
        "settings": {
            summary.mode: {
                "median": round(summary.median, 4),
                "q25": round(summary.q25, 4),
                "q75": round(summary.q75, 4),
                "iqr": format_iqr(summary.q25, summary.q75),
            }
            for summary in analysis.setting_summaries
        },
        "friedman": {
            "statistic": round(analysis.friedman_stat, 4),
            "p_value": round(analysis.friedman_p, 6),
            "kendalls_w": round(analysis.kendalls_w, 4),
            "significant": bool(analysis.friedman_p < 0.05),
        },
        "post_hoc_wilcoxon_holm": [
            {
                "comparison": pairwise_label(result.mode_a, result.mode_b),
                "mode_a": result.mode_a,
                "mode_b": result.mode_b,
                "median_paired_difference": round(result.median_paired_diff, 4),
                "rank_biserial": round(result.rank_biserial, 4),
                "p_raw": round(result.p_raw, 6),
                "p_holm": round(result.p_holm, 6),
                "significant": bool(result.significant),
                "reported": bool(analysis.friedman_p < 0.05),
            }
            for result in analysis.post_hoc
        ],
        "significant_post_hoc_differences": significant_post_hoc_summary(
            analysis.post_hoc,
            analysis.friedman_p,
        ),
    }


def print_results_table(table: pd.DataFrame) -> None:
    print("\nValidation statistics (case-level, Friedman + Wilcoxon post-hoc)\n")
    print(table.to_string(index=False))


def print_post_hoc_table(table: pd.DataFrame) -> None:
    print("\nPairwise Wilcoxon signed-rank tests (Holm-corrected)\n")
    print(table.to_string(index=False))


def print_mixed_model_results(results: Sequence[Dict[str, Any]]) -> None:
    print("\nExploratory mixed-effects robustness check")
    print("Model: score ~ setting * complexity + (1 | case_id)\n")
    for result in results:
        print(
            f"[{result['metric'].capitalize()}] converged={result['converged']}, "
            f"n={result['n_observations']} observations, "
            f"{result['n_cases']} cases"
        )
        if result.get("error"):
            print(f"  Note: {result['error']}")
        if result.get("warning"):
            print(f"  Warning: {result['warning']}")
        for coefficient in result["coefficients"]:
            print(
                f"  {coefficient['term']}: "
                f"coef={coefficient['coef']:.4f}, "
                f"p={coefficient['p']:.4f}"
            )
        print()


def run_statistical_analysis(
    df: pd.DataFrame,
    skip_mixed_model: bool,
) -> Tuple[pd.DataFrame, pd.DataFrame, List[MetricAnalysis], List[Dict[str, Any]]]:
    modes = [mode for mode in EVALUATION_MODES if mode in set(df["mode"])]
    case_df = aggregate_case_level(df, modes)

    analyses = [analyze_metric(case_df, metric, modes) for metric in METRICS]
    results_table = build_results_table(analyses)
    post_hoc_table = build_post_hoc_table(analyses)

    mixed_model_results: List[Dict[str, Any]] = []
    if not skip_mixed_model:
        for metric in METRICS:
            mixed_model_results.append(run_mixed_model(case_df, metric))

    return results_table, post_hoc_table, analyses, mixed_model_results


def save_statistical_outputs(
    results_table: pd.DataFrame,
    post_hoc_table: pd.DataFrame,
    analyses: Sequence[MetricAnalysis],
    mixed_model_results: Sequence[Dict[str, Any]],
    stats_table_path: str,
    stats_json_path: str,
) -> None:
    os.makedirs(os.path.dirname(stats_table_path) or ".", exist_ok=True)
    results_table.to_csv(stats_table_path, index=False)
    post_hoc_table.to_csv(stats_table_path.replace(".csv", "_posthoc.csv"), index=False)

    payload = {
        "design": {
            "unit_of_analysis": "planning case (diff_key)",
            "aggregation": "median score per case and prompting setting",
            "main_test": "Friedman test across prompting settings",
            "post_hoc": "Wilcoxon signed-rank tests with Holm correction",
            "effect_sizes": {
                "friedman": "Kendall's W",
                "post_hoc": "matched-pairs rank-biserial correlation",
            },
        },
        "metrics": [analysis_to_dict(analysis) for analysis in analyses],
        "mixed_models": mixed_model_results,
    }
    save_json(stats_json_path, payload)


def ordered_modes(df: pd.DataFrame) -> List[str]:
    return [mode for mode in EVALUATION_MODES if mode in set(df["mode"])]


def apply_plot_style() -> None:
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
        }
    )


def apply_main_setting_plot_style() -> None:
    apply_style()


def setting_tick_labels(modes: Sequence[str]) -> List[str]:
    return [PROMPTING_LABELS[mode].replace(" ", "\n", 1) for mode in modes]


def share_below_threshold(values: pd.Series, threshold: float) -> float:
    if values.empty:
        return float("nan")
    return float((values < threshold).mean() * 100.0)


def plot_clarity_below_threshold_panel(
    ax: plt.Axes,
    case_df: pd.DataFrame,
    modes: Sequence[str],
    threshold: float,
) -> None:
    shares = [share_below_threshold(case_df.loc[case_df["mode"] == mode, "clarity"], threshold) for mode in modes]
    counts = [
        int((case_df.loc[case_df["mode"] == mode, "clarity"] < threshold).sum())
        for mode in modes
    ]
    x = np.arange(len(modes))
    bars = ax.bar(
        x,
        shares,
        width=0.58,
        color=[MODE_COLORS[mode] for mode in modes],
        alpha=1.0,
        edgecolor="white",
        linewidth=0.8,
        zorder=2,
    )
    for bar, count, share in zip(bars, counts, shares):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.8,
            f"{share:.1f}%\n{count}/150 cases",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(setting_tick_labels(modes))
    ax.set_ylabel(f"Cases with clarity score < {threshold:.0f} (%)")
    ymax = max(max(shares) * 1.5, 5.0) if shares else 5.0
    ax.set_ylim(0, ymax)
    ax.set_title("(a) Clarity below threshold - lower is better", loc="left", pad=12)
    ax.grid(axis="y", color="#dddddd", linewidth=0.5, zorder=0)


def plot_coherence_distribution_panel(ax: plt.Axes, case_df: pd.DataFrame, modes: Sequence[str]) -> None:
    data = [case_df.loc[case_df["mode"] == mode, "coherence"].to_numpy() for mode in modes]
    positions = np.arange(len(modes))
    violin_width = 0.72

    parts = ax.violinplot(
        data,
        positions=positions,
        widths=violin_width,
        showmeans=False,
        showmedians=False,
        showextrema=False,
    )
    for index, body in enumerate(parts["bodies"]):
        body.set_facecolor(MODE_COLORS[modes[index]])
        body.set_edgecolor("#333333")
        body.set_alpha(0.35)
        body.set_linewidth(0.8)

    box = ax.boxplot(
        data,
        positions=positions,
        widths=0.14,
        patch_artist=True,
        showfliers=True,
        medianprops={"color": "black", "linewidth": 1.4},
        boxprops={"facecolor": "white", "edgecolor": "#333333", "linewidth": 1.0, "alpha": 0.9},
        whiskerprops={"color": "#333333", "linewidth": 1.0},
        capprops={"color": "#333333", "linewidth": 1.0},
        flierprops={
            "marker": "o",
            "markersize": 3,
            "markerfacecolor": "#666666",
            "markeredgecolor": "none",
            "alpha": 0.35,
        },
        zorder=3,
    )
    for patch, mode in zip(box["boxes"], modes):
        patch.set_facecolor(MODE_COLORS[mode])
        patch.set_alpha(0.55)

    ax.set_xticks(positions)
    ax.set_xticklabels(setting_tick_labels(modes))
    ax.set_ylabel("Validation score (0-10)")
    ax.set_ylim(0, 10)
    ax.set_yticks(np.arange(0, 11, 2))
    ax.set_title("(b) Coherence - higher is better", loc="left", pad=12)
    ax.grid(axis="y", color="#dddddd", linewidth=0.5, zorder=0)


def plot_main_setting_figure(
    case_df: pd.DataFrame,
    output_path: str,
    dpi: int,
    clarity_threshold: float = CLARITY_QUALITY_THRESHOLD,
) -> None:
    modes = list(MODE_ORDER)
    if clarity_threshold != 8:
        raise ValueError("Figure 8.9 requires a strict clarity threshold of 8.")
    expected_keys = load_balanced_diff_keys()
    if len(expected_keys) != 150:
        raise ValueError("Expected the original 150 balanced case identifiers.")
    for mode in modes:
        rows = case_df.loc[case_df["mode"] == mode]
        if len(rows) != 150 or set(rows["diff_key"]) != set(expected_keys):
            raise ValueError(f"{mode}: expected one aggregate for each of the 150 paired cases.")
        values = rows[["clarity", "coherence"]].to_numpy()
        if not np.isfinite(values).all() or ((values < 0) | (values > 10)).any():
            raise ValueError("Validation scores must be finite and within 0-10.")
    apply_main_setting_plot_style()
    fig, axes = plt.subplots(2, 1, figsize=(WIDTH, 6.4))
    fig.subplots_adjust(left=0.14, right=0.97, bottom=0.09, top=0.94, hspace=0.62)
    plot_clarity_below_threshold_panel(axes[0], case_df, modes, clarity_threshold)
    plot_coherence_distribution_panel(axes[1], case_df, modes)
    export_figure(fig, output_path, "Output clarity and coherence.",
        "Figure 8.9. LLM-as-a-judge scores on a 0-10 scale for the same 150 planning "
        "cases per configuration. Scores are first averaged across validation steps within "
        "each validation record, then aggregated by the median of records per case and "
        "configuration; each case contributes one clarity and one coherence score. "
        "(a) Percentage and count (k/150 cases) with aggregate clarity strictly below 8; "
        "lower is better. Clarity concerns understandable, structured, planner-appropriate "
        "communication. (b) Coherence concerns consistency with and derivability from the "
        "supplied evidence; higher is better. Colored violins show kernel density estimates "
        "over the observed score range, bounded within 0-10. Boxes span the 25th-75th "
        "percentiles (interquartile range, IQR); black horizontal lines mark medians. "
        "Whiskers reach the most extreme observations within 1.5 IQR of the box; caps mark "
        "their endpoints and small circles show observations beyond the whiskers. No "
        "additional median diamond or significance symbols are shown. These validation "
        "scores are not direct measures of planner performance.", dpi=dpi)
    plt.close(fig)


def heatmap_matrix(
    case_df: pd.DataFrame,
    metric: str,
    modes: Sequence[str],
    complexity_groups: Sequence[str],
    value_fn,
    annotation: str,
) -> Tuple[np.ndarray, List[List[str]]]:
    matrix = np.full((len(modes), len(complexity_groups)), np.nan)
    annotations: List[List[str]] = []
    for row_index, mode in enumerate(modes):
        row_labels: List[str] = []
        for col_index, group in enumerate(complexity_groups):
            values = case_df.loc[
                (case_df["mode"] == mode) & (case_df["complexity_group_merged"] == group),
                metric,
            ]
            value = value_fn(values)
            matrix[row_index, col_index] = value
            if np.isnan(value):
                row_labels.append("n/a")
            elif annotation == "share_below":
                count = int((values < CLARITY_QUALITY_THRESHOLD).sum())
                row_labels.append(f"{value:.1f}%\n(n={count})")
            else:
                row_labels.append(f"{value:.2f}")
        annotations.append(row_labels)
    return matrix, annotations


def draw_heatmap_panel(
    ax: plt.Axes,
    matrix: np.ndarray,
    annotations: List[List[str]],
    modes: Sequence[str],
    complexity_groups: Sequence[str],
    title: str,
    cmap: str,
    vmin: float,
    vmax: float,
    cbar_label: str,
) -> None:
    masked = np.ma.masked_invalid(matrix)
    image = ax.imshow(masked, aspect="auto", cmap=cmap, vmin=vmin, vmax=vmax)
    ax.set_xticks(np.arange(len(complexity_groups)))
    ax.set_yticks(np.arange(len(modes)))
    ax.set_xticklabels(
        [MERGED_COMPLEXITY_LABELS[group] for group in complexity_groups],
        rotation=15,
        ha="right",
        rotation_mode="anchor",
    )
    ax.set_yticklabels([PROMPTING_LABELS[mode] for mode in modes])
    ax.set_xlabel("Planning complexity score group")
    ax.set_title(title)

    for row_index in range(len(modes)):
        for col_index in range(len(complexity_groups)):
            value = matrix[row_index, col_index]
            if np.isnan(value):
                continue
            text_color = "white" if value > (vmin + 0.62 * (vmax - vmin)) else "black"
            ax.text(
                col_index,
                row_index,
                annotations[row_index][col_index],
                ha="center",
                va="center",
                color=text_color,
                fontsize=8.5,
            )

    cbar = plt.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(cbar_label)


def plot_complexity_heatmap_figure(
    case_df: pd.DataFrame,
    output_path: str,
    dpi: int,
) -> None:
    modes = ordered_modes(case_df)
    enriched = add_merged_complexity_group(case_df)
    complexity_groups = [
        group for group in MERGED_COMPLEXITY_ORDER if group in enriched["complexity_group_merged"].unique()
    ]
    apply_plot_style()

    clarity_matrix, clarity_annotations = heatmap_matrix(
        enriched,
        "clarity",
        modes,
        complexity_groups,
        lambda values: share_below_threshold(values, CLARITY_QUALITY_THRESHOLD),
        annotation="share_below",
    )
    coherence_matrix, coherence_annotations = heatmap_matrix(
        enriched,
        "coherence",
        modes,
        complexity_groups,
        lambda values: float(np.median(values)) if not values.empty else float("nan"),
        annotation="median",
    )

    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.4), constrained_layout=True)
    draw_heatmap_panel(
        axes[0],
        clarity_matrix,
        clarity_annotations,
        modes,
        complexity_groups,
        title=f"Clarity: share below {CLARITY_QUALITY_THRESHOLD:.0f}",
        cmap="YlOrRd",
        vmin=0.0,
        vmax=max(15.0, np.nanmax(clarity_matrix) * 1.15),
        cbar_label="Share below threshold (%)",
    )
    draw_heatmap_panel(
        axes[1],
        coherence_matrix,
        coherence_annotations,
        modes,
        complexity_groups,
        title="Coherence: median score",
        cmap="YlGnBu",
        vmin=0.0,
        vmax=10.0,
        cbar_label="Median validation score",
    )

    for axis in axes:
        axis.tick_params(top=False, bottom=True, left=True, right=False)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    df, summary = load_plot_data(args.summary)

    results_table, post_hoc_table, analyses, mixed_model_results = run_statistical_analysis(
        df,
        skip_mixed_model=args.skip_mixed_model,
    )
    save_statistical_outputs(
        results_table,
        post_hoc_table,
        analyses,
        mixed_model_results,
        args.stats_table,
        args.stats_json,
    )

    print_results_table(results_table)
    print_post_hoc_table(post_hoc_table)
    if mixed_model_results:
        print_mixed_model_results(mixed_model_results)

    if not args.no_plot:
        modes = ordered_modes(df)
        case_df = aggregate_case_level(df, modes)
        plot_main_setting_figure(case_df, args.output, args.dpi)
        plot_complexity_heatmap_figure(case_df, args.heatmap_output, args.dpi)
        print(f"\nWrote main figure to {args.output.replace(os.sep, '/')}")
        print(f"Wrote heatmap figure to {args.heatmap_output.replace(os.sep, '/')}")

    print(f"Wrote results table to {args.stats_table.replace(os.sep, '/')}")
    print(f"Wrote detailed statistics to {args.stats_json.replace(os.sep, '/')}")
    print(f"Model: {format_model_slug(summary['model_slug'])}")


if __name__ == "__main__":
    main()
