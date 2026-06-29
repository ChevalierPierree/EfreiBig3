"""Retrain robust flight-delay models for the RNCP40875 deliverable."""

from __future__ import annotations

import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler


RANDOM_STATE = 42
MAX_ROWS = 800_000
CPU_POWER_W = 25
GRID_GCO2_PER_KWH = 50

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "outputs"
ARTIFACT_DIR = OUTPUT_DIR / "model_artifacts"
DATA_PATH = OUTPUT_DIR / "flights_dashboard.csv"

CONTEXTS = {
    "preflight": {
        "description": "Prediction avant depart programme, sans variable post-evenement.",
        "categorical": ["AIRLINE", "ORIGIN_AIRPORT", "DESTINATION_AIRPORT", "DEP_PERIOD"],
        "numeric": [
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
        ],
        "include_random_forest": True,
    },
    "operational_live": {
        "description": "Prediction apres observation du retard au depart. Plus precise, mais non disponible avant depart.",
        "categorical": ["AIRLINE", "ORIGIN_AIRPORT", "DESTINATION_AIRPORT", "DEP_PERIOD"],
        "numeric": [
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
            "DEPARTURE_DELAY",
            "DEP_DELAY_POSITIVE",
            "DEP_DELAY_OVER_15",
        ],
        "include_random_forest": False,
    },
}


def load_frame() -> tuple[pd.DataFrame, pd.Series]:
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
            "DEPARTURE_DELAY",
            "IS_DELAYED",
        }
    )
    df = pd.read_csv(DATA_PATH, usecols=required, low_memory=False).dropna(subset=["IS_DELAYED"]).copy()
    if len(df) > MAX_ROWS:
        df = df.sample(n=MAX_ROWS, random_state=RANDOM_STATE)
    for col in ["AIRLINE", "ORIGIN_AIRPORT", "DESTINATION_AIRPORT", "DEP_PERIOD"]:
        df[col] = df[col].astype("string").fillna("UNKNOWN")
    df["IS_DELAYED"] = df["IS_DELAYED"].astype(int)
    df["MONTH_SIN"] = np.sin(2 * np.pi * df["MONTH"] / 12)
    df["MONTH_COS"] = np.cos(2 * np.pi * df["MONTH"] / 12)
    df["HOUR_SIN"] = np.sin(2 * np.pi * df["SCHEDULED_DEP_HOUR"] / 24)
    df["HOUR_COS"] = np.cos(2 * np.pi * df["SCHEDULED_DEP_HOUR"] / 24)
    df["IS_LONG_HAUL"] = (df["DISTANCE"] >= 1500).astype(int)
    df["DEP_DELAY_POSITIVE"] = df["DEPARTURE_DELAY"].clip(lower=0)
    df["DEP_DELAY_OVER_15"] = (df["DEPARTURE_DELAY"] > 15).astype(int)
    return df, df["IS_DELAYED"].copy()


def make_ohe_preprocessor(categorical: list[str], numeric: list[str]) -> ColumnTransformer:
    return ColumnTransformer(
        [
            (
                "cat",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("encoder", OneHotEncoder(handle_unknown="ignore", max_categories=120, sparse_output=True)),
                    ]
                ),
                categorical,
            ),
            (
                "num",
                Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]),
                numeric,
            ),
        ]
    )


def make_ordinal_preprocessor(categorical: list[str], numeric: list[str]) -> ColumnTransformer:
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
                categorical,
            ),
            ("num", Pipeline([("imputer", SimpleImputer(strategy="median"))]), numeric),
        ]
    )


def build_models(categorical: list[str], numeric: list[str], include_random_forest: bool) -> dict[str, Pipeline]:
    ohe = make_ohe_preprocessor(categorical, numeric)
    ordinal = make_ordinal_preprocessor(categorical, numeric)
    models = {
        "Baseline_majoritaire": Pipeline([("prep", ohe), ("clf", DummyClassifier(strategy="most_frequent"))]),
        "LogisticRegression_balanced": Pipeline(
            [
                ("prep", ohe),
                (
                    "clf",
                    LogisticRegression(
                        max_iter=1200,
                        class_weight="balanced",
                        solver="saga",
                        random_state=RANDOM_STATE,
                    ),
                ),
            ]
        ),
        "HistGradientBoosting": Pipeline(
            [
                ("prep", ordinal),
                (
                    "clf",
                    HistGradientBoostingClassifier(
                        max_iter=260,
                        learning_rate=0.055,
                        max_leaf_nodes=39,
                        min_samples_leaf=35,
                        l2_regularization=0.05,
                        random_state=RANDOM_STATE,
                    ),
                ),
            ]
        ),
    }
    if include_random_forest:
        models["RandomForest_balanced"] = Pipeline(
            [
                ("prep", ohe),
                (
                    "clf",
                    RandomForestClassifier(
                        n_estimators=100,
                        max_depth=16,
                        min_samples_leaf=25,
                        class_weight="balanced_subsample",
                        n_jobs=-1,
                        random_state=RANDOM_STATE,
                    ),
                ),
            ]
        )
    return models


