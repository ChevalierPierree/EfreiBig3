"""Train a tuned preflight model for route/airline/month scenario prediction."""

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
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
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
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler


RANDOM_STATE = 42
MAX_ROWS = 800_000
PEAK_TRAVEL_MONTHS = {6, 7, 8, 11, 12}

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "outputs"
ARTIFACT_DIR = OUTPUT_DIR / "model_artifacts"
DATA_PATH = OUTPUT_DIR / "flights_dashboard.csv"

SCENARIO_MODEL_PATH = ARTIFACT_DIR / "scenario_preflight_tuned_model.joblib"
SCENARIO_METADATA_PATH = ARTIFACT_DIR / "scenario_preflight_tuned_metadata.json"
SCENARIO_COMPARISON_PATH = ARTIFACT_DIR / "scenario_model_comparison.csv"
SCENARIO_TEST_PREDICTIONS_PATH = ARTIFACT_DIR / "scenario_model_test_predictions.csv"
SCENARIO_SEGMENT_METRICS_PATH = ARTIFACT_DIR / "scenario_model_segment_metrics.csv"
SCENARIO_RUN_SUMMARY_PATH = ARTIFACT_DIR / "scenario_model_run_summary.csv"

CATEGORICAL_FEATURES = [
    "AIRLINE",
    "ORIGIN_AIRPORT",
    "DESTINATION_AIRPORT",
    "DEP_PERIOD",
    "TRAVEL_SCENARIO",
    "ROUTE",
    "AIRLINE_ROUTE",
]

NUMERIC_FEATURES = [
    "MONTH",
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
    "IS_PEAK_TRAVEL_MONTH",
]

OUTPUT_CONTEXT_COLS = [
    "MONTH",
    "AIRLINE",
    "ORIGIN_AIRPORT",
    "DESTINATION_AIRPORT",
    "SCHEDULED_DEP_HOUR",
    "IS_WEEKEND",
    "TRAVEL_SCENARIO",
]


def add_scenario_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["AIRLINE", "ORIGIN_AIRPORT", "DESTINATION_AIRPORT", "DEP_PERIOD"]:
        out[col] = out[col].astype("string").fillna("UNKNOWN")
    out["IS_DELAYED"] = out["IS_DELAYED"].astype(int)
    out["IS_PEAK_TRAVEL_MONTH"] = out["MONTH"].isin(PEAK_TRAVEL_MONTHS).astype(int)
    out["TRAVEL_SCENARIO"] = np.where(
        out["IS_PEAK_TRAVEL_MONTH"].eq(1),
        "vacances_ou_forte_demande",
        "hors_vacances",
    )
    out["MONTH_SIN"] = np.sin(2 * np.pi * out["MONTH"] / 12)
    out["MONTH_COS"] = np.cos(2 * np.pi * out["MONTH"] / 12)
    out["HOUR_SIN"] = np.sin(2 * np.pi * out["SCHEDULED_DEP_HOUR"] / 24)
    out["HOUR_COS"] = np.cos(2 * np.pi * out["SCHEDULED_DEP_HOUR"] / 24)
    out["IS_LONG_HAUL"] = (out["DISTANCE"] >= 1500).astype(int)
    out["ROUTE"] = out["ORIGIN_AIRPORT"].astype(str) + "-" + out["DESTINATION_AIRPORT"].astype(str)
    out["AIRLINE_ROUTE"] = out["AIRLINE"].astype(str) + "-" + out["ROUTE"].astype(str)
    return out


def load_frame() -> tuple[pd.DataFrame, pd.Series]:
    required = [
        "MONTH",
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
    ]
    df = pd.read_csv(DATA_PATH, usecols=required, low_memory=False).dropna(subset=["IS_DELAYED"]).copy()
    if len(df) > MAX_ROWS:
        df = df.sample(n=MAX_ROWS, random_state=RANDOM_STATE)
    df = add_scenario_features(df)
    return df, df["IS_DELAYED"].copy()


def make_ordinal_preprocessor() -> ColumnTransformer:
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
                CATEGORICAL_FEATURES,
            ),
            ("num", Pipeline([("imputer", SimpleImputer(strategy="median"))]), NUMERIC_FEATURES),
        ]
    )


def make_ohe_preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        [
            (
                "cat",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("encoder", OneHotEncoder(handle_unknown="ignore", max_categories=160, sparse_output=True)),
                    ]
                ),
                CATEGORICAL_FEATURES,
            ),
            (
                "num",
                Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]),
                NUMERIC_FEATURES,
            ),
        ]
    )


