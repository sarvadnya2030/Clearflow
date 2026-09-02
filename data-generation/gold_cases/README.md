# Gold Cases — Independently Verified Root-Cause Incidents

**Why this exists**: the original 101-incident "clean" set conflated two
different things — "we know the root cause because we're the ones who
injected it" (the experimenter's privileged knowledge) and "there is
real evidence in the system that lets an independent investigator verify
the root cause" (what a benchmark actually needs). 68 of the 101
incidents had *no* discoverable evidence at all (crash faults used
`kill -9`, which gives the dying service zero chance to log anything).
An RCA method's guess couldn't be meaningfully scored against those
labels — there was nothing for a method to find, so a "correct" label
with no supporting evidence isn't a real test case, it's an assertion.

**What a gold case requires, all four, before it counts**:
1. A real fault injected into the real, live-running infra (not
   simulated).
2. **Independent, discoverable evidence** — evidence that doesn't come
   from the injector announcing what it did. As of 2026-09-02 this means
   `scripts/health_witness_monitor.py` running concurrently (an
   `/actuator/health` poller with zero knowledge of what was injected)
   plus the real downstream symptom pattern (e.g. payments stalling at a
   specific pipeline stage).
2. A **blind investigation**: the evidence is read and reasoned over
   BEFORE checking the injector's own ground-truth log, exactly the way
   an on-call engineer would have to — not reverse-engineered from
   already knowing the answer.
3. A written **reasoning trace**: what evidence was read, what the
   competing hypotheses were, why the conclusion follows from the
   evidence and not from foreknowledge.
4. **Confirmation**: the blind conclusion is checked against the
   injector's own log. Only if they match does the case count as gold.
   If they don't match, that's a finding in itself (the evidence was
   misleading) and gets recorded, not discarded.

## Format

One JSON file per case in this directory, `{incident_id}.json`:
```
{
  "incident_id": "LIVE-...",
  "fault_type": "...", "injector_claimed_root": "...",
  "injection_time": "...", "duration_seconds": ...,
  "evidence_reviewed": ["exact ES query / witness log excerpt used"],
  "reasoning_trace": "full prose: what I read, what I ruled out, why",
  "blind_conclusion": "...",
  "confirmed": true/false,
  "confirmation_basis": "what independent evidence proved it, not just 'injector said so'",
  "raw_events": [ ... the full ES event list from _pending_{id}.json's
                  "events" field, copied in verbatim ... ]
}
```

**`raw_events` is required, not optional, as of 2026-09-02.** Copy the
`_pending_{incident_id}.json` evidence bundle's full `events` array
into the finalized gold case before deleting the pending file. Reason:
this project already lost a paper's headline empirical result once to
exactly the failure mode this prevents -- `metrics.csv`'s underlying
evidence aged out of Elasticsearch silently, and nobody found out until
someone tried to reproduce the number weeks later (see `BENCHMARK_GOAL.md`,
2026-09-02 "metrics.csv" entry). A gold case with only curated excerpts
and no raw evidence is exactly as vulnerable. `eval_baseline_rca.py`'s
`get_events()` already prefers `raw_events` when present and only falls
back to a live ES query for older cases that predate this convention --
run `backfill_raw_evidence.py` after adding new cases without it.

## Status

Started 2026-09-02, in progress. See `../gold_cases_manifest.csv` for the
running index (one row per case, confirmed/pending/rejected). 39 cases as
of 2026-09-02 (35 confirmed, 4 evidence-free), all backfilled with raw_events.
