"""
Dashboard Streamlit - Projet RNCP40875 retards de vols.

Structure cible :
- Page 1 : vue executive
- Page 2 : analyse operationnelle
- Page 3 : recommandations
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


APP_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = APP_DIR / "outputs"
DATA_PATH = OUTPUT_DIR / "flights_dashboard.csv"
MODEL_PATH = OUTPUT_DIR / "model_comparison.csv"
MODEL_ARTIFACT_DIR = OUTPUT_DIR / "model_artifacts"
CONFUSION_WIDE_PATH = MODEL_ARTIFACT_DIR / "model_confusion_matrix_wide.csv"
SCENARIO_MODEL_PATH = MODEL_ARTIFACT_DIR / "segment_finetuned_preflight_model.joblib"
SCENARIO_METADATA_PATH = MODEL_ARTIFACT_DIR / "segment_finetuned_metadata.json"
SCENARIO_COMPARISON_PATH = MODEL_ARTIFACT_DIR / "segment_finetuned_tuning_results.csv"
SCENARIO_OVERALL_PATH = MODEL_ARTIFACT_DIR / "segment_finetuned_overall_metrics.csv"
SCENARIO_SEGMENT_PATH = MODEL_ARTIFACT_DIR / "segment_finetuned_filter_metrics.csv"
SCENARIO_METRICS_PATH = MODEL_ARTIFACT_DIR / "segment_finetuned_scenario_metrics.csv"
SCENARIO_MONTH_METRICS_PATH = MODEL_ARTIFACT_DIR / "segment_finetuned_scenario_month_metrics.csv"
SCENARIO_DISTRIBUTION_PATH = MODEL_ARTIFACT_DIR / "segment_finetuned_sample_distribution.csv"
SCENARIO_PREDICTIONS_PATH = MODEL_ARTIFACT_DIR / "segment_finetuned_test_predictions.csv"
CONSOLIDATED_DIR = OUTPUT_DIR / "consolidated_dashboards"
AIRLINES_REF = APP_DIR / "flights_delay" / "airlines.csv"
AIRPORTS_REF = APP_DIR / "flights_delay" / "airports.csv"
PEAK_TRAVEL_MONTHS = {6, 7, 8, 11, 12}
NORMAL_TRAVEL_MONTHS = {3, 4, 5, 9, 10}

MONTH_NAMES = {
    1: "Janvier",
    2: "Février",
    3: "Mars",
    4: "Avril",
    5: "Mai",
    6: "Juin",
    7: "Juillet",
    8: "Août",
    9: "Septembre",
    10: "Octobre",
    11: "Novembre",
    12: "Décembre",
}
MONTH_SHORT = {
    1: "Jan",
    2: "Fév",
    3: "Mar",
    4: "Avr",
    5: "Mai",
    6: "Juin",
    7: "Juil",
    8: "Août",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Déc",
}
DOW_NAMES = {
    1: "Lundi",
    2: "Mardi",
    3: "Mercredi",
    4: "Jeudi",
    5: "Vendredi",
    6: "Samedi",
    7: "Dimanche",
}
DOW_SHORT = {1: "Lun", 2: "Mar", 3: "Mer", 4: "Jeu", 5: "Ven", 6: "Sam", 7: "Dim"}

INK = "#111827"
MUTED = "#6B7280"
LINE = "#E5E7EB"
SOFT = "#F8FAFC"
ACCENT = "#2563EB"
RISK = "#DC2626"
WARN = "#F59E0B"
GOOD = "#059669"


st.set_page_config(
    page_title="RNCP40875 - Retards de vols",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.main .block-container {
    max-width: 1360px;
    padding-top: 1.6rem;
    padding-bottom: 4rem;
}
h1 {
    font-size: 2.7rem;
    line-height: 1.05;
    letter-spacing: -0.025em;
}
h2, h3 {
    letter-spacing: 0;
}
.hero {
    border-bottom: 1px solid #E5E7EB;
    padding-bottom: 1.2rem;
    margin-bottom: 1.2rem;
}
.subtitle {
    color: #6B7280;
    font-size: 1.03rem;
    margin-top: .25rem;
}
.kpi-card {
    border-top: 1px solid #E5E7EB;
    padding: .9rem 0 .35rem 0;
}
.kpi-label {
    color: #6B7280;
    font-size: .72rem;
    letter-spacing: .08em;
    text-transform: uppercase;
}
.kpi-value {
    color: #111827;
    font-size: 2.1rem;
    font-weight: 430;
    letter-spacing: -0.025em;
    margin-top: .2rem;
}
.kpi-help {
    color: #6B7280;
    font-size: .82rem;
}
.note {
    background: #F8FAFC;
    border-left: 3px solid #111827;
    border-radius: 0 6px 6px 0;
    padding: .85rem 1rem;
    color: #374151;
    margin: .75rem 0 1rem 0;
}
.tag {
    display: inline-block;
    border: 1px solid #E5E7EB;
    border-radius: 999px;
    padding: .22rem .6rem;
    margin: .15rem .16rem .15rem 0;
    color: #374151;
    font-size: .8rem;
    background: #FFFFFF;
}
div[data-testid="stSidebar"] {
    background: #FAFAFA;
}
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def load_dashboard_data() -> pd.DataFrame:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Fichier introuvable : {DATA_PATH}")

    df = pd.read_csv(DATA_PATH, low_memory=False)
    for col in ["AIRLINE", "ORIGIN_AIRPORT", "DESTINATION_AIRPORT", "DEP_PERIOD"]:
        if col in df.columns:
            df[col] = df[col].astype(str)

    if AIRLINES_REF.exists():
        airlines = pd.read_csv(AIRLINES_REF).rename(columns={"AIRLINE": "AIRLINE_NAME"})
        df = df.merge(airlines, left_on="AIRLINE", right_on="IATA_CODE", how="left")
        df["AIRLINE_NAME"] = df["AIRLINE_NAME"].fillna(df["AIRLINE"])
        df = df.drop(columns=["IATA_CODE"], errors="ignore")
    else:
        df["AIRLINE_NAME"] = df["AIRLINE"]

    if AIRPORTS_REF.exists():
        airports = pd.read_csv(AIRPORTS_REF)
        origin_ref = airports.rename(
            columns={
                "IATA_CODE": "ORIGIN_AIRPORT",
                "AIRPORT": "ORIGIN_AIRPORT_NAME",
                "CITY": "ORIGIN_CITY",
                "STATE": "ORIGIN_STATE",
            }
        )[["ORIGIN_AIRPORT", "ORIGIN_AIRPORT_NAME", "ORIGIN_CITY", "ORIGIN_STATE"]]
        dest_ref = airports.rename(
            columns={
                "IATA_CODE": "DESTINATION_AIRPORT",
                "AIRPORT": "DESTINATION_AIRPORT_NAME",
                "CITY": "DESTINATION_CITY",
                "STATE": "DESTINATION_STATE",
            }
        )[["DESTINATION_AIRPORT", "DESTINATION_AIRPORT_NAME", "DESTINATION_CITY", "DESTINATION_STATE"]]
        df = df.merge(origin_ref, on="ORIGIN_AIRPORT", how="left")
        df = df.merge(dest_ref, on="DESTINATION_AIRPORT", how="left")

    return df


@st.cache_data(show_spinner=False)
def read_csv_or_empty(path: Path) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path, low_memory=False)
    return pd.DataFrame()


@st.cache_data(show_spinner=False)
def read_json_or_empty(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


@st.cache_resource(show_spinner=False)
def load_joblib_model(path: Path):
    if path.exists():
        return joblib.load(path)
    return None


def fmt_int(value: float | int) -> str:
    return f"{int(value):,}".replace(",", " ")


def pct(value: float) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{value * 100:.1f} %"


def metric_block(label: str, value: str, help_text: str) -> None:
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-help">{help_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def note(text: str) -> None:
    st.markdown(f"<div class='note'>{text}</div>", unsafe_allow_html=True)


def base_layout(height: int = 380) -> dict:
    return {
        "height": height,
        "margin": {"l": 28, "r": 28, "t": 58, "b": 42},
        "paper_bgcolor": "white",
        "plot_bgcolor": "white",
        "font": {"color": MUTED, "size": 12},
        "xaxis": {"showgrid": False, "zeroline": False, "color": MUTED},
        "yaxis": {"showgrid": True, "gridcolor": LINE, "zeroline": False, "color": MUTED},
        "hoverlabel": {"bgcolor": "white", "bordercolor": LINE, "font": {"color": INK}},
    }


def rate_by(frame: pd.DataFrame, group_cols: list[str], min_volume: int = 1) -> pd.DataFrame:
    out = (
        frame.groupby(group_cols, dropna=False, as_index=False)
        .agg(
            nb_vols=("IS_DELAYED", "size"),
            nb_retards=("IS_DELAYED", "sum"),
            taux_retard=("IS_DELAYED", "mean"),
            retard_arrivee_moyen=("ARRIVAL_DELAY", "mean"),
            retard_depart_moyen=("DEPARTURE_DELAY", "mean"),
            distance_moyenne=("DISTANCE", "mean"),
        )
    )
    out = out[out["nb_vols"].ge(min_volume)].copy()
    out["taux_retard_pct"] = out["taux_retard"] * 100
    return out


def horizontal_bar(
    data: pd.DataFrame,
    x_col: str,
    y_col: str,
    title: str,
    color: str,
    suffix: str = "",
    height: int = 420,
) -> go.Figure:
    fig = go.Figure(
        go.Bar(
            x=data[x_col],
            y=data[y_col],
            orientation="h",
            marker_color=color,
            text=[f"{v:.1f}{suffix}" if isinstance(v, float) else f"{v}{suffix}" for v in data[x_col]],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>%{x:.2f}" + suffix + "<extra></extra>",
        )
    )
    fig.update_layout(title=title, showlegend=False, **base_layout(height))
    fig.update_yaxes(showgrid=False)
    return fig


def line_chart(data: pd.DataFrame, x_col: str, y_col: str, title: str, y_suffix: str = "") -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=data[x_col],
            y=data[y_col],
            mode="lines+markers",
            line={"color": INK, "width": 2},
            marker={"size": 7, "color": INK},
            hovertemplate="<b>%{x}</b><br>%{y:.1f}" + y_suffix + "<extra></extra>",
        )
    )
    fig.update_layout(title=title, showlegend=False, **base_layout())
    if y_suffix:
        fig.update_yaxes(ticksuffix=f" {y_suffix}")
    return fig


def gauge_chart(value_pct: float, target_pct: float, title: str) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value_pct,
            number={"suffix": " %", "font": {"size": 38, "color": INK}},
            title={"text": title, "font": {"size": 16, "color": INK}},
            gauge={
                "axis": {"range": [0, max(35, value_pct + 5)], "tickcolor": MUTED, "ticksuffix": "%"},
                "bar": {"color": RISK if value_pct > target_pct else GOOD, "thickness": 0.28},
                "bgcolor": "white",
                "borderwidth": 1,
                "bordercolor": LINE,
                "steps": [
                    {"range": [0, target_pct], "color": "#E7F7EF"},
                    {"range": [target_pct, target_pct + 5], "color": "#FEF3C7"},
                    {"range": [target_pct + 5, max(35, value_pct + 5)], "color": "#FEE2E2"},
                ],
                "threshold": {
                    "line": {"color": INK, "width": 3},
                    "thickness": 0.8,
                    "value": target_pct,
                },
            },
        )
    )
    fig.update_layout(**base_layout(300))
    return fig


def donut_chart(labels: list[str], values: list[int | float], title: str) -> go.Figure:
    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.62,
            marker={"colors": [GOOD, RISK]},
            textinfo="label+percent",
            hovertemplate="<b>%{label}</b><br>%{value:,} vols<br>%{percent}<extra></extra>",
        )
    )
    fig.update_layout(title=title, showlegend=False, **base_layout(300))
    return fig


def grouped_model_metrics(model_metrics: pd.DataFrame, title: str) -> go.Figure:
    metric_cols = [col for col in ["roc_auc", "recall", "precision", "f1"] if col in model_metrics.columns]
    chart = model_metrics[["contexte", *metric_cols]].melt(
        id_vars="contexte",
        var_name="métrique",
        value_name="score",
    )
    label_map = {
        "roc_auc": "ROC-AUC",
        "recall": "Recall",
        "precision": "Precision",
        "f1": "F1",
    }
    chart["métrique"] = chart["métrique"].map(label_map).fillna(chart["métrique"])
    fig = go.Figure()
    colors = {"ROC-AUC": INK, "Recall": RISK, "Precision": WARN, "F1": ACCENT}
    for metric in chart["métrique"].unique():
        subset = chart[chart["métrique"].eq(metric)]
        fig.add_trace(
            go.Bar(
                x=subset["contexte"],
                y=subset["score"],
                name=metric,
                marker_color=colors.get(metric, ACCENT),
                text=[f"{v:.2f}" for v in subset["score"]],
                textposition="outside",
                hovertemplate="<b>%{x}</b><br>" + metric + " : %{y:.3f}<extra></extra>",
            )
        )
    fig.update_layout(
        title=title,
        barmode="group",
        legend={"orientation": "h", "y": -0.18},
        **base_layout(300),
    )
    fig.update_yaxes(range=[0, 1], tickformat=".0%")
    return fig


def recommendation_matrix(recommendations: pd.DataFrame) -> go.Figure:
    fig = go.Figure(
        go.Scatter(
            x=recommendations["Effort"],
            y=recommendations["Impact"],
            mode="markers+text",
            text=recommendations["Priorité"],
            textposition="middle center",
            customdata=np.stack(
                [
                    recommendations["Recommandation"],
                    recommendations["Horizon"],
                    recommendations["KPI de suivi"],
                ],
                axis=-1,
            ),
            marker={
                "size": recommendations["Score"].mul(2.2).add(18),
                "color": recommendations["Score"],
                "colorscale": [[0, "#DBEAFE"], [0.5, "#FBBF24"], [1, "#DC2626"]],
                "line": {"color": "white", "width": 2},
                "showscale": True,
                "colorbar": {"title": "Score"},
            },
            hovertemplate=(
                "<b>Priorité %{text}</b><br>%{customdata[0]}<br>"
                "Horizon : %{customdata[1]}<br>KPI : %{customdata[2]}"
                "<br>Impact %{y}/5 - Effort %{x}/5<extra></extra>"
            ),
        )
    )
    fig.add_hline(y=3, line_dash="dot", line_color=LINE)
    fig.add_vline(x=3, line_dash="dot", line_color=LINE)
    fig.update_layout(
        title="Matrice de priorisation impact / effort",
        xaxis_title="Effort de mise en oeuvre",
        yaxis_title="Impact métier attendu",
        showlegend=False,
        **base_layout(460),
    )
    fig.update_xaxes(range=[0.5, 5.5], dtick=1)
    fig.update_yaxes(range=[0.5, 5.5], dtick=1)
    return fig


def timeline_chart(action_plan: pd.DataFrame) -> go.Figure:
    colors = {"0-30 jours": GOOD, "30-60 jours": WARN, "60-90 jours": ACCENT, "Continu": INK}
    fig = go.Figure()
    for horizon, subset in action_plan.groupby("Horizon", sort=False):
        fig.add_trace(
            go.Bar(
                y=subset["Chantier"],
                x=subset["Durée"],
                base=subset["Début"],
                orientation="h",
                name=horizon,
                marker_color=colors.get(horizon, ACCENT),
                customdata=np.stack([subset["Livrable"], subset["KPI"]], axis=-1),
                hovertemplate="<b>%{y}</b><br>%{customdata[0]}<br>KPI : %{customdata[1]}<extra></extra>",
            )
        )
    fig.update_layout(
        title="Feuille de route de déploiement IA",
        barmode="stack",
        xaxis_title="Jours depuis le lancement",
        legend={"orientation": "h", "y": -0.2},
        **base_layout(460),
    )
    fig.update_yaxes(showgrid=False, autorange="reversed")
    return fig


def confusion_heatmap(row: pd.Series, title: str) -> go.Figure:
    matrix = np.array([[row["tn"], row["fp"]], [row["fn"], row["tp"]]], dtype=float)
    total = matrix.sum()
    text = [
        [
            f"TN<br>{int(matrix[0, 0]):,}<br>{matrix[0, 0] / total:.1%}",
            f"FP<br>{int(matrix[0, 1]):,}<br>{matrix[0, 1] / total:.1%}",
        ],
        [
            f"FN<br>{int(matrix[1, 0]):,}<br>{matrix[1, 0] / total:.1%}",
            f"TP<br>{int(matrix[1, 1]):,}<br>{matrix[1, 1] / total:.1%}",
        ],
    ]
    fig = go.Figure(
        go.Heatmap(
            z=matrix,
            x=["Prédit non retard", "Prédit retard"],
            y=["Réel non retard", "Réel retard"],
            colorscale="Blues",
            text=text,
            texttemplate="%{text}",
            hovertemplate="%{y}<br>%{x}<br>%{z:,} vols<extra></extra>",
        )
    )
    fig.update_layout(title=title, **base_layout(360))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=False)
    return fig


def risk_status(rate_pct: float) -> tuple[str, str, str]:
    if pd.isna(rate_pct):
        return "Non estimable", MUTED, "Pas assez d'historique disponible."
    if rate_pct >= 25:
        return "Critique", RISK, "Décision immédiate : pré-alerte et renfort opérationnel."
    if rate_pct >= 20:
        return "Élevé", WARN, "Décision : surveillance active et préparation des ressources."
    if rate_pct >= 15:
        return "Sous vigilance", ACCENT, "Décision : suivi renforcé, sans mobilisation lourde."
    return "Acceptable", GOOD, "Décision : traitement standard avec monitoring."


def confidence_label(volume: int) -> str:
    if volume >= 500:
        return "Forte"
    if volume >= 100:
        return "Moyenne"
    if volume >= 30:
        return "Faible"
    return "Très faible"


def segment_summary(frame: pd.DataFrame, mask: pd.Series, label: str) -> dict:
    segment = frame.loc[mask]
    if segment.empty:
        return {
            "Référence": label,
            "nb_vols": 0,
            "taux_retard_pct": np.nan,
            "retard_arrivee_moyen": np.nan,
            "retard_depart_moyen": np.nan,
            "fiabilité": "Aucune",
        }
    volume = len(segment)
    return {
        "Référence": label,
        "nb_vols": volume,
        "taux_retard_pct": segment["IS_DELAYED"].mean() * 100,
        "retard_arrivee_moyen": segment["ARRIVAL_DELAY"].mean(),
        "retard_depart_moyen": segment["DEPARTURE_DELAY"].mean(),
        "fiabilité": confidence_label(volume),
    }


def scenario_comparison_chart(scenario_df: pd.DataFrame, selected_label: str) -> go.Figure:
    chart = scenario_df[scenario_df["nb_vols"].gt(0)].copy()
    colors = [RISK if ref == selected_label else ACCENT for ref in chart["Référence"]]
    fig = go.Figure(
        go.Bar(
            x=chart["taux_retard_pct"],
            y=chart["Référence"],
            orientation="h",
            marker_color=colors,
            text=[f"{v:.1f} %" for v in chart["taux_retard_pct"]],
            textposition="outside",
            customdata=np.stack([chart["nb_vols"], chart["fiabilité"]], axis=-1),
            hovertemplate=(
                "<b>%{y}</b><br>%{x:.2f} % de retards"
                "<br>%{customdata[0]:,} vols"
                "<br>Fiabilité : %{customdata[1]}<extra></extra>"
            ),
        )
    )
    fig.update_layout(title="Comparaison du scénario avec les références historiques", showlegend=False, **base_layout(440))
    fig.update_xaxes(ticksuffix=" %")
    fig.update_yaxes(showgrid=False, autorange="reversed")
    return fig


def operational_playbook(level: str) -> pd.DataFrame:
    playbooks = {
        "Critique": [
            {
                "Décision": "Pré-alerte passagers",
                "Action métier": "Préparer message retard probable, options de correspondance et alternatives self-service.",
                "Responsable": "Expérience client",
                "KPI": "Taux de passagers notifiés, correspondances protégées",
            },
            {
                "Décision": "Renfort escale",
                "Action métier": "Ajouter agents porte/embarquement sur le créneau et contrôler la rotation appareil.",
                "Responsable": "Opérations sol",
                "KPI": "Retard départ moyen, temps de rotation",
            },
            {
                "Décision": "Pilotage correspondances",
                "Action métier": "Identifier passagers en correspondance courte et prioriser réacheminement si nécessaire.",
                "Responsable": "Hub control",
                "KPI": "Correspondances manquées, réacheminements anticipés",
            },
        ],
        "Élevé": [
            {
                "Décision": "Surveillance active",
                "Action métier": "Mettre le vol dans la watchlist opérationnelle et vérifier météo, équipage, appareil.",
                "Responsable": "Centre opérations",
                "KPI": "Retards détectés avant H-2",
            },
            {
                "Décision": "Préparation porte",
                "Action métier": "Sécuriser affectation porte, équipe sol et disponibilité embarquement.",
                "Responsable": "Escale",
                "KPI": "Retard départ moyen",
            },
        ],
        "Sous vigilance": [
            {
                "Décision": "Monitoring standard renforcé",
                "Action métier": "Contrôler le statut du vol dans le rituel opérationnel sans mobilisation supplémentaire.",
                "Responsable": "Supervision opérationnelle",
                "KPI": "Taux de retard par créneau",
            }
        ],
        "Acceptable": [
            {
                "Décision": "Traitement nominal",
                "Action métier": "Maintenir le processus standard et suivre les KPI de ponctualité.",
                "Responsable": "Opérations",
                "KPI": "Ponctualité globale",
            }
        ],
    }
    return pd.DataFrame(playbooks.get(level, playbooks["Acceptable"]))


def dep_period_from_hour(hour: int) -> str:
    if 5 <= hour < 12:
        return "matin"
    if 12 <= hour < 18:
        return "après-midi"
    if 18 <= hour < 23:
        return "soir"
    return "nuit"


def scenario_feature_row(
    source: pd.DataFrame,
    month: int,
    airline: str,
    origin: str,
    destination: str,
    hour: int | str,
    weekend_mode: str,
    metadata: dict,
) -> pd.DataFrame:
    route_mask = source["ORIGIN_AIRPORT"].eq(origin) & source["DESTINATION_AIRPORT"].eq(destination)
    airline_mask = source["AIRLINE"].eq(airline)
    base_segment = source[route_mask & airline_mask]
    if base_segment.empty:
        base_segment = source[route_mask]
    if base_segment.empty:
        base_segment = source[airline_mask]
    if base_segment.empty:
        base_segment = source

    if hour == "Toutes":
        scheduled_hour = int(round(base_segment["SCHEDULED_DEP_HOUR"].median()))
    else:
        scheduled_hour = int(hour)
    scheduled_hour = int(np.clip(scheduled_hour, 0, 23))

    if weekend_mode == "Week-end":
        is_weekend = 1
        day_of_week = 6
    elif weekend_mode == "Semaine":
        is_weekend = 0
        day_of_week = 3
    else:
        is_weekend = int(round(base_segment["IS_WEEKEND"].median()))
        day_of_week = 6 if is_weekend else 3

    route_reference = source[route_mask]
    if route_reference.empty:
        route_reference = base_segment
    distance = float(route_reference["DISTANCE"].median())
    scheduled_time = float(route_reference["SCHEDULED_TIME"].median())
    holiday_months = set(metadata.get("holiday_months", sorted(PEAK_TRAVEL_MONTHS)))
    normal_months = set(metadata.get("normal_months", sorted(NORMAL_TRAVEL_MONTHS)))
    is_peak = int(month in holiday_months)
    if month in holiday_months:
        scenario_label = "incident_vacances"
    elif month in normal_months:
        scenario_label = "normal_sans_vacances"
    else:
        scenario_label = "intermediaire"
    route = f"{origin}-{destination}"

    row = {
        "AIRLINE": airline,
        "ORIGIN_AIRPORT": origin,
        "DESTINATION_AIRPORT": destination,
        "DEP_PERIOD": dep_period_from_hour(scheduled_hour),
        "SCENARIO": scenario_label,
        "TRAVEL_SCENARIO": "vacances_ou_forte_demande" if is_peak else "hors_vacances",
        "ROUTE": route,
        "AIRLINE_ROUTE": f"{airline}-{route}",
        "MONTH": month,
        "DAY": 15,
        "DAY_OF_WEEK": day_of_week,
        "IS_WEEKEND": is_weekend,
        "SCHEDULED_DEP_HOUR": scheduled_hour,
        "SCHEDULED_TIME": scheduled_time,
        "DISTANCE": distance,
        "MONTH_SIN": np.sin(2 * np.pi * month / 12),
        "MONTH_COS": np.cos(2 * np.pi * month / 12),
        "HOUR_SIN": np.sin(2 * np.pi * scheduled_hour / 24),
        "HOUR_COS": np.cos(2 * np.pi * scheduled_hour / 24),
        "IS_LONG_HAUL": int(distance >= 1500),
        "IS_HOLIDAY_MONTH": is_peak,
        "IS_PEAK_TRAVEL_MONTH": is_peak,
    }
    features = metadata.get("features", list(row.keys()))
    return pd.DataFrame([{feature: row.get(feature, np.nan) for feature in features}])


def prediction_probability(model, features: pd.DataFrame) -> float:
    if model is None:
        return np.nan
    return float(model.predict_proba(features)[:, 1][0])


def filtered_prediction_metrics(predictions: pd.DataFrame, threshold: float) -> tuple[pd.DataFrame, str]:
    if predictions.empty:
        return pd.DataFrame(), "Aucune ligne de test ne correspond exactement aux filtres."

    y_true = predictions["y_true"].astype(int)
    y_score = predictions["y_score"].astype(float)
    y_pred = (y_score >= threshold).astype(int)
    warning = ""
    roc_auc = np.nan
    if y_true.nunique() >= 2:
        roc_auc = roc_auc_score(y_true, y_score)
    else:
        warning = "Une seule classe est présente dans ce filtre : ROC-AUC non interprétable."

    metrics = pd.DataFrame(
        [
            {
                "nb_test": len(predictions),
                "taux_retard_réel": y_true.mean(),
                "taux_retard_prédit": y_pred.mean(),
                "score_moyen": y_score.mean(),
                "accuracy": accuracy_score(y_true, y_pred),
                "balanced_acc": balanced_accuracy_score(y_true, y_pred) if y_true.nunique() >= 2 else np.nan,
                "precision": precision_score(y_true, y_pred, zero_division=0),
                "recall": recall_score(y_true, y_pred, zero_division=0),
                "f1": f1_score(y_true, y_pred, zero_division=0),
                "roc_auc": roc_auc,
            }
        ]
    )
    if len(predictions) < 50:
        warning = (warning + " " if warning else "") + "Volume test faible : interpréter la mesure avec prudence."
    return metrics, warning


def vacation_comparison_chart(comparison: pd.DataFrame) -> go.Figure:
    fig = go.Figure(
        go.Bar(
            x=comparison["Scénario"],
            y=comparison["Probabilité retard"],
            marker_color=[GOOD, RISK],
            text=[f"{v:.1%}" for v in comparison["Probabilité retard"]],
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>%{y:.2%}<extra></extra>",
        )
    )
    fig.update_layout(title="Scénario hors vacances vs vacances", showlegend=False, **base_layout(360))
    fig.update_yaxes(tickformat=".0%", range=[0, max(0.45, comparison["Probabilité retard"].max() + 0.08)])
    return fig


def selected_kpi_table() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "KPI": "Vols analysés",
                "Pourquoi ce choix": "Contrôle le volume et la fiabilité des comparaisons. Un taux sans volume peut conduire à une mauvaise décision.",
                "Décision associée": "Valider si un segment est suffisamment représentatif avant action.",
            },
            {
                "KPI": "Taux de retard",
                "Pourquoi ce choix": "Mesure centrale de ponctualité, alignée sur le seuil métier de 15 minutes à l'arrivée.",
                "Décision associée": "Identifier périodes, compagnies, routes ou aéroports prioritaires.",
            },
            {
                "KPI": "Retard moyen arrivée",
                "Pourquoi ce choix": "Traduit l'impact client et l'ampleur réelle du problème quand un vol dévie de son horaire.",
                "Décision associée": "Prioriser la communication passagers et les plans de correspondance.",
            },
            {
                "KPI": "Retard médian arrivée",
                "Pourquoi ce choix": "Indicateur robuste aux retards extrêmes, utile pour comprendre l'expérience typique.",
                "Décision associée": "Distinguer problème structurel et incidents isolés.",
            },
            {
                "KPI": "Retard moyen départ",
                "Pourquoi ce choix": "Plus actionnable côté opérations, car il dépend de la rotation, des équipes sol et de l'embarquement.",
                "Décision associée": "Ajuster ressources, portes, marges de rotation et priorités au sol.",
            },
            {
                "KPI": "Recall du modèle retard",
                "Pourquoi ce choix": "Dans une logique d'alerte, manquer un vrai retard est souvent plus coûteux qu'une fausse alerte.",
                "Décision associée": "Choisir le seuil de déclenchement des alertes opérationnelles.",
            },
        ]
    )


def filters_table() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Filtre": "Page", "Rôle": "Sépare pilotage exécutif, diagnostic et plan d'action."},
            {"Filtre": "Mois", "Rôle": "Isole la saisonnalité et les périodes météo ou vacances à risque."},
            {"Filtre": "Jour de semaine", "Rôle": "Compare semaine, week-end et journées opérationnellement chargées."},
            {"Filtre": "Compagnie", "Rôle": "Compare la performance opérationnelle par transporteur."},
            {"Filtre": "Heure de départ", "Rôle": "Mesure l'effet cascade des rotations au fil de la journée."},
            {"Filtre": "Ville de départ", "Rôle": "Filtre les aéroports de départ par leur ville de rattachement."},
            {"Filtre": "Aéroport de départ", "Rôle": "Cible les hubs à traiter côté sol, porte, taxi-out ou rotation."},
            {"Filtre": "Ville d'arrivée", "Rôle": "Filtre les destinations par leur ville de rattachement."},
            {"Filtre": "Aéroport d'arrivée", "Rôle": "Analyse l'impact destination et correspondances."},
            {"Filtre": "Statut retardé uniquement", "Rôle": "Concentre l'analyse sur les incidents déjà avérés."},
            {"Filtre": "Volume minimum", "Rôle": "Évite de prendre des décisions sur des segments trop petits."},
            {"Filtre": "Recherche et tri table", "Rôle": "Permet d'auditer rapidement les lignes et segments spécifiques."},
        ]
    )


with st.spinner("Chargement des données..."):
    df = load_dashboard_data()
    model_df = read_csv_or_empty(MODEL_PATH)
    confusion_wide_df = read_csv_or_empty(CONFUSION_WIDE_PATH)
    scenario_model = load_joblib_model(SCENARIO_MODEL_PATH)
    scenario_metadata = read_json_or_empty(SCENARIO_METADATA_PATH)
    scenario_comparison_df = read_csv_or_empty(SCENARIO_COMPARISON_PATH)
    scenario_overall_df = read_csv_or_empty(SCENARIO_OVERALL_PATH)
    scenario_segment_df = read_csv_or_empty(SCENARIO_SEGMENT_PATH)
    scenario_metrics_df = read_csv_or_empty(SCENARIO_METRICS_PATH)
    scenario_month_metrics_df = read_csv_or_empty(SCENARIO_MONTH_METRICS_PATH)
    scenario_distribution_df = read_csv_or_empty(SCENARIO_DISTRIBUTION_PATH)
    scenario_predictions_df = read_csv_or_empty(SCENARIO_PREDICTIONS_PATH)
    manifest_df = read_csv_or_empty(CONSOLIDATED_DIR / "dashboard_sources_manifest.csv")
    consolidated_kpi_df = read_csv_or_empty(CONSOLIDATED_DIR / "dashboard_kpi_summary.csv")
    consolidated_monthly_df = read_csv_or_empty(CONSOLIDATED_DIR / "all_monthly_delay.csv")


st.sidebar.title("Navigation")
page = st.sidebar.radio(
    "Pages",
    ["Page 1 - Vue exécutive", "Page 2 - Analyse opérationnelle", "Page 3 - Recommandations"],
)

st.sidebar.divider()
st.sidebar.title("Filtres globaux")
months_sel = st.sidebar.multiselect(
    "Mois",
    list(MONTH_NAMES.keys()),
    default=list(MONTH_NAMES.keys()),
    format_func=lambda value: MONTH_NAMES[value],
)
dow_sel = st.sidebar.multiselect(
    "Jour de semaine",
    list(DOW_NAMES.keys()),
    default=list(DOW_NAMES.keys()),
    format_func=lambda value: DOW_NAMES[value],
)
airline_options = sorted(df["AIRLINE_NAME"].dropna().unique())
airline_sel = st.sidebar.multiselect("Compagnie", airline_options, default=airline_options)
hour_min, hour_max = st.sidebar.slider("Heure de départ programmée", 0, 23, (0, 23))

origin_city_options = sorted(df["ORIGIN_CITY"].dropna().astype(str).unique()) if "ORIGIN_CITY" in df.columns else []
origin_city_sel = st.sidebar.multiselect(
    "Ville de départ",
    origin_city_options,
    default=[],
    help="Filtre les aéroports de départ associés à la ville.",
)
origin_airport_source = df.copy()
if origin_city_sel and "ORIGIN_CITY" in origin_airport_source.columns:
    origin_airport_source = origin_airport_source[origin_airport_source["ORIGIN_CITY"].astype(str).isin(origin_city_sel)]
origin_sel = st.sidebar.multiselect(
    "Aéroport de départ",
    sorted(origin_airport_source["ORIGIN_AIRPORT"].dropna().astype(str).unique()),
    default=[],
    help="Vide = tous les aéroports.",
)

dest_city_options = sorted(df["DESTINATION_CITY"].dropna().astype(str).unique()) if "DESTINATION_CITY" in df.columns else []
dest_city_sel = st.sidebar.multiselect(
    "Ville d'arrivée",
    dest_city_options,
    default=[],
    help="Filtre les aéroports d'arrivée associés à la ville.",
)
dest_airport_source = df.copy()
if dest_city_sel and "DESTINATION_CITY" in dest_airport_source.columns:
    dest_airport_source = dest_airport_source[dest_airport_source["DESTINATION_CITY"].astype(str).isin(dest_city_sel)]
dest_sel = st.sidebar.multiselect(
    "Aéroport d'arrivée",
    sorted(dest_airport_source["DESTINATION_AIRPORT"].dropna().astype(str).unique()),
    default=[],
    help="Vide = toutes les destinations.",
)
only_delayed = st.sidebar.checkbox("Vols retardés uniquement", value=False)

mask = (
    df["MONTH"].isin(months_sel)
    & df["DAY_OF_WEEK"].isin(dow_sel)
    & df["AIRLINE_NAME"].isin(airline_sel)
    & df["SCHEDULED_DEP_HOUR"].between(hour_min, hour_max)
)
if origin_city_sel and "ORIGIN_CITY" in df.columns:
    mask &= df["ORIGIN_CITY"].astype(str).isin(origin_city_sel)
if origin_sel:
    mask &= df["ORIGIN_AIRPORT"].isin(origin_sel)
if dest_city_sel and "DESTINATION_CITY" in df.columns:
    mask &= df["DESTINATION_CITY"].astype(str).isin(dest_city_sel)
if dest_sel:
    mask &= df["DESTINATION_AIRPORT"].isin(dest_sel)
if only_delayed:
    mask &= df["IS_DELAYED"].eq(1)

dff = df.loc[mask].copy()
if dff.empty:
    st.warning("Aucune donnée ne correspond aux filtres sélectionnés.")
    st.stop()

total_flights = len(dff)
delay_rate = dff["IS_DELAYED"].mean()
mean_arrival_delay = dff["ARRIVAL_DELAY"].mean()
median_arrival_delay = dff["ARRIVAL_DELAY"].median()
mean_departure_delay = dff["DEPARTURE_DELAY"].mean()
late_flights = int(dff["IS_DELAYED"].sum())

monthly = rate_by(dff, ["MONTH"]).sort_values("MONTH")
monthly["month_label"] = monthly["MONTH"].map(MONTH_SHORT)
monthly_rank = monthly.copy()
monthly_rank["mois"] = monthly_rank["MONTH"].map(MONTH_NAMES)
monthly_rank = monthly_rank.sort_values(["taux_retard_pct", "nb_vols"], ascending=[False, False])
hourly = rate_by(dff, ["SCHEDULED_DEP_HOUR"]).sort_values("SCHEDULED_DEP_HOUR")
airline_perf = rate_by(dff, ["AIRLINE", "AIRLINE_NAME"], min_volume=300)
airport_perf = rate_by(dff, ["ORIGIN_AIRPORT"], min_volume=300)
routes = rate_by(dff, ["ORIGIN_AIRPORT", "DESTINATION_AIRPORT"], min_volume=100)
routes["route"] = routes["ORIGIN_AIRPORT"].astype(str) + " - " + routes["DESTINATION_AIRPORT"].astype(str)


st.markdown(
    """
    <div class="hero">
        <h1>Retards de vols US 2015</h1>
        <div class="subtitle">Dashboard RNCP40875 structuré en 3 pages : pilotage, diagnostic opérationnel et recommandations.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

