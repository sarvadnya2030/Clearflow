FROM eclipse-temurin:21-jdk-alpine AS builder
WORKDIR /workspace
RUN apk add --no-cache maven bash
COPY . /workspace
RUN ./mvnw -q -pl aml-compliance -am package -DskipTests || mvn -q -pl aml-compliance -am package -DskipTests

FROM eclipse-temurin:21-jre-alpine
WORKDIR /app
RUN addgroup -S clearflow && adduser -S clearflow -G clearflow
USER 1001
COPY --from=builder /workspace/aml-compliance/target/aml-compliance-1.0.0.jar /app/app.jar
ENV JAVA_OPTS="-XX:+UseContainerSupport -XX:MaxRAMPercentage=75.0 -Djava.security.egd=file:/dev/./urandom"
EXPOSE 8083
HEALTHCHECK --interval=30s --timeout=10s --retries=5 CMD wget -q -O- http://localhost:8083/actuator/health | grep UP || exit 1
ENTRYPOINT ["sh","-c","java $JAVA_OPTS -jar /app/app.jar"]
