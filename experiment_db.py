import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Iterator, Optional


EXPERIMENT_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_type TEXT NOT NULL,
    hyperparameters TEXT NOT NULL,
    train_config TEXT NOT NULL,
    created_at TEXT NOT NULL,
    mlflow_run_id TEXT,
    mlflow_tracking_uri TEXT,
    metrics TEXT,
    data_source TEXT,
    notes TEXT
);
"""


def ensure_tables(conn: sqlite3.Connection) -> None:
    """Create the experiments table if it is missing."""
    conn.execute(EXPERIMENT_TABLE_DDL)


def _json_dumps(data: Dict) -> str:
    """Serialize dictionaries with sorted keys for stable storage."""
    return json.dumps(data, sort_keys=True)


def insert_experiment(
    conn: sqlite3.Connection,
    *,
    model_type: str,
    hyperparameters: Dict,
    train_config: Dict,
    mlflow_run_id: Optional[str] = None,
    mlflow_tracking_uri: Optional[str] = None,
    metrics: Optional[Dict] = None,
    data_source: Optional[str] = None,
    notes: Optional[str] = None,
) -> int:
    """Insert a new experiment row and return its primary key."""
    ensure_tables(conn)
    created_at = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        """
        INSERT INTO experiments (
            model_type,
            hyperparameters,
            train_config,
            created_at,
            mlflow_run_id,
            mlflow_tracking_uri,
            metrics,
            data_source,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            model_type,
            _json_dumps(hyperparameters),
            _json_dumps(train_config),
            created_at,
            mlflow_run_id,
            mlflow_tracking_uri,
            _json_dumps(metrics) if metrics else None,
            data_source,
            notes,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def _row_to_dict(row: sqlite3.Row) -> Dict:
    """Convert a sqlite row into a structured dictionary."""
    if row is None:
        raise ValueError("Experiment record not found.")
    return {
        "id": row["id"],
        "model_type": row["model_type"],
        "hyperparameters": json.loads(row["hyperparameters"]),
        "train_config": json.loads(row["train_config"]),
        "created_at": row["created_at"],
        "mlflow_run_id": row["mlflow_run_id"],
        "mlflow_tracking_uri": row["mlflow_tracking_uri"],
        "metrics": json.loads(row["metrics"]) if row["metrics"] else None,
        "data_source": row["data_source"],
        "notes": row["notes"],
    }


def fetch_latest_experiment(conn: sqlite3.Connection) -> Dict:
    """Return the most recent experiment row."""
    ensure_tables(conn)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM experiments ORDER BY created_at DESC LIMIT 1"
    )
    row = cursor.fetchone()
    if row is None:
        raise ValueError("No experiments found in the database.")
    return _row_to_dict(row)


def fetch_experiment_by_id(conn: sqlite3.Connection, experiment_id: int) -> Dict:
    """Return a specific experiment row by its primary key."""
    ensure_tables(conn)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM experiments WHERE id = ?", (experiment_id,)
    )
    row = cursor.fetchone()
    if row is None:
        raise ValueError(f"Experiment with id={experiment_id} not found.")
    return _row_to_dict(row)


@contextmanager
def connect(db_path: str) -> Iterator[sqlite3.Connection]:
    """Context manager for sqlite connections with WAL enabled."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        yield conn
    finally:
        conn.close()
