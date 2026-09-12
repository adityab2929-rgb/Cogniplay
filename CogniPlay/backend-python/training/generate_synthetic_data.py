"""Generate deterministic, non-clinical fixtures for CogniPlay pipeline tests.

The generator makes complete raw-session payloads, then derives training CSVs
through the production `extract_features` and `build_sequence` functions.
It intentionally creates *synthetic* labels only for development/testing.
"""

import csv
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

# Permit `python training/generate_synthetic_data.py` from any working folder.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from features.extract_features import (
    FEATURE_NAMES, SEQUENCE_FEATURES, SEQUENCE_LENGTH, build_sequence,
    extract_features,
)

SEED = 20260912
# Eight equally represented profiles x 1,250 = 10,000 complete sessions.
SAMPLES_PER_PROFILE = 1250
OUTPUT_DIR = Path(__file__).resolve().parent / "synthetic_data"
PROFILES: List[Tuple[str, int, int, int]] = [
    ("typical", 0, 0, 0),
    ("dyslexia_pattern", 1, 0, 0),
    ("dyscalculia_pattern", 0, 1, 0),
    ("adhd_pattern", 0, 0, 1),
    ("dyslexia_dyscalculia_pattern", 1, 1, 0),
    ("dyslexia_adhd_pattern", 1, 0, 1),
    ("dyscalculia_adhd_pattern", 0, 1, 1),
    ("combined_pattern", 1, 1, 1),
]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def jitter(rng: random.Random, centre: float, spread: float,
           low: float, high: float) -> float:
    return clamp(rng.gauss(centre, spread), low, high)


def count_pair(rng: random.Random, total: int, rate: float) -> int:
    return min(total, max(0, int(round(total * rate + rng.uniform(-0.45, 0.45)))))


def make_letter_game(rng: random.Random, dyslexia: int) -> Dict[str, Any]:
    total = rng.randint(52, 88)
    if dyslexia:
        accuracy = jitter(rng, 0.61, 0.09, 0.35, 0.79)
        bd_rate = jitter(rng, 0.18, 0.045, 0.10, 0.32)
        pq_rate = jitter(rng, 0.12, 0.04, 0.06, 0.25)
        hesitation = jitter(rng, 1650, 380, 700, 2900)
        response = jitter(rng, 3200, 650, 1000, 5800)
    else:
        accuracy = jitter(rng, 0.93, 0.035, 0.82, 0.99)
        bd_rate = jitter(rng, 0.008, 0.007, 0.0, 0.028)
        pq_rate = jitter(rng, 0.006, 0.006, 0.0, 0.025)
        hesitation = jitter(rng, 420, 170, 50, 900)
        response = jitter(rng, 1450, 350, 600, 2600)
    correct = int(round(total * accuracy))
    wrong = total - correct
    bd = min(wrong, count_pair(rng, total, bd_rate))
    pq = min(max(0, wrong - bd), count_pair(rng, total, pq_rate))
    errors = []
    for i in range(bd):
        shown = "b" if i % 2 == 0 else "d"
        errors.append({"shown": shown, "clicked": "d" if shown == "b" else "b", "time_ms": round(response)})
    for i in range(pq):
        shown = "p" if i % 2 == 0 else "q"
        errors.append({"shown": shown, "clicked": "q" if shown == "p" else "p", "time_ms": round(response)})
    return {
        "total_clicks": total, "correct_clicks": correct, "wrong_clicks": wrong,
        "accuracy": round(correct / total, 6), "avg_response_time_ms": round(response, 3),
        "letter_errors": errors, "bd_confusion_count": bd,
        "pq_confusion_count": pq, "hesitation_avg_ms": round(hesitation, 3),
    }


