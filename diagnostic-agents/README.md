# Real-Time Payment Cascade Intelligence Diagnostic Agents

Autonomous agents that detect payment failures, classify root causes, and suggest repairs using Claude AI.

## Architecture

- **DiagnosticAgent** — Uses Claude Haiku for fast investigation of individual payments or systemic failures
- **RepairAgent** — Consults playbook and suggests specific repairs
- **HumanInTheLoopCLI** — CLI interface for operator approval/rejection of repairs
- **AgentRunner** — Orchestrates continuous monitoring and alerting

## Quick Start

```bash
# Set API key
export ANTHROPIC_API_KEY=sk-...

# One-shot investigation
python3 -c "from diagnostic_agent import DiagnosticAgent; agent = DiagnosticAgent(); print(agent.investigate_payment('payment-uuid'))"

# Continuous monitoring (alerting on cascades)
python3 agent_runner.py --mode=continuous

# Investigate specific payment and show HITL
python3 agent_runner.py --mode=investigate --payment-id=<uuid>
```

## Tools Integrated

Agents call MCP gateway endpoints:
- `/mcp/api/payments/{id}/explain` — Payment journey explanation
- `/mcp/api/payments/{id}/timeline` — 7-stage pipeline timeline
- `/mcp/api/failures/detect-systemic` — Cascade detection
- `/actuator/metrics` — Operational metrics

## Failure Classification

| Failure Type | Root Cause | Fix |
|---|---|---|
| INSUFFICIENT_LIQUIDITY | H2 nostro_accounts empty | Reseed table |
| EMBARGO_BLOCKED | Debtor/creditor in embargo list | Expected behavior |
| AML_SANCTIONS_HIT | Name matched SDN/PEP | Manual review |
| CIRCUIT_BREAKER_OPEN | Connection pool exhausted | Increase pool |
| VALIDATION_FAILED | Invalid IBAN/BIC | Check format |
| ROUTING_FAILED | No available rail | Check corridor config |
| SETTLEMENT_TIMEOUT | Settlement service slow | Restart service |

## Cost Optimization

- **DiagnosticAgent** uses Claude Haiku (fast, cheap) for routine scanning
- **RepairAgent** is deterministic (no LLM needed) — direct playbook lookup
- **Complex cascades** escalate to Claude Sonnet for multi-payment analysis
- **Tool calls** are cached — repeated investigations of same payment ID hit cache

## Enterprise Features

- ✅ Autonomous failure detection (no human intervention needed)
- ✅ Structured repair recommendations with confidence scores
- ✅ Human-in-the-loop approval for risky changes
- ✅ Playbook-based fixes for common failure modes
- ✅ Audit trail of agent decisions and operator approvals
