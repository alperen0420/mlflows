pipeline {
    agent any

    environment {
        VENV = "${WORKSPACE}/.venv"
        DB_PATH = "${WORKSPACE}/experiments.db"
        MLFLOW_DB = "${WORKSPACE}/experiments.mlflow.db"
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
                sh '''
                    python -m venv "${VENV}"
                    . "${VENV}/bin/activate"
                    pip install --upgrade pip
                    if [ -f requirements.txt ]; then
                        pip install -r requirements.txt
                    else
                        pip install pandas scikit-learn mlflow matplotlib
                    fi
                '''
            }
        }

        stage('Static Checks') {
            steps {
                sh '''
                    . "${VENV}/bin/activate"
                    python -m compileall main.py retrain.py reporting.py experiment_db.py training_utils.py
                '''
            }
        }

        stage('Train Model') {
            steps {
                sh '''
                    . "${VENV}/bin/activate"
                    python main.py --mlflow-tracking-uri "sqlite:///${MLFLOW_DB}" --db-path "${DB_PATH}"
                '''
            }
        }

        stage('Retrain (Smoke)') {
            steps {
                sh '''
                    . "${VENV}/bin/activate"
                    python retrain.py --mlflow-tracking-uri "sqlite:///${MLFLOW_DB}" --db-path "${DB_PATH}" --reuse-mlflow-uri
                '''
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
