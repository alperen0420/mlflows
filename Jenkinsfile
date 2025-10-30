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
                            python -m compileall main.py retrain.py reporting.py experiment_db.py training_utils.py
                        '''
                    } else {
                        powershell '''
                            $venv = Join-Path $env:WORKSPACE ".venv"
                            $py = Join-Path $venv "Scripts\\python.exe"
                            & $py -m compileall main.py retrain.py reporting.py experiment_db.py training_utils.py
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
