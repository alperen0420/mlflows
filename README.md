# Student Performance Regression Project

This project trains a regression model on the UCI student performance dataset, logs experiments to MLflow and stores metadata in SQLite. Two entrypoints are provided:

- `main.py`: trains a model with predefined hyperparameters, logs results to MLflow, and records metadata in `experiments.db`.
- `retrain.py`: reloads the latest (or specified) experiment configuration from SQLite and re-runs training, logging a new MLflow run.

Artifacts such as diagnostic plots and prediction tables are uploaded to MLflow under the `analysis/` artifact folder.

## Jenkins Integration

A declarative pipeline (`Jenkinsfile`) is included to automate model training in CI:

1. **Checkout** the repository.
2. **Setup Python** virtual environment and install dependencies from `requirements.txt`.
3. **Static Checks** compile Python files to catch syntax errors.
4. **Train Model** executes `main.py` with MLflow tracking configured to use `experiments.mlflow.db` inside the Jenkins workspace.
5. **Retrain (Smoke)** runs `retrain.py` to ensure experiment metadata replay works.

Both MLflow artifact directories (`mlruns/**`) and SQLite databases (`*.db`) are archived as build artifacts.

### Prerequisites on the Jenkins Agent

- Python 3.10+ installed and accessible as `python`.
- Ability to create virtual environments (`venv`).
- Network access to download the dataset on the first run.

If the agent runs on Windows, convert the shell steps in the `Jenkinsfile` to PowerShell equivalents and adjust virtual environment activation paths (`.\\${VENV}\\Scripts\\Activate.ps1`).

## Manual Usage

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Train the baseline model and log to SQLite-backed MLflow:

```bash
python main.py --use-mlflow-sqlite
```

Retrain using stored experiment configuration:

```bash
python retrain.py --reuse-mlflow-uri
```

Start the MLflow UI pointing at the generated databases:

```bash
python -m mlflow ui \
  --backend-store-uri sqlite:///$(pwd)/experiments.mlflow.db \
  --default-artifact-root file://$(pwd)/mlruns
```
