# Student Performance Regression Project

This project trains a regression model on the UCI student performance dataset, logs experiments to MLflow and stores both experiment metadata *and the exact train/test rows* inside SQLite. Two entrypoints are provided:

- `main.py`: trains a model with predefined hyperparameters, logs results to MLflow, and records metadata in `experiments.db`.
- `retrain.py`: reloads the latest (or specified) experiment configuration from SQLite and re-runs training, logging a new MLflow run.

Artifacts such as diagnostic plots, prediction tables, and feature importance CSVs are uploaded to MLflow under the `analysis/` artifact folder, while the underlying dataset rows used for each split are mirrored in the `dataset_snapshots` table of `experiments.db`.

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

If the agent runs on Windows the provided pipeline already switches to PowerShell, creates the venv in `%WORKSPACE%\.venv`, and normalizes MLflow URIs (see the `isUnix()` checks inside `Jenkinsfile`).

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

Windows PowerShell eşdeğeri:

```powershell
python -m mlflow ui `
  --backend-store-uri sqlite:///$(Get-Location)/experiments.mlflow.db `
  --default-artifact-root file:///(Get-Location)/mlruns
```

## Veriyi ve Modelleri GitHub/DVC ile Paylaşma

- `.data/student-mat.csv`, `experiments*.db` ve `mlruns/` artık **Git tarafından izleniyor**; Jenkins veya yerel çalıştırma sonrası oluşan verileri doğrudan commit & push edebilirsin.
- `dvc.yaml` içindeki `train` stage’i, `main.py --use-mlflow-sqlite` komutunu tanımlar ve çıktıları `outs-no-cache` olarak işaretler. Böylece dosyalar workspace’de kalırken DVC metadata’sı Git’e eklenir.
- DVC kullanımı için örnek:
  ```bash
  dvc init
  dvc repro
  git add dvc.yaml dvc.lock .dvc/ .data mlruns experiments*.db
  git commit -m "Track data and ML artifacts"
  git push
  ```
- Bu sayede hem data hem de MLflow’un ürettiği derlenmiş modeller GitHub üzerinde saklanır; başka bir kullanıcı depoyu çekip `dvc repro` ya da doğrudan `python main.py` komutuyla aynı sonuçları alabilir.
