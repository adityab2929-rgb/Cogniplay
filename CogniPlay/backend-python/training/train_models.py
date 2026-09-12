"""Train CogniPlay architectures for a development-only pipeline demonstration.

This utility deliberately refuses synthetic fixtures as a source for live
checkpoints. It is not a clinical-model training or validation workflow.
"""

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from features.extract_features import FEATURE_NAMES, SEQUENCE_FEATURES, SEQUENCE_LENGTH


def load_cnn(path: Path) -> Tuple[np.ndarray, np.ndarray]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    x = np.asarray([[float(row[name]) for name in FEATURE_NAMES] for row in rows], dtype=np.float32)
    y = np.asarray([float(row["dyslexia_label"]) for row in rows], dtype=np.float32)
    return x, y


def load_lstm(path: Path) -> Tuple[np.ndarray, np.ndarray]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    groups: Dict[str, List[Dict[str, str]]] = {}
    for row in rows:
        groups.setdefault(row["session_id"], []).append(row)
    sequences, labels = [], []
    for session_id in sorted(groups):
        group = sorted(groups[session_id], key=lambda row: int(row["timestep"]))
        if len(group) != SEQUENCE_LENGTH:
            raise ValueError("Session {0} does not have six timesteps".format(session_id))
        sequences.append([[float(row[name]) for name in ("interval_score", "correct_norm", "wrong_norm", "score_change")] for row in group])
        labels.append(float(group[0]["adhd_label"]))
    return np.asarray(sequences, dtype=np.float32), np.asarray(labels, dtype=np.float32)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "demo_models")
    parser.add_argument("--epochs", type=int, default=80)
    args = parser.parse_args()
    if "synthetic" in str(args.data_dir).lower() and "saved_models" in str(args.output_dir).lower():
        raise SystemExit("Refusing to install synthetic-trained weights in saved_models.")
    try:
        import torch
        import torch.nn as nn
    except ImportError as exc:
        raise SystemExit("Install PyTorch before training: pip install torch") from exc
    from models.cnn_model import DyslexiaCNN
    from models.lstm_model import AttentionLSTM
    if not isinstance(DyslexiaCNN(), nn.Module) or not isinstance(AttentionLSTM(), nn.Module):
        raise SystemExit("PyTorch model implementations are unavailable.")
    torch.manual_seed(20260912)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for model, x, y, filename in (
        (DyslexiaCNN(), *load_cnn(args.data_dir / "cnn_training.csv"), "dyslexia_cnn.pt"),
        (AttentionLSTM(), *load_lstm(args.data_dir / "lstm_training.csv"), "adhd_lstm.pt"),
    ):
        tensor_x = torch.from_numpy(x).view(-1, 1, len(FEATURE_NAMES)) if filename.startswith("dyslexia") else torch.from_numpy(x).view(-1, SEQUENCE_LENGTH, SEQUENCE_FEATURES)
        tensor_y = torch.from_numpy(y).view(-1, 1)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
        loss_fn = nn.BCELoss()
        model.train()
        for _ in range(args.epochs):
            optimizer.zero_grad()
            loss = loss_fn(model(tensor_x), tensor_y)
            loss.backward()
            optimizer.step()
        torch.save(model.state_dict(), args.output_dir / filename)
    print("Demo checkpoints written to {0}; do not deploy synthetic-trained weights.".format(args.output_dir))


if __name__ == "__main__":
    main()
