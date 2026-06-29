"""Consolidate dashboard outputs from the project folders."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = ROOT.parents[1]
CHAARGERRR = ROOT.parents[0]
OUTPUT_DIR = ROOT / "outputs"
CONSOLIDATED_DIR = OUTPUT_DIR / "consolidated_dashboards"
SAMPLE_ROWS_PER_SOURCE = 25_000
RANDOM_STATE = 42

SOURCES = [
    {
        "source": "DATA S",
        "folder": CHAARGERRR / "DATA S",
        "description": "Notebook initial complété avec exports dashboard complets.",
    },
    {
        "source": "DATA S 2",
        "folder": DOWNLOADS / "DATA S 2",
        "description": "Notebook exécuté hors dossier mère, conservé comme référence de comparaison.",
    },
    {
        "source": "DATA S 3",
        "folder": ROOT,
        "description": "Version finale enrichie avec Streamlit, rapport et livrable Pilé.",
    },
]

TABLES = {
    "monthly_delay": ["monthly_delay.csv", "outputs/aggregates/monthly.csv"],
    "airline_delay": ["airline_delay.csv", "outputs/aggregates/airline.csv"],
    "airport_delay": ["airport_delay.csv", "outputs/aggregates/airport_origin.csv"],
    "destination_delay": ["destination_delay.csv"],
    "flights_dashboard": ["flights_dashboard.csv", "outputs/flights_dashboard.csv"],
}


def find_table(folder: Path, candidates: list[str]) -> Path | None:
    for rel in candidates:
        path = folder / rel
        if path.exists():
            return path
    return None


def count_lines(path: Path) -> int:
    with path.open("rb") as handle:
        return sum(1 for _ in handle)


def normalize_table(df: pd.DataFrame, source: str, table_name: str) -> pd.DataFrame:
    out = df.copy()
    out.insert(0, "source_notebook", source)
    out.insert(1, "dashboard_table", table_name)
    return out


def standardize_kpis(df: pd.DataFrame, source: str) -> dict:
    row: dict = {"source_notebook": source}

    n_col = next((c for c in ["nb_vols", "n_vols", "n"] if c in df.columns), None)
    rate_col = next((c for c in ["taux_retard", "taux", "delay_rate"] if c in df.columns), None)
    arr_col = next((c for c in ["retard_moyen_arrivee", "retard_moy_arrivee", "ARRIVAL_DELAY"] if c in df.columns), None)
    dep_col = next((c for c in ["retard_moyen_depart", "retard_moy_depart", "DEPARTURE_DELAY"] if c in df.columns), None)

    if n_col and rate_col:
        total = df[n_col].sum()
        row["nb_vols"] = total
        row["taux_retard_moyen"] = (df[n_col] * df[rate_col]).sum() / total if total else None
    elif "IS_DELAYED" in df.columns:
        row["nb_vols"] = len(df)
        row["taux_retard_moyen"] = df["IS_DELAYED"].mean()

    if n_col and arr_col:
        total = df[n_col].sum()
        row["retard_arrivee_moyen"] = (df[n_col] * df[arr_col]).sum() / total if total else None
    elif arr_col:
        row["retard_arrivee_moyen"] = df[arr_col].mean()

    if n_col and dep_col:
        total = df[n_col].sum()
        row["retard_depart_moyen"] = (df[n_col] * df[dep_col]).sum() / total if total else None
    elif dep_col:
        row["retard_depart_moyen"] = df[dep_col].mean()

    return row


def sample_large_dashboard(path: Path, rows: int) -> pd.DataFrame:
    """Read a representative bounded sample without loading multi-GB CSVs at once."""
    if rows <= SAMPLE_ROWS_PER_SOURCE:
        return pd.read_csv(path)

    frac = min(1.0, SAMPLE_ROWS_PER_SOURCE / rows * 1.4)
    pieces = []
    for chunk in pd.read_csv(path, chunksize=200_000):
        take = max(1, int(len(chunk) * frac))
        pieces.append(chunk.sample(n=min(take, len(chunk)), random_state=RANDOM_STATE))

    sample = pd.concat(pieces, ignore_index=True, sort=False)
    if len(sample) > SAMPLE_ROWS_PER_SOURCE:
        sample = sample.sample(n=SAMPLE_ROWS_PER_SOURCE, random_state=RANDOM_STATE)
    return sample


def main() -> None:
    CONSOLIDATED_DIR.mkdir(parents=True, exist_ok=True)

    manifest_rows = []
    aggregate_frames: dict[str, list[pd.DataFrame]] = {
        "monthly_delay": [],
        "airline_delay": [],
        "airport_delay": [],
        "destination_delay": [],
    }
    flight_samples = []
    kpi_rows = []

    for source_def in SOURCES:
        source = source_def["source"]
        folder = source_def["folder"]
        for table_name, candidates in TABLES.items():
            path = find_table(folder, candidates)
            if path is None:
                manifest_rows.append(
                    {
                        "source_notebook": source,
                        "dashboard_table": table_name,
                        "path": "",
                        "exists": False,
                        "rows": 0,
                        "size_mb": 0,
                        "description": source_def["description"],
                    }
                )
                continue

            rows = max(count_lines(path) - 1, 0)
            manifest_rows.append(
                {
                    "source_notebook": source,
                    "dashboard_table": table_name,
                    "path": str(path),
                    "exists": True,
                    "rows": rows,
                    "size_mb": path.stat().st_size / (1024**2),
                    "description": source_def["description"],
                }
            )

            if table_name == "flights_dashboard":
                sample = sample_large_dashboard(path, rows)
                flight_samples.append(normalize_table(sample, source, table_name))
                kpi_rows.append(standardize_kpis(sample, source))
            else:
                df = pd.read_csv(path)
                aggregate_frames[table_name].append(normalize_table(df, source, table_name))
                if table_name == "monthly_delay":
                    kpi_rows.append(standardize_kpis(df, source))

    manifest = pd.DataFrame(manifest_rows)
    manifest.to_csv(CONSOLIDATED_DIR / "dashboard_sources_manifest.csv", index=False)

    for table_name, frames in aggregate_frames.items():
        if frames:
            pd.concat(frames, ignore_index=True, sort=False).to_csv(
                CONSOLIDATED_DIR / f"all_{table_name}.csv",
                index=False,
            )

    if flight_samples:
        pd.concat(flight_samples, ignore_index=True, sort=False).to_csv(
            CONSOLIDATED_DIR / "all_flights_dashboard_samples.csv",
            index=False,
        )

    if kpi_rows:
        pd.DataFrame(kpi_rows).drop_duplicates(subset=["source_notebook"], keep="first").to_csv(
            CONSOLIDATED_DIR / "dashboard_kpi_summary.csv",
            index=False,
        )


if __name__ == "__main__":
    main()
