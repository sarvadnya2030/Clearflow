package com.clearflow.mcp.tool;

import com.clearflow.mcp.service.ElasticsearchLogFetcher;
import com.clearflow.mcp.service.PaymentTimelineReconstructor;
import com.clearflow.mcp.service.PaymentTimelineReconstructor.PaymentTimeline;
import com.clearflow.mcp.service.PaymentTimelineReconstructor.PipelineStage;
import com.clearflow.mcp.service.PaymentTimelineReconstructor.StageStatus;
import org.springframework.stereotype.Component;

import java.util.Map;

@Component
public class PaymentTimelineTool implements MCPTool {

    private final ElasticsearchLogFetcher logFetcher;
    private final PaymentTimelineReconstructor reconstructor;

    public PaymentTimelineTool(ElasticsearchLogFetcher logFetcher,
                               PaymentTimelineReconstructor reconstructor) {
        this.logFetcher = logFetcher;
        this.reconstructor = reconstructor;
    }

    @Override
    public String name() { return "payment_timeline"; }

    @Override
    public String description() { return "Returns chronological payment pipeline timeline from Elasticsearch logs"; }

    @Override
    public Object execute(Map<String, Object> input) {
        String paymentId = (String) input.get("paymentId");
        if (paymentId == null || paymentId.isBlank()) {
            return Map.of("error", "paymentId is required");
        }

        PaymentTimeline timeline = reconstructor.reconstruct(
                paymentId, logFetcher.fetchLogsForPayment(paymentId));

        // Build compact text for LLM context
        StringBuilder sb = new StringBuilder();
        sb.append("Timeline for ").append(paymentId)
          .append(" [").append(timeline.overallStatus()).append("] ")
          .append(timeline.totalLogEvents()).append(" log events\n");

        for (PipelineStage stage : timeline.stages()) {
            String icon = switch (stage.status()) {
                case COMPLETED -> "✅";
                case FAILED    -> "❌";
                case SKIPPED   -> "⏭ ";
                case PENDING   -> "⏳";
            };
            sb.append(String.format("  Stage %d %-26s %s %s",
                    stage.order(), stage.displayName() + ":", icon, stage.status()));
            if (stage.keyEvent() != null) sb.append(" [").append(stage.keyEvent()).append("]");
            if (stage.timestamp() != null) sb.append(" at ").append(stage.timestamp());
            if (stage.status() == StageStatus.FAILED) sb.append(" ← FAILURE");
            sb.append("\n");
        }
        return sb.toString();
    }
}
