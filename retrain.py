import argparse
import json
from pathlib import Path
from typing import Optional

import mlflow
import mlflow.sklearn
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

from experiment_db import (
    connect,
    fetch_experiment_by_id,
    fetch_latest_experiment,
    insert_experiment,
)
from reporting import log_regression_artifacts
from training_utils import (
    DATA_URL,
    TARGET_COLUMN,
    build_pipeline,
    load_student_performance_dataset,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild and retrain a model using parameters stored in SQLite."
    )
    parser.add_argument(
        "--db-path",
        default="experiments.db",
        help="SQLite database file that contains experiment metadata.",
    )
    parser.add_argument(
        "--experiment-id",
        type=int,
        help="ID of the experiment to reload. If omitted, the latest one is used.",
    )
    parser.add_argument(
        "--experiment-name",
        default="student-performance-regression",
        help="MLflow experiment name.",
    )
    parser.add_argument(
        "--run-name",
        default=None,
        help="Optional MLflow run name override.",
    )
    parser.add_argument(
        "--mlflow-tracking-uri",
        default=None,
        help="Explicit tracking URI. Takes highest precedence.",
    )
    parser.add_argument(
        "--reuse-mlflow-uri",
        action="store_true",
        help="Use the tracking URI stored in the experiment metadata if available.",
    )
    parser.add_argument(
        "--use-mlflow-sqlite",
        action="store_true",
        help="Fallback to using a SQLite MLflow backend alongside the database path.",
    )
    parser.add_argument(
        "--notes",
        default=None,
        help="Optional notes to store for the new experiment record.",
    )
    return parser.parse_args()


def resolve_tracking_uri(
    *,
    args: argparse.Namespace,
    db_path: Path,
    stored_uri: Optional[str],
) -> Optional[str]:
    if args.mlflow_tracking_uri:
        return args.mlflow_tracking_uri
    if args.reuse_mlflow_uri and stored_uri:
        return stored_uri
    if args.use_mlflow_sqlite:
        return f"sqlite:///{db_path.with_suffix('.mlflow.db')}"
    return None


def main() -> None:
    args = parse_args()
    db_path = Path(args.db_path)

    with connect(str(db_path)) as conn:
        if args.experiment_id is not None:
            record = fetch_experiment_by_id(conn, args.experiment_id)
        else:
            record = fetch_latest_experiment(conn)

    data_source = record["data_source"] or DATA_URL
    dataframe = load_student_performance_dataset(data_source)
    if TARGET_COLUMN not in dataframe.columns:
        raise ValueError(f"Target column '{TARGET_COLUMN}' not found in dataset.")

    features = dataframe.drop(columns=[TARGET_COLUMN])
    target = dataframe[TARGET_COLUMN]

    numeric_features = features.select_dtypes(include=["int64", "float64"]).columns.tolist()
    categorical_features = features.select_dtypes(include=["object", "category"]).columns.tolist()

    hyperparameters = record["hyperparameters"]
    train_config = record["train_config"]

    random_state = train_config.get("random_state", 42)
    test_size = train_config.get("test_size", 0.2)

    tracking_uri = resolve_tracking_uri(
        args=args,
        db_path=db_path,
        stored_uri=record.get("mlflow_tracking_uri"),
    )
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)

    mlflow.set_experiment(args.experiment_name)
    run_name = args.run_name or f"retrain-from-{record['id']}"

    pipeline = build_pipeline(
        numeric_features=numeric_features,
        categorical_features=categorical_features,
        hyperparameters=hyperparameters,
    )

    X_train, X_test, y_train, y_test = train_test_split(
        features,
        target,
        test_size=test_size,
        random_state=random_state,
    )

    with mlflow.start_run(run_name=run_name) as run:
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
        mlflow.log_param("test_size", test_size)
        mlflow.log_param("random_state", random_state)
        mlflow.log_param("origin_experiment_id", record["id"])
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
            tags={
                "origin_experiment_id": str(record["id"]),
                "target": TARGET_COLUMN,
            },
        )

        retrain_config = {
            **train_config,
            "origin_experiment_id": record["id"],
            "train_rows": len(X_train),
            "test_rows": len(X_test),
        }

        with connect(str(db_path)) as conn:
            insert_experiment(
                conn,
                model_type=record["model_type"],
                hyperparameters=hyperparameters,
                train_config=retrain_config,
                mlflow_run_id=run.info.run_id,
                mlflow_tracking_uri=mlflow.get_tracking_uri(),
                metrics=metrics,
                data_source=data_source,
                notes=args.notes or f"Retrained from experiment {record['id']}",
            )

    print(
        json.dumps(
            {
                "origin_experiment_id": record["id"],
                "mlflow_run_id": run.info.run_id,
                "metrics": metrics,
                "tracking_uri": mlflow.get_tracking_uri(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
