#!/usr/bin/env python3
"""Trace a single question through the search pipeline step by step.

Usage:
    python eval/trace_question.py locomo_4
    python eval/trace_question.py locomo_12 --v2
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Load .env
env_file = Path(__file__).parents[1] / ".env"
for line in env_file.read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ[k] = v

# SearchV2 env
os.environ["CAIRN_SEARCH_V2"] = "true"
os.environ["CAIRN_GRAPH_BACKEND"] = "neo4j"
os.environ["CAIRN_NEO4J_URI"] = "bolt://localhost:7687"
os.environ["CAIRN_NEO4J_PASSWORD"] = "cairn-dev-password"
os.environ["CAIRN_RERANKING"] = "true"
os.environ["CAIRN_RERANKER_BACKEND"] = "bedrock"
os.environ["CAIRN_RERANKER_REGION"] = "us-west-2"


def main():
    question_id = sys.argv[1] if len(sys.argv) > 1 else "locomo_4"
    use_v2 = "--v2" in sys.argv

    # Load question
    from eval.benchmark.locomo.adapter import LoCoMoAdapter
    adapter = LoCoMoAdapter()
    data_dir = str(Path(__file__).parents[0] / "benchmark" / "data" / "locomo")
    dataset = adapter.load(data_dir)
    question = None
    for q in dataset.questions:
        if q.id == question_id:
            question = q
            break
    if not question:
        print(f"Question {question_id} not found")
        return

    print(f"{'='*70}")
    print(f"  Question: {question.question}")
    print(f"  Expected: {question.expected_answer}")
    print(f"  Type:     {question.question_type}")
    print(f"{'='*70}")

    # Create services (reuse eval DB)
    from eval.model_compare import MODEL_REGISTRY
    from eval.benchmark.runner_bench import _create_services

    model_spec = MODEL_REGISTRY["titan_v2"]
    eval_dsn = f"postgresql://cairn:cairn-dev-password@localhost:5432/cairn_eval_locomo_titan_v2"
    search_engine, memory_store, llm = _create_services(eval_dsn, model_spec, skip_enricher=True)

    project = "benchmark"

    # ── Step 1: Legacy RRF search ──
    print(f"\n{'─'*70}")
    print("  STEP 1: Legacy RRF Search (top 10)")
    print(f"{'─'*70}")

    from cairn.core.search import SearchEngine
    if isinstance(search_engine, SearchEngine):
        legacy_engine = search_engine
    else:
        legacy_engine = search_engine.fallback_engine

    legacy_results = legacy_engine.search(
        query=question.question,
        project=project,
        limit=10,
        include_full=True,
    )

    for i, r in enumerate(legacy_results[:5], 1):
        content = (r.get("content") or r.get("summary", ""))[:120]
        score = r.get("score", 0)
        comps = r.get("score_components", {})
        comp_str = " ".join(f"{k}={v:.4f}" for k, v in comps.items() if v > 0)
        print(f"  [{i}] id={r['id']} score={score:.4f} {comp_str}")
        print(f"      {content}")

    # Check if expected answer appears in results
    expected_lower = str(question.expected_answer).lower()
    found_at = None
    for i, r in enumerate(legacy_results, 1):
        content = (r.get("content") or "").lower()
        if expected_lower in content or any(w in content for w in expected_lower.split() if len(w) > 3):
            found_at = i
            break
    print(f"\n  Expected answer in top 10? {'YES at position ' + str(found_at) if found_at else 'NO'}")

    # ── Step 2: Router classification ──
    if use_v2 and llm:
        print(f"\n{'─'*70}")
        print("  STEP 2: Router Classification")
        print(f"{'─'*70}")

        from cairn.core.router import QueryRouter
        router = QueryRouter(llm)
        route = router.route(question.question)
        print(f"  query_type:   {route.query_type}")
        print(f"  aspects:      {route.aspects}")
        print(f"  entity_hints: {route.entity_hints}")
        print(f"  temporal:     after={route.temporal.after}, before={route.temporal.before}")
        print(f"  confidence:   {route.confidence}")

        # ── Step 3: Graph handler ──
        print(f"\n{'─'*70}")
        print(f"  STEP 3: Graph Handler ({route.query_type})")
        print(f"{'─'*70}")

        from cairn.core.handlers import HANDLERS, SearchContext, handle_exploratory
        from cairn.graph import get_graph_provider

        graph = get_graph_provider()
        if graph:
            graph.connect()
            graph.ensure_schema()

        project_id = None
        proj_row = legacy_engine.db.execute_one(
            "SELECT id FROM projects WHERE name = %s", (project,)
        )
        if proj_row:
            project_id = proj_row["id"]

        ctx = SearchContext(
            query=question.question,
            route=route,
            project_id=project_id,
            project_name=project,
            db=legacy_engine.db,
            embedding=legacy_engine.embedding,
            graph=graph,
            limit=10,
        )

        handler = HANDLERS.get(route.query_type, handle_exploratory)
        try:
            graph_candidates = handler(ctx)
            print(f"  Handler returned {len(graph_candidates)} candidates")
            for i, c in enumerate(graph_candidates[:5], 1):
                content = c.get("content", "")[:120]
                score = c.get("score", 0)
                print(f"  [{i}] id={c['id']} score={score:.4f}")
                print(f"      {content}")

            found_at_graph = None
            for i, c in enumerate(graph_candidates, 1):
                content = (c.get("content") or "").lower()
                if expected_lower in content or any(w in content for w in expected_lower.split() if len(w) > 3):
                    found_at_graph = i
                    break
            print(f"\n  Expected answer in graph results? {'YES at position ' + str(found_at_graph) if found_at_graph else 'NO'}")
        except Exception as e:
            print(f"  Handler FAILED: {e}")

    # ── Step 4: Reranking ──
    print(f"\n{'─'*70}")
    print("  STEP 4: Reranking (top 10 from RRF pool of 50)")
    print(f"{'─'*70}")

    # Get wider RRF pool
    rrf_pool = legacy_engine.search(
        query=question.question,
        project=project,
        limit=50,
        include_full=True,
    )
    print(f"  RRF pool: {len(rrf_pool)} candidates")

    # Check if expected answer is in the pool
    found_in_pool = None
    for i, r in enumerate(rrf_pool, 1):
        content = (r.get("content") or "").lower()
        if expected_lower in content or any(w in content for w in expected_lower.split() if len(w) > 3):
            found_in_pool = i
            break
    print(f"  Expected answer in pool of 50? {'YES at position ' + str(found_in_pool) if found_in_pool else 'NO'}")

    # Rerank
    from cairn.core.reranker import get_reranker
    reranker = get_reranker(
        backend=os.getenv("CAIRN_RERANKER_BACKEND", "local"),
        region=os.getenv("CAIRN_RERANKER_REGION", "us-east-1"),
    )

    # Convert to reranker format
    rerank_input = []
    for r in rrf_pool:
        rerank_input.append({
            "id": r["id"],
            "content": r.get("content") or r.get("summary", ""),
            "row": r,
            "score": r.get("score", 0),
        })

    try:
        reranked = reranker.rerank(question.question, rerank_input, limit=10)
        print(f"  Reranked top 10:")
        for i, c in enumerate(reranked[:5], 1):
            content = c.get("content", "")[:120]
            rs = c.get("rerank_score", 0)
            print(f"  [{i}] id={c['id']} rerank={rs:.4f}")
            print(f"      {content}")

        found_at_rerank = None
        for i, c in enumerate(reranked, 1):
            content = (c.get("content") or "").lower()
            if expected_lower in content or any(w in content for w in expected_lower.split() if len(w) > 3):
                found_at_rerank = i
                break
        print(f"\n  Expected answer after reranking? {'YES at position ' + str(found_at_rerank) if found_at_rerank else 'NO'}")
    except Exception as e:
        print(f"  Reranking FAILED: {e}")

    # ── Step 5: RAG generation ──
    print(f"\n{'─'*70}")
    print("  STEP 5: RAG Answer Generation")
    print(f"{'─'*70}")

    from eval.benchmark.rag import evaluate_question
    extra_kwargs = adapter.get_search_kwargs(question)
    result = evaluate_question(
        question=question,
        search_engine=search_engine,
        llm=llm,
        judge_llm=llm,
        project=project,
        search_limit=10,
        extra_search_kwargs=extra_kwargs,
    )
    print(f"  Generated: {result.generated_answer}")
    print(f"  Expected:  {result.expected_answer}")
    print(f"  Score:     {result.judge_score}")
    print(f"  Reasoning: {result.judge_reasoning[:200]}")

    print(f"\n{'='*70}")


if __name__ == "__main__":
    main()
