import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

SECURITY_CONTROLS = {
    "dataset_integrity": {
        "description": "Verify dataset hash and statistical profile to detect poisoning or tampering.",
        "owasp": "ML01 Data Poisoning",
        "mitre": ["ATLAS.TA0001 Initial Access", "ATLAS.T1546 Poison Training Data"],
    },
    "experiment_store": {
        "description": "Ensure dataset snapshots exist for both splits to defend supply-chain attacks.",
        "owasp": "ML06 Supply-Chain Vulnerability",
        "mitre": ["ATLAS.T1521 Manipulate ML Supply Chain"],
    },
    "model_signatures": {
        "description": "Validate MLflow model artifacts via SHA-256 signatures.",
        "owasp": "ML05 Model Theft",
        "mitre": ["ATLAS.T1600 Exfiltration of ML Assets"],
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_dataset_profile(csv_path: Path, tolerance_pct: float) -> Dict:
    df = pd.read_csv(csv_path, sep=";")
    numeric = df.select_dtypes(include=["number"])
    stats = {}
    for column in numeric.columns:
        series = numeric[column].astype(float)
        stats[column] = {
            "mean": float(series.mean()),
            "std": float(series.std(ddof=0)),
            "min": float(series.min()),
            "max": float(series.max()),
        }

    return {
        "path": str(csv_path),
        "sha256": sha256_file(csv_path),
        "tolerance_pct": tolerance_pct,
        "stats": stats,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def verify_dataset(baseline: Dict, current: Dict) -> None:
    tolerance = baseline.get("tolerance_pct", 15.0)
    if baseline["sha256"] != current["sha256"]:
        raise SystemExit(
            "Dataset hash mismatch detected. Possible tampering or drift in .data/student-mat.csv"
        )

    baseline_stats = baseline.get("stats", {})
    current_stats = current.get("stats", {})
    problems = []
    for column, reference in baseline_stats.items():
        if column not in current_stats:
            problems.append(f"Column '{column}' missing from current dataset profile.")
            continue
        for metric in ("mean", "std", "min", "max"):
            ref_value = reference.get(metric, 0.0)
            curr_value = current_stats[column].get(metric)
            if ref_value == 0:
                continue
            delta_pct = abs(curr_value - ref_value) / abs(ref_value) * 100
            if delta_pct > tolerance:
                problems.append(
                    f"{column}.{metric} deviated by {delta_pct:.2f}% "
                    f"(baseline={ref_value:.4f}, current={curr_value:.4f})"
                )

    if problems:
        raise SystemExit(
            "Dataset statistical checks failed:\n- " + "\n- ".join(problems)
        )


def verify_database(db_path: Path) -> None:
    if not db_path.exists():
        raise SystemExit(f"SQLite database missing: {db_path}")

    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='dataset_snapshots'"
        )
        if cursor.fetchone() is None:
            raise SystemExit("dataset_snapshots table not found in experiments.db")

        split_counts = dict(
            conn.execute(
                "SELECT split, COUNT(*) FROM dataset_snapshots GROUP BY split"
            )
        )
        missing = {"train", "test"} - set(split_counts)
        if missing:
            raise SystemExit(
                f"dataset_snapshots missing expected splits: {', '.join(sorted(missing))}"
            )
        if any(count == 0 for count in split_counts.values()):
            raise SystemExit("dataset_snapshots table contains empty splits.")


def collect_model_artifacts(mlruns_dir: Path) -> Dict[str, Path]:
    artifacts = {}
    if not mlruns_dir.exists():
        return artifacts

    for experiment_dir in mlruns_dir.iterdir():
        if not experiment_dir.is_dir() or experiment_dir.name.startswith("."):
            continue
        if experiment_dir.name in {"models", "tmp"}:
            continue
        for run_dir in experiment_dir.iterdir():
            if not run_dir.is_dir() or run_dir.name.startswith("."):
                continue
            candidate = run_dir / "artifacts" / "model" / "model.pkl"
            if candidate.exists():
                artifacts[run_dir.name] = candidate
    return artifacts


def verify_model_signatures(
    signatures_path: Path,
    artifacts: Dict[str, Path],
    record: bool,
) -> str:
    if not signatures_path.exists():
        if record and artifacts:
            data = {
                run_id: {
                    "sha256": sha256_file(path),
                    "path": path.as_posix(),
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                }
                for run_id, path in artifacts.items()
            }
            signatures_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            print(f"[mlsecops] recorded {len(data)} model signatures.")
        return "recorded" if record and artifacts else "missing"

    signatures = json.loads(signatures_path.read_text(encoding="utf-8"))
    errors = []
    for run_id, info in signatures.items():
        recorded_path = Path(info["path"])
        if not recorded_path.exists():
            errors.append(f"Recorded model artifact missing: {recorded_path}")
            continue
        current_hash = sha256_file(recorded_path)
        if current_hash != info.get("sha256"):
            errors.append(f"Model hash mismatch for run {run_id}")

    if errors:
        raise SystemExit("Model signature verification failed:\n- " + "\n- ".join(errors))

    new_records = 0
    if record:
        for run_id, path in artifacts.items():
            if run_id in signatures:
                continue
            signatures[run_id] = {
                "sha256": sha256_file(path),
                "path": path.as_posix(),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
            new_records += 1
        if new_records:
            signatures_path.write_text(json.dumps(signatures, indent=2), encoding="utf-8")
            print(f"[mlsecops] appended signatures for {new_records} new model artifacts.")
            return "recorded"

    return "verified"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run MLSecOps security checks for the student performance project."
    )
    parser.add_argument("--dataset", required=True, help="Path to the training dataset CSV.")
    parser.add_argument(
        "--baseline",
        default="security_baseline.json",
        help="JSON file storing dataset baseline profile.",
    )
    parser.add_argument(
        "--experiments-db",
        required=True,
        help="Path to experiments SQLite database.",
    )
    parser.add_argument(
        "--mlruns",
        default="mlruns",
        help="Directory containing MLflow runs (optional for signature checks).",
    )
    parser.add_argument(
        "--tolerance-pct",
        type=float,
        default=15.0,
        help="Allowed percentage deviation for dataset statistics.",
    )
    parser.add_argument(
        "--reset-baseline",
        action="store_true",
        help="Recompute and overwrite the baseline profile.",
    )
    parser.add_argument(
        "--model-signatures",
        default="model_signatures.json",
        help="Optional JSON file containing model artifact signatures.",
    )
    parser.add_argument(
        "--record-model-signatures",
        action="store_true",
        help="Append missing model signatures to the signature file.",
    )
    parser.add_argument(
        "--report-path",
        default="security_report.json",
        help="Path to write the MLSecOps audit report (JSON).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report_entries: List[Dict] = []
    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        raise SystemExit(f"Dataset not found at {dataset_path}")

    baseline_path = Path(args.baseline)
    if args.reset_baseline or not baseline_path.exists():
        profile = build_dataset_profile(dataset_path, args.tolerance_pct)
        baseline_path.write_text(json.dumps({"dataset": profile}, indent=2), encoding="utf-8")
        print(f"[mlsecops] Baseline profile created at {baseline_path}")

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    current_profile = build_dataset_profile(dataset_path, args.tolerance_pct)
    verify_dataset(baseline["dataset"], current_profile)
    report_entries.append(
        {
            "control": "dataset_integrity",
            **SECURITY_CONTROLS["dataset_integrity"],
            "status": "passed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    print("[mlsecops] Dataset integrity and statistics verified.")

    verify_database(Path(args.experiments_db))
    report_entries.append(
        {
            "control": "experiment_store",
            **SECURITY_CONTROLS["experiment_store"],
            "status": "passed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    print("[mlsecops] SQLite experiment store integrity verified.")

    artifacts = collect_model_artifacts(Path(args.mlruns))
    signature_status = verify_model_signatures(
        Path(args.model_signatures),
        artifacts,
        record=args.record_model_signatures,
    )
    report_entries.append(
        {
            "control": "model_signatures",
            **SECURITY_CONTROLS["model_signatures"],
            "status": signature_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    print("[mlsecops] MLSecOps checks completed successfully.")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": current_profile,
        "controls": report_entries,
    }
    Path(args.report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
