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

public class OpenRouterLLMClient implements LLMClient {

    private static final Logger log = LoggerFactory.getLogger(OpenRouterLLMClient.class);

    private final String baseUrl;
    private final String apiKey;
    private final String model;
    private final ObjectMapper mapper;
    private final HttpClient http;

    public OpenRouterLLMClient(String baseUrl, String apiKey, String model, ObjectMapper mapper) {
        this.baseUrl = baseUrl;
        this.apiKey = apiKey;
        this.model = model;
        this.mapper = mapper;
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();
    }

    @Override
    public String chat(List<LLMMessage> messages) {
        try {
            var body = mapper.writeValueAsString(Map.of(
                    "model", model,
                    "messages", messages.stream()
                            .map(m -> Map.of("role", m.role(), "content", m.content()))
                            .toList()
            ));

            var request = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + "/chat/completions"))
                    .header("Content-Type", "application/json")
                    .header("Authorization", "Bearer " + apiKey)
                    .header("HTTP-Referer", "https://clearflow.internal")
                    .header("X-Title", "ClearFlow MCP")
                    .timeout(Duration.ofSeconds(120))
                    .POST(HttpRequest.BodyPublishers.ofString(body))
                    .build();

            var response = http.send(request, HttpResponse.BodyHandlers.ofString());
            JsonNode node = mapper.readTree(response.body());
            return node.path("choices").path(0).path("message").path("content")
                    .asText("No response from OpenRouter");
        } catch (Exception e) {
            log.error("OpenRouter call failed: {}", e.getMessage());
            return "OpenRouter unavailable: " + e.getMessage();
        }
    }

    @Override
    public String providerName() {
        return "openrouter/" + model;
    }
}
