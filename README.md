# Student Performance Regression Project

This project trains a regression model on the UCI student performance dataset, logs every experiment to MLflow, and persists both metadata and the exact train/test rows to SQLite. Two CLIs drive the workflow:

- `main.py` trains a baseline model, logs metrics/artifacts to MLflow, and writes metadata + dataset snapshots to `experiments.db`.
- `retrain.py` reloads a stored experiment configuration from SQLite, retrains the same pipeline, and records a fresh MLflow run plus metadata.

MLflow artifacts include diagnostic plots (`analysis/` folder), prediction tables, feature-importance CSVs, and the serialized model. The SQLite database stores hyperparameters, metrics, MLflow run ids, and per-row snapshots of the training/test splits (`dataset_snapshots` table).

## Jenkins Pipeline

`Jenkinsfile` defines a declarative pipeline:

1. **Checkout** source code.
2. **Setup Python** virtual environment and install `requirements.txt` (includes DVC, MLflow, sklearn, etc.).
3. **Static Checks** running `python -m compileall` on all core modules (including `security_checks.py`).
4. **Train Model** by executing `main.py` with an on-disk MLflow SQLite backend.
5. **Retrain (Smoke)** running `retrain.py` to ensure experiment metadata replay works.
6. **MLSecOps Audit** invokes `security_checks.py` to validate veri bütünlüğü, `dataset_snapshots` tutarlılığı ve (varsa) model imza dosyaları. Çalışmanın çıktısı `security_report.json` dosyasına yazılır ve MITRE ATLAS & OWASP ML Top 10 kontrolleriyle eşleştirilir.
7. **DVC Snapshot** executes `dvc repro` (fast if nothing changed) and, when `dvc.lock` differs, automatically commits the updated lock file (`ci: update dvc lock [skip ci]`). This stage creates a full history of dataset/model versions without pushing to a remote.

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

- `.data/student-mat.csv`, `experiments*.db`, and `mlruns/` are tracked by DVC (Git `.gitignore` excludes them) so veri + modeller cache üzerinden yönetilir.
- `dvc.yaml` defines a `train` stage that maps to `python main.py --use-mlflow-sqlite`. Tüm çıktılar `outs` altında listelenir; `dvc repro` değişiklik algıladığında stage'i yeniden çalıştırır.
- Jenkins' **DVC Snapshot** stage runs `dvc repro`, then `git add dvc.lock` and `git commit "ci: update dvc lock [skip ci]"` whenever the lock file changes (no `dvc push` required).
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

## MLSecOps (Güvenlik) Entegrasyonu

`security_checks.py`, `security_baseline.json`, `model_signatures.json` ve Jenkins’teki MLSecOps Audit stage’i, “MLSecOps – Yapay Zeka Mühendisleri İçin Kapsamlı Güvenlik Operasyonları Rehberi”nde tarif edilen OWASP ML Top 10 + MITRE ATLAS tehditlerine karşı aşağıdaki kontrolleri uygular:

- **Veri bütünlüğü (OWASP ML01 / MITRE ATLAS T1546):** dataset SHA-256 hash'i ve istatistik profili (mean, std, min, max) `security_baseline.json` ile karşılaştırılır; zehirleme veya tedarik zinciri riskleri erken yakalanır.
- **Deney deposu güvenliği (OWASP ML06 / MITRE ATLAS T1521):** `dataset_snapshots` tablosunun varlığı ve train/test kayıtları doğrulanır; deney tekrarlanabilirliği garanti altına alınır.
- **Model imzaları (OWASP ML05 / MITRE ATLAS T1600):** `model_signatures.json` ile MLflow model artefaktlarının SHA-256 hash’i doğrulanabilir veya kayıt altına alınabilir.
- **CI entegrasyonu:** Jenkins'teki **MLSecOps Audit** stage'i, rehberin "güvenlik sonradan eklenmemeli" ilkesini takip ederek pipeline'ı durduracak zorlayıcı bir kontrol sağlar.
- **Raporlama:** `security_report.json`, her kontrolde hangi OWASP/MITRE maddesinin kapsandığını ve son durumunu listeler. Hocanıza / yönetime çıktıyı göstererek güvenlik kanıtı sunabilirsiniz.

### Komutlar

Günlük doğrulama (CI ile aynı):

```bash
python security_checks.py \
  --dataset .data/student-mat.csv \
  --baseline security_baseline.json \
  --experiments-db experiments.db \
  --mlruns mlruns \
  --model-signatures model_signatures.json \
  --report-path security_report.json
```

Dataset'i bilinçli şekilde güncellediğinde:

```bash
python security_checks.py \
  --dataset .data/student-mat.csv \
  --baseline security_baseline.json \
  --experiments-db experiments.db \
  --mlruns mlruns \
  --reset-baseline
git add security_baseline.json
git commit -m "Refresh MLSecOps dataset baseline"
```

Model imzalarını kaydetmek istediğinde:

```bash
python security_checks.py \
  --dataset .data/student-mat.csv \
  --baseline security_baseline.json \
  --experiments-db experiments.db \
  --mlruns mlruns \
  --model-signatures model_signatures.json \
  --record-model-signatures
git add model_signatures.json
git commit -m "Record model signatures"
```

**Sana düşenler:** veri kaynağını değiştirdiğinde `--reset-baseline` ile profili güncelle; hassas modelleri yayınlarken `--record-model-signatures` ile hash kaydı tut; Jenkins MLSecOps stage’i çalışmadan önce MLflow UI/DB Browser gibi dosyayı kilitleyen süreçleri kapat; `security_report.json` dosyasını MLflow run’ına artefact olarak ekleyerek sunumlarda kanıt olarak kullan. Böylece hocanın talep ettiği MITRE ATLAS + OWASP uyumluluğunu pratik olarak göstermiş olursun.
