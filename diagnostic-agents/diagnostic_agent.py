"""Diagnostic Agent — investigates payment failures and classifies root causes."""

from agent_base import BaseAgent
from config import MODEL_DIAGNOSTIC, MODEL_COMPLEX, MAX_TOKENS_COMPLEX
import requests
import json
from datetime import datetime, timedelta

class DiagnosticAgent(BaseAgent):
    """Autonomous agent that detects and classifies payment failures."""
    
    def investigate_payment(self, payment_id: str) -> dict:
        """Investigate a specific payment failure."""
        system_prompt = """You are a payment systems diagnostician. Your job is to investigate 
payment failures in ClearFlow and determine the root cause.

When investigating, use the available tools to:
1. Explain the payment's journey through the pipeline
2. Get the timeline of stages it passed through
3. Identify which stage failed
4. Classify the failure type

Provide a structured diagnosis with: failure_type, root_cause, confidence_score (0-1), 
affected_stage, evidence, and suggested_remediation."""
        
        user_prompt = f"""Investigate payment {payment_id} and determine why it failed. 
Use the explain_payment and get_payment_timeline tools to gather evidence."""
        
        diagnosis_text = self.run_agent_loop(system_prompt, user_prompt)
        
        # Parse diagnosis into structured format
        return self._parse_diagnosis(diagnosis_text, payment_id)
    
    def scan_for_failures(self, window_minutes: int = 15) -> list:
        """Proactively scan recent payments for failures."""
        system_prompt = """You are analyzing recent payment activity to identify patterns of failure.
        
Use detect_systemic_failures to check for cascade patterns. Return a list of:
- failure_count: number of failed payments
- affected_services: which services are failing  
- cascade_detected: is this a cascading failure pattern?
- severity: LOW/MEDIUM/HIGH/CRITICAL"""
        
        user_prompt = f"Scan the last {window_minutes} minutes for systemic failures."
        
        analysis = self.run_agent_loop(system_prompt, user_prompt)
        return [{"analysis": analysis, "timestamp": datetime.now().isoformat()}]
    
    def _parse_diagnosis(self, diagnosis_text: str, payment_id: str) -> dict:
        """Parse agent diagnosis into structured format."""
        # Simple parsing — in production, use structured JSON from Claude
        failure_types = {
            "liquidity": "INSUFFICIENT_LIQUIDITY",
            "embargo": "EMBARGO_BLOCKED",
            "fraud": "FRAUD_BLOCKED",
            "aml": "AML_SANCTIONS_HIT",
            "validation": "VALIDATION_FAILED",
            "routing": "ROUTING_FAILED",
            "settlement": "SETTLEMENT_TIMEOUT"
        }
        
        detected_type = "UNKNOWN"
        confidence = 0.5
        
        for keyword, ftype in failure_types.items():
            if keyword.lower() in diagnosis_text.lower():
                detected_type = ftype
                confidence = 0.8
                break
        
        return {
            "payment_id": payment_id,
            "failure_type": detected_type,
            "root_cause": diagnosis_text[:200],
            "confidence_score": confidence,
            "full_analysis": diagnosis_text,
            "timestamp": datetime.now().isoformat()
        }
