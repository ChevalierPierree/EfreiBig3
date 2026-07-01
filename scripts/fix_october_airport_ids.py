"""Corrige la particularité du jeu 2015 : en octobre, ORIGIN_AIRPORT et
DESTINATION_AIRPORT contiennent des identifiants numériques (codes DOT, ex. 10135)
au lieu des codes IATA (ex. SEA). Ce script reconstruit la correspondance
identifiant -> IATA (logique fournie par Jean) et l'applique aux fichiers de
sortie utilisés par le dashboard, pour que les aéroports soient lisibles.

Usage : python scripts/fix_october_airport_ids.py
Idempotent : relançable sans risque (n'agit que sur les valeurs numériques).
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
REF_DIR = BASE_DIR / "flights_delay"

# Fichiers de sortie susceptibles de contenir des identifiants d'aéroport.
TARGET_FILES = [
    BASE_DIR / "outputs" / "flights_dashboard.csv",
    BASE_DIR / "outputs" / "aggregates" / "airport_origin.csv",
    BASE_DIR / "outputs" / "consolidated_dashboards" / "all_airport_delay.csv",
    BASE_DIR / "outputs" / "consolidated_dashboards" / "all_destination_delay.csv",
    BASE_DIR / "outputs" / "consolidated_dashboards" / "all_flights_dashboard_samples.csv",
    BASE_DIR / "outputs" / "model_artifacts" / "segment_finetuned_test_predictions.csv",
    BASE_DIR / "outputs" / "model_artifacts" / "segment_finetuned_filter_metrics.csv",
    BASE_DIR / "outputs" / "model_artifacts" / "scenario_model_test_predictions.csv",
    BASE_DIR / "outputs" / "model_artifacts" / "scenario_model_segment_metrics.csv",
]
AIRPORT_COLUMNS = ["ORIGIN_AIRPORT", "DESTINATION_AIRPORT", "AIRPORT"]


def normalize_airport_text(value, remove_common_words=False):
    if pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value).replace("\xa0", " "))
    text = text.encode("ascii", "ignore").decode("ascii").lower().replace("&", "and")
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    if remove_common_words:
        text = re.sub(
            r"\b(airport|international|regional|municipal|field|metropolitan)\b",
            " ", text,
        )
    return re.sub(r"\s+", " ", text).strip()


def collect_numeric_ids(files):
    ids = set()
    for path in files:
        if not path.exists():
            continue
        df = pd.read_csv(path, low_memory=False)
        for col in AIRPORT_COLUMNS:
            if col in df.columns:
                s = df[col].astype("string").dropna()
                ids |= set(s[s.str.fullmatch(r"\d+")])
    return ids


def build_mapping(numeric_ids):
    airport_ids_path = REF_DIR / "L_AIRPORT_ID.csv"
    airports_path = REF_DIR / "airports.csv"
    if not airport_ids_path.exists() or not airports_path.exists():
        raise FileNotFoundError(
            f"Référentiels requis : {airport_ids_path} et {airports_path}"
        )

    airport_ids = pd.read_csv(airport_ids_path, dtype={"Code": "string"}).rename(
        columns={"Code": "AIRPORT_ID", "Description": "DESCRIPTION"}
    )
    description_parts = airport_ids["DESCRIPTION"].str.extract(
        r"^(?P<ID_CITY>.*), (?P<ID_STATE>[A-Z]{2}): (?P<ID_NAME>.*)$"
    )
    airport_ids = pd.concat([airport_ids, description_parts], axis=1)
    airports_reference = pd.read_csv(airports_path, dtype={"IATA_CODE": "string"})

    airport_ids["NAME_KEY"] = airport_ids["ID_NAME"].map(
        lambda value: normalize_airport_text(value, remove_common_words=True)
    )
    airport_ids["CITY_KEY"] = airport_ids["ID_CITY"].map(normalize_airport_text)
    airports_reference["NAME_KEY"] = airports_reference["AIRPORT"].map(
        lambda value: normalize_airport_text(value, remove_common_words=True)
    )
    airports_reference["CITY_KEY"] = airports_reference["CITY"].map(normalize_airport_text)

    target_ids = pd.Index(sorted(numeric_ids))
    reference = airport_ids.loc[airport_ids["AIRPORT_ID"].isin(target_ids)].copy()

    # 1) Correspondance exacte sur l'État et le nom normalisé.
    exact = reference.merge(
        airports_reference[["IATA_CODE", "STATE", "NAME_KEY"]],
        left_on=["ID_STATE", "NAME_KEY"],
        right_on=["STATE", "NAME_KEY"],
        how="left",
    )
    mapping = dict(
        exact.loc[exact["IATA_CODE"].notna(), ["AIRPORT_ID", "IATA_CODE"]]
        .drop_duplicates("AIRPORT_ID")
        .itertuples(index=False, name=None)
    )

    # 2) Correspondance par ville/État lorsqu'elle ne désigne qu'un aéroport.
    remaining = reference.loc[~reference["AIRPORT_ID"].isin(mapping)]
    for row in remaining.itertuples():
        candidates = airports_reference.loc[
            airports_reference["STATE"].eq(row.ID_STATE)
            & airports_reference["CITY_KEY"].map(
                lambda city: (
                    city == row.CITY_KEY
                    or city in row.CITY_KEY
                    or row.CITY_KEY in city
                )
            )
        ]
        if len(candidates) == 1:
            mapping[row.AIRPORT_ID] = candidates.iloc[0]["IATA_CODE"]

    # 3) Cas particuliers validés manuellement.
    mapping.update({
        "11193": "CVG", "11278": "DCA", "12016": "GUM",
        "12264": "IAD", "12266": "IAH", "14222": "PPG",
    })

    missing = sorted(set(target_ids) - set(mapping))
    if missing:
        raise AssertionError(f"Identifiants non retrouvés : {missing}")
    return mapping


def apply_mapping(files, mapping):
    total_cells = 0
    for path in files:
        if not path.exists():
            continue
        df = pd.read_csv(path, low_memory=False)
        changed = 0
        for col in AIRPORT_COLUMNS:
            if col not in df.columns:
                continue
            s = df[col].astype("string")
            numeric = s.str.fullmatch(r"\d+").fillna(False)
            if not numeric.any():
                continue
            df.loc[numeric, col] = s[numeric].map(mapping).to_numpy()
            changed += int(numeric.sum())
        if changed:
            df.to_csv(path, index=False)
            total_cells += changed
            print(f"  {path.relative_to(BASE_DIR)} : {changed} valeurs corrigées")
    return total_cells


def main():
    numeric_ids = collect_numeric_ids(TARGET_FILES)
    print(f"{len(numeric_ids)} identifiants numériques détectés dans les sorties.")
    if not numeric_ids:
        print("Rien à corriger — déjà en codes IATA.")
        return
    mapping = build_mapping(numeric_ids)
    print(f"{len(mapping)} correspondances identifiant -> IATA construites.")
    print("Application aux fichiers :")
    total = apply_mapping(TARGET_FILES, mapping)
    print(f"Terminé : {total} valeurs converties en codes IATA.")

    # Vérification finale.
    remaining = collect_numeric_ids(TARGET_FILES)
    if remaining:
        print(f"ATTENTION : identifiants numériques restants : {sorted(remaining)[:10]}")
        sys.exit(1)
    print("Vérifié : plus aucun identifiant numérique dans les sorties.")


if __name__ == "__main__":
    main()
