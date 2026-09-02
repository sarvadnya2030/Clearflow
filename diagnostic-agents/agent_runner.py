"""Orchestrator for diagnostic agents."""

import sys
import argparse
from diagnostic_agent import DiagnosticAgent
from repair_agent import RepairAgent
from hitl_interface import HumanInTheLoopCLI

class AgentRunner:
    """Orchestrates all agents for continuous monitoring or one-shot investigation."""
    
    def __init__(self):
        self.diagnostic = DiagnosticAgent()
        self.repair = RepairAgent()
        self.hitl = HumanInTheLoopCLI()
    
    def investigate_payment(self, payment_id: str):
        """One-shot: investigate specific payment and show HITL."""
        print(f"\n🔍 Investigating payment {payment_id}...")
        diagnosis = self.diagnostic.investigate_payment(payment_id)
        
        print(f"\n✓ Diagnosis: {diagnosis['failure_type']}")
        print(f"  Confidence: {diagnosis['confidence_score']:.0%}")
        print(f"  Root Cause: {diagnosis['root_cause']}")
        
        suggestion = self.repair.suggest_repair(diagnosis)
        decision = self.hitl.present_suggestion(suggestion)
        
        if decision.get("approved"):
            if suggestion.fix_command:
                print(f"\n▶️ Would execute: {suggestion.fix_command}")
            print("✓ Repair approved (would execute in production)")
        else:
            print("✗ Repair rejected or skipped")
    
    def scan_continuous(self):
        """Continuous monitoring: periodically scan for systemic failures."""
        print("▶️ Starting continuous monitoring (Ctrl+C to stop)...")
        try:
            while True:
                failures = self.diagnostic.scan_for_failures(window_minutes=15)
                if failures:
                    print(f"⚠️  Found failures: {failures[0]['analysis'][:200]}...")
        except KeyboardInterrupt:
            print("\n✓ Monitoring stopped")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ClearFlow Diagnostic Agent Runner")
    parser.add_argument("--mode", choices=["investigate", "continuous"], default="investigate",
                      help="Mode: investigate specific payment or continuous monitoring")
    parser.add_argument("--payment-id", help="Payment ID for investigate mode")
    
    args = parser.parse_args()
    runner = AgentRunner()
    
    if args.mode == "investigate":
        if not args.payment_id:
            print("Error: --payment-id required for investigate mode")
            sys.exit(1)
        runner.investigate_payment(args.payment_id)
    elif args.mode == "continuous":
        runner.scan_continuous()
