package com.clearflow.mcp.controller;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/mcp/admin")
public class AdminController {

    private static final Map<String, Integer> SERVICE_PORTS = Map.ofEntries(
        Map.entry("aml-compliance", 8083),
        Map.entry("routing-execution", 8084),
        Map.entry("settlement", 8085),
        Map.entry("validation-enrichment", 8082),
        Map.entry("audit", 8086),
        Map.entry("fraud-scoring", 8081)
    );

    @PostMapping("/service/{serviceId}/stop")
    public ResponseEntity<?> stopService(@PathVariable String serviceId) {
        if (!SERVICE_PORTS.containsKey(serviceId)) {
            return ResponseEntity.badRequest().body(Map.of("error", "Unknown service: " + serviceId));
        }
        try {
            Integer port = SERVICE_PORTS.get(serviceId);
            stopServiceByPort(port);
            return ResponseEntity.ok(Map.of(
                "status", "stopped",
                "service", serviceId,
                "port", port
            ));
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(Map.of("error", "Failed to stop service: " + e.getMessage()));
        }
    }

    @PostMapping("/service/{serviceId}/start")
    public ResponseEntity<?> startService(@PathVariable String serviceId) {
        if (!SERVICE_PORTS.containsKey(serviceId)) {
            return ResponseEntity.badRequest().body(Map.of("error", "Unknown service: " + serviceId));
        }
        try {
            Integer port = SERVICE_PORTS.get(serviceId);
            startServiceByPort(serviceId, port);
            return ResponseEntity.ok(Map.of(
                "status", "starting",
                "service", serviceId,
                "port", port
            ));
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(Map.of("error", "Failed to start service: " + e.getMessage()));
        }
    }

    private void stopServiceByPort(Integer port) throws Exception {
        String cmd = "lsof -ti :" + port + " | xargs kill -9 2>/dev/null || true";
        ProcessBuilder pb = new ProcessBuilder("bash", "-c", cmd);
        pb.start().waitFor();
        Thread.sleep(1000);
    }

    private void startServiceByPort(String serviceId, Integer port) throws Exception {
        String baseDir = "/home/admin-/Desktop/EDI6/clearflow";
        String logDir = baseDir + "/dev-logs";

        String jarPath = resolveJarPath(baseDir, serviceId);
        if (jarPath == null) {
            throw new Exception("JAR file not found for service: " + serviceId);
        }

        String cmd = String.format(
            "cd %s && nohup java -Dspring.profiles.active=dev -Xmx1536m -Xms512m " +
            "-XX:+UseG1GC -XX:MaxGCPauseMillis=200 -jar %s > %s/%s.log 2>&1 &",
            baseDir, jarPath, logDir, serviceId
        );

        ProcessBuilder pb = new ProcessBuilder("bash", "-c", cmd);
        pb.start().waitFor();
        Thread.sleep(2000);
    }

    private String resolveJarPath(String baseDir, String serviceId) {
        String[] possible = {
            baseDir + "/" + serviceId + "/target/" + serviceId + "-1.0.0.jar",
            baseDir + "/" + serviceId + "/target/" + serviceId.replace("-", "") + "-1.0.0.jar",
        };
        for (String path : possible) {
            if (new java.io.File(path).exists()) {
                return path;
            }
        }
        return null;
    }
}