def make_number_game(rng: random.Random, dyscalculia: int) -> Dict[str, Any]:
    total = 20
    if dyscalculia:
        small = jitter(rng, 0.76, 0.10, 0.45, 0.92)
        large = jitter(rng, 0.34, 0.12, 0.10, 0.58)
        response = jitter(rng, 3250, 650, 1200, 5800)
        error_size = jitter(rng, 3.6, 1.0, 1.5, 7.5)
    else:
        small = jitter(rng, 0.95, 0.035, 0.82, 1.0)
        large = jitter(rng, 0.89, 0.055, 0.70, 0.98)
        response = jitter(rng, 1500, 340, 600, 2600)
        error_size = jitter(rng, 1.1, 0.35, 1.0, 2.0)
    accuracy = (small + large) / 2.0
    correct = int(round(total * accuracy))
    wrong = total - correct
    errors = []
    for i in range(wrong):
        shown = rng.randint(1, 10)
        offset = max(1, int(round(error_size + rng.uniform(-0.5, 0.5))))
        answered = clamp(shown + (offset if i % 2 else -offset), 1, 10)
        if answered == shown:
            answered = 1 if shown > 1 else 2
        errors.append({"shown": shown, "answered": int(answered)})
    return {
        "total_rounds": total, "correct_answers": correct, "wrong_answers": wrong,
        "accuracy": round(correct / total, 6), "avg_response_time_ms": round(response, 3),
        "number_errors": errors, "subitizing_accuracy_1_5": round(small, 6),
        "subitizing_accuracy_6_10": round(large, 6),
    }


def make_butterfly_game(rng: random.Random, adhd: int) -> Dict[str, Any]:
    intervals: List[Dict[str, Any]] = []
    for index in range(SEQUENCE_LENGTH):
        if adhd:
            score = jitter(rng, 0.86 - 0.085 * index, 0.075, 0.28, 0.94)
            catches = rng.randint(15, 40)
        else:
            score = jitter(rng, 0.91 - 0.004 * index, 0.025, 0.80, 0.96)
            catches = rng.randint(18, 35)
        # Each fixture records at least one wrong-target catch. It preserves a
        # plausible high-accuracy typical pattern while avoiding identical
        # all-perfect six-step LSTM sequences across a large synthetic set.
        correct = min(catches - 1, int(round(catches * score)))
        intervals.append({"interval": index, "correct": correct,
                          "wrong": catches - correct,
                          "score": round(correct / catches, 6)})
    total = sum(item["correct"] + item["wrong"] for item in intervals)
    correct = sum(item["correct"] for item in intervals)
    wrong = total - correct
    scores = [item["score"] for item in intervals]
    drop = sum(scores[:3]) / 3.0 - sum(scores[3:]) / 3.0
    response = jitter(rng, 2550 if adhd else 1450, 550 if adhd else 280, 600, 5600)
    return {
        "total_catches": total, "correct_catches": correct, "wrong_catches": wrong,
        "accuracy": round(correct / total, 6), "impulsivity_score": round(wrong / total, 6),
        "attention_by_interval": intervals, "performance_drop": round(max(0.0, drop), 6),
        "avg_response_time_ms": round(response, 3),
    }


def make_shape_game(rng: random.Random, dyslexia: int, adhd: int) -> Dict[str, Any]:
    difficulty = dyslexia or adhd
    accuracy = jitter(rng, 0.69 if difficulty else 0.88, 0.08 if difficulty else 0.04, 0.45, 0.97)
    tremor = jitter(rng, 0.30 if difficulty else 0.12, 0.08 if difficulty else 0.04, 0.02, 0.55)
    speed = jitter(rng, 160 if difficulty else 220, 35, 70, 330)
    return {
        "shapes_completed": 3, "circle_accuracy": round(accuracy, 6),
        "square_accuracy": round(clamp(accuracy + rng.uniform(-0.06, 0.06), 0, 1), 6),
        "triangle_accuracy": round(clamp(accuracy + rng.uniform(-0.06, 0.06), 0, 1), 6),
        "overall_accuracy": round(accuracy, 6), "avg_tremor_score": round(tremor, 6),
        "avg_drawing_speed": round(speed, 3), "shapes": [],
    }


