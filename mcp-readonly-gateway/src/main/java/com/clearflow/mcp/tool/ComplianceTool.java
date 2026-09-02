package com.clearflow.mcp.tool;

import com.clearflow.mcp.service.ElasticsearchLogFetcher;
import com.clearflow.mcp.service.ElasticsearchLogFetcher.LogEntry;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;

@Component
public class ComplianceTool implements MCPTool {

    private final ElasticsearchLogFetcher logFetcher;

    public ComplianceTool(ElasticsearchLogFetcher logFetcher) {
        this.logFetcher = logFetcher;
    }

    @Override
    public String name() { return "compliance"; }

    @Override
    public String description() { return "Reads AML screening and sanctions decision from Elasticsearch logs"; }

    @Override
    public Object execute(Map<String, Object> input) {
        String paymentId = (String) input.get("paymentId");
        if (paymentId == null || paymentId.isBlank()) {
            return Map.of("error", "paymentId is required");
        }

        List<LogEntry> logs = logFetcher.fetchLogsForPayment(paymentId);

        // Find the AML screening result
        return logs.stream()
                .filter(e -> "aml-compliance".equals(e.service()) && e.screeningResult() != null)
                .findFirst()
                .map(e -> {
                    StringBuilder sb = new StringBuilder();
                    sb.append("AML screening for ").append(paymentId).append(": ")
                      .append(e.screeningResult());
                    if (e.matchScore() != null) sb.append(" matchScore=").append(String.format("%.2f", e.matchScore()));
                    if (e.listHit() != null && !e.listHit().isBlank()) sb.append(" entity=").append(e.listHit());
                    if (e.eventType() != null) sb.append(" [").append(e.eventType()).append("]");
                    return (Object) sb.toString();
                })
                .orElseGet(() -> {
                    // Check for embargo hit in validation
                    return logs.stream()
                            .filter(e -> "EMBARGO_HIT".equals(e.eventType()))
                            .findFirst()
                            .map(e -> (Object) ("EMBARGO_HIT at validation-enrichment"
                                    + (e.message() != null ? ": " + e.message() : "")))
                            .orElse("No AML/compliance data found for " + paymentId);
                });
    }
}
