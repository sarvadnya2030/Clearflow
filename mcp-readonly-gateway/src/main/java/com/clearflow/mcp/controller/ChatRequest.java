package com.clearflow.mcp.controller;

import com.clearflow.mcp.llm.LLMMessage;

import java.util.List;

public record ChatRequest(String question, String paymentId, List<LLMMessage> history) {}
