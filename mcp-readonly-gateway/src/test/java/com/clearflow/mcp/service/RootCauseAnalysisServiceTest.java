package com.clearflow.mcp.service;

import com.clearflow.mcp.llm.LLMClient;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class RootCauseAnalysisServiceTest {

    @Test
    void explain_returnsNoDataFallback_whenPaymentNotFound() {
        ElasticsearchLogFetcher logFetcher = mock(ElasticsearchLogFetcher.class);
        when(logFetcher.fetchLogsForPayment("PAY-DEMO-TEST")).thenReturn(List.of());

        PaymentTimelineReconstructor reconstructor = new PaymentTimelineReconstructor();
        RootCauseClassifier classifier = new RootCauseClassifier();
        LLMClient llmClient = mock(LLMClient.class);
        ObjectMapper objectMapper = new ObjectMapper();

        RootCauseAnalysisService service = new RootCauseAnalysisService(
                logFetcher, reconstructor, classifier, llmClient, objectMapper);

        RootCauseAnalysisService.ExplainResponse response = service.explain("PAY-DEMO-TEST");

        assertThat(response).isNotNull();
        assertThat(response.overallStatus()).isEqualTo("NOT_FOUND");
        assertThat(response.causeCategory()).isEqualTo("NO_DATA");
        assertThat(response.primaryCause()).contains("No logs found");
        assertThat(response.primaryEvidence()).contains("Elasticsearch log entries");
        assertThat(response.narrativeSummary()).contains("No payment events found in Elasticsearch");

        verifyNoInteractions(llmClient);
    }
}