def candidate_models() -> dict[str, Pipeline]:
    hgb_candidates = {
        "HGB_tuned_A": dict(max_iter=240, learning_rate=0.045, max_leaf_nodes=31, min_samples_leaf=45, l2_regularization=0.05),
        "HGB_tuned_B": dict(max_iter=320, learning_rate=0.035, max_leaf_nodes=39, min_samples_leaf=35, l2_regularization=0.10),
        "HGB_tuned_C": dict(max_iter=280, learning_rate=0.055, max_leaf_nodes=63, min_samples_leaf=40, l2_regularization=0.05),
        "HGB_tuned_D": dict(max_iter=220, learning_rate=0.065, max_leaf_nodes=31, min_samples_leaf=25, l2_regularization=0.00),
        "HGB_tuned_E": dict(max_iter=360, learning_rate=0.030, max_leaf_nodes=31, min_samples_leaf=60, l2_regularization=0.15),
        "HGB_tuned_F": dict(max_iter=300, learning_rate=0.045, max_leaf_nodes=79, min_samples_leaf=50, l2_regularization=0.10),
    }
    models: dict[str, Pipeline] = {
        "LogisticRegression_balanced": Pipeline(
            [
                ("prep", make_ohe_preprocessor()),
                (
                    "clf",
                    LogisticRegression(
                        max_iter=1000,
                        class_weight="balanced",
                        solver="saga",
                        random_state=RANDOM_STATE,
                    ),
                ),
            ]
        )
    }
    for name, params in hgb_candidates.items():
        models[name] = Pipeline(
            [
                ("prep", make_ordinal_preprocessor()),
                (
                    "clf",
                    HistGradientBoostingClassifier(
                        random_state=RANDOM_STATE,
                        **params,
                    ),
                ),
            ]
        )
    return models


def balanced_sample_weight(y: pd.Series) -> np.ndarray:
    counts = y.value_counts().to_dict()
    total = len(y)
    return y.map({label: total / (len(counts) * count) for label, count in counts.items()}).to_numpy()


def predict_scores(model: Pipeline, frame: pd.DataFrame) -> np.ndarray:
    return model.predict_proba(frame)[:, 1]


def best_threshold(y_true: pd.Series, y_score: np.ndarray) -> float:
    thresholds = np.linspace(0.05, 0.75, 141)
    best_t, best_s = 0.5, -np.inf
    for threshold in thresholds:
        pred = (y_score >= threshold).astype(int)
        score = f1_score(y_true, pred, zero_division=0)
        if score > best_s:
            best_t, best_s = float(threshold), float(score)
    return best_t


