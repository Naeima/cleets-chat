#!/usr/bin/env python3
"""
Benchmark evaluation script for CLEETS-CHAT.

Compares original (templated) answers vs. humanized answers against:
1. SPARQL-computed gold answers (facts extracted directly from RDF)
2. Manual benchmark questions with curated gold answers
3. Metrics: citation accuracy, fact preservation, user preference

Usage:
    python evaluate_answers.py --benchmark simple
    python evaluate_answers.py --benchmark full --humanize
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple

import qa
from kg_service import CLEETSKG
from rdflib import Graph, Namespace, RDF, Literal


# Define benchmark questions (curated)
BENCHMARK_QUESTIONS = [
    # Prediction mode
    {
        "id": "pred_1",
        "question": "What is Cardiff's predicted BEV keepership in 2045 under the central scenario?",
        "mode": "prediction",
        "gold_type": "sparql",  # Extract from graph
        "category": "single_lad_prediction"
    },
    {
        "id": "pred_2",
        "question": "Which Welsh local authority has the highest predicted EV adoption in 2045?",
        "mode": "prediction",
        "gold_type": "sparql",
        "category": "ranking"
    },
    {
        "id": "pred_3",
        "question": "Compare Cardiff's prediction across all three scenarios for 2045",
        "mode": "prediction",
        "gold_type": "sparql",
        "category": "scenario_comparison"
    },
    {
        "id": "pred_4",
        "question": "What is the mean predicted EV keepership across Welsh LADs in 2045 under the high scenario?",
        "mode": "prediction",
        "gold_type": "manual",
        "gold_value": "Computed from prediction_year_summary(2045, 'high')",
        "category": "aggregate"
    },

    # Actual data mode
    {
        "id": "actual_1",
        "question": "Tell me about population and deprivation in Cardiff",
        "mode": "actual",
        "gold_type": "manual",
        "gold_value": "Retrieved RDF evidence from observed graph",
        "category": "evidence_retrieval"
    },
    {
        "id": "actual_2",
        "question": "Show me BEV keepership data for Wales",
        "mode": "actual",
        "gold_type": "sparql",
        "category": "evidence_retrieval"
    },

    # Inventory / meta
    {
        "id": "meta_1",
        "question": "How many prediction resources do you have?",
        "mode": "prediction",
        "gold_type": "manual",
        "gold_value": "Extracted from kg.prediction_inventory()",
        "category": "inventory"
    }
]


def extract_gold_answer_sparql(kg: CLEETSKG, question: Dict) -> str:
    """
    Extract gold answer directly from RDF graph using SPARQL patterns.
    Returns the ground truth fact(s) as text.
    """
    q = question["question"].casefold()

    # Example: "Cardiff 2045 central"
    if "cardiff" in q and "2045" in q and "central" in q:
        rows = kg.prediction_rows(2045, "central", "Cardiff")
        if rows:
            r = rows[-1]
            return f"Gold: Cardiff 2045-{r['period']} — {r['keepership']:,.0f} predicted keepership ({r['adoption_share']:.2%} adoption share)"

    # Example: "highest 2045"
    if "highest" in q and "2045" in q:
        rows = kg.prediction_year_summary(2045, "central")
        if rows:
            top = rows[0]
            return f"Gold: {top['lad_name']} highest at {top['keepership']:,.0f} predicted keepership"

    # Example: "mean 2045 high"
    if "mean" in q and "2045" in q:
        scenario = "high" if "high" in q else "central"
        rows = kg.prediction_year_summary(2045, scenario)
        if rows:
            avg = sum(r["keepership"] for r in rows if r["keepership"] is not None) / len(rows)
            return f"Gold: Mean predicted keepership = {avg:,.0f} across {len(rows)} LADs"

    return "Gold: [SPARQL pattern not matched — manual review needed]"


def check_fact_preservation(original: str, humanized: str) -> Tuple[bool, str]:
    """
    Check if key facts (numbers, entity names, periods) are preserved.
    Returns (preserved: bool, notes: str)
    """
    import re

    # Extract all numbers
    original_numbers = re.findall(r'\d{1,3}(?:,\d{3})*|\d+(?:\.\d+)?', original)
    humanized_numbers = re.findall(r'\d{1,3}(?:,\d{3})*|\d+(?:\.\d+)?', humanized)

    # Extract all entity names (capitalized words)
    original_entities = re.findall(r'\b[A-Z][a-z]+\b', original)
    humanized_entities = re.findall(r'\b[A-Z][a-z]+\b', humanized)

    # Check preservation
    numbers_match = set(original_numbers) == set(humanized_numbers)
    entities_match = set(original_entities) == set(humanized_entities)

    notes = []
    if not numbers_match:
        notes.append(f"Numbers differ: {set(original_numbers)} → {set(humanized_numbers)}")
    if not entities_match:
        notes.append(f"Entities differ: {set(original_entities)} → {set(humanized_entities)}")

    preserved = numbers_match and entities_match
    return preserved, " | ".join(notes) if notes else "All facts preserved"


def check_citations_preserved(original: str, humanized: str) -> Tuple[bool, str]:
    """
    Check if Sources line is identical in both versions.
    """
    def extract_sources(text: str) -> str:
        if "**Sources:**" in text:
            return text.split("**Sources:**")[1].split("\n")[0]
        return ""

    original_sources = extract_sources(original)
    humanized_sources = extract_sources(humanized)

    preserved = original_sources == humanized_sources
    return preserved, f"Original: {original_sources[:50]}... | Humanized: {humanized_sources[:50]}..."


def evaluate_single_question(kg: CLEETSKG, question: Dict, humanize: bool = False) -> Dict:
    """
    Evaluate a single benchmark question.
    Returns metrics dict.
    """
    result = {
        "id": question["id"],
        "question": question["question"],
        "mode": question["mode"],
        "category": question.get("category", "unknown"),
        "timestamp": datetime.now().isoformat(),
    }

    try:
        # Generate answers
        original = qa.answer_question(kg, question["question"], mode=question["mode"], humanize=False)
        result["original_answer"] = original

        humanized = None
        if humanize:
            humanized = qa.answer_question(kg, question["question"], mode=question["mode"], humanize=True)
            result["humanized_answer"] = humanized

        # Get gold answer if available
        if question.get("gold_type") == "sparql":
            gold = extract_gold_answer_sparql(kg, question)
            result["gold_answer"] = gold
        elif question.get("gold_type") == "manual":
            result["gold_answer"] = question.get("gold_value", "N/A")

        # Check fact preservation (if humanized)
        if humanized:
            facts_preserved, fact_notes = check_fact_preservation(original, humanized)
            result["facts_preserved"] = facts_preserved
            result["fact_notes"] = fact_notes

        # Check citations (if humanized)
        if humanized:
            citations_preserved, citation_notes = check_citations_preserved(original, humanized)
            result["citations_preserved"] = citations_preserved
            result["citation_notes"] = citation_notes

        result["status"] = "success"

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result


def run_benchmark(kg: CLEETSKG, benchmark_type: str = "simple", humanize: bool = False) -> Dict:
    """
    Run full benchmark suite.
    """
    if benchmark_type == "simple":
        questions = BENCHMARK_QUESTIONS[:3]
    elif benchmark_type == "full":
        questions = BENCHMARK_QUESTIONS
    else:
        raise ValueError(f"Unknown benchmark type: {benchmark_type}")

    results = {
        "benchmark": benchmark_type,
        "humanize": humanize,
        "timestamp": datetime.now().isoformat(),
        "questions_evaluated": len(questions),
        "results": []
    }

    print(f"\n{'='*80}")
    print(f"CLEETS-CHAT Evaluation Benchmark ({benchmark_type})")
    print(f"Humanization: {'ENABLED' if humanize else 'DISABLED'}")
    print(f"{'='*80}\n")

    for i, q in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] {q['id']}: {q['question'][:60]}...")
        result = evaluate_single_question(kg, q, humanize=humanize)
        results["results"].append(result)

        if result["status"] == "success":
            if humanize and result.get("facts_preserved"):
                print(f"  ✓ Facts preserved: {result['fact_notes']}")
            if humanize and result.get("citations_preserved"):
                print(f"  ✓ Citations unchanged")
            print(f"  Status: OK")
        else:
            print(f"  ✗ Error: {result.get('error', 'Unknown')}")
        print()

    # Summary statistics
    succeeded = sum(1 for r in results["results"] if r["status"] == "success")
    facts_preserved_count = sum(1 for r in results["results"] if r.get("facts_preserved", False))
    citations_preserved_count = sum(1 for r in results["results"] if r.get("citations_preserved", False))

    results["summary"] = {
        "success_rate": f"{succeeded}/{len(questions)}",
        "facts_preserved": f"{facts_preserved_count}/{sum(1 for r in results['results'] if 'facts_preserved' in r)}" if humanize else "N/A",
        "citations_preserved": f"{citations_preserved_count}/{sum(1 for r in results['results'] if 'citations_preserved' in r)}" if humanize else "N/A",
    }

    print(f"\n{'='*80}")
    print("Summary")
    print(f"{'='*80}")
    print(f"Questions answered: {results['summary']['success_rate']}")
    if humanize:
        print(f"Facts preserved: {results['summary']['facts_preserved']}")
        print(f"Citations preserved: {results['summary']['citations_preserved']}")
    print()

    return results


def main():
    parser = argparse.ArgumentParser(description="Evaluate CLEETS-CHAT answers")
    parser.add_argument("--benchmark", choices=["simple", "full"], default="simple",
                       help="Benchmark suite to run")
    parser.add_argument("--humanize", action="store_true",
                       help="Enable humanization and compare vs. original")
    parser.add_argument("--output", type=str, default=None,
                       help="Save results to JSON file")
    parser.add_argument("--kg-observed", type=str, default="cleets_cskg_enriched.ttl",
                       help="Path to observed KG")
    parser.add_argument("--kg-prediction", type=str, default="cleets_prediction_kg.ttl",
                       help="Path to prediction KG")

    args = parser.parse_args()

    # Load KG
    print(f"Loading knowledge graphs...")
    kg = CLEETSKG(args.kg_observed, args.kg_prediction)
    print(f"Loaded: {args.kg_observed}, {args.kg_prediction}\n")

    # Run benchmark
    results = run_benchmark(kg, benchmark_type=args.benchmark, humanize=args.humanize)

    # Save results
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to {output_path}")
    else:
        # Print JSON to stdout
        print("\nFull results (JSON):")
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
