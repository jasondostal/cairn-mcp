#!/usr/bin/env python3
"""Quick launcher for LoCoMo benchmark eval."""

import os
from pathlib import Path

# Load .env
env_file = Path(__file__).parent / ".env"
for line in env_file.read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ[k] = v

# v2: intent-routed search with Neo4j graph
os.environ["CAIRN_SEARCH_V2"] = "true"
os.environ["CAIRN_GRAPH_BACKEND"] = "neo4j"
os.environ["CAIRN_NEO4J_URI"] = "bolt://localhost:7687"
os.environ["CAIRN_NEO4J_PASSWORD"] = "cairn-dev-password"

# Reranking
os.environ["CAIRN_RERANKING"] = "true"
os.environ["CAIRN_RERANKER_BACKEND"] = "bedrock"
os.environ["CAIRN_RERANKER_REGION"] = "us-west-2"

# Legacy features OFF
os.environ["CAIRN_MCA_GATE"] = "false"
os.environ["CAIRN_TYPE_ROUTING"] = "false"
os.environ["CAIRN_SPREADING_ACTIVATION"] = "false"

from eval.benchmark.runner_bench import run_benchmark

run_benchmark(
    benchmark_name="locomo",
    strategy_name="two_pass",
    model_names=["titan_v2"],
    no_enrich=True,
    keep_dbs=True,
    reuse_db=False,  # Fresh ingestion with new prompts
    verbose=True,
    workers=8,
    max_questions=199,
    conversation_filter="conv-26",
)
