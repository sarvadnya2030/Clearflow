package com.clearflow.mcp.llm;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Map;

/**
 * LLM client for NVIDIA NIM (integrate.api.nvidia.com).
 * Sends enable_thinking=true + reasoning_budget so the model thinks before answering.
 * Only the final content (not the reasoning chain) is returned to the caller.
 */
public class NvidiaLLMClient implements LLMClient {

    private static final Logger log = LoggerFactory.getLogger(NvidiaLLMClient.class);

    private static final String BASE_URL = "https://integrate.api.nvidia.com/v1";

    private final String apiKey;
    private final String model;
    private final int reasoningBudget;
    private final ObjectMapper mapper;
    private final HttpClient http;

    public NvidiaLLMClient(String apiKey, String model, int reasoningBudget, ObjectMapper mapper) {
        this.apiKey = apiKey;
        this.model = model;
        this.reasoningBudget = reasoningBudget;
        this.mapper = mapper;
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(15))
                .build();
    }

    @Override
    public String chat(List<LLMMessage> messages) {
        try {
            var body = mapper.writeValueAsString(Map.of(
                    "model", model,
                    "messages", messages.stream()
                            .map(m -> Map.of("role", m.role(), "content", m.content()))
                            .toList(),
                    "temperature", 0.6,
                    "top_p", 0.95,
                    "max_tokens", 65536,
                    "stream", false,
                    "chat_template_kwargs", Map.of("enable_thinking", true),
                    "reasoning_budget", reasoningBudget
            ));

            var request = HttpRequest.newBuilder()
                    .uri(URI.create(BASE_URL + "/chat/completions"))
                    .header("Content-Type", "application/json")
                    .header("Authorization", "Bearer " + apiKey)
                    .timeout(Duration.ofSeconds(180))
                    .POST(HttpRequest.BodyPublishers.ofString(body))
                    .build();

            var response = http.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() != 200) {
                log.error("NVIDIA API returned HTTP {}: {}", response.statusCode(), response.body());
                return "NVIDIA API error: HTTP " + response.statusCode();
            }

            JsonNode node = mapper.readTree(response.body());
            JsonNode message = node.path("choices").path(0).path("message");

            // Prefer final content; reasoning_content is the internal thinking chain
            String content = message.path("content").asText(null);
            if (content != null && !content.isBlank()) {
                return content;
            }

            // Fallback: return reasoning if content is empty
            String reasoning = message.path("reasoning_content").asText(null);
            if (reasoning != null && !reasoning.isBlank()) {
                log.warn("NVIDIA response had no content — returning reasoning_content");
                return reasoning;
            }

            return "No response from NVIDIA NIM";

        } catch (Exception e) {
            log.error("NVIDIA NIM call failed: {}", e.getMessage());
            return "NVIDIA NIM unavailable: " + e.getMessage();
        }
    }

    @Override
    public String providerName() {
        return "nvidia-nim/" + model;
    }
}
