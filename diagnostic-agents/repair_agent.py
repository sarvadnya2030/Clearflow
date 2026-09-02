"""RepairAgent — suggests specific fixes for detected failures."""

from dataclasses import dataclass

@dataclass
class RepairSuggestion:
    """Structured repair recommendation."""
    failure_type: str
    root_cause: str
    fix_description: str
    fix_command: str = None
    config_file: str = None
    config_change: str = None
    auto_safe: bool = False  # Can execute without human approval?
    impact: str = None
    confidence: float = 0.8

class RepairAgent:
    """Suggests specific fixes based on failure diagnosis."""
    
    REPAIR_PLAYBOOK = {
        "INSUFFICIENT_LIQUIDITY": {
            "root_cause": "H2 nostro_accounts table empty or SYSTIMESTAMP SQL error",
            "fix": "Reseed nostro_accounts table with sufficient liquidity (10M per currency)",
            "auto_safe": False,
            "fix_command": "curl -X POST http://localhost:8084/actuator/liquidity/reseed",
            "config_file": "routing-execution/src/main/resources/data.sql",
            "impact": "All payments requiring liquidity reservation will now succeed"
        },
        "EMBARGO_BLOCKED": {
            "root_cause": "Debtor or creditor country is on embargo list (IR, KP, RU, SY, CU, SD, MM)",
            "fix": "Expected behavior — AML compliance correctly blocking embargoed countries",
            "auto_safe": False,
            "fix": "No fix needed. This is correct behavior per compliance.",
            "impact": "This is a feature, not a bug"
        },
        "AML_SANCTIONS_HIT": {
            "root_cause": "Debtor/creditor name matched SDN/PEP lists via fuzzy screening",
            "fix": "Verify screening is correct; if false positive, update SDN rules",
            "auto_safe": False,
            "impact": "Payment blocked by AML compliance as designed"
        },
        "CIRCUIT_BREAKER_OPEN": {
            "root_cause": "ActiveMQ circuit breaker opened due to connection pool exhaustion",
            "fix": "Increase ActiveMQ pool or reset circuit breaker",
            "auto_safe": True,
            "fix_command": "curl -X POST http://localhost:8080/actuator/circuitbreakers/activemq/state -d CLOSED",
            "config_file": "gateway/src/main/resources/application-dev.yml",
            "config_change": "spring.artemis.pool.max-connections: 200 (from 50)",
            "impact": "Circuit breaker will recover and accept new transactions"
        },
        "VALIDATION_FAILED": {
            "root_cause": "IBAN/BIC/Currency validation failed or embargo blocked",
            "fix": "Check IBAN format is correct (IBAN_* constants in test)",
            "auto_safe": False,
            "impact": "Payment cannot proceed until IBAN is valid per ISO 13616"
        },
        "ROUTING_FAILED": {
            "root_cause": "No available payment rail for this corridor",
            "fix": "Check rail configuration supports debtor→creditor country pair",
            "auto_safe": False,
            "impact": "Payment must select a supported rail or fail"
        },
        "SETTLEMENT_TIMEOUT": {
            "root_cause": "Settlement service did not respond within timeout",
            "fix": "Restart settlement service or increase timeout",
            "auto_safe": False,
            "fix_command": "bash stop_live_traffic.sh && bash start_live_traffic.sh",
            "impact": "Payment may complete if retry succeeds"
        }
    }
    
    def suggest_repair(self, diagnosis: dict) -> RepairSuggestion:
        """Given a diagnosis, produce a repair recommendation."""
        failure_type = diagnosis.get("failure_type", "UNKNOWN")
        playbook_entry = self.REPAIR_PLAYBOOK.get(failure_type)
        
        if not playbook_entry:
            return RepairSuggestion(
                failure_type=failure_type,
                root_cause="Unknown failure type",
                fix_description="No automated fix available. Manual investigation required.",
                auto_safe=False,
                confidence=0.3
            )
        
        return RepairSuggestion(
            failure_type=failure_type,
            root_cause=playbook_entry.get("root_cause", ""),
            fix_description=playbook_entry.get("fix", ""),
            fix_command=playbook_entry.get("fix_command"),
            config_file=playbook_entry.get("config_file"),
            config_change=playbook_entry.get("config_change"),
            auto_safe=playbook_entry.get("auto_safe", False),
            impact=playbook_entry.get("impact", ""),
            confidence=0.85
        )
