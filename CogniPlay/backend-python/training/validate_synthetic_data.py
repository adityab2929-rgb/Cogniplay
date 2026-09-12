"""Validate the synthetic fixture files against CogniPlay's live contracts."""

import csv
import json
import math
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from features.extract_features import FEATURE_NAMES, SEQUENCE_FEATURES, SEQUENCE_LENGTH, build_sequence, extract_features

DATA_DIR = Path(__file__).resolve().parent / "synthetic_data"


def read_csv(name: str) -> List[Dict[str, str]]:
    with (DATA_DIR / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    raw = [json.loads(line) for line in (DATA_DIR / "raw_sessions.jsonl").read_text(encoding="utf-8").splitlines() if line]
    labels = read_csv("labels.csv")
    cnn_rows = read_csv("cnn_training.csv")
    lstm_rows = read_csv("lstm_training.csv")
    require(len(raw) == len(labels) == len(cnn_rows) == 240, "Expected 240 sessions")
    require(len(lstm_rows) == 240 * SEQUENCE_LENGTH, "Unexpected LSTM row count")
    require(list(cnn_rows[0].keys()) == ["session_id", "synthetic_profile", "dyslexia_label"] + FEATURE_NAMES, "CNN header/order mismatch")
    require(list(lstm_rows[0].keys()) == ["session_id", "synthetic_profile", "adhd_label", "timestep", "interval_score", "correct_norm", "wrong_norm", "score_change"], "LSTM header/order mismatch")
    raw_by_id = {item["session_id"]: item for item in raw}
    require(len(raw_by_id) == len(raw), "Duplicate raw session IDs")
    require({row["session_id"] for row in labels} == set(raw_by_id), "Label/raw ID mismatch")
    require({row["session_id"] for row in cnn_rows} == set(raw_by_id), "CNN/raw ID mismatch")
    cnn_input_rows = set()
    for row in cnn_rows:
        values = [float(row[name]) for name in FEATURE_NAMES]
        require(all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in values), "Invalid CNN value")
        key = tuple(round(value, 8) for value in values)
        require(key not in cnn_input_rows, "Duplicate CNN input row")
        cnn_input_rows.add(key)
        features, _ = extract_features(raw_by_id[row["session_id"]])
        require(np.allclose(features, np.asarray(values), atol=1e-7), "CNN feature mismatch")
    grouped: Dict[str, List[Dict[str, str]]] = {}
    for row in lstm_rows:
        grouped.setdefault(row["session_id"], []).append(row)
        for name in ("interval_score", "correct_norm", "wrong_norm", "score_change"):
            value = float(row[name])
            require(math.isfinite(value) and 0.0 <= value <= 1.0, "Invalid LSTM value")
    require(set(grouped) == set(raw_by_id), "LSTM/raw ID mismatch")
    sequence_keys = set()
    for session_id, rows in grouped.items():
        rows.sort(key=lambda item: int(item["timestep"]))
        require([int(item["timestep"]) for item in rows] == list(range(SEQUENCE_LENGTH)), "Bad LSTM timesteps")
        sequence = np.asarray([[float(row[name]) for name in ("interval_score", "correct_norm", "wrong_norm", "score_change")] for row in rows])
        require(sequence.shape == (SEQUENCE_LENGTH, SEQUENCE_FEATURES), "Bad LSTM shape")
        require(np.allclose(sequence, build_sequence(raw_by_id[session_id]), atol=1e-7), "LSTM sequence mismatch")
        key = tuple(np.round(sequence.reshape(-1), 8))
        require(key not in sequence_keys, "Duplicate LSTM sequence")
        sequence_keys.add(key)
    print("PASS: 240 complete, unique sessions; 20-feature CNN rows and 6x4 LSTM sequences match live extraction.")


if __name__ == "__main__":
    main()