metric_cols = st.columns(5)
with metric_cols[0]:
    metric_block("Vols analysés", fmt_int(total_flights), "volume de la sélection")
with metric_cols[1]:
    metric_block("Taux de retard", pct(delay_rate), "arrivée > 15 min")
with metric_cols[2]:
    metric_block("Vols retardés", fmt_int(late_flights), "incidents dans la sélection")
with metric_cols[3]:
    metric_block("Retard moyen arrivée", f"{mean_arrival_delay:+.1f} min", "impact client")
with metric_cols[4]:
    metric_block("Retard moyen départ", f"{mean_departure_delay:+.1f} min", "levier opérations")


if page == "Page 1 - Vue exécutive":
    st.subheader("Page 1 - Vue exécutive")
    note(
        "Objectif : donner en une page les signaux nécessaires à une direction opérations : niveau de ponctualité, "
        "périodes à risque, segments prioritaires et qualité du modèle prédictif."
    )

    target_delay_rate_pct = 15.0
    status_label = "maîtrisé" if delay_rate * 100 <= target_delay_rate_pct else "sous surveillance"
    st.markdown("### Synthèse immédiate")
    s1, s2, s3 = st.columns([0.9, 0.9, 1.2], gap="large")
    with s1:
        st.plotly_chart(
            gauge_chart(delay_rate * 100, target_delay_rate_pct, "Taux de retard"),
            width="stretch",
            config={"displayModeBar": False},
        )
        st.caption(
            f"Lecture : niveau {status_label}. Le seuil de vigilance interne est fixé à {target_delay_rate_pct:.0f} % de vols retardés."
        )
    with s2:
        st.plotly_chart(
            donut_chart(
                ["À l'heure", "Retardés"],
                [total_flights - late_flights, late_flights],
                "Répartition des vols",
            ),
            width="stretch",
            config={"displayModeBar": False},
        )
        st.caption("Objectif : voir immédiatement si le problème est marginal ou structurel dans la sélection.")
    with s3:
        if model_df.empty:
            st.info("Aucune métrique modèle disponible.")
        else:
            st.plotly_chart(
                grouped_model_metrics(model_df, "Modèles : lecture des métriques clés"),
                width="stretch",
                config={"displayModeBar": False},
            )
            st.caption("Le recall limite les retards manqués ; le F1 arbitre précision et couverture des alertes.")

    st.divider()
    c1, c2 = st.columns([1.15, 0.85], gap="large")
    with c1:
        fig = line_chart(
            monthly,
            "month_label",
            "taux_retard_pct",
            "Évolution mensuelle du taux de retard",
            "%",
        )
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    with c2:
        peak_month = monthly.loc[monthly["taux_retard_pct"].idxmax()]
        peak_hour = hourly.loc[hourly["taux_retard_pct"].idxmax()]
        top_airline = airline_perf.sort_values("taux_retard_pct", ascending=False).head(1)
        top_airline_name = top_airline["AIRLINE_NAME"].iloc[0] if not top_airline.empty else "n/a"
        top_airline_rate = top_airline["taux_retard_pct"].iloc[0] if not top_airline.empty else np.nan
        st.markdown("### Points d'attention")
        st.write(f"- Mois le plus exposé : **{MONTH_NAMES[int(peak_month['MONTH'])]}** ({peak_month['taux_retard_pct']:.1f} %).")
        st.write(f"- Heure la plus exposée : **{int(peak_hour['SCHEDULED_DEP_HOUR'])}h** ({peak_hour['taux_retard_pct']:.1f} %).")
        st.write(f"- Compagnie la plus exposée dans la sélection : **{top_airline_name}** ({top_airline_rate:.1f} %).")
        st.markdown(
            "<span class='tag'>C3.2 Datavisualisation</span><span class='tag'>C3.3 EDA</span><span class='tag'>Pilotage opérationnel</span>",
            unsafe_allow_html=True,
        )

    st.markdown("### Mois avec le plus de retards")
    m1, m2 = st.columns([1.05, 0.95], gap="large")
    with m1:
        top_months = monthly_rank.head(8).sort_values("taux_retard_pct")
        st.plotly_chart(
            horizontal_bar(top_months, "taux_retard_pct", "mois", "Mois les plus critiques", RISK, "%", 390),
            width="stretch",
            config={"displayModeBar": False},
        )
    with m2:
        st.dataframe(
            monthly_rank[
                ["mois", "nb_vols", "nb_retards", "taux_retard_pct", "retard_arrivee_moyen", "retard_depart_moyen"]
            ]
            .head(12)
            .round(2),
            width="stretch",
            hide_index=True,
        )

    st.divider()
    c3, c4 = st.columns(2, gap="large")
    with c3:
        top_airlines = airline_perf.sort_values("taux_retard_pct", ascending=False).head(10).sort_values("taux_retard_pct")
        st.plotly_chart(
            horizontal_bar(top_airlines, "taux_retard_pct", "AIRLINE_NAME", "Top compagnies à risque", ACCENT, "%"),
            width="stretch",
            config={"displayModeBar": False},
        )
    with c4:
        top_airports = airport_perf.sort_values("taux_retard_pct", ascending=False).head(10).sort_values("taux_retard_pct")
        st.plotly_chart(
            horizontal_bar(top_airports, "taux_retard_pct", "ORIGIN_AIRPORT", "Top aéroports de départ à risque", RISK, "%"),
            width="stretch",
            config={"displayModeBar": False},
        )

    c5, c6 = st.columns(2, gap="large")
    with c5:
        impact_airlines = airline_perf.sort_values("nb_retards", ascending=False).head(10).sort_values("nb_retards")
        st.plotly_chart(
            horizontal_bar(
                impact_airlines,
                "nb_retards",
                "AIRLINE_NAME",
                "Compagnies qui génèrent le plus de retards",
                WARN,
                "",
            ),
            width="stretch",
            config={"displayModeBar": False},
        )
    with c6:
        impact_routes = routes.sort_values("nb_retards", ascending=False).head(10).sort_values("nb_retards")
        st.plotly_chart(
            horizontal_bar(
                impact_routes,
                "nb_retards",
                "route",
                "Routes qui génèrent le plus de retards",
                INK,
                "",
            ),
            width="stretch",
            config={"displayModeBar": False},
        )

    st.markdown("### KPIs choisis et justification")
    st.dataframe(selected_kpi_table(), width="stretch", hide_index=True)

    if not model_df.empty:
        best = model_df.sort_values(["f1", "roc_auc"], ascending=False).iloc[0]
        st.markdown("### Synthèse modèle prédictif")
        note(
            "Deux contextes sont distingués : le modèle pré-vol n'utilise pas le retard au départ, "
            "le modèle operational_live l'utilise et devient donc nettement plus précis mais seulement après observation du départ."
        )
        if "contexte" in model_df.columns:
            st.dataframe(
                model_df[
                    [
                        "contexte",
                        "modèle",
                        "threshold",
                        "accuracy",
                        "balanced_acc",
                        "precision",
                        "recall",
                        "f1",
                        "roc_auc",
                    ]
                ].round(4),
                width="stretch",
                hide_index=True,
            )
        m1, m2, m3, m4, m5 = st.columns(5)
        with m1:
            metric_block("Contexte recommandé", str(best.get("contexte", "n/a")), "meilleur F1")
        with m2:
            metric_block("Modèle", str(best["modèle"]), "artefact sauvegardé")
        with m3:
            metric_block("ROC-AUC", f"{best['roc_auc']:.3f}", "discrimination")
        with m4:
            metric_block("Recall retard", f"{best['recall']:.3f}", "retards détectés")
        with m5:
            metric_block("F1", f"{best['f1']:.3f}", "équilibre precision/recall")


