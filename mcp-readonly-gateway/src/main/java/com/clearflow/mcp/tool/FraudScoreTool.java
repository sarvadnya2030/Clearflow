package com.clearflow.mcp.tool;

import com.clearflow.mcp.service.ElasticsearchLogFetcher;
import com.clearflow.mcp.service.ElasticsearchLogFetcher.LogEntry;
import org.springframework.stereotype.Component;

import java.util.Comparator;
import java.util.List;
import java.util.Map;

@Component
public class FraudScoreTool implements MCPTool {

    private final ElasticsearchLogFetcher logFetcher;

    public FraudScoreTool(ElasticsearchLogFetcher logFetcher) {
        this.logFetcher = logFetcher;
    }

    @Override
    public String name() { return "fraud_score"; }

    @Override
    public String description() { return "Retrieves fraud score and risk classification from Elasticsearch logs"; }

    @Override
    public Object execute(Map<String, Object> input) {
        String paymentId = (String) input.get("paymentId");
        if (paymentId == null || paymentId.isBlank()) {
            return Map.of("error", "paymentId is required");
        }

        List<LogEntry> logs = logFetcher.fetchLogsForPayment(paymentId);

        // Find the fraud scoring entry with the highest score
        return logs.stream()
                .filter(e -> "fraud-scoring".equals(e.service()) && e.fraudScore() != null)
                .max(Comparator.comparingDouble(LogEntry::fraudScore))
                .map(e -> {
                    StringBuilder sb = new StringBuilder();
                    sb.append("Fraud score for ").append(paymentId).append(": ");
                    sb.append(String.format("%.2f", e.fraudScore()));
                    if (e.riskBand() != null) sb.append(" (").append(e.riskBand()).append(")");
                    if (e.durationMs() != null) sb.append(" computed in ").append(e.durationMs()).append("ms");
                    return (Object) sb.toString();
                })
                .orElseGet(() -> {
                    // No fraud-scoring logs — check if any log has fraud fields
                    return logs.stream()
                            .filter(e -> e.fraudScore() != null)
                            .findFirst()
                            .map(e -> (Object) ("fraudScore=" + String.format("%.2f", e.fraudScore())
                                    + (e.riskBand() != null ? " riskBand=" + e.riskBand() : "")))
                            .orElse("No fraud score data found for " + paymentId);
                });
    }
}
