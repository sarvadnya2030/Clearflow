package com.clearflow.mcp.tool;

import org.springframework.stereotype.Component;

import java.util.Map;

@Component
public class MetricsTool implements MCPTool {
    @Override
    public String name() { return "metrics"; }
    @Override
    public String description() { return "Provides read-only rail and fraud analytics aggregates"; }
    @Override
    public Object execute(Map<String, Object> input) { return Map.of("tool", name(), "input", input); }
}
