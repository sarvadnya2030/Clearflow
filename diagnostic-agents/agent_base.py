"""Base agent with Claude API integration and MCP tool calling."""

import anthropic
import requests
import json
from typing import Any, Optional
from config import ANTHROPIC_API_KEY, MODEL_DIAGNOSTIC, MAX_TOKENS_DIAGNOSTIC, MCP_URL

class BaseAgent:
    """Base class for diagnostic agents using Claude with tool use."""
    
    def __init__(self, model: str = MODEL_DIAGNOSTIC, max_tokens: int = MAX_TOKENS_DIAGNOSTIC):
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.model = model
        self.max_tokens = max_tokens
        self.mcp_url = MCP_URL
        self.tools = self._build_mcp_tools()
    
    def _build_mcp_tools(self) -> list:
        """Build tool definitions that map to MCP gateway endpoints."""
        return [
            {
                "name": "explain_payment",
                "description": "Get detailed explanation of a payment's full pipeline journey",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "payment_id": {"type": "string", "description": "Payment UUID to explain"}
                    },
                    "required": ["payment_id"]
                }
            },
            {
                "name": "get_payment_timeline",
                "description": "Get 7-stage pipeline timeline for a payment",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "payment_id": {"type": "string", "description": "Payment UUID"}
                    },
                    "required": ["payment_id"]
                }
            },
            {
                "name": "detect_systemic_failures",
                "description": "Detect if there are systemic failures across multiple services",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "window_minutes": {"type": "integer", "description": "Time window to analyze (default 15)"}
                    }
                }
            },
            {
                "name": "get_ops_metrics",
                "description": "Get real-time operational metrics",
                "input_schema": {
                    "type": "object",
                    "properties": {}
                }
            }
        ]
    
    def _call_mcp_tool(self, tool_name: str, tool_input: dict) -> str:
        """Call MCP gateway endpoint and return JSON result."""
        try:
            endpoint_map = {
                "explain_payment": f"/mcp/api/payments/{tool_input.get('payment_id')}/explain",
                "get_payment_timeline": f"/mcp/api/payments/{tool_input.get('payment_id')}/timeline",
                "detect_systemic_failures": "/mcp/api/failures/detect-systemic",
                "get_ops_metrics": "/actuator/metrics"
            }
            
            endpoint = endpoint_map.get(tool_name, "")
            if not endpoint:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
            
            params = {}
            if tool_name == "detect_systemic_failures" and "window_minutes" in tool_input:
                params["window"] = tool_input["window_minutes"]
            
            response = requests.get(
                f"{self.mcp_url}{endpoint}",
                params=params,
                timeout=5
            )
            response.raise_for_status()
            return json.dumps(response.json())
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    def run_agent_loop(self, system_prompt: str, user_prompt: str) -> str:
        """Run Claude with tool use loop until completion."""
        messages = [{"role": "user", "content": user_prompt}]
        
        while True:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt,
                tools=self.tools,
                messages=messages
            )
            
            # Check if we're done
            if response.stop_reason == "end_turn":
                # Extract final text response
                for block in response.content:
                    if hasattr(block, "text"):
                        return block.text
                return "Analysis complete."
            
            # Handle tool use
            if response.stop_reason == "tool_use":
                # Collect all tool results
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = self._call_mcp_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result
                        })
                
                # Add assistant response and tool results to messages
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
            else:
                # Unexpected stop reason
                break
        
        return "Agent completed without final response."
