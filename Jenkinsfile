pipeline {
    agent any

    environment {
        PYTHONPATH = "${WORKSPACE}"
    }

    options {
        timestamps()
        disableConcurrentBuilds()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Setup Python') {
            steps {
                script {
                    if (isUnix()) {
                        sh '''
                            VENV="${WORKSPACE}/.venv"
                            python3 -m venv "$VENV"
                            . "$VENV/bin/activate"
                            pip install --upgrade pip
                            if [ -f requirements.txt ]; then
                                pip install -r requirements.txt
                            else
                                pip install pandas scikit-learn mlflow matplotlib
                            fi
                        '''
                    } else {
                        powershell '''
                            $venv = Join-Path $env:WORKSPACE ".venv"
                            if (-not (Test-Path $venv)) { python -m venv $venv }
                            $py = Join-Path $venv "Scripts\\python.exe"
                            & $py -m pip install --upgrade pip
                            if (Test-Path "requirements.txt") {
                                & $py -m pip install -r requirements.txt
                            } else {
                                & $py -m pip install pandas scikit-learn mlflow matplotlib
                            }
                        '''
                    }
                }
            }
        }

        stage('Static Checks') {
            steps {
                script {
                    if (isUnix()) {
                        sh '''
                            VENV="${WORKSPACE}/.venv"
                            . "$VENV/bin/activate"
                            python -m compileall main.py retrain.py reporting.py experiment_db.py training_utils.py security_checks.py
                        '''
                    } else {
                        powershell '''
                            $venv = Join-Path $env:WORKSPACE ".venv"
                            $py = Join-Path $venv "Scripts\\python.exe"
                            & $py -m compileall main.py retrain.py reporting.py experiment_db.py training_utils.py security_checks.py
                        '''
                    }
                }
            }
        }

        stage('Train Model') {
            steps {
                script {
                    if (isUnix()) {
                        sh '''
                            VENV="${WORKSPACE}/.venv"
                            DB_PATH="${WORKSPACE}/experiments.db"
                            MLFLOW_DB="${WORKSPACE}/experiments.mlflow.db"
                            . "$VENV/bin/activate"
                            python main.py --mlflow-tracking-uri "sqlite:///${MLFLOW_DB}" --db-path "${DB_PATH}"
                        '''
                    } else {
                        powershell '''
                            $venv = Join-Path $env:WORKSPACE ".venv"
                            $py = Join-Path $venv "Scripts\\python.exe"
                            $db = Join-Path $env:WORKSPACE "experiments.db"
                            $mlflowDb = Join-Path $env:WORKSPACE "experiments.mlflow.db"
                            $mlflowUri = "sqlite:///" + ($mlflowDb.Replace('\\', '/'))
                            & $py main.py --mlflow-tracking-uri $mlflowUri --db-path $db
                        '''
                    }
                }
            }
        }

        stage('Retrain (Smoke)') {
            steps {
                script {
                    if (isUnix()) {
                        sh '''
                            VENV="${WORKSPACE}/.venv"
                            DB_PATH="${WORKSPACE}/experiments.db"
                            MLFLOW_DB="${WORKSPACE}/experiments.mlflow.db"
                            . "$VENV/bin/activate"
                            python retrain.py --mlflow-tracking-uri "sqlite:///${MLFLOW_DB}" --db-path "${DB_PATH}" --reuse-mlflow-uri
                        '''
                    } else {
                        powershell '''
                            $venv = Join-Path $env:WORKSPACE ".venv"
                            $py = Join-Path $venv "Scripts\\python.exe"
                            $db = Join-Path $env:WORKSPACE "experiments.db"
                            $mlflowDb = Join-Path $env:WORKSPACE "experiments.mlflow.db"
                            $mlflowUri = "sqlite:///" + ($mlflowDb.Replace('\\', '/'))
                            & $py retrain.py --mlflow-tracking-uri $mlflowUri --db-path $db --reuse-mlflow-uri
                        '''
                    }
                }
            }
        }

        stage('MLSecOps Audit') {
            steps {
                script {
                    if (isUnix()) {
                        sh '''
                            VENV="${WORKSPACE}/.venv"
                            . "$VENV/bin/activate"
                            python security_checks.py \
                                --dataset ".data/student-mat.csv" \
                                --baseline "security_baseline.json" \
                                --experiments-db "${WORKSPACE}/experiments.db" \
                                --mlruns "${WORKSPACE}/mlruns" \
                                --model-signatures "model_signatures.json" \
                                --report-path "${WORKSPACE}/security_report.json"
                        '''
                    } else {
                        powershell '''
                            $venv = Join-Path $env:WORKSPACE ".venv"
                            $py = Join-Path $venv "Scripts\\python.exe"
                            & $py security_checks.py `
                                --dataset .data\\student-mat.csv `
                                --baseline security_baseline.json `
                                --experiments-db (Join-Path $env:WORKSPACE "experiments.db") `
                                --mlruns (Join-Path $env:WORKSPACE "mlruns") `
                                --model-signatures model_signatures.json `
                                --report-path (Join-Path $env:WORKSPACE "security_report.json")
                        '''
                    }
                }
            }
        }

        stage('Fairness (Fairlearn)') {
            steps {
                script {
                    if (isUnix()) {
                        sh '''
                            VENV="${WORKSPACE}/.venv"
                            . "$VENV/bin/activate"
                            python ci_fairness.py --dataset ".data/student-mat.csv" --sensitive-feature sex --output "fairness_report.json"
                        '''
                    } else {
                        powershell '''
                            $venv = Join-Path $env:WORKSPACE ".venv"
                            $py = Join-Path $venv "Scripts\\python.exe"
                            & $py ci_fairness.py --dataset .data\\student-mat.csv --sensitive-feature sex --output fairness_report.json
                        '''
                    }
                }
            }
            post {
                always {
                    archiveArtifacts artifacts: 'fairness_report.json', allowEmptyArchive: true, fingerprint: true
                }
            }
        }

        stage('Giskard Scan') {
            steps {
                script {
                    if (isUnix()) {
                        sh '''
                            VENV="${WORKSPACE}/.venv"
                            . "$VENV/bin/activate"
                            python ci_giskard_scan.py --dataset ".data/student-mat.csv" --output-dir "giskard_reports"
                        '''
                    } else {
                        powershell '''
                            $venv = Join-Path $env:WORKSPACE ".venv"
                            $py = Join-Path $venv "Scripts\\python.exe"
                            & $py ci_giskard_scan.py --dataset .data\\student-mat.csv --output-dir giskard_reports
                        '''
                    }
                }
            }
            post {
                always {
                    archiveArtifacts artifacts: 'giskard_reports/**', allowEmptyArchive: true, fingerprint: true
                }
            }
        }

        stage('Garak Security Scan') {
            steps {
                script {
                    if (isUnix()) {
                        sh '''
                            VENV="${WORKSPACE}/.venv"
                            export HF_HOME="${WORKSPACE}/.cache/huggingface"
                            export GARAK_RUN_DIR="${WORKSPACE}/garak_reports"
                            . "$VENV/bin/activate"
                            mkdir -p "${GARAK_RUN_DIR}"
                            python -m garak -m huggingface:distilgpt2 -p promptinject --report_prefix "${GARAK_RUN_DIR}/scan"
                        '''
                    } else {
                        powershell '''
                            $venv = Join-Path $env:WORKSPACE ".venv"
                            $py = Join-Path $venv "Scripts\\python.exe"
                            $env:HF_HOME = Join-Path $env:WORKSPACE ".cache\\huggingface"
                            $env:GARAK_RUN_DIR = Join-Path $env:WORKSPACE "garak_reports"
                            if (-not (Test-Path $env:GARAK_RUN_DIR)) { New-Item -ItemType Directory -Path $env:GARAK_RUN_DIR | Out-Null }
                            $prefix = Join-Path $env:GARAK_RUN_DIR "scan"
                            & $py -m garak -m huggingface:distilgpt2 -p promptinject --report_prefix $prefix
                        '''
                    }
                }
            }
            post {
                always {
                    archiveArtifacts artifacts: 'garak_reports/**', allowEmptyArchive: true, fingerprint: true
                }
            }
        }

        stage('DVC Snapshot') {
            steps {
                script {
                    if (isUnix()) {
                        sh '''
                            VENV="${WORKSPACE}/.venv"
                            . "$VENV/bin/activate"
                            if [ ! -d ".dvc" ]; then
                                dvc init -q
                            fi
                            dvc repro
                            git config user.name "Jenkins CI"
                            git config user.email "jenkins@example.com"
                            if [ -f dvc.lock ] && ! git diff --quiet -- dvc.lock; then
                                git add dvc.lock
                                git commit -m "ci: update dvc lock [skip ci]" || true
                            fi
                        '''
                    } else {
                        powershell '''
                            $venv = Join-Path $env:WORKSPACE ".venv"
                            $py = Join-Path $venv "Scripts\\python.exe"
                            if (-not (Test-Path ".dvc")) {
                                & $py -m dvc init -q
                            }
                            & $py -m dvc repro
                            git config user.name "Jenkins CI"
                            git config user.email "jenkins@example.com"
                            if (Test-Path "dvc.lock") {
                                git diff --quiet -- dvc.lock
                                if ($LASTEXITCODE -ne 0) {
                                    git add dvc.lock
                                    git commit -m "ci: update dvc lock [skip ci]" | Out-Null
                                }
                            }
                        '''
                    }
                }
            }
        }

        stage('SBOM (CycloneDX)') {
            steps {
                script {
                    if (isUnix()) {
                        sh '''
                            VENV="${WORKSPACE}/.venv"
                            PY="$VENV/bin/python"
                            . "$VENV/bin/activate"
                            "$PY" -m cyclonedx_py requirements requirements.txt -o sbom.json --of JSON
                        '''
                    } else {
                        powershell '''
                            $venv = Join-Path $env:WORKSPACE ".venv"
                            $py = Join-Path $venv "Scripts\\python.exe"
                            & $py -m pip install --upgrade cyclonedx-bom
                            & $py -m cyclonedx_py requirements requirements.txt -o sbom.json --of JSON
                        '''
                    }
                }
            }
            post {
                always {
                    archiveArtifacts artifacts: 'sbom.json', allowEmptyArchive: true, fingerprint: true
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'mlruns/**', fingerprint: true, allowEmptyArchive: true
            archiveArtifacts artifacts: '*.db', fingerprint: true, allowEmptyArchive: true
        }
        success {
            echo 'Pipeline completed successfully.'
        }
        failure {
            echo 'Pipeline failed. Check console output for details.'
        }
    }
}