def evaluate_scores(
    split: str,
    model_name: str,
    y_true: pd.Series,
    y_score: np.ndarray,
    threshold: float,
    train_time_s: float,
) -> dict:
    pred = (y_score >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
    return {
        "split": split,
        "modèle": model_name,
        "threshold": threshold,
        "accuracy": accuracy_score(y_true, pred),
        "balanced_acc": balanced_accuracy_score(y_true, pred),
        "precision": precision_score(y_true, pred, zero_division=0),
        "recall": recall_score(y_true, pred, zero_division=0),
        "f1": f1_score(y_true, pred, zero_division=0),
        "roc_auc": roc_auc_score(y_true, y_score),
        "brier_score": brier_score_loss(y_true, y_score),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "tp": int(tp),
        "train_time_s": train_time_s,
    }


def segment_metrics(predictions: pd.DataFrame, group_cols: list[str], threshold: float) -> pd.DataFrame:
    rows = []
    for keys, group in predictions.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        if len(group) < 50 or group["y_true"].nunique() < 2:
            continue
        pred = (group["y_score"] >= threshold).astype(int)
        row = {col: value for col, value in zip(group_cols, keys)}
        row.update(
            {
                "nb_test": len(group),
                "taux_retard_reel": group["y_true"].mean(),
                "taux_retard_prédit": pred.mean(),
                "accuracy": accuracy_score(group["y_true"], pred),
                "balanced_acc": balanced_accuracy_score(group["y_true"], pred),
                "precision": precision_score(group["y_true"], pred, zero_division=0),
                "recall": recall_score(group["y_true"], pred, zero_division=0),
                "f1": f1_score(group["y_true"], pred, zero_division=0),
                "roc_auc": roc_auc_score(group["y_true"], group["y_score"]),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    df, y = load_frame()
    features = CATEGORICAL_FEATURES + NUMERIC_FEATURES
    x = df[features].copy()
    stratify_key = (
        y.astype(str)
        + "_m"
        + df["MONTH"].astype(str)
        + "_p"
        + df["IS_PEAK_TRAVEL_MONTH"].astype(str)
    )

    x_trainval, x_test, y_trainval, y_test, trainval_idx, test_idx = train_test_split(
        x,
        y,
        df.index,
        test_size=0.20,
        stratify=stratify_key,
        random_state=RANDOM_STATE,
    )
    trainval_strata = stratify_key.loc[trainval_idx]
    x_train, x_val, y_train, y_val = train_test_split(
        x_trainval,
        y_trainval,
        test_size=0.25,
        stratify=trainval_strata,
        random_state=RANDOM_STATE,
    )

    comparison_rows = []
    fitted_models = {}
    train_weights = balanced_sample_weight(y_train)
    for model_name, model in candidate_models().items():
        started = time.perf_counter()
        fit_kwargs = {}
        if model_name.startswith("HGB_"):
            fit_kwargs["clf__sample_weight"] = train_weights
        model.fit(x_train, y_train, **fit_kwargs)
        train_time = time.perf_counter() - started
        fitted_models[model_name] = model

        val_score = predict_scores(model, x_val)
        threshold = best_threshold(y_val, val_score)
        comparison_rows.append(evaluate_scores("validation", model_name, y_val, val_score, threshold, train_time))
        print(
            f"{model_name}: validation AUC={comparison_rows[-1]['roc_auc']:.3f}, "
            f"F1={comparison_rows[-1]['f1']:.3f}, recall={comparison_rows[-1]['recall']:.3f}, "
            f"threshold={threshold:.3f}",
            flush=True,
        )

    validation_df = pd.DataFrame(comparison_rows)
    validation_df["selection_score"] = (
        validation_df["f1"] * 0.50
        + validation_df["balanced_acc"] * 0.30
        + validation_df["roc_auc"] * 0.15
        + (1 - validation_df["brier_score"]) * 0.05
    )
    best_row = validation_df.sort_values(["selection_score", "f1", "roc_auc"], ascending=False).iloc[0]
    best_model_name = str(best_row["modèle"])
    best_model = fitted_models[best_model_name]
    threshold = float(best_row["threshold"])

    test_score = predict_scores(best_model, x_test)
    test_row = evaluate_scores("test", best_model_name, y_test, test_score, threshold, float(best_row["train_time_s"]))
    comparison_df = pd.concat([validation_df, pd.DataFrame([test_row])], ignore_index=True)

    test_context = df.loc[test_idx, OUTPUT_CONTEXT_COLS].reset_index(drop=True)
    predictions = test_context.copy()
    predictions["y_true"] = y_test.reset_index(drop=True).astype(int)
    predictions["y_score"] = test_score
    predictions["y_pred"] = (test_score >= threshold).astype(int)

    segment_tables = [
        segment_metrics(predictions, ["TRAVEL_SCENARIO"], threshold),
        segment_metrics(predictions, ["MONTH"], threshold),
        segment_metrics(predictions, ["AIRLINE"], threshold),
        segment_metrics(predictions, ["ORIGIN_AIRPORT"], threshold),
        segment_metrics(predictions, ["DESTINATION_AIRPORT"], threshold),
        segment_metrics(predictions, ["MONTH", "AIRLINE"], threshold),
        segment_metrics(predictions, ["AIRLINE", "ORIGIN_AIRPORT", "DESTINATION_AIRPORT"], threshold),
    ]
    segment_df = pd.concat([table for table in segment_tables if not table.empty], ignore_index=True)

    joblib.dump(best_model, SCENARIO_MODEL_PATH)
    comparison_df.to_csv(SCENARIO_COMPARISON_PATH, index=False)
    predictions.to_csv(SCENARIO_TEST_PREDICTIONS_PATH, index=False)
    segment_df.to_csv(SCENARIO_SEGMENT_METRICS_PATH, index=False)
    pd.DataFrame(
        [
            {"item": "sample_size", "value": len(df)},
            {"item": "train_size", "value": len(x_train)},
            {"item": "validation_size", "value": len(x_val)},
            {"item": "test_size", "value": len(x_test)},
            {"item": "positive_rate", "value": float(y.mean())},
            {"item": "holiday_months", "value": ",".join(map(str, sorted(PEAK_TRAVEL_MONTHS)))},
            {"item": "stratification", "value": "IS_DELAYED + MONTH + IS_PEAK_TRAVEL_MONTH"},
            {"item": "selection_score", "value": "0.50*F1 + 0.30*balanced_acc + 0.15*roc_auc + 0.05*(1-brier)"},
            {"item": "random_state", "value": RANDOM_STATE},
        ]
    ).to_csv(SCENARIO_RUN_SUMMARY_PATH, index=False)
    SCENARIO_METADATA_PATH.write_text(
        json.dumps(
            {
                "context": "scenario_preflight_tuned",
                "description": (
                    "Modele pre-vol fine-tune pour simuler un depart selon mois, compagnie, "
                    "aeroport de depart et aeroport d'arrivee. Aucune variable post-evenement n'est utilisee."
                ),
                "model_name": best_model_name,
                "threshold": threshold,
                "features": features,
                "categorical": CATEGORICAL_FEATURES,
                "numeric": NUMERIC_FEATURES,
                "peak_travel_months": sorted(PEAK_TRAVEL_MONTHS),
                "artifact": str(SCENARIO_MODEL_PATH),
                "test_metrics": test_row,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(
        f"Best scenario model: {best_model_name} | test AUC={test_row['roc_auc']:.3f}, "
        f"F1={test_row['f1']:.3f}, recall={test_row['recall']:.3f}, threshold={threshold:.3f}",
        flush=True,
    )


if __name__ == "__main__":
    main()