elif page == "Page 2 - Analyse opérationnelle":
    st.subheader("Page 2 - Analyse opérationnelle")
    note(
        "Objectif : identifier où intervenir concrètement : heure, jour, compagnie, aéroport, route et lignes détaillées. "
        "Les seuils de volume évitent les conclusions fragiles."
    )

    min_volume = st.slider("Volume minimum des segments", 50, 5000, 500, step=50)
    op_tabs = st.tabs(["Temporalité", "Compagnies et aéroports", "Routes", "Données"])

    with op_tabs[0]:
        c1, c2 = st.columns(2, gap="large")
        with c1:
            st.plotly_chart(
                line_chart(hourly, "SCHEDULED_DEP_HOUR", "taux_retard_pct", "Taux de retard par heure", "%"),
                width="stretch",
                config={"displayModeBar": False},
            )
        with c2:
            volume_by_hour = hourly.copy()
            fig = go.Figure(
                go.Bar(
                    x=volume_by_hour["SCHEDULED_DEP_HOUR"],
                    y=volume_by_hour["nb_vols"],
                    marker_color=INK,
                    hovertemplate="%{x}h<br>%{y:,} vols<extra></extra>",
                )
            )
            fig.update_layout(title="Volume de vols par heure", showlegend=False, **base_layout())
            fig.update_xaxes(dtick=2, ticksuffix="h")
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

        heatmap_data = (
            dff.groupby(["DAY_OF_WEEK", "MONTH"])["IS_DELAYED"]
            .mean()
            .mul(100)
            .reset_index()
            .pivot(index="DAY_OF_WEEK", columns="MONTH", values="IS_DELAYED")
        )
        fig = go.Figure(
            go.Heatmap(
                z=heatmap_data.values,
                x=[MONTH_SHORT[int(c)] for c in heatmap_data.columns],
                y=[DOW_SHORT[int(r)] for r in heatmap_data.index],
                colorscale="Reds",
                text=[[f"{v:.0f}%" for v in row] for row in heatmap_data.values],
                texttemplate="%{text}",
                hovertemplate="%{y} - %{x}<br>%{z:.1f}%<extra></extra>",
            )
        )
        fig.update_layout(title="Carte de chaleur : mois x jour de semaine", showlegend=False, **base_layout(430))
        fig.update_yaxes(showgrid=False)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

        st.markdown("#### Données exposées sur les mois les plus en retard")
        selected_month_detail = st.selectbox(
            "Mois à analyser",
            monthly_rank["MONTH"].tolist(),
            format_func=lambda value: f"{MONTH_NAMES[int(value)]} - {monthly_rank.loc[monthly_rank['MONTH'].eq(value), 'taux_retard_pct'].iloc[0]:.1f} % de retards",
            key="month_detail_select",
        )
        month_df = dff[dff["MONTH"].eq(selected_month_detail)].copy()
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            metric_block("Vols du mois", fmt_int(len(month_df)), MONTH_NAMES[int(selected_month_detail)])
        with m2:
            metric_block("Taux de retard", pct(month_df["IS_DELAYED"].mean()), "sélection filtrée")
        with m3:
            metric_block("Retard moyen arrivée", f"{month_df['ARRIVAL_DELAY'].mean():+.1f} min", "impact client")
        with m4:
            metric_block("Retard moyen départ", f"{month_df['DEPARTURE_DELAY'].mean():+.1f} min", "levier opérationnel")

        detail_tabs = st.tabs(["Compagnies du mois", "Départs du mois", "Arrivées du mois"])
        with detail_tabs[0]:
            month_airlines = rate_by(month_df, ["AIRLINE", "AIRLINE_NAME"], min_volume=50)
            st.dataframe(
                month_airlines.sort_values(["taux_retard_pct", "nb_vols"], ascending=[False, False]).head(30).round(2),
                width="stretch",
                hide_index=True,
            )
        with detail_tabs[1]:
            departure_groups = ["ORIGIN_CITY", "ORIGIN_AIRPORT"] if "ORIGIN_CITY" in month_df.columns else ["ORIGIN_AIRPORT"]
            month_departures = rate_by(month_df, departure_groups, min_volume=50)
            st.dataframe(
                month_departures.sort_values(["taux_retard_pct", "nb_vols"], ascending=[False, False]).head(30).round(2),
                width="stretch",
                hide_index=True,
            )
        with detail_tabs[2]:
            arrival_groups = ["DESTINATION_CITY", "DESTINATION_AIRPORT"] if "DESTINATION_CITY" in month_df.columns else ["DESTINATION_AIRPORT"]
            month_arrivals = rate_by(month_df, arrival_groups, min_volume=50)
            st.dataframe(
                month_arrivals.sort_values(["taux_retard_pct", "nb_vols"], ascending=[False, False]).head(30).round(2),
                width="stretch",
                hide_index=True,
            )

    with op_tabs[1]:
        airline_filtered = rate_by(dff, ["AIRLINE", "AIRLINE_NAME"], min_volume=min_volume)
        airport_filtered = rate_by(dff, ["ORIGIN_AIRPORT"], min_volume=min_volume)
        c1, c2 = st.columns(2, gap="large")
        with c1:
            st.markdown("#### Compagnies")
            st.dataframe(
                airline_filtered.sort_values(["taux_retard_pct", "nb_vols"], ascending=[False, False]).head(25).round(3),
                width="stretch",
                hide_index=True,
            )
        with c2:
            st.markdown("#### Aéroports de départ")
            st.dataframe(
                airport_filtered.sort_values(["taux_retard_pct", "nb_vols"], ascending=[False, False]).head(25).round(3),
                width="stretch",
                hide_index=True,
            )

        scatter = airline_filtered.copy()
        fig = go.Figure(
            go.Scatter(
                x=scatter["nb_vols"],
                y=scatter["taux_retard_pct"],
                mode="markers+text",
                text=scatter["AIRLINE"],
                textposition="top center",
                marker={
                    "size": np.clip(scatter["retard_arrivee_moyen"].abs() + 8, 8, 32),
                    "color": scatter["taux_retard_pct"],
                    "colorscale": "Reds",
                    "showscale": True,
                },
                hovertemplate="<b>%{text}</b><br>%{x:,} vols<br>%{y:.1f}% retards<extra></extra>",
            )
        )
        fig.update_layout(
            title="Compagnies : volume vs taux de retard",
            xaxis_title="Nombre de vols",
            yaxis_title="Taux de retard (%)",
            showlegend=False,
            **base_layout(470),
        )
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    with op_tabs[2]:
        route_filtered = rate_by(dff, ["ORIGIN_AIRPORT", "DESTINATION_AIRPORT"], min_volume=min_volume)
        route_filtered["route"] = route_filtered["ORIGIN_AIRPORT"].astype(str) + " - " + route_filtered["DESTINATION_AIRPORT"].astype(str)
        c1, c2 = st.columns(2, gap="large")
        with c1:
            top_volume = route_filtered.sort_values("nb_vols", ascending=False).head(15).sort_values("nb_vols")
            st.plotly_chart(
                horizontal_bar(top_volume, "nb_vols", "route", "Routes les plus fréquentes", INK, "", 560),
                width="stretch",
                config={"displayModeBar": False},
            )
        with c2:
            top_risk = route_filtered.sort_values("taux_retard_pct", ascending=False).head(15).sort_values("taux_retard_pct")
            st.plotly_chart(
                horizontal_bar(top_risk, "taux_retard_pct", "route", "Routes les plus risquées", RISK, "%", 560),
                width="stretch",
                config={"displayModeBar": False},
            )
        st.dataframe(
            route_filtered.sort_values(["taux_retard_pct", "nb_vols"], ascending=[False, False]).head(100).round(3),
            width="stretch",
            hide_index=True,
        )

    with op_tabs[3]:
        st.markdown("#### Table de contrôle")
        search = st.text_input("Recherche texte", placeholder="Compagnie, ville, aéroport...")
        sort_col = st.selectbox(
            "Trier par",
            [c for c in dff.columns if c != "IATA_CODE"],
            index=[c for c in dff.columns if c != "IATA_CODE"].index("ARRIVAL_DELAY"),
        )
        sort_ascending = st.toggle("Tri croissant", value=False)
        visible_cols = st.multiselect(
            "Colonnes affichées",
            dff.columns.tolist(),
            default=[
                c
                for c in [
                    "MONTH",
                    "DAY",
                    "AIRLINE_NAME",
                    "ORIGIN_AIRPORT",
                    "ORIGIN_CITY",
                    "DESTINATION_AIRPORT",
                    "DESTINATION_CITY",
                    "SCHEDULED_DEP_HOUR",
                    "DEP_PERIOD",
                    "DEPARTURE_DELAY",
                    "ARRIVAL_DELAY",
                    "IS_DELAYED",
                ]
                if c in dff.columns
            ],
        )
        table = dff.copy()
        if search.strip():
            text_cols = table.select_dtypes(include=["object", "string"]).columns.tolist()
            mask_text = table[text_cols].astype("string").fillna("").agg(" ".join, axis=1).str.lower()
            table = table[mask_text.str.contains(search.strip().lower(), regex=False)]
        table = table.sort_values(sort_col, ascending=sort_ascending, na_position="last")
        st.dataframe(table[visible_cols].head(1500), width="stretch", height=520, hide_index=True)
        st.download_button(
            "Télécharger la sélection filtrée",
            data=table[visible_cols].to_csv(index=False).encode("utf-8"),
            file_name="selection_operationnelle.csv",
            mime="text/csv",
        )


