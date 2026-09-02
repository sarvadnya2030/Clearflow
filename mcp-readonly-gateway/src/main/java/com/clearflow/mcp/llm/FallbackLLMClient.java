package com.clearflow.mcp.llm;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;

/**
 * Tries primary first; if it returns an error string or throws, falls back to secondary.
 */
public class FallbackLLMClient implements LLMClient {

    private static final Logger log = LoggerFactory.getLogger(FallbackLLMClient.class);

    private final LLMClient primary;
    private final LLMClient secondary;

    public FallbackLLMClient(LLMClient primary, LLMClient secondary) {
        this.primary = primary;
        this.secondary = secondary;
    }

    @Override
    public String chat(List<LLMMessage> messages) {
        try {
            String result = primary.chat(messages);
            if (result != null && !isError(result)) {
                return result;
            }
            log.warn("Primary LLM ({}) returned error — falling back to {}", primary.providerName(), secondary.providerName());
        } catch (Exception e) {
            log.warn("Primary LLM ({}) threw exception — falling back: {}", primary.providerName(), e.getMessage());
        }
        return secondary.chat(messages);
    }

    @Override
    public String providerName() {
        return primary.providerName() + " (fallback: " + secondary.providerName() + ")";
    }

    private static boolean isError(String result) {
        if (result == null || result.isBlank()) return true;
        return result.startsWith("Ollama unavailable")
            || result.startsWith("NVIDIA API error")
            || result.startsWith("NVIDIA NIM unavailable")
            || result.startsWith("OpenRouter unavailable")
            || result.startsWith("No response from");
    }
}
