# Student Performance Regression Project

This project trains a regression model on the UCI student performance dataset, logs every experiment to MLflow, and persists both metadata and the exact train/test rows to SQLite. Two CLIs drive the workflow:

- `main.py` trains a baseline model, logs metrics/artifacts to MLflow, and writes metadata + dataset snapshots to `experiments.db`.
- `retrain.py` reloads a stored experiment configuration from SQLite, retrains the same pipeline, and records a fresh MLflow run plus metadata.

MLflow artifacts include diagnostic plots (`analysis/` folder), prediction tables, feature-importance CSVs, and the serialized model. The SQLite database stores hyperparameters, metrics, MLflow run ids, and per-row snapshots of the training/test splits (`dataset_snapshots` table).

## Jenkins Pipeline

`Jenkinsfile` defines a declarative pipeline:

1. **Checkout** source code.
2. **Setup Python** virtual environment and install `requirements.txt` (includes DVC, MLflow, sklearn, etc.).
3. **Static Checks** running `python -m compileall` on the key modules.
4. **Train Model** by executing `main.py` with an on-disk MLflow SQLite backend.
5. **Retrain (Smoke)** running `retrain.py` to ensure experiment metadata replay works.
6. **DVC Snapshot** executes `dvc repro` (fast if nothing changed) and, when `dvc.lock` differs, automatically commits the updated lock file (`ci: update dvc lock [skip ci]`). This stage creates a full history of dataset/model versions without pushing to a remote.

Artifacts (`mlruns/**`, `*.db`) are archived for each build. The pipeline already handles both Linux (`sh`) and Windows (`powershell`) agents and normalizes MLflow URIs on Windows.

## Manual Usage

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

python main.py --use-mlflow-sqlite
python retrain.py --reuse-mlflow-uri
```

MLflow UI examples:

```bash
python -m mlflow ui \
  --backend-store-uri sqlite:///$(pwd)/experiments.mlflow.db \
  --default-artifact-root file://$(pwd)/mlruns
```

```powershell
python -m mlflow ui `
  --backend-store-uri sqlite:///$(Get-Location)/experiments.mlflow.db `
  --default-artifact-root file:///(Get-Location)/mlruns
```

## DVC & Data Versioning

- `.data/student-mat.csv`, `experiments*.db`, and `mlruns/` are tracked by Git so data + models can live in the same repo.
- `dvc.yaml` defines a `train` stage that maps to `python main.py --use-mlflow-sqlite` with outputs marked as `outs-no-cache`. `dvc repro` will detect when inputs change and rerun as needed.
- Jenkins’ **DVC Snapshot** stage runs `dvc repro`, then `git add dvc.lock` and `git commit "ci: update dvc lock [skip ci]"` whenever the lock file changes (no `dvc push` required).
- Local workflow example:
  ```bash
  dvc init
  dvc repro
  git add dvc.yaml dvc.lock .dvc/ .data mlruns experiments*.db
  git commit -m "Track data and ML artifacts"
  git push
  ```
- To inspect history, use `git log -- dvc.lock`, `dvc metrics show -T`, or `dvc dag`. All DVC activity also appears in Jenkins logs after each build.

With this setup you can reproduce any experiment (via MLflow artifacts + dataset snapshots), track data/model versions through DVC, and keep Jenkins as the single source of truth for automated runs.
