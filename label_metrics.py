"""Silver-label vs. assessment metrics for experiment evaluation."""

from __future__ import annotations

import math
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from alignment_analysis import SCORE_LABELS, SCORE_ORDINAL

REPORT_LABELS = list(SCORE_LABELS)


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def empty_label_metrics() -> Dict[str, Any]:
    return {
        "n_total": 0,
        "n_valid": 0,
        "invalid_rate": None,
        "confusion_matrix_silver_rows_pred_columns": {
            label: {col: 0 for col in REPORT_LABELS} for label in REPORT_LABELS
        },
        "class_recall": {label: None for label in REPORT_LABELS},
        "macro_recall": None,
        "exact_match_rate": None,
        "mean_ordinal_deviation": None,
        "signed_ordinal_deviation": None,
        "harmful_optimism_global": None,
        "harmful_optimism_at_risk": None,
        "severe_harmful_optimism": None,
        "over_caution_global": None,
        "over_caution_at_risk": None,
        "silver_distribution": {label: 0.0 for label in REPORT_LABELS},
        "predicted_distribution": {label: 0.0 for label in REPORT_LABELS},
    }


def evaluate_label_metrics(
    df: pd.DataFrame,
    silver_col: str = "silver_label",
    pred_col: str = "score",
) -> Dict[str, Any]:
    if df.empty:
        return empty_label_metrics()

    valid = df[silver_col].isin(SCORE_ORDINAL) & df[pred_col].isin(SCORE_ORDINAL)
    invalid_rate = 1.0 - valid.mean()

    d = df.loc[valid].copy()
    n = len(d)

    if n == 0:
        result = empty_label_metrics()
        result["n_total"] = len(df)
        result["invalid_rate"] = float(invalid_rate)
        return result

    d["silver_ord"] = d[silver_col].map(SCORE_ORDINAL)
    d["pred_ord"] = d[pred_col].map(SCORE_ORDINAL)
    d["ordinal_delta"] = d["pred_ord"] - d["silver_ord"]

    cm = pd.crosstab(d[silver_col], d[pred_col])
    cm = cm.reindex(index=REPORT_LABELS, columns=REPORT_LABELS, fill_value=0)

    support = cm.sum(axis=1)
    class_recall = {
        label: (cm.loc[label, label] / support.loc[label])
        if support.loc[label] > 0
        else np.nan
        for label in REPORT_LABELS
    }

    macro_recall = float(np.nanmean(list(class_recall.values())))

    exact_match_rate = float((d["ordinal_delta"] == 0).mean())
    mean_ordinal_deviation = float(d["ordinal_delta"].abs().mean())
    signed_ordinal_deviation = float(d["ordinal_delta"].mean())

    harmful_optimism_mask = d["ordinal_delta"] < 0
    over_caution_mask = d["ordinal_delta"] > 0

    at_risk_optimism = d["silver_ord"] > 0
    at_risk_caution = d["silver_ord"] < 2

    harmful_optimism_global = float(harmful_optimism_mask.mean())
    harmful_optimism_at_risk = (
        float((harmful_optimism_mask & at_risk_optimism).sum() / at_risk_optimism.sum())
        if at_risk_optimism.sum() > 0
        else np.nan
    )

    severe_harmful_optimism_mask = (d[silver_col] == "ablehnen") & (
        d[pred_col] == "eher akzeptieren"
    )
    silver_ablehnen_count = (d[silver_col] == "ablehnen").sum()
    severe_harmful_optimism = (
        float(severe_harmful_optimism_mask.sum() / silver_ablehnen_count)
        if silver_ablehnen_count > 0
        else np.nan
    )

    over_caution_global = float(over_caution_mask.mean())
    over_caution_at_risk = (
        float((over_caution_mask & at_risk_caution).sum() / at_risk_caution.sum())
        if at_risk_caution.sum() > 0
        else np.nan
    )

    silver_distribution = (
        d[silver_col]
        .value_counts(normalize=True)
        .reindex(REPORT_LABELS, fill_value=0)
        .to_dict()
    )

    predicted_distribution = (
        d[pred_col]
        .value_counts(normalize=True)
        .reindex(REPORT_LABELS, fill_value=0)
        .to_dict()
    )

    return {
        "n_total": len(df),
        "n_valid": n,
        "invalid_rate": float(invalid_rate),
        "confusion_matrix_silver_rows_pred_columns": cm.to_dict(),
        "class_recall": class_recall,
        "macro_recall": macro_recall,
        "exact_match_rate": exact_match_rate,
        "mean_ordinal_deviation": mean_ordinal_deviation,
        "signed_ordinal_deviation": signed_ordinal_deviation,
        "harmful_optimism_global": harmful_optimism_global,
        "harmful_optimism_at_risk": harmful_optimism_at_risk,
        "severe_harmful_optimism": severe_harmful_optimism,
        "over_caution_global": over_caution_global,
        "over_caution_at_risk": over_caution_at_risk,
        "silver_distribution": silver_distribution,
        "predicted_distribution": predicted_distribution,
    }


def evaluate_pairs(pairs: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not pairs:
        return empty_label_metrics()

    df = pd.DataFrame(
        {
            "silver_label": [pair["silver_label"] for pair in pairs],
            "score": [pair["assessment_score"] for pair in pairs],
        }
    )
    return _json_safe(evaluate_label_metrics(df))


def confusion_matrix_dataframe(metrics: Dict[str, Any]) -> pd.DataFrame:
    matrix = metrics["confusion_matrix_silver_rows_pred_columns"]
    return pd.DataFrame(matrix).reindex(
        index=REPORT_LABELS, columns=REPORT_LABELS, fill_value=0
    )
