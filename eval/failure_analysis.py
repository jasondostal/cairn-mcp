#!/usr/bin/env python3
"""Pipeline stage measurement: where does retrieval break down?

Measures pass rate at each stage of the search pipeline:
  Stage 1: IN_DB      — is the answer stored in the database at all?
  Stage 2: RRF_TOP50  — does RRF retrieval find it in top 50 candidates?
  Stage 3: RERANK_TOP10 — does reranking promote it to top 10?
  Stage 4: RAG_CORRECT — does the LLM generate the right answer?

Each stage is a gate. If stage N fails, stages N+1..4 are "blocked".
This tells us exactly where to focus improvement efforts.

Usage:
    python -u eval/failure_analysis.py [--db DB_NAME] [--conv CONV_ID] [--workers N]
"""

from __future__ import annotations

import argparse
import os
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Load .env
env_file = Path(__file__).parents[1] / ".env"
for line in env_file.read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ[k] = v

os.environ["CAIRN_SEARCH_V2"] = "true"
os.environ["CAIRN_GRAPH_BACKEND"] = "neo4j"
os.environ["CAIRN_NEO4J_URI"] = "bolt://localhost:7687"
os.environ["CAIRN_NEO4J_PASSWORD"] = "cairn-dev-password"
os.environ["CAIRN_RERANKING"] = "true"
os.environ["CAIRN_RERANKER_BACKEND"] = "bedrock"
os.environ["CAIRN_RERANKER_REGION"] = "us-west-2"
os.environ["CAIRN_MCA_GATE"] = "false"
os.environ["CAIRN_TYPE_ROUTING"] = "false"
os.environ["CAIRN_SPREADING_ACTIVATION"] = "false"


