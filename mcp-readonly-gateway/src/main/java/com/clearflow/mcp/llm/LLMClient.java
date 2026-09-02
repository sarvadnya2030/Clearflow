package com.clearflow.mcp.llm;

import java.util.List;

public interface LLMClient {
    String chat(List<LLMMessage> messages);
    String providerName();
}
