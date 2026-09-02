pipeline {
  agent { docker { image 'maven:3.9.6-eclipse-temurin-21' } }
  stages {
    stage('Checkout') { steps { checkout scm } }
    stage('Build') { steps { sh 'mvn clean compile -B' } }
    stage('Unit Tests') {
      steps { sh 'mvn test -B' }
      post { always { junit '**/target/surefire-reports/*.xml' } }
    }
    stage('Integration Tests') { steps { sh 'mvn verify -P integration-tests -B' } }
    stage('Code Coverage') {
      steps { sh 'mvn jacoco:check -B' }
      post { always { jacoco execPattern: '**/target/jacoco.exec' } }
    }
    stage('SonarQube') {
      steps { withSonarQubeEnv('SonarQube') { sh 'mvn sonar:sonar -B' } }
      post { always { waitForQualityGate abortPipeline: true } }
    }
    stage('Docker Build') {
      steps { sh 'docker-compose -f infrastructure/docker-compose.yml build' }
    }
  }
  post {
    always { cleanWs() }
    failure { mail to: 'team@clearflow.com', subject: "BUILD FAILED: ${env.JOB_NAME}" }
  }
}