def answer_in_results(expected: str, results: list[dict]) -> int | None:
    """Check if expected answer appears in search results. Returns position (1-indexed) or None."""
    expected_lower = expected.lower().strip()
    key_terms = [w for w in expected_lower.split() if len(w) > 3]

    for i, r in enumerate(results, 1):
        content = (r.get("content") or "").lower()

        # Exact substring
        if expected_lower in content:
            return i

        # Key term match
        if key_terms and all(t in content for t in key_terms):
            return i

    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="cairn_eval_locomo_titan_v2_two_pass")
    parser.add_argument("--conv", default="conv-26")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    from eval.benchmark.locomo.adapter import LoCoMoAdapter
    from eval.benchmark.rag import evaluate_question
    from eval.benchmark.runner_bench import _create_services
    from eval.model_compare import MODEL_REGISTRY
    from cairn.core.reranker import get_reranker
    from cairn.config import RerankerConfig

    # Load dataset
    adapter = LoCoMoAdapter()
    data_dir = str(Path(__file__).parent / "benchmark" / "data" / "locomo")
    dataset = adapter.load(data_dir)

    questions = dataset.questions
    if args.conv:
        questions = [q for q in questions if q.metadata.get("conversation_id") == args.conv]
    print(f"Pipeline analysis: {len(questions)} questions ({args.conv or 'all'})")
    print(f"Database: {args.db}\n")

    # Connect
    eval_dsn = f"postgresql://cairn:cairn-dev-password@localhost:5432/{args.db}"
    model_spec = MODEL_REGISTRY["titan_v2"]
    search_engine, memory_store, llm = _create_services(
        eval_dsn, model_spec, skip_enricher=True, pool_size=args.workers + 4,
    )

    from cairn.core.search import SearchEngine
    legacy_engine = search_engine
    if not isinstance(search_engine, SearchEngine):
        legacy_engine = search_engine.fallback_engine

    reranker = get_reranker(RerankerConfig(
        backend=os.getenv("CAIRN_RERANKER_BACKEND", "local"),
        bedrock_region=os.getenv("CAIRN_RERANKER_REGION", "us-east-1"),
    ))

    project = "benchmark"
    results = []
    counter = {"done": 0}
    lock = threading.Lock()
    total = len(questions)
    t_start = time.time()

    def analyze_one(question):
        expected = str(question.expected_answer)

        # ── Stage 1: IN_DB ──
        in_db = False
        try:
            expected_lower = expected.lower().strip()
            row = legacy_engine.db.execute_one(
                "SELECT id FROM memories WHERE lower(content) LIKE %s LIMIT 1",
                (f"%{expected_lower}%",),
            )
            if row:
                in_db = True
            else:
                key_terms = [w for w in expected_lower.split() if len(w) > 3]
                if key_terms:
                    conditions = " AND ".join(["lower(content) LIKE %s"] * min(len(key_terms), 3))
                    params = tuple(f"%{t}%" for t in key_terms[:3])
                    row = legacy_engine.db.execute_one(
                        f"SELECT id FROM memories WHERE {conditions} LIMIT 1",
                        params,
                    )
                    if row:
                        in_db = True
        except Exception:
            pass

        # ── Stage 2: RRF_TOP50 ──
        rrf_pos = None
        rrf_results = []
        try:
            rrf_results = legacy_engine.search(
                query=question.question,
                project=project,
                limit=50,
                include_full=True,
            )
            rrf_pos = answer_in_results(expected, rrf_results)
        except Exception:
            pass

        # ── Stage 3: RERANK_TOP10 ──
        rerank_pos = None
        try:
            if rrf_results:
                rerank_input = [
                    {"id": r["id"], "content": r.get("content") or r.get("summary", ""),
                     "row": r, "score": r.get("score", 0)}
                    for r in rrf_results
                ]
                reranked = reranker.rerank(question.question, rerank_input, limit=10)
                rerank_pos = answer_in_results(expected, reranked)
        except Exception:
            pass

        # ── Stage 4: RAG_CORRECT ──
        correct = False
        generated = ""
        try:
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
            correct = (result.judge_score or 0) >= 0.5
            generated = result.generated_answer
        except Exception as e:
            generated = f"ERROR: {e}"

        with lock:
            counter["done"] += 1
            n = counter["done"]
            elapsed = time.time() - t_start
            rate = n / elapsed if elapsed > 0 else 0
            eta = (total - n) / rate if rate > 0 else 0
            if n % 20 == 0 or n == total:
                print(f"  [{n}/{total}] {rate:.1f} q/s  ETA {eta:.0f}s")

        return {
            "id": question.id,
            "type": question.question_type,
            "question": question.question,
            "expected": expected,
            "generated": generated,
            "in_db": in_db,
            "rrf_pos": rrf_pos,        # position in RRF top-50 (None = not found)
            "rerank_pos": rerank_pos,   # position in reranked top-10 (None = not found)
            "correct": correct,
        }

    # Run in parallel
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(analyze_one, q): q for q in questions}
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda r: r["id"])

    # ── Pipeline Summary ──
    print(f"\n{'='*70}")
    print("  PIPELINE STAGE PASS RATES")
    print(f"{'='*70}")

    n_in_db = sum(1 for r in results if r["in_db"])
    n_rrf = sum(1 for r in results if r["rrf_pos"] is not None)
    n_rrf_top10 = sum(1 for r in results if r["rrf_pos"] is not None and r["rrf_pos"] <= 10)
    n_rerank = sum(1 for r in results if r["rerank_pos"] is not None)
    n_correct = sum(1 for r in results if r["correct"])

    stages = [
        ("Stage 1: IN_DB", n_in_db, "answer exists in database"),
        ("Stage 2: RRF_TOP50", n_rrf, "found by RRF in top 50"),
        ("Stage 2b: RRF_TOP10", n_rrf_top10, "found by RRF in top 10 (no reranker)"),
        ("Stage 3: RERANK_TOP10", n_rerank, "in top 10 after reranking"),
        ("Stage 4: RAG_CORRECT", n_correct, "correct final answer"),
    ]

    for label, count, desc in stages:
        pct = count / total * 100
        print(f"  {label:25s} {count:4d}/{total}  ({pct:5.1f}%)  {desc}")

    # Drop-off between stages
    print(f"\n  STAGE DROP-OFF:")
    print(f"    DB → RRF:        {n_in_db - n_rrf:4d} lost  (search can't find what's stored)")
    print(f"    RRF → Rerank:    {n_rrf - n_rerank:4d} lost  (reranker drops relevant results)")
    rrf_gain = n_rerank - n_rrf_top10
    print(f"    Rerank vs no-rerank: {'+' if rrf_gain >= 0 else ''}{rrf_gain:d}  (reranker {'helps' if rrf_gain > 0 else 'hurts' if rrf_gain < 0 else 'neutral'})")
    print(f"    Rerank → RAG:    {n_rerank - n_correct:4d} lost  (LLM fails to use retrieved context)")

    # ── By question type ──
    print(f"\n{'─'*70}")
    print("  BY QUESTION TYPE (pass rate at each stage)")
    print(f"{'─'*70}")
    print(f"  {'type':15s} {'total':>5s}  {'in_db':>6s}  {'rrf50':>6s}  {'rrf10':>6s}  {'rerank':>6s}  {'correct':>7s}")

    by_type = {}
    for r in results:
        by_type.setdefault(r["type"], []).append(r)

    for qtype, items in sorted(by_type.items()):
        n = len(items)
        db = sum(1 for r in items if r["in_db"])
        rrf = sum(1 for r in items if r["rrf_pos"] is not None)
        rrf10 = sum(1 for r in items if r["rrf_pos"] is not None and r["rrf_pos"] <= 10)
        rrk = sum(1 for r in items if r["rerank_pos"] is not None)
        cor = sum(1 for r in items if r["correct"])
        print(f"  {qtype:15s} {n:5d}  {db/n*100:5.1f}%  {rrf/n*100:5.1f}%  {rrf10/n*100:5.1f}%  {rrk/n*100:5.1f}%  {cor/n*100:6.1f}%")

    # ── Failures at each stage ──
    # Stage 1 failures: NOT IN DB
    not_in_db = [r for r in results if not r["in_db"] and not r["correct"]]
    if not_in_db:
        print(f"\n{'─'*70}")
        print(f"  NOT IN DB — {len(not_in_db)} questions (ingestion failures)")
        print(f"{'─'*70}")
        for r in not_in_db[:15]:
            print(f"  [{r['type']:12s}] Q: {r['question'][:90]}")
            print(f"               A: {str(r['expected'])[:90]}")
            print()

    # Stage 2 failures: IN DB but NOT RETRIEVED
    not_retrieved = [r for r in results if r["in_db"] and r["rrf_pos"] is None and not r["correct"]]
    if not_retrieved:
        print(f"\n{'─'*70}")
        print(f"  IN DB but NOT RETRIEVED — {len(not_retrieved)} questions (search failures)")
        print(f"{'─'*70}")
        for r in not_retrieved[:15]:
            print(f"  [{r['type']:12s}] Q: {r['question'][:90]}")
            print(f"               A: {str(r['expected'])[:90]}")
            print()

    # Stage 3 failures: RETRIEVED but DROPPED BY RERANKER
    dropped = [r for r in results if r["rrf_pos"] is not None and r["rerank_pos"] is None and not r["correct"]]
    if dropped:
        print(f"\n{'─'*70}")
        print(f"  DROPPED BY RERANKER — {len(dropped)} questions")
        print(f"{'─'*70}")
        for r in dropped[:10]:
            print(f"  [{r['type']:12s}] Q: {r['question'][:90]}")
            print(f"               A: {str(r['expected'])[:90]}  (was RRF pos {r['rrf_pos']})")
            print()

    # Stage 4 failures: RETRIEVED but RAG WRONG
    rag_fail = [r for r in results if r["rerank_pos"] is not None and not r["correct"]]
    if rag_fail:
        print(f"\n{'─'*70}")
        print(f"  RAG FAILURES — {len(rag_fail)} questions (retrieved but wrong answer)")
        print(f"{'─'*70}")
        for r in rag_fail[:15]:
            print(f"  [{r['type']:12s}] Q: {r['question'][:90]}")
            print(f"               A: {str(r['expected'])[:90]}")
            print(f"               G: {str(r['generated'])[:90]}")
            print()


if __name__ == "__main__":
    main()