def predict_scores(model: Pipeline, x_frame: pd.DataFrame) -> np.ndarray:
    return model.predict_proba(x_frame)[:, 1] if hasattr(model, "predict_proba") else model.predict(x_frame)


def best_threshold(y_true: pd.Series, y_score: np.ndarray, objective: str) -> float:
    thresholds = np.linspace(0.05, 0.95, 181)
    best_t, best_s = 0.5, -np.inf
    for threshold in thresholds:
        pred = (y_score >= threshold).astype(int)
        score = f1_score(y_true, pred, zero_division=0) if objective == "f1" else balanced_accuracy_score(y_true, pred)
        if score > best_s:
            best_t, best_s = float(threshold), float(score)
    return best_t


def evaluate(
    context: str,
    model_name: str,
    variant: str,
    y_true: pd.Series,
    y_score: np.ndarray,
    threshold: float,
    train_time_s: float,
) -> tuple[dict, list[dict], list[dict]]:
    pred = (y_score >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
    report = classification_report(y_true, pred, labels=[0, 1], output_dict=True, zero_division=0)
    metrics = {
        "contexte": context,
        "modèle": model_name,
        "variante": variant,
        "threshold": threshold,
        "accuracy": accuracy_score(y_true, pred),
        "balanced_acc": balanced_accuracy_score(y_true, pred),
        "precision": precision_score(y_true, pred, zero_division=0),
        "recall": recall_score(y_true, pred, zero_division=0),
        "f1": f1_score(y_true, pred, zero_division=0),
        "roc_auc": roc_auc_score(y_true, y_score),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "tp": int(tp),
        "train_time_s": train_time_s,
        "energie_Wh": train_time_s * CPU_POWER_W / 3600,
        "co2_g": (train_time_s * CPU_POWER_W / 3600) / 1000 * GRID_GCO2_PER_KWH,
    }
    labels = {0: "à l'heure", 1: "en retard"}
    cm = confusion_matrix(y_true, pred, labels=[0, 1])
    confusions = []
    for actual_idx, actual_label in enumerate([0, 1]):
        total = cm[actual_idx].sum()
        for pred_idx, pred_label in enumerate([0, 1]):
            count = int(cm[actual_idx, pred_idx])
            confusions.append(
                {
                    "contexte": context,
                    "modèle": model_name,
                    "variante": variant,
                    "threshold": threshold,
                    "actual": labels[actual_label],
                    "predicted": labels[pred_label],
                    "count": count,
                    "pct_actual": count / total if total else 0,
                }
            )
    reports = []
    for label, values in report.items():
        if isinstance(values, dict):
            reports.append(
                {
                    "contexte": context,
                    "modèle": model_name,
                    "variante": variant,
                    "threshold": threshold,
                    "classe": label,
                    "precision": values.get("precision", np.nan),
                    "recall": values.get("recall", np.nan),
                    "f1_score": values.get("f1-score", np.nan),
                    "support": values.get("support", np.nan),
                }
            )
    return metrics, confusions, reports


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    df, y = load_frame()
    all_metrics, recommended_metrics = [], []
    all_confusions, recommended_confusions = [], []
    all_reports, recommended_reports = [], []
    metadata = {}

    for context, spec in CONTEXTS.items():
        categorical = spec["categorical"]
        numeric = spec["numeric"]
        features = categorical + numeric
        x = df[features].copy()
        x_trainval, x_test, y_trainval, y_test = train_test_split(
            x, y, test_size=0.20, stratify=y, random_state=RANDOM_STATE
        )
        x_train, x_val, y_train, y_val = train_test_split(
            x_trainval, y_trainval, test_size=0.25, stratify=y_trainval, random_state=RANDOM_STATE
        )

        context_recommended = []
        trained = {}
        for model_name, model in build_models(categorical, numeric, spec["include_random_forest"]).items():
            started = time.perf_counter()
            model.fit(x_train, y_train)
            train_time = time.perf_counter() - started
            trained[model_name] = model
            val_score = predict_scores(model, x_val)
            test_score = predict_scores(model, x_test)
            thresholds = {
                "seuil_0_50": 0.50,
                "seuil_optimise_f1": best_threshold(y_val, val_score, "f1"),
                "seuil_optimise_balanced_accuracy": best_threshold(y_val, val_score, "balanced_accuracy"),
            }
            for variant, threshold in thresholds.items():
                metrics, confusions, reports = evaluate(context, model_name, variant, y_test, test_score, threshold, train_time)
                all_metrics.append(metrics)
                all_confusions.extend(confusions)
                all_reports.extend(reports)
                if variant == "seuil_optimise_f1":
                    context_recommended.append(metrics)
            row = context_recommended[-1]
            print(
                f"{context} | {model_name}: AUC={row['roc_auc']:.3f}, "
                f"precision={row['precision']:.3f}, recall={row['recall']:.3f}, F1={row['f1']:.3f}",
                flush=True,
            )

        context_df = pd.DataFrame(context_recommended)
        best = context_df.sort_values(["f1", "roc_auc", "balanced_acc"], ascending=False).iloc[0].to_dict()
        best_name = str(best["modèle"])
        recommended_metrics.append(best)
        recommended_confusions.extend(
            [
                row
                for row in all_confusions
                if row["contexte"] == context and row["modèle"] == best_name and row["variante"] == "seuil_optimise_f1"
            ]
        )
        recommended_reports.extend(
            [
                row
                for row in all_reports
                if row["contexte"] == context and row["modèle"] == best_name and row["variante"] == "seuil_optimise_f1"
            ]
        )
        artifact_path = ARTIFACT_DIR / f"best_{context}_model.joblib"
        joblib.dump(trained[best_name], artifact_path)
        metadata[context] = {
            "model_name": best_name,
            "threshold": float(best["threshold"]),
            "features": features,
            "categorical": categorical,
            "numeric": numeric,
            "description": spec["description"],
            "artifact": str(artifact_path),
        }

    recommended_df = pd.DataFrame(recommended_metrics).sort_values(["contexte", "f1"], ascending=[True, False])
    all_metrics_df = pd.DataFrame(all_metrics).sort_values(["contexte", "modèle", "variante"])
    rec_confusions_df = pd.DataFrame(recommended_confusions)
    all_confusions_df = pd.DataFrame(all_confusions)
    rec_reports_df = pd.DataFrame(recommended_reports)
    all_reports_df = pd.DataFrame(all_reports)

    confusion_wide = recommended_df[
        [
            "contexte",
            "modèle",
            "variante",
            "threshold",
            "tn",
            "fp",
            "fn",
            "tp",
            "accuracy",
            "balanced_acc",
            "precision",
            "recall",
            "f1",
            "roc_auc",
        ]
    ].copy()
    confusion_wide["specificity"] = confusion_wide["tn"] / (confusion_wide["tn"] + confusion_wide["fp"])
    confusion_wide["false_negative_rate"] = confusion_wide["fn"] / (confusion_wide["fn"] + confusion_wide["tp"])
    confusion_wide["false_positive_rate"] = confusion_wide["fp"] / (confusion_wide["fp"] + confusion_wide["tn"])

    recommended_df.to_csv(OUTPUT_DIR / "model_comparison.csv", index=False)
    recommended_df.to_csv(ARTIFACT_DIR / "model_metrics_detailed.csv", index=False)
    all_metrics_df.to_csv(ARTIFACT_DIR / "model_metrics_all_thresholds.csv", index=False)
    rec_confusions_df.to_csv(ARTIFACT_DIR / "model_confusion_matrices.csv", index=False)
    all_confusions_df.to_csv(ARTIFACT_DIR / "model_confusion_matrices_all_thresholds.csv", index=False)
    confusion_wide.to_csv(ARTIFACT_DIR / "model_confusion_matrix_wide.csv", index=False)
    rec_reports_df.to_csv(ARTIFACT_DIR / "model_classification_report.csv", index=False)
    all_reports_df.to_csv(ARTIFACT_DIR / "model_classification_report_all_thresholds.csv", index=False)
    pd.DataFrame(
        [
            {"item": "sample_size", "value": len(df)},
            {"item": "train_size", "value": int(len(df) * 0.60)},
            {"item": "validation_size", "value": int(len(df) * 0.20)},
            {"item": "test_size", "value": int(len(df) * 0.20)},
            {"item": "positive_rate", "value": float(y.mean())},
            {"item": "contexts", "value": ", ".join(CONTEXTS.keys())},
            {"item": "random_state", "value": RANDOM_STATE},
        ]
    ).to_csv(ARTIFACT_DIR / "modeling_run_summary.csv", index=False)
    (ARTIFACT_DIR / "best_models_metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
