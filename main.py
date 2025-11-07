import argparse
import json
from pathlib import Path

import mlflow
import mlflow.sklearn
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

from experiment_db import connect, insert_dataset_split, insert_experiment
from reporting import log_regression_artifacts
from training_utils import (
    DATA_URL,
    TARGET_COLUMN,
    build_pipeline,
    load_student_performance_dataset,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train a student performance regression model."
    )
    parser.add_argument(
        "--db-path",
        default="experiments.db",
        help="SQLite database file to store experiment metadata.",
    )
    parser.add_argument(
        "--experiment-name",
        default="student-performance-regression",
        help="MLflow experiment name.",
    )
    parser.add_argument(
        "--run-name",
        default="baseline-random-forest",
        help="Optional MLflow run name.",
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=0.2,
        help="Fraction of data used for evaluation.",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="Random seed used for splitting and the model.",
    )
    parser.add_argument(
        "--use-mlflow-sqlite",
        action="store_true",
        help="Use a SQLite backend store for MLflow tracking.",
    )
    parser.add_argument(
        "--mlflow-tracking-uri",
        default=None,
        help="Override tracking URI. Takes precedence over --use-mlflow-sqlite.",
    )
    parser.add_argument(
        "--notes",
        default=None,
        help="Optional free-form notes stored alongside the experiment metadata.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    data_frame = load_student_performance_dataset(DATA_URL)
    if TARGET_COLUMN not in data_frame.columns:
        raise ValueError(f"Target column '{TARGET_COLUMN}' not found in dataset.")

    features = data_frame.drop(columns=[TARGET_COLUMN])
    target = data_frame[TARGET_COLUMN]

    numeric_features = features.select_dtypes(include=["int64", "float64"]).columns.tolist()
    categorical_features = features.select_dtypes(include=["object", "category"]).columns.tolist()

    hyperparameters = {
        "n_estimators": 200,
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

    tracking_uri = args.mlflow_tracking_uri
    if tracking_uri is None and args.use_mlflow_sqlite:
        tracking_uri = f"sqlite:///{db_path.with_suffix('.mlflow.db')}"
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)

    mlflow.set_experiment(args.experiment_name)

    with mlflow.start_run(run_name=args.run_name) as run:
        pipeline.fit(X_train, y_train)
        test_predictions = pipeline.predict(X_test)
        train_predictions = pipeline.predict(X_train)

        test_mse = mean_squared_error(y_test, test_predictions)
        test_mae = mean_absolute_error(y_test, test_predictions)
        test_r2 = r2_score(y_test, test_predictions)

        train_mse = mean_squared_error(y_train, train_predictions)
        train_mae = mean_absolute_error(y_train, train_predictions)
        train_r2 = r2_score(y_train, train_predictions)

        metrics = {
            "train_mse": train_mse,
            "train_mae": train_mae,
            "train_r2": train_r2,
            "test_mse": test_mse,
            "test_mae": test_mae,
            "test_r2": test_r2,
        }
        mlflow.log_metrics(metrics)
        mlflow.log_params({f"model__{key}": value for key, value in hyperparameters.items()})
        mlflow.log_param("target_column", TARGET_COLUMN)
        mlflow.log_param("test_size", args.test_size)
        mlflow.log_param("random_state", args.random_state)
        mlflow.log_artifact(Path(__file__).name)
        mlflow.sklearn.log_model(pipeline, artifact_path="model")
        log_regression_artifacts(
            pipeline=pipeline,
            X_train=X_train,
            y_train=y_train,
            X_test=X_test,
            y_test=y_test,
            train_predictions=train_predictions,
            test_predictions=test_predictions,
            metrics=metrics,
            artifact_path="analysis",
            tags={"target": TARGET_COLUMN},
        )

        train_config = {
            "test_size": args.test_size,
            "random_state": args.random_state,
            "target_column": TARGET_COLUMN,
            "feature_count": len(features.columns),
            "train_rows": len(X_train),
            "test_rows": len(X_test),
        }

        with connect(str(db_path)) as conn:
            experiment_id = insert_experiment(
                conn,
                model_type="RandomForestRegressor",
                hyperparameters=hyperparameters,
                train_config=train_config,
                mlflow_run_id=run.info.run_id,
                mlflow_tracking_uri=mlflow.get_tracking_uri(),
                metrics=metrics,
                data_source=DATA_URL,
                notes=args.notes,
            )
            insert_dataset_split(
                conn,
                experiment_id=experiment_id,
                split="train",
                features_rows=X_train.reset_index(drop=True).to_dict(orient="records"),
                target_values=y_train.reset_index(drop=True).tolist(),
            )
            insert_dataset_split(
                conn,
                experiment_id=experiment_id,
                split="test",
                features_rows=X_test.reset_index(drop=True).to_dict(orient="records"),
                target_values=y_test.reset_index(drop=True).tolist(),
            )

    print(
        json.dumps(
            {
                "experiment_id": experiment_id,
                "mlflow_run_id": run.info.run_id,
                "metrics": metrics,
                "tracking_uri": mlflow.get_tracking_uri(),
                "db_path": str(db_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