else:
    st.subheader("Page 3 - Recommandations")
    note(
        "Objectif : transformer les analyses en décisions concrètes. Cette page sert de support métier : "
        "simuler un départ, qualifier le risque, puis appliquer le bon playbook opérationnel."
    )

    st.markdown("### Simulateur de départ")
    note(
        "Le simulateur estime le risque à partir de l'historique observé. Il ne remplace pas une prédiction temps réel, "
        "mais il permet d'imaginer un départ selon un mois, une destination et une compagnie pour préparer une décision."
    )

    sim_source = df

    airline_lookup = (
        sim_source[["AIRLINE", "AIRLINE_NAME"]]
        .drop_duplicates("AIRLINE")
        .sort_values("AIRLINE_NAME")
        .copy()
    )
    airline_labels = dict(zip(airline_lookup["AIRLINE"], airline_lookup["AIRLINE_NAME"]))

    origin_cols = [
        col
        for col in ["ORIGIN_AIRPORT", "ORIGIN_CITY", "ORIGIN_AIRPORT_NAME", "ORIGIN_STATE"]
        if col in sim_source.columns
    ]
    dest_cols = [
        col
        for col in ["DESTINATION_AIRPORT", "DESTINATION_CITY", "DESTINATION_AIRPORT_NAME", "DESTINATION_STATE"]
        if col in sim_source.columns
    ]
    origin_lookup = sim_source[origin_cols].drop_duplicates("ORIGIN_AIRPORT").copy()
    dest_lookup = sim_source[dest_cols].drop_duplicates("DESTINATION_AIRPORT").copy()

    def airport_label(row: pd.Series, prefix: str) -> str:
        code_col = f"{prefix}_AIRPORT"
        parts = [str(row[code_col])]
        for col in [f"{prefix}_CITY", f"{prefix}_STATE", f"{prefix}_AIRPORT_NAME"]:
            if col in row.index and pd.notna(row[col]) and str(row[col]).lower() not in {"unknown", "nan"}:
                parts.append(str(row[col]))
        return " - ".join(parts)

    origin_lookup["label"] = origin_lookup.apply(lambda row: airport_label(row, "ORIGIN"), axis=1)
    dest_lookup["label"] = dest_lookup.apply(lambda row: airport_label(row, "DESTINATION"), axis=1)
    origin_lookup = origin_lookup.sort_values("label")
    dest_lookup = dest_lookup.sort_values("label")
    origin_labels = dict(zip(origin_lookup["ORIGIN_AIRPORT"], origin_lookup["label"]))
    destination_labels = dict(zip(dest_lookup["DESTINATION_AIRPORT"], dest_lookup["label"]))

    sim_c1, sim_c2, sim_c3, sim_c4 = st.columns(4, gap="large")
    with sim_c1:
        selected_sim_month = st.selectbox(
            "Mois du départ",
            list(MONTH_NAMES.keys()),
            index=5,
            format_func=lambda value: MONTH_NAMES[value],
        )
    with sim_c2:
        selected_sim_airline = st.selectbox(
            "Compagnie",
            airline_lookup["AIRLINE"].tolist(),
            format_func=lambda value: f"{value} - {airline_labels.get(value, value)}",
        )
    with sim_c3:
        selected_sim_origin = st.selectbox(
            "Aéroport de départ",
            origin_lookup["ORIGIN_AIRPORT"].tolist(),
            format_func=lambda value: origin_labels.get(value, str(value)),
        )
    with sim_c4:
        selected_sim_destination = st.selectbox(
            "Aéroport d'arrivée",
            dest_lookup["DESTINATION_AIRPORT"].tolist(),
            format_func=lambda value: destination_labels.get(value, str(value)),
        )

    sim_o1, sim_o2, sim_o3 = st.columns(3, gap="large")
    with sim_o1:
        selected_sim_hour = st.selectbox(
            "Heure de départ",
            ["Toutes"] + list(range(24)),
            format_func=lambda value: "Toutes heures" if value == "Toutes" else f"{int(value):02d}h",
        )
    with sim_o2:
        selected_sim_weekend = st.selectbox(
            "Type de jour",
            ["Indifférent", "Semaine", "Week-end"],
        )
    with sim_o3:
        min_sim_volume = st.slider("Volume minimum fiable", 30, 1000, 100, step=10)

    month_mask = sim_source["MONTH"].eq(selected_sim_month)
    airline_mask = sim_source["AIRLINE"].eq(selected_sim_airline)
    origin_mask = sim_source["ORIGIN_AIRPORT"].eq(selected_sim_origin)
    destination_mask = sim_source["DESTINATION_AIRPORT"].eq(selected_sim_destination)
    route_mask = origin_mask & destination_mask
    optional_mask = pd.Series(True, index=sim_source.index)
    optional_label_parts = []
    if selected_sim_hour != "Toutes":
        optional_mask &= sim_source["SCHEDULED_DEP_HOUR"].eq(int(selected_sim_hour))
        optional_label_parts.append(f"{int(selected_sim_hour):02d}h")
    if selected_sim_weekend != "Indifférent":
        weekend_value = 1 if selected_sim_weekend == "Week-end" else 0
        optional_mask &= sim_source["IS_WEEKEND"].eq(weekend_value)
        optional_label_parts.append(selected_sim_weekend)

    scenario_masks = []
    if optional_label_parts:
        scenario_masks.append(
            (
                "Scénario complet",
                month_mask & airline_mask & route_mask & optional_mask,
            )
        )
    scenario_masks.extend(
        [
            ("Mois + compagnie + route", month_mask & airline_mask & route_mask),
            ("Compagnie + route", airline_mask & route_mask),
            ("Mois + route", month_mask & route_mask),
            ("Route départ-arrivée", route_mask),
            ("Compagnie + départ", airline_mask & origin_mask),
            ("Compagnie + arrivée", airline_mask & destination_mask),
            ("Mois + compagnie", month_mask & airline_mask),
            ("Départ", origin_mask),
            ("Arrivée", destination_mask),
            ("Compagnie", airline_mask),
            ("Mois", month_mask),
            ("Global historique", pd.Series(True, index=sim_source.index)),
        ]
    )
    scenario_df = pd.DataFrame(
        [segment_summary(sim_source, mask, label) for label, mask in scenario_masks]
    )
    available_scenarios = scenario_df[scenario_df["nb_vols"].gt(0)].copy()
    reliable_scenarios = available_scenarios[available_scenarios["nb_vols"].ge(min_sim_volume)]
    selected_scenario = (
        reliable_scenarios.iloc[0]
        if not reliable_scenarios.empty
        else available_scenarios.iloc[0]
    )
    risk_level, risk_color, risk_message = risk_status(selected_scenario["taux_retard_pct"])

    sim_m1, sim_m2, sim_m3, sim_m4 = st.columns(4)
    with sim_m1:
        metric_block("Risque estimé", f"{selected_scenario['taux_retard_pct']:.1f} %", selected_scenario["Référence"])
    with sim_m2:
        metric_block("Niveau", risk_level, risk_message)
    with sim_m3:
        metric_block("Historique utilisé", fmt_int(selected_scenario["nb_vols"]), f"fiabilité {selected_scenario['fiabilité'].lower()}")
    with sim_m4:
        metric_block("Retard moyen attendu", f"{selected_scenario['retard_arrivee_moyen']:+.1f} min", "arrivée")

    st.markdown(
        f"""
        <div class="note" style="border-left-color:{risk_color}">
            <strong>Lecture métier :</strong> pour {MONTH_NAMES[int(selected_sim_month)]}, avec
            {airline_labels.get(selected_sim_airline, selected_sim_airline)} de
            {origin_labels.get(selected_sim_origin, selected_sim_origin)} vers
            {destination_labels.get(selected_sim_destination, selected_sim_destination)},
            le segment retenu est <strong>{selected_scenario['Référence']}</strong>.
            {risk_message}
        </div>
        """,
        unsafe_allow_html=True,
    )

    sc1, sc2 = st.columns([1.05, 0.95], gap="large")
    with sc1:
        st.plotly_chart(
            scenario_comparison_chart(scenario_df, selected_scenario["Référence"]),
            width="stretch",
            config={"displayModeBar": False},
        )
    with sc2:
        st.markdown("#### Actions recommandées pour ce départ")
        st.dataframe(operational_playbook(risk_level), width="stretch", hide_index=True)
        st.markdown("#### Références statistiques")
        st.dataframe(
            scenario_df.round(
                {
                    "taux_retard_pct": 2,
                    "retard_arrivee_moyen": 2,
                    "retard_depart_moyen": 2,
                }
            ),
            width="stretch",
            hide_index=True,
        )

    st.markdown("### Prédiction modèle fine-tunée")
    if scenario_model is None or not scenario_metadata:
        st.warning("Modèle segment_finetuned introuvable. Relancer `python scripts/train_segment_finetuned_model.py`.")
    else:
        scenario_threshold = float(scenario_metadata.get("threshold", 0.5))
        feature_row = scenario_feature_row(
            sim_source,
            int(selected_sim_month),
            str(selected_sim_airline),
            str(selected_sim_origin),
            str(selected_sim_destination),
            selected_sim_hour,
            selected_sim_weekend,
            scenario_metadata,
        )
        model_probability = prediction_probability(scenario_model, feature_row)
        model_pred = int(model_probability >= scenario_threshold)
        model_message = (
            "Score supérieur au seuil : déclencher le playbook d'alerte."
            if model_pred
            else "Score inférieur au seuil : garder le vol en surveillance standard."
        )

        p1, p2, p3, p4 = st.columns(4)
        with p1:
            metric_block("Score modèle", f"{model_probability:.1%}", "retard > 15 min")
        with p2:
            metric_block("Seuil d'alerte", f"{scenario_threshold:.2f}", "optimisé sur validation")
        with p3:
            metric_block("Décision modèle", "Alerte" if model_pred else "Pas d'alerte", scenario_metadata.get("model_name", "modèle"))
        with p4:
            metric_block("Lecture", "Action" if model_pred else "Surveillance", model_message)

        st.markdown("#### Playbook déclenché par la prédiction")
        st.dataframe(
            operational_playbook("Élevé" if model_pred else risk_level),
            width="stretch",
            hide_index=True,
        )

        no_incident_month = sorted(scenario_metadata.get("normal_months", sorted(NORMAL_TRAVEL_MONTHS)))[1]
        incident_month = sorted(scenario_metadata.get("holiday_months", sorted(PEAK_TRAVEL_MONTHS)))[1]
        no_incident_row = scenario_feature_row(
            sim_source,
            no_incident_month,
            str(selected_sim_airline),
            str(selected_sim_origin),
            str(selected_sim_destination),
            selected_sim_hour,
            selected_sim_weekend,
            scenario_metadata,
        )
        incident_row = scenario_feature_row(
            sim_source,
            incident_month,
            str(selected_sim_airline),
            str(selected_sim_origin),
            str(selected_sim_destination),
            selected_sim_hour,
            selected_sim_weekend,
            scenario_metadata,
        )
        scenario_compare = pd.DataFrame(
            [
                {
                    "Scénario": f"Hors vacances - {MONTH_NAMES[no_incident_month]}",
                    "Probabilité retard": prediction_probability(scenario_model, no_incident_row),
                },
                {
                    "Scénario": f"Vacances / forte demande - {MONTH_NAMES[incident_month]}",
                    "Probabilité retard": prediction_probability(scenario_model, incident_row),
                },
            ]
        )
        pc1, pc2 = st.columns([1.0, 1.0], gap="large")
        with pc1:
            st.plotly_chart(
                vacation_comparison_chart(scenario_compare),
                width="stretch",
                config={"displayModeBar": False},
            )
        with pc2:
            st.markdown("#### Hypothèses de prédiction")
            hypothesis_cols = [
                col
                for col in [
                    "MONTH",
                    "AIRLINE",
                    "ORIGIN_AIRPORT",
                    "DESTINATION_AIRPORT",
                    "SCHEDULED_DEP_HOUR",
                    "IS_WEEKEND",
                    "SCENARIO",
                    "TRAVEL_SCENARIO",
                    "IS_HOLIDAY_MONTH",
                    "DISTANCE",
                    "SCHEDULED_TIME",
                ]
                if col in feature_row.columns
            ]
            st.dataframe(
                feature_row[hypothesis_cols].round(2),
                width="stretch",
                hide_index=True,
            )

        st.markdown("### Mesure du modèle par filtres métier")
        if scenario_overall_df.empty:
            st.info("Aucune métrique holdout du modèle fine-tuné disponible.")
        else:
            overall = scenario_overall_df.iloc[0]
            fm1, fm2, fm3, fm4, fm5 = st.columns(5)
            with fm1:
                metric_block("ROC-AUC test", f"{overall['roc_auc']:.3f}", "discrimination")
            with fm2:
                metric_block("Recall test", f"{overall['recall']:.3f}", "retards détectés")
            with fm3:
                metric_block("Precision test", f"{overall['precision']:.3f}", "alertes justes")
            with fm4:
                metric_block("F1 test", f"{overall['f1']:.3f}", "compromis")
            with fm5:
                metric_block("Test holdout", fmt_int(overall["test_size"]), "jamais vu à l'entraînement")

        mt1, mt2 = st.columns([0.9, 1.1], gap="large")
        with mt1:
            if not scenario_metrics_df.empty:
                scenario_chart = scenario_metrics_df.copy()
                scenario_chart["scénario"] = scenario_chart["SCENARIO"].replace(
                    {
                        "normal_sans_vacances": "Sans vacances",
                        "incident_vacances": "Vacances / incident",
                        "intermediaire": "Intermédiaire",
                    }
                )
                fig = go.Figure()
                for metric, color in [("recall", RISK), ("precision", WARN), ("f1", ACCENT)]:
                    fig.add_trace(
                        go.Bar(
                            x=scenario_chart["scénario"],
                            y=scenario_chart[metric],
                            name=metric,
                            marker_color=color,
                            text=[f"{v:.2f}" for v in scenario_chart[metric]],
                            textposition="outside",
                        )
                    )
                fig.update_layout(title="Performance test par scénario", barmode="group", **base_layout(390))
                fig.update_yaxes(range=[0, 1], tickformat=".0%")
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
                st.dataframe(scenario_metrics_df.round(4), width="stretch", hide_index=True)
        with mt2:
            if not scenario_segment_df.empty:
                filter_options = scenario_segment_df["filter_type"].dropna().unique().tolist()
                default_index = filter_options.index("MONTH_AIRLINE_ORIGIN_DESTINATION") if "MONTH_AIRLINE_ORIGIN_DESTINATION" in filter_options else 0
                selected_metric_filter = st.selectbox(
                    "Mesure par filtre",
                    filter_options,
                    index=default_index,
                    key="segment_metric_filter",
                )
                metric_table = scenario_segment_df[scenario_segment_df["filter_type"].eq(selected_metric_filter)].copy()
                metric_table = metric_table.sort_values(["nb_vols_test", "f1"], ascending=[False, False])
                st.dataframe(metric_table.head(150).round(4), width="stretch", hide_index=True)
                st.caption(
                    "Ces métriques sont calculées sur le test holdout. Les segments à faible volume doivent rester interprétés avec prudence."
                )

        if not scenario_comparison_df.empty:
            st.markdown("### Fine-tuning réalisé")
            st.dataframe(scenario_comparison_df.round(4), width="stretch", hide_index=True)
        if not scenario_month_metrics_df.empty:
            st.markdown("### Détail scénarios par mois")
            st.dataframe(scenario_month_metrics_df.round(4), width="stretch", hide_index=True)
        if not scenario_distribution_df.empty:
            st.markdown("### Répartition d'apprentissage par scénario")
            st.dataframe(scenario_distribution_df.head(80).round(4), width="stretch", hide_index=True)

    recommendations = pd.DataFrame(
        [
            {
                "Priorité": "1",
                "Recommandation": "Activer une watchlist opérationnelle sur les segments à risque élevé.",
                "Déclencheur métier": "Taux de retard simulé ou observé >= 20 % avec volume fiable.",
                "Action métier": "Contrôler appareil, équipage, météo, porte et ressources sol dès H-3.",
                "Signal utilisé": "Simulateur, taux par mois, compagnie, destination, heure et heatmap.",
                "Impact attendu": "Moins de retards subis et meilleure anticipation des arbitrages terrain.",
                "Impact": 5,
                "Effort": 3,
                "Horizon": "0-30 jours",
                "Responsable": "Centre opérations",
                "KPI de suivi": "Taux de retard, retards détectés avant H-2, retard moyen départ",
            },
            {
                "Priorité": "2",
                "Recommandation": "Protéger les passagers en correspondance sur destinations sensibles.",
                "Déclencheur métier": "Destination ou route avec risque élevé et retard moyen arrivée positif.",
                "Action métier": "Identifier correspondances courtes, préparer réacheminement et rapprocher les portes si possible.",
                "Signal utilisé": "Risque destination, retard arrivée moyen, volume retardé.",
                "Impact attendu": "Réduction des correspondances manquées et meilleure expérience passager.",
                "Impact": 5,
                "Effort": 2,
                "Horizon": "0-30 jours",
                "Responsable": "Hub control / Expérience client",
                "KPI de suivi": "Correspondances protégées, passagers réacheminés, NPS incident",
            },
            {
                "Priorité": "3",
                "Recommandation": "Adapter la promesse client selon le niveau de risque du départ.",
                "Déclencheur métier": "Scénario simulé critique ou modèle au-dessus du seuil d'alerte.",
                "Action métier": "Envoyer une notification graduée : surveillance, retard probable, options alternatives.",
                "Signal utilisé": "Risque simulé, recall modèle, faux négatifs, seuil opérationnel.",
                "Impact attendu": "Information plus tôt, moins de stress passager et meilleure gestion des flux.",
                "Impact": 5,
                "Effort": 4,
                "Horizon": "30-60 jours",
                "Responsable": "Digital client",
                "KPI de suivi": "Recall, faux négatifs, taux de notification",
            },
            {
                "Priorité": "4",
                "Recommandation": "Revoir les buffers de rotation sur compagnies et créneaux récurrents.",
                "Déclencheur métier": "Retards croissants en fin de journée ou compagnie avec volume de retards élevé.",
                "Action métier": "Ajouter marge de rotation, revoir affectation porte et séquence d'embarquement.",
                "Signal utilisé": "Taux par heure, retard départ moyen, compagnies générant le plus de retards.",
                "Impact attendu": "Réduction de l'effet cascade sur les vols suivants.",
                "Impact": 4,
                "Effort": 4,
                "Horizon": "60-90 jours",
                "Responsable": "Planning réseau",
                "KPI de suivi": "Taux de retard par heure, retard moyen arrivée",
            },
            {
                "Priorité": "5",
                "Recommandation": "Gouverner le modèle comme un outil d'aide à la décision, pas comme une décision automatique.",
                "Déclencheur métier": "Dérive KPI, baisse du recall ou augmentation des faux négatifs.",
                "Action métier": "Revue mensuelle, seuils validés par les opérations, audit des erreurs et retraining contrôlé.",
                "Signal utilisé": "KPI exécutifs, matrices de confusion, dérive données et métriques modèle.",
                "Impact attendu": "Système d'alerte fiable, explicable et aligné avec la gouvernance IA.",
                "Impact": 4,
                "Effort": 2,
                "Horizon": "Continu",
                "Responsable": "Data / IA governance",
                "KPI de suivi": "ROC-AUC, F1, dérive données",
            },
        ]
    )
    recommendations["Score"] = recommendations["Impact"] * (6 - recommendations["Effort"])

    action_plan = pd.DataFrame(
        [
            {
                "Horizon": "0-30 jours",
                "Début": 0,
                "Durée": 30,
                "Chantier": "Cadrage opérationnel et KPI",
                "Livrable": "Cibles de ponctualité, seuils, owners et rituel de pilotage",
                "KPI": "Taux de retard, volumes, retard moyen",
            },
            {
                "Horizon": "0-30 jours",
                "Début": 0,
                "Durée": 30,
                "Chantier": "Priorisation hubs et routes",
                "Livrable": "Liste des segments à fort volume et fort risque",
                "KPI": "Retards évités sur segments prioritaires",
            },
            {
                "Horizon": "30-60 jours",
                "Début": 30,
                "Durée": 30,
                "Chantier": "Pilote modèle d'alerte",
                "Livrable": "Test contrôlé du modèle preflight puis operational_live",
                "KPI": "Recall, F1, faux négatifs",
            },
            {
                "Horizon": "60-90 jours",
                "Début": 60,
                "Durée": 30,
                "Chantier": "Industrialisation SI",
                "Livrable": "API d'inférence, monitoring et reprise manuelle",
                "KPI": "Disponibilité, latence, dérive modèle",
            },
            {
                "Horizon": "Continu",
                "Début": 90,
                "Durée": 30,
                "Chantier": "Gouvernance et amélioration",
                "Livrable": "Revue mensuelle performance, biais, énergie et retraining",
                "KPI": "Stabilité métriques, CO2, auditabilité",
            },
        ]
    )

    r1, r2 = st.columns([1.05, 0.95], gap="large")
    with r1:
        st.plotly_chart(
            recommendation_matrix(recommendations),
            width="stretch",
            config={"displayModeBar": False},
        )
    with r2:
        st.plotly_chart(
            timeline_chart(action_plan),
            width="stretch",
            config={"displayModeBar": False},
        )

    st.markdown("### Recommandations priorisées")
    st.dataframe(
        recommendations[
            [
                "Priorité",
                "Recommandation",
                "Déclencheur métier",
                "Action métier",
                "Signal utilisé",
                "Impact attendu",
                "Horizon",
                "Responsable",
                "KPI de suivi",
                "Impact",
                "Effort",
                "Score",
            ]
        ],
        width="stretch",
        hide_index=True,
    )

    st.markdown("### Plan d'action 30 / 60 / 90 jours")
    st.dataframe(
        action_plan[["Horizon", "Chantier", "Livrable", "KPI"]],
        width="stretch",
        hide_index=True,
    )

    st.markdown("### Filtres ajoutés et rôle métier")
    st.dataframe(filters_table(), width="stretch", hide_index=True)

    st.markdown("### Décisions que le dashboard permet de prendre")
    decisions = pd.DataFrame(
        [
            {
                "Décision": "Planifier plus d'équipes au sol",
                "Condition observée": "Pic de retard sur mois, jour ou heure avec volume important",
                "Page": "Page 1 et Page 2",
                "Urgence": 5,
                "Impact": 5,
            },
            {
                "Décision": "Prioriser un hub ou une route pour audit",
                "Condition observée": "Taux de retard élevé + volume minimum respecté",
                "Page": "Page 2",
                "Urgence": 4,
                "Impact": 5,
            },
            {
                "Décision": "Déclencher des notifications passagers",
                "Condition observée": "Segments ou modèle indiquant un risque de retard supérieur au seuil retenu",
                "Page": "Page 3",
                "Urgence": 4,
                "Impact": 4,
            },
            {
                "Décision": "Ajuster les buffers horaires",
                "Condition observée": "Retards croissants en fin de journée ou sur routes critiques",
                "Page": "Page 2 et Page 3",
                "Urgence": 3,
                "Impact": 4,
            },
            {
                "Décision": "Choisir le modèle d'alerte",
                "Condition observée": "Meilleur compromis ROC-AUC, recall, F1 et faux négatifs",
                "Page": "Page 1 et Page 3",
                "Urgence": 5,
                "Impact": 4,
            },
        ]
    )
    d1, d2 = st.columns([0.9, 1.1], gap="large")
    with d1:
        fig = go.Figure(
            go.Bar(
                x=decisions["Impact"],
                y=decisions["Décision"],
                orientation="h",
                marker_color=ACCENT,
                text=[f"Impact {v}/5" for v in decisions["Impact"]],
                textposition="outside",
                hovertemplate="<b>%{y}</b><br>Impact %{x}/5<extra></extra>",
            )
        )
        fig.update_layout(title="Décisions à plus fort impact", showlegend=False, **base_layout(380))
        fig.update_xaxes(range=[0, 5.6], dtick=1)
        fig.update_yaxes(showgrid=False)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    with d2:
        st.dataframe(decisions, width="stretch", hide_index=True)

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("### Comparaison modèles")
        if model_df.empty:
            st.info("Aucun fichier de comparaison modèle trouvé.")
        else:
            st.caption(
                "preflight = prédiction avant départ sans fuite de données ; "
                "operational_live = prédiction après observation du retard départ, plus précise mais utilisable plus tard."
            )
            st.plotly_chart(
                grouped_model_metrics(model_df, "Arbitrage modèle : précision, recall et F1"),
                width="stretch",
                config={"displayModeBar": False},
            )
            st.dataframe(model_df.round(4), width="stretch", hide_index=True)
    with c2:
        st.markdown("### Matrice synthétique")
        if confusion_wide_df.empty:
            st.info("Aucune matrice de confusion trouvée.")
        else:
            st.dataframe(confusion_wide_df.round(4), width="stretch", hide_index=True)

    if not confusion_wide_df.empty:
        st.markdown("### Matrices de confusion visuelles")
        matrix_cols = st.columns(min(2, len(confusion_wide_df)), gap="large")
        for idx, (_, row) in enumerate(confusion_wide_df.head(2).iterrows()):
            with matrix_cols[idx]:
                st.plotly_chart(
                    confusion_heatmap(row, f"{row['contexte']} - {row['modèle']}"),
                    width="stretch",
                    config={"displayModeBar": False},
                )

    if not consolidated_kpi_df.empty or not consolidated_monthly_df.empty:
        st.markdown("### Dashboards consolidés des notebooks")
        note(
            "Cette section reprend les exports disponibles dans les différents dossiers du projet pour vérifier la cohérence "
            "des KPI et rendre visibles les tableaux de bord produits pendant l'analyse."
        )
        cc1, cc2 = st.columns([0.9, 1.1], gap="large")
        with cc1:
            if consolidated_kpi_df.empty:
                st.info("Aucun résumé KPI consolidé trouvé.")
            else:
                source_kpi = consolidated_kpi_df.copy()
                source_kpi["taux_retard_pct"] = source_kpi["taux_retard_moyen"] * 100
                fig = go.Figure(
                    go.Bar(
                        x=source_kpi["source_notebook"],
                        y=source_kpi["taux_retard_pct"],
                        marker_color=ACCENT,
                        text=[f"{v:.1f} %" for v in source_kpi["taux_retard_pct"]],
                        textposition="outside",
                        customdata=np.stack([source_kpi["nb_vols"], source_kpi["retard_arrivee_moyen"]], axis=-1),
                        hovertemplate=(
                            "<b>%{x}</b><br>%{y:.2f} % de retards"
                            "<br>%{customdata[0]:,} vols"
                            "<br>Retard arrivée moyen : %{customdata[1]:.2f} min<extra></extra>"
                        ),
                    )
                )
                fig.update_layout(title="Cohérence du taux de retard par source", showlegend=False, **base_layout(380))
                fig.update_yaxes(ticksuffix=" %")
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
                st.dataframe(source_kpi.round(3), width="stretch", hide_index=True)
        with cc2:
            if consolidated_monthly_df.empty:
                st.info("Aucun agrégat mensuel consolidé trouvé.")
            else:
                cons_month = consolidated_monthly_df.copy()
                if "taux_retard_pct" not in cons_month.columns:
                    cons_month["taux_retard_pct"] = cons_month["taux_retard"] * 100
                cons_month["taux_retard_pct"] = cons_month["taux_retard_pct"].fillna(cons_month["taux_retard"] * 100)
                cons_month["month_label"] = cons_month["MONTH"].map(MONTH_SHORT)
                fig = go.Figure()
                for source, subset in cons_month.sort_values("MONTH").groupby("source_notebook"):
                    fig.add_trace(
                        go.Scatter(
                            x=subset["month_label"],
                            y=subset["taux_retard_pct"],
                            mode="lines+markers",
                            name=source,
                            hovertemplate="<b>%{fullData.name}</b><br>%{x}<br>%{y:.2f} %<extra></extra>",
                        )
                    )
                fig.update_layout(
                    title="Tendance mensuelle comparée entre notebooks",
                    legend={"orientation": "h", "y": -0.18},
                    **base_layout(470),
                )
                fig.update_yaxes(ticksuffix=" %")
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    if not manifest_df.empty:
        st.markdown("### Sources consolidées")
        st.dataframe(manifest_df, width="stretch", hide_index=True)


st.caption("Projet RNCP40875 - Dashboard de pilotage des retards de vols.")
