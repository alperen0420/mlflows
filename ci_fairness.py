"""
Generate a simple fairness report using Fairlearn for the student performance model.

It trains the same RandomForest pipeline as main.py, evaluates per-group metrics
for a chosen sensitive feature, and saves a JSON summary for CI/Jenkins.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from fairlearn.metrics import MetricFrame
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

from training_utils import TARGET_COLUMN, build_pipeline, load_student_performance_dataset


def load_dataset(path_or_url: str) -> pd.DataFrame:
    local_path = Path(path_or_url)
    if local_path.exists():
        return pd.read_csv(local_path, sep=";")
    return load_student_performance_dataset(path_or_url)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Fairlearn fairness report.")
    parser.add_argument(
        "--dataset",
        default=".data/student-mat.csv",
        help="Local CSV (preferred) or URL to the student dataset.",
    )
    parser.add_argument(
        "--sensitive-feature",
        default="sex",
        help="Column name to evaluate group fairness on.",
    )
    parser.add_argument(
        "--output",
        default="fairness_report.json",
        help="Where to store the JSON report.",
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

    df = load_dataset(args.dataset)
    if TARGET_COLUMN not in df.columns:
        raise ValueError(f"Target column '{TARGET_COLUMN}' not found in dataset")
    if args.sensitive_feature not in df.columns:
        raise ValueError(
            f"Sensitive feature '{args.sensitive_feature}' not found in dataset"
        )

    features = df.drop(columns=[TARGET_COLUMN])
    target = df[TARGET_COLUMN]

    numeric_features = (
        features.select_dtypes(include=["int64", "float64"]).columns.tolist()
    )
    categorical_features = (
        features.select_dtypes(include=["object", "category"]).columns.tolist()
    )

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
        stratify=None,
    )

    pipeline.fit(X_train, y_train)
    y_pred = pipeline.predict(X_test)

    metric_frame = MetricFrame(
        metrics={
            "mae": mean_absolute_error,
            "r2": r2_score,
        },
        y_true=y_test,
        y_pred=y_pred,
        sensitive_features=X_test[args.sensitive_feature],
    )

    report = {
        "sensitive_feature": args.sensitive_feature,
        "overall": {
            "mae": metric_frame.overall["mae"],
            "r2": metric_frame.overall["r2"],
        },
        "by_group": {
            str(group): {
                "mae": metric_frame.by_group["mae"][group],
                "r2": metric_frame.by_group["r2"][group],
            }
            for group in metric_frame.by_group.index
        },
        "dataset": {
            "rows": len(df),
            "features": len(features.columns),
            "test_rows": len(X_test),
        },
    }

    output_path = Path(args.output)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[Fairlearn] Report saved to {output_path.resolve()}")


if __name__ == "__main__":
    main()