def make_payload(rng: random.Random, session_id: str, profile: str,
                 dyslexia: int, dyscalculia: int, adhd: int) -> Dict[str, Any]:
    gaze_efficiency = jitter(rng, 0.68 if adhd else 0.93, 0.10 if adhd else 0.03, 0.40, 0.99)
    fixations = rng.randint(110, 180)
    off_screen = int(round((1.0 - gaze_efficiency) * fixations))
    return {
        "session_id": session_id, "synthetic_profile": profile,
        "child_id": "synthetic-child-" + session_id, "child_name": "Synthetic",
        "child_age": rng.choice([4, 5]), "session_date": "2026-09-12T00:00:00Z",
        "total_duration_ms": 600000, "letter_land": make_letter_game(rng, dyslexia),
        "number_ninja": make_number_game(rng, dyscalculia),
        "butterfly_game": make_butterfly_game(rng, adhd),
        "shape_tracer": make_shape_game(rng, dyslexia, adhd),
        "eye_tracking": {"available": True, "total_fixations": fixations,
                         "avg_fixation_duration_ms": 450,
                         "off_screen_count": off_screen,
                         "gaze_efficiency": round(gaze_efficiency, 6)},
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    rng = random.Random(SEED)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    number = 1
    for profile, dyslexia, dyscalculia, adhd in PROFILES:
        for _ in range(SAMPLES_PER_PROFILE):
            session_id = "S{0:04d}".format(number)
            number += 1
            records.append((session_id, profile, dyslexia, dyscalculia, adhd,
                            make_payload(rng, session_id, profile, dyslexia, dyscalculia, adhd)))

    raw_path = OUTPUT_DIR / "raw_sessions.jsonl"
    with raw_path.open("w", encoding="utf-8", newline="") as handle:
        for *_, payload in records:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

    with (OUTPUT_DIR / "labels.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["session_id", "synthetic_profile", "dyslexia_label", "dyscalculia_label", "adhd_label"])
        writer.writeheader()
        for session_id, profile, dyslexia, dyscalculia, adhd, _ in records:
            writer.writerow({"session_id": session_id, "synthetic_profile": profile,
                             "dyslexia_label": dyslexia, "dyscalculia_label": dyscalculia,
                             "adhd_label": adhd})

    cnn_fields = ["session_id", "synthetic_profile", "dyslexia_label"] + list(FEATURE_NAMES)
    lstm_fields = ["session_id", "synthetic_profile", "adhd_label", "timestep", "interval_score", "correct_norm", "wrong_norm", "score_change"]
    with (OUTPUT_DIR / "cnn_training.csv").open("w", newline="", encoding="utf-8") as cnn_handle, \
         (OUTPUT_DIR / "lstm_training.csv").open("w", newline="", encoding="utf-8") as lstm_handle:
        cnn_writer = csv.DictWriter(cnn_handle, fieldnames=cnn_fields)
        lstm_writer = csv.DictWriter(lstm_handle, fieldnames=lstm_fields)
        cnn_writer.writeheader()
        lstm_writer.writeheader()
        for session_id, profile, dyslexia, _, adhd, payload in records:
            features, names = extract_features(payload)
            if names != FEATURE_NAMES:
                raise RuntimeError("Feature-name contract changed")
            cnn_row = {"session_id": session_id, "synthetic_profile": profile,
                       "dyslexia_label": dyslexia}
            cnn_row.update({name: "{0:.8f}".format(float(features[index])) for index, name in enumerate(names)})
            cnn_writer.writerow(cnn_row)
            sequence = build_sequence(payload)
            if sequence.shape != (SEQUENCE_LENGTH, SEQUENCE_FEATURES):
                raise RuntimeError("Sequence contract changed")
            for timestep, row in enumerate(sequence):
                lstm_writer.writerow({"session_id": session_id, "synthetic_profile": profile,
                                      "adhd_label": adhd, "timestep": timestep,
                                      "interval_score": "{0:.8f}".format(float(row[0])),
                                      "correct_norm": "{0:.8f}".format(float(row[1])),
                                      "wrong_norm": "{0:.8f}".format(float(row[2])),
                                      "score_change": "{0:.8f}".format(float(row[3]))})

    manifest = {
        "purpose": "synthetic development fixtures only; not clinical data or deployable models",
        "seed": SEED, "sessions": len(records), "profiles": len(PROFILES),
        "cnn_input_shape": [len(records), 1, len(FEATURE_NAMES)],
        "lstm_input_shape": [len(records), SEQUENCE_LENGTH, SEQUENCE_FEATURES],
        "feature_names": FEATURE_NAMES,
        "files": {name: sha256(OUTPUT_DIR / name) for name in ["raw_sessions.jsonl", "labels.csv", "cnn_training.csv", "lstm_training.csv"]},
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Generated {0} synthetic sessions in {1}".format(len(records), OUTPUT_DIR))


if __name__ == "__main__":
    main()
