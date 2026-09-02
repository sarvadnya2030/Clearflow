package com.clearflow.mcp.config;

import com.clearflow.mcp.tool.ClearFlowMcpTools;
import org.springframework.ai.tool.ToolCallbackProvider;
import org.springframework.ai.tool.method.MethodToolCallbackProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Registers ClearFlowMcpTools with the Spring AI MCP server.
 *
 * The ToolCallbackProvider bean is picked up by Spring AI's MCP server
 * auto-configuration. Each @Tool annotated method in ClearFlowMcpTools
 * becomes a discoverable, callable tool in the MCP protocol:
 *
 *   tools/list  → returns all 6 tools with descriptions
 *   tools/call  → invokes the tool and returns structured result
 *
 * MCP clients connect via:
 *   SSE:  GET  /mcp/sse
 *   HTTP: POST /mcp/message
 */
@Configuration
public class McpToolsConfig {

    @Bean
    public ToolCallbackProvider clearflowToolCallbackProvider(ClearFlowMcpTools tools) {
        return MethodToolCallbackProvider.builder()
                .toolObjects(tools)
                .build();
    }
}
