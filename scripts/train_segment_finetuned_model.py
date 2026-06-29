"""Fine-tune a preflight model focused on business filters and scenarios.

The model is designed for operational simulation before departure, using:
- month
- airline
- origin airport
- destination airport
- scheduled hour and route characteristics

Outputs are consumed by dashboard.py.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder
from sklearn.utils.class_weight import compute_sample_weight


RANDOM_STATE = 42
MAX_ROWS = 800_000
ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "outputs"
ARTIFACT_DIR = OUTPUT_DIR / "model_artifacts"
DATA_PATH = OUTPUT_DIR / "flights_dashboard.csv"

HOLIDAY_MONTHS = {6, 7, 8, 11, 12}
NORMAL_MONTHS = {3, 4, 5, 9, 10}

CATEGORICAL = ["AIRLINE", "ORIGIN_AIRPORT", "DESTINATION_AIRPORT", "DEP_PERIOD", "SCENARIO"]
NUMERIC = [
    "MONTH",
    "DAY",
    "DAY_OF_WEEK",
    "IS_WEEKEND",
    "SCHEDULED_DEP_HOUR",
    "SCHEDULED_TIME",
    "DISTANCE",
    "MONTH_SIN",
    "MONTH_COS",
    "HOUR_SIN",
    "HOUR_COS",
    "IS_LONG_HAUL",
    "IS_HOLIDAY_MONTH",
]
FEATURES = CATEGORICAL + NUMERIC


def scenario_from_month(month: int) -> str:
    if int(month) in HOLIDAY_MONTHS:
        return "incident_vacances"
    if int(month) in NORMAL_MONTHS:
        return "normal_sans_vacances"
    return "intermediaire"


def load_frame() -> pd.DataFrame:
    required = sorted(
        {
            "MONTH",
            "DAY",
            "DAY_OF_WEEK",
            "IS_WEEKEND",
            "AIRLINE",
            "ORIGIN_AIRPORT",
            "DESTINATION_AIRPORT",
            "SCHEDULED_DEP_HOUR",
            "DEP_PERIOD",
            "DISTANCE",
            "SCHEDULED_TIME",
            "IS_DELAYED",
        }
    )
    df = pd.read_csv(DATA_PATH, usecols=required, low_memory=False).dropna(subset=["IS_DELAYED"]).copy()
    if len(df) > MAX_ROWS:
        df = df.sample(n=MAX_ROWS, random_state=RANDOM_STATE)

    for col in ["AIRLINE", "ORIGIN_AIRPORT", "DESTINATION_AIRPORT", "DEP_PERIOD"]:
        df[col] = df[col].astype("string").fillna("UNKNOWN")
    df["IS_DELAYED"] = df["IS_DELAYED"].astype(int)
    df["SCHEDULED_TIME"] = pd.to_numeric(df["SCHEDULED_TIME"], errors="coerce")
    df["DISTANCE"] = pd.to_numeric(df["DISTANCE"], errors="coerce")
    df["SCENARIO"] = df["MONTH"].map(scenario_from_month).astype("string")
    df["IS_HOLIDAY_MONTH"] = df["MONTH"].isin(HOLIDAY_MONTHS).astype(int)
    df["MONTH_SIN"] = np.sin(2 * np.pi * df["MONTH"] / 12)
    df["MONTH_COS"] = np.cos(2 * np.pi * df["MONTH"] / 12)
    df["HOUR_SIN"] = np.sin(2 * np.pi * df["SCHEDULED_DEP_HOUR"] / 24)
    df["HOUR_COS"] = np.cos(2 * np.pi * df["SCHEDULED_DEP_HOUR"] / 24)
    df["IS_LONG_HAUL"] = (df["DISTANCE"] >= 1500).astype(int)
    return df


def stable_strata(frame: pd.DataFrame) -> pd.Series:
    strata = (
        frame["IS_DELAYED"].astype(str)
        + "_"
        + frame["SCENARIO"].astype(str)
        + "_"
        + frame["MONTH"].astype(str)
        + "_"
        + frame["AIRLINE"].astype(str)
    )
    counts = strata.value_counts()
    coarse = frame["IS_DELAYED"].astype(str) + "_" + frame["SCENARIO"].astype(str) + "_" + frame["MONTH"].astype(str)
    return strata.where(strata.map(counts).ge(20), coarse)


def make_preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        [
            (
                "cat",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        (
                            "encoder",
                            OrdinalEncoder(
                                handle_unknown="use_encoded_value",
                                unknown_value=-1,
                                encoded_missing_value=-1,
                            ),
                        ),
                    ]
                ),
                CATEGORICAL,
            ),
            ("num", Pipeline([("imputer", SimpleImputer(strategy="median"))]), NUMERIC),
        ]
    )


def make_model(params: dict) -> Pipeline:
    return Pipeline(
        [
            ("prep", make_preprocessor()),
            (
                "clf",
                HistGradientBoostingClassifier(
                    random_state=RANDOM_STATE,
                    **params,
                ),
            ),
        ]
    )


def candidate_grid() -> list[dict]:
    return [
        {"max_iter": 220, "learning_rate": 0.045, "max_leaf_nodes": 31, "min_samples_leaf": 35, "l2_regularization": 0.03},
        {"max_iter": 260, "learning_rate": 0.055, "max_leaf_nodes": 39, "min_samples_leaf": 35, "l2_regularization": 0.05},
        {"max_iter": 320, "learning_rate": 0.040, "max_leaf_nodes": 47, "min_samples_leaf": 45, "l2_regularization": 0.08},
        {"max_iter": 280, "learning_rate": 0.070, "max_leaf_nodes": 31, "min_samples_leaf": 55, "l2_regularization": 0.10},
        {"max_iter": 360, "learning_rate": 0.035, "max_leaf_nodes": 63, "min_samples_leaf": 50, "l2_regularization": 0.06},
        {"max_iter": 240, "learning_rate": 0.065, "max_leaf_nodes": 47, "min_samples_leaf": 30, "l2_regularization": 0.04},
    ]


def select_threshold(y_true: pd.Series, y_score: np.ndarray) -> tuple[float, pd.DataFrame]:
    rows = []
    for threshold in np.linspace(0.05, 0.70, 131):
        pred = (y_score >= threshold).astype(int)
        rows.append(
            {
                "threshold": float(threshold),
                "precision": precision_score(y_true, pred, zero_division=0),
                "recall": recall_score(y_true, pred, zero_division=0),
                "f1": f1_score(y_true, pred, zero_division=0),
                "balanced_acc": balanced_accuracy_score(y_true, pred),
            }
        )
    table = pd.DataFrame(rows)
    table["business_score"] = table["f1"] * 0.45 + table["balanced_acc"] * 0.30 + table["recall"] * 0.25
    eligible = table[table["precision"].ge(0.30) & table["recall"].ge(0.50)]
    selected = eligible.sort_values(["f1", "balanced_acc", "business_score"], ascending=False).head(1)
    if selected.empty:
        selected = table.sort_values(["f1", "balanced_acc", "business_score"], ascending=False).head(1)
    return float(selected["threshold"].iloc[0]), table


def metrics_at_threshold(y_true: pd.Series, y_score: np.ndarray, threshold: float) -> dict:
    pred = (y_score >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
    return {
        "threshold": threshold,
        "accuracy": accuracy_score(y_true, pred),
        "balanced_acc": balanced_accuracy_score(y_true, pred),
        "precision": precision_score(y_true, pred, zero_division=0),
        "recall": recall_score(y_true, pred, zero_division=0),
        "f1": f1_score(y_true, pred, zero_division=0),
        "roc_auc": roc_auc_score(y_true, y_score),
        "average_precision": average_precision_score(y_true, y_score),
        "brier_score": brier_score_loss(y_true, y_score),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "tp": int(tp),
    }


def group_metrics(
    frame: pd.DataFrame,
    y_true: pd.Series,
    y_score: np.ndarray,
    threshold: float,
    group_cols: list[str],
    filter_type: str,
    min_n: int,
) -> pd.DataFrame:
    work = frame[group_cols].copy()
    work["y_true"] = y_true.to_numpy()
    work["score"] = y_score
    work["pred"] = (y_score >= threshold).astype(int)
    rows = []
    for keys, part in work.groupby(group_cols, dropna=False):
        if len(part) < min_n:
            continue
        if not isinstance(keys, tuple):
            keys = (keys,)
        tn, fp, fn, tp = confusion_matrix(part["y_true"], part["pred"], labels=[0, 1]).ravel()
        positives = int(part["y_true"].sum())
        rows.append(
            {
                "filter_type": filter_type,
                **{col: value for col, value in zip(group_cols, keys)},
                "nb_vols_test": len(part),
                "positive_rate": part["y_true"].mean(),
                "score_moyen": part["score"].mean(),
                "prediction_rate": part["pred"].mean(),
                "precision": precision_score(part["y_true"], part["pred"], zero_division=0),
                "recall": recall_score(part["y_true"], part["pred"], zero_division=0) if positives else np.nan,
                "f1": f1_score(part["y_true"], part["pred"], zero_division=0) if positives else np.nan,
                "tn": int(tn),
                "fp": int(fp),
                "fn": int(fn),
                "tp": int(tp),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_frame()
    y = df["IS_DELAYED"].copy()
    x = df[FEATURES].copy()

    x_trainval, x_test, y_trainval, y_test = train_test_split(
        x,
        y,
        test_size=0.20,
        random_state=RANDOM_STATE,
        stratify=stable_strata(df),
    )
    trainval_df = df.loc[x_trainval.index].copy()
    x_train, x_val, y_train, y_val = train_test_split(
        x_trainval,
        y_trainval,
        test_size=0.25,
        random_state=RANDOM_STATE,
        stratify=stable_strata(trainval_df),
    )

    sample_weight = compute_sample_weight(class_weight="balanced", y=y_train)
    tuning_rows = []
    trained_models = {}
    for idx, params in enumerate(candidate_grid(), start=1):
        model = make_model(params)
        started = time.perf_counter()
        model.fit(x_train, y_train, clf__sample_weight=sample_weight)
        train_time = time.perf_counter() - started
        val_score = model.predict_proba(x_val)[:, 1]
        threshold, threshold_table = select_threshold(y_val, val_score)
        metrics = metrics_at_threshold(y_val, val_score, threshold)
        row = {
            "candidate": f"HistGB_tuned_{idx}",
            "train_time_s": train_time,
            **params,
            **metrics,
        }
        row["business_score"] = row["f1"] * 0.45 + row["balanced_acc"] * 0.30 + row["recall"] * 0.25
        tuning_rows.append(row)
        trained_models[row["candidate"]] = (model, params, threshold, threshold_table)
        print(
            f"{row['candidate']} | AUC={row['roc_auc']:.3f}, "
            f"precision={row['precision']:.3f}, recall={row['recall']:.3f}, F1={row['f1']:.3f}, "
            f"threshold={threshold:.3f}",
            flush=True,
        )

    tuning_df = pd.DataFrame(tuning_rows).sort_values(["business_score", "f1", "roc_auc"], ascending=False)
    best_name = str(tuning_df.iloc[0]["candidate"])
    best_model, best_params, best_threshold, threshold_table = trained_models[best_name]
    test_score = best_model.predict_proba(x_test)[:, 1]
    overall_metrics = metrics_at_threshold(y_test, test_score, best_threshold)
    overall_df = pd.DataFrame(
        [
            {
                "model_name": best_name,
                "sample_size": len(df),
                "train_size": len(x_train),
                "validation_size": len(x_val),
                "test_size": len(x_test),
                "positive_rate": y.mean(),
                "scenario_holiday_months": ",".join(map(str, sorted(HOLIDAY_MONTHS))),
                "scenario_normal_months": ",".join(map(str, sorted(NORMAL_MONTHS))),
                **best_params,
                **overall_metrics,
            }
        ]
    )

    test_frame = df.loc[x_test.index].copy()
    filter_tables = [
        group_metrics(test_frame, y_test, test_score, best_threshold, ["MONTH"], "MONTH", 100),
        group_metrics(test_frame, y_test, test_score, best_threshold, ["AIRLINE"], "AIRLINE", 100),
        group_metrics(test_frame, y_test, test_score, best_threshold, ["ORIGIN_AIRPORT"], "ORIGIN_AIRPORT", 100),
        group_metrics(test_frame, y_test, test_score, best_threshold, ["DESTINATION_AIRPORT"], "DESTINATION_AIRPORT", 100),
        group_metrics(
            test_frame,
            y_test,
            test_score,
            best_threshold,
            ["MONTH", "AIRLINE", "ORIGIN_AIRPORT", "DESTINATION_AIRPORT"],
            "MONTH_AIRLINE_ORIGIN_DESTINATION",
            30,
        ),
    ]
    filter_metrics = pd.concat([table for table in filter_tables if not table.empty], ignore_index=True)
    scenario_metrics = group_metrics(test_frame, y_test, test_score, best_threshold, ["SCENARIO"], "SCENARIO", 100)
    month_scenario_metrics = group_metrics(test_frame, y_test, test_score, best_threshold, ["SCENARIO", "MONTH"], "SCENARIO_MONTH", 100)
    test_predictions = test_frame[
        [
            "MONTH",
            "AIRLINE",
            "ORIGIN_AIRPORT",
            "DESTINATION_AIRPORT",
            "SCHEDULED_DEP_HOUR",
            "IS_WEEKEND",
            "SCENARIO",
        ]
    ].copy()
    test_predictions["y_true"] = y_test.to_numpy()
    test_predictions["y_score"] = test_score
    test_predictions["y_pred"] = (test_score >= best_threshold).astype(int)

    distribution = (
        df.groupby(["SCENARIO", "MONTH", "IS_DELAYED"], as_index=False)
        .size()
        .rename(columns={"size": "nb_vols"})
    )
    distribution["part"] = distribution["nb_vols"] / distribution.groupby(["SCENARIO", "MONTH"])["nb_vols"].transform("sum")

    final_model = make_model(best_params)
    final_weights = compute_sample_weight(class_weight="balanced", y=y_trainval)
    final_model.fit(x_trainval, y_trainval, clf__sample_weight=final_weights)

    tuning_df.to_csv(ARTIFACT_DIR / "segment_finetuned_tuning_results.csv", index=False)
    threshold_table.to_csv(ARTIFACT_DIR / "segment_finetuned_thresholds.csv", index=False)
    overall_df.to_csv(ARTIFACT_DIR / "segment_finetuned_overall_metrics.csv", index=False)
    filter_metrics.to_csv(ARTIFACT_DIR / "segment_finetuned_filter_metrics.csv", index=False)
    scenario_metrics.to_csv(ARTIFACT_DIR / "segment_finetuned_scenario_metrics.csv", index=False)
    month_scenario_metrics.to_csv(ARTIFACT_DIR / "segment_finetuned_scenario_month_metrics.csv", index=False)
    distribution.to_csv(ARTIFACT_DIR / "segment_finetuned_sample_distribution.csv", index=False)
    test_predictions.to_csv(ARTIFACT_DIR / "segment_finetuned_test_predictions.csv", index=False)
    joblib.dump(final_model, ARTIFACT_DIR / "segment_finetuned_preflight_model.joblib")

    metadata = {
        "model_name": best_name,
        "artifact": str(ARTIFACT_DIR / "segment_finetuned_preflight_model.joblib"),
        "features": FEATURES,
        "categorical": CATEGORICAL,
        "numeric": NUMERIC,
        "threshold": float(best_threshold),
        "params": best_params,
        "holiday_months": sorted(HOLIDAY_MONTHS),
        "normal_months": sorted(NORMAL_MONTHS),
        "scenario_definition": {
            "normal_sans_vacances": "Mois sans forte pression vacances retenus pour comparaison : mars, avril, mai, septembre, octobre.",
            "incident_vacances": "Mois à forte pression vacances retenus pour stress-test : juin, juillet, août, novembre, décembre.",
            "intermediaire": "Autres mois conservés dans l'apprentissage mais non utilisés comme scénario principal.",
        },
        "evaluation_note": "Métriques calculées sur test holdout 20 %, avant refit final sur train+validation.",
    }
    (ARTIFACT_DIR / "segment_finetuned_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("Best segment model:", best_name, flush=True)
    print(overall_df.to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
