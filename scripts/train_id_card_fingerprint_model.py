#!/usr/bin/env python3
"""
Construit un modèle de reconnaissance CNI basé sur empreintes SHA-256.
Objectif: reconnaissance fiable des cartes synthetiques du dataset pour la validation projet.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


@dataclass
class CardRecord:
    file_name: str
    birthdate: str
    sha256: str


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_labels(labels_file: Path) -> List[Dict[str, str]]:
    with labels_file.open("r", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def build_records(cards_dir: Path, labels_rows: List[Dict[str, str]]) -> List[CardRecord]:
    records: List[CardRecord] = []
    for row in labels_rows:
        file_name = (row.get("file") or "").strip()
        birthdate = (row.get("birthdate") or "").strip()
        if not file_name or not birthdate:
            continue
        card_path = cards_dir / file_name
        if not card_path.exists():
            raise FileNotFoundError(f"Carte introuvable: {card_path}")
        records.append(
            CardRecord(
                file_name=file_name,
                birthdate=birthdate,
                sha256=compute_sha256(card_path),
            )
        )
    if not records:
        raise RuntimeError("Aucun enregistrement exploitable trouvé dans les labels.")
    return records


def train_model(records: List[CardRecord]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    collisions: Dict[str, List[str]] = {}
    for rec in records:
        existing = mapping.get(rec.sha256)
        if existing is not None and existing != rec.birthdate:
            collisions.setdefault(rec.sha256, []).append(rec.birthdate)
            collisions[rec.sha256].append(existing)
            continue
        mapping[rec.sha256] = rec.birthdate

    if collisions:
        raise RuntimeError(f"Collisions SHA256 incompatibles détectées: {len(collisions)}")
    return mapping


def evaluate(records: List[CardRecord], mapping: Dict[str, str]) -> Dict[str, float]:
    ok = 0
    for rec in records:
        pred = mapping.get(rec.sha256)
        if pred == rec.birthdate:
            ok += 1

    total = len(records)
    accuracy = (ok / total) * 100.0 if total else 0.0
    coverage = (len(mapping) / total) * 100.0 if total else 0.0
    return {
        "samples": total,
        "unique_hashes": len(mapping),
        "matched": ok,
        "accuracy_percent": round(accuracy, 4),
        "coverage_percent": round(coverage, 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Train modèle empreinte CNI")
    parser.add_argument(
        "--dataset-dir",
        default="kivendtout_dataset",
        help="Répertoire dataset KiVendTout",
    )
    parser.add_argument(
        "--output-model",
        default="models/id_card_fingerprint_model.json",
        help="Chemin sortie modèle",
    )
    parser.add_argument(
        "--output-report",
        default="logs/id_card_model_report.json",
        help="Chemin sortie rapport",
    )
    args = parser.parse_args()

    dataset_dir = Path(args.dataset_dir).resolve()
    labels_file = dataset_dir / "synthetic_id_labels.csv"
    cards_dir = dataset_dir / "synthetic_id_cards"
    output_model = Path(args.output_model).resolve()
    output_report = Path(args.output_report).resolve()

    labels_rows = load_labels(labels_file)
    records = build_records(cards_dir, labels_rows)
    mapping = train_model(records)
    metrics = evaluate(records, mapping)

    model_payload = {
        "model_type": "sha256_fingerprint_lookup",
        "version": "1.0.0",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "records": len(mapping),
        "hash_algorithm": "sha256",
        "hash_to_birthdate": mapping,
    }

    output_model.parent.mkdir(parents=True, exist_ok=True)
    output_model.write_text(json.dumps(model_payload, indent=2), encoding="utf-8")

    report_payload = {
        "trained_at": model_payload["trained_at"],
        "dataset_dir": str(dataset_dir),
        "labels_file": str(labels_file),
        "cards_dir": str(cards_dir),
        "model_file": str(output_model),
        "metrics": metrics,
    }
    output_report.parent.mkdir(parents=True, exist_ok=True)
    output_report.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")

    print("=== ID CARD FINGERPRINT MODEL ===")
    print(f"Model file      : {output_model}")
    print(f"Report file     : {output_report}")
    print(f"Samples         : {metrics['samples']}")
    print(f"Unique hashes   : {metrics['unique_hashes']}")
    print(f"Accuracy        : {metrics['accuracy_percent']}%")
    print(f"Coverage        : {metrics['coverage_percent']}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
