"""
Lightweight Giskard scan for the student performance regression model.

Trains the pipeline, wraps it with Giskard Model/Dataset, runs scan, and
writes JSON/HTML reports for CI/Jenkins.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict

import pandas as pd
from sklearn.model_selection import train_test_split

from training_utils import TARGET_COLUMN, build_pipeline, load_student_performance_dataset

# Force UTF-8 to avoid Windows charmap issues with emojis/logs.
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass


def load_dataset(path_or_url: str) -> pd.DataFrame:
    local_path = Path(path_or_url)
    if local_path.exists():
        return pd.read_csv(local_path, sep=";")
    return load_student_performance_dataset(path_or_url)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Giskard scan.")
    parser.add_argument(
        "--dataset",
        default=".data/student-mat.csv",
        help="Local CSV (preferred) or URL to the student dataset.",
    )
    parser.add_argument(
        "--output-dir",
        default="giskard_reports",
        help="Directory to store Giskard outputs.",
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=0.2,
        help="Test split size.",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="Random seed.",
    )
    args = parser.parse_args()

    try:
        from giskard import Dataset, Model, scan
    except Exception as exc:  # pylint: disable=broad-except
        print(f"[Giskard] Import failed: {exc}", file=sys.stderr)
        sys.exit(1)

    df = load_dataset(args.dataset)
    if TARGET_COLUMN not in df.columns:
        raise ValueError(f"Target column '{TARGET_COLUMN}' not found in dataset")

    features = df.drop(columns=[TARGET_COLUMN])
    target = df[TARGET_COLUMN]

    numeric_features = (
        features.select_dtypes(include=["int64", "float64"]).columns.tolist()
    )
    categorical_features = (
        features.select_dtypes(include=["object", "category"]).columns.tolist()
    )
    feature_types: Dict[str, str] = {
        col: ("category" if col in categorical_features else "numeric")
        for col in features.columns
    }

    # Keep the model light for CI.
    hyperparameters = {
        "n_estimators": 120,
        "max_depth": 8,
        "random_state": args.random_state,
        "n_jobs": -1,
    }
    pipeline = build_pipeline(
        numeric_features=numeric_features,
        categorical_features=categorical_features,
        hyperparameters=hyperparameters,
    )

    X_train, X_test, y_train, y_test = train_test_split(
        features,
        target,
        test_size=args.test_size,
        random_state=args.random_state,
    )
    pipeline.fit(X_train, y_train)

    giskard_df = X_test.copy()
    giskard_df[TARGET_COLUMN] = y_test.reset_index(drop=True)

    dataset = Dataset(
        df=giskard_df,
        target=TARGET_COLUMN,
        name="student-performance",
        column_types=feature_types,
    )
    model = Model(
        model=pipeline.predict,
        model_type="regression",
        name="random_forest_student",
        feature_names=features.columns.tolist(),
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "giskard_report.json"
    html_path = output_dir / "giskard_report.html"

    try:
        result = scan(model=model, dataset=dataset)
    except Exception as exc:  # pylint: disable=broad-except
        json_path.write_text(
            json.dumps({"error": f"scan_failed: {exc}"}, indent=2),
            encoding="utf-8",
        )
        html_path.write_text(
            f"<html><body>Giskard scan failed during scan(): {exc}</body></html>",
            encoding="utf-8",
        )
        print(f"[Giskard] scan() failed: {exc}", file=sys.stderr)
        return

    # Export JSON
    try:
        if hasattr(result, "to_json"):
            result.to_json(json_path)
        else:
            json_path.write_text(json.dumps(result, default=str, indent=2), encoding="utf-8")
    except Exception as exc:  # pylint: disable=broad-except
        json_path.write_text(
            json.dumps({"error": f"export_json_failed: {exc}"}, indent=2),
            encoding="utf-8",
        )
        print(f"[Giskard] to_json failed: {exc}", file=sys.stderr)

    # Export HTML
    try:
        if hasattr(result, "to_html"):
            result.to_html(html_path)
        elif hasattr(result, "to_html_file"):
            result.to_html_file(html_path)
        else:
            html_path.write_text("<html><body>No HTML exporter available</body></html>", encoding="utf-8")
    except Exception as exc:  # pylint: disable=broad-except
        html_path.write_text(
            f"<html><body>Giskard HTML export failed: {exc}</body></html>",
            encoding="utf-8",
        )
        print(f"[Giskard] HTML export failed: {exc}", file=sys.stderr)

    print(f"[Giskard] Reports saved under {output_dir.resolve()}")


if __name__ == "__main__":
    main()
