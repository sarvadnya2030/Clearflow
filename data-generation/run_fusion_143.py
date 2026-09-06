#!/usr/bin/env python3
"""Runs the real graph+LLM fusion method (scratch_graph_llm_fusion.py) --
the same one that scored 0.624 on the 101-incident benchmark -- against
the full, fresh 143-incident output_live set instead, using the evidence
built by build_fusion_evidence_143.py. Same prompt, same model, same
single-shot-per-incident design; only the incident population is new.
"""
import sys

import pandas as pd

sys.path.insert(0, ".")
import scratch_graph_llm_fusion as sgf

df = pd.read_csv("fusion_evidence_143.csv").set_index("incident_id")
client = sgf.eh._get_llm_client()
results = sgf.run_many(df, client)
results.to_csv("scratch_graph_llm_fusion_143_results.csv", index=False)
sgf.print_summary(results)
