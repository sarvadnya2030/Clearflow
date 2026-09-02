package com.clearflow.mcp.tool;

import java.util.Map;

public interface MCPTool {
    String name();
    String description();
    Object execute(Map<String, Object> input);
}
