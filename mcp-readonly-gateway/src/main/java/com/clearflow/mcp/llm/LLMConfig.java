package com.clearflow.mcp.llm;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class LLMConfig {

    @Value("${clearflow.llm.provider:ollama}")
    private String provider;

    @Value("${clearflow.llm.ollama.base-url:http://localhost:11434}")
    private String ollamaBaseUrl;

    @Value("${clearflow.llm.ollama.model:llama3.2}")
    private String ollamaModel;

    @Value("${clearflow.llm.openrouter.base-url:https://openrouter.ai/api/v1}")
    private String openrouterBaseUrl;

    @Value("${clearflow.llm.openrouter.api-key:}")
    private String openrouterApiKey;

    @Value("${clearflow.llm.openrouter.model:meta-llama/llama-3.2-3b-instruct:free}")
    private String openrouterModel;

    @Value("${clearflow.llm.nvidia.api-key:}")
    private String nvidiaApiKey;

    @Value("${clearflow.llm.nvidia.model:nvidia/nemotron-3-nano-omni-30b-a3b-reasoning}")
    private String nvidiaModel;

    @Value("${clearflow.llm.nvidia.reasoning-budget:16384}")
    private int nvidiaReasoningBudget;

    @Bean
    public LLMClient llmClient(ObjectMapper objectMapper) {
        if ("nvidia".equalsIgnoreCase(provider)) {
            return new NvidiaLLMClient(nvidiaApiKey, nvidiaModel, nvidiaReasoningBudget, objectMapper);
        }
        if ("openrouter".equalsIgnoreCase(provider)) {
            return new OpenRouterLLMClient(openrouterBaseUrl, openrouterApiKey, openrouterModel, objectMapper);
        }
        if ("nvidia-fallback".equalsIgnoreCase(provider)) {
            NvidiaLLMClient nvidia = new NvidiaLLMClient(nvidiaApiKey, nvidiaModel, nvidiaReasoningBudget, objectMapper);
            OpenRouterLLMClient openRouter = new OpenRouterLLMClient(openrouterBaseUrl, openrouterApiKey, openrouterModel, objectMapper);
            return new FallbackLLMClient(nvidia, openRouter);
        }
        OllamaLLMClient ollama = new OllamaLLMClient(ollamaBaseUrl, ollamaModel, objectMapper);
        if ("fallback".equalsIgnoreCase(provider)) {
            OpenRouterLLMClient openRouter = new OpenRouterLLMClient(openrouterBaseUrl, openrouterApiKey, openrouterModel, objectMapper);
            return new FallbackLLMClient(ollama, openRouter);
        }
        return ollama;
    }

    /** Second, always-Ollama bean -- independent of whatever `provider` is
     * configured for the primary `llmClient` bean above (currently
     * nvidia-fallback). Exists so CascadeFailureDetector.diagnoseWithSLM can
     * genuinely compare a real local SLM (qwen3:4b, real weights on this
     * machine, real Ollama round-trip) against the cloud LLM path in the
     * same eval pipeline, not just document that Ollama access exists. */
    @Bean(name = "ollamaSlmClient")
    public LLMClient ollamaSlmClient(ObjectMapper objectMapper) {
        return new OllamaLLMClient(ollamaBaseUrl, ollamaModel, objectMapper);
    }
}
