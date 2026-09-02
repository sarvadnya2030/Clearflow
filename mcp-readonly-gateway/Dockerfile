FROM eclipse-temurin:21-jdk-alpine AS builder
WORKDIR /workspace
RUN apk add --no-cache maven bash
COPY . /workspace
RUN ./mvnw -q -pl mcp-readonly-gateway -am package -DskipTests \
 || mvn -q -pl mcp-readonly-gateway -am package -DskipTests

FROM eclipse-temurin:21-jre-alpine
WORKDIR /app
RUN addgroup -S clearflow && adduser -S clearflow -G clearflow
USER 1001
COPY --from=builder /workspace/mcp-readonly-gateway/target/mcp-readonly-gateway-1.0.0.jar /app/app.jar
ENV JAVA_OPTS="-XX:+UseContainerSupport -XX:MaxRAMPercentage=75.0 -Djava.security.egd=file:/dev/./urandom"
EXPOSE 8087
HEALTHCHECK --interval=30s --timeout=10s --retries=5 CMD wget -q -O- http://localhost:8087/actuator/health | grep UP || exit 1
ENTRYPOINT ["sh","-c","java $JAVA_OPTS -jar /app/app.jar"]
