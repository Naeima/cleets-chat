#!/usr/bin/env python3
"""
CLEETS-CHAT Feedback Analysis: Analyze stakeholder scores to improve answers

This script processes feedback collected from the dashboard and provides:
- Average scores by mode (actual vs prediction)
- Humanization effectiveness (humanized vs templated)
- Identify low-scoring answers for improvement
- Trend analysis over time
- Recommendations for prompt refinement

Run:
    python analyze_feedback.py [--output report.json] [--export feedback.csv]
"""

import sqlite3
import json
import csv
import argparse
from datetime import datetime
from collections import defaultdict
from pathlib import Path

FEEDBACK_DB = "cleets_feedback.db"

def load_feedback(db_path=FEEDBACK_DB):
    """Load all feedback from database."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('SELECT * FROM feedback ORDER BY timestamp DESC')
    columns = [description[0] for description in c.description]
    feedback = [dict(zip(columns, row)) for row in c.fetchall()]
    conn.close()
    return feedback

def analyze_feedback(feedback):
    """Analyze feedback and generate statistics."""
    if not feedback:
        return {
            "status": "no_data",
            "message": "No feedback collected yet"
        }

    # Basic statistics
    scores = [f['score'] for f in feedback if f['score']]
    avg_score = sum(scores) / len(scores) if scores else 0

    # Score distribution
    score_dist = defaultdict(int)
    for f in feedback:
        if f['score']:
            score_dist[f['score']] += 1

    # Mode analysis
    mode_stats = defaultdict(lambda: {'count': 0, 'scores': []})
    for f in feedback:
        mode = f['mode'] or 'unknown'
        mode_stats[mode]['count'] += 1
        if f['score']:
            mode_stats[mode]['scores'].append(f['score'])

    for mode in mode_stats:
        scores = mode_stats[mode]['scores']
        mode_stats[mode]['avg_score'] = sum(scores) / len(scores) if scores else 0
        mode_stats[mode]['min_score'] = min(scores) if scores else 0
        mode_stats[mode]['max_score'] = max(scores) if scores else 0

    # Humanization effectiveness
    humanized_feedback = [f for f in feedback if f['humanized']]
    templated_feedback = [f for f in feedback if not f['humanized']]

    humanized_scores = [f['score'] for f in humanized_feedback if f['score']]
    templated_scores = [f['score'] for f in templated_feedback if f['score']]

    humanized_avg = sum(humanized_scores) / len(humanized_scores) if humanized_scores else 0
    templated_avg = sum(templated_scores) / len(templated_scores) if templated_scores else 0

    # Low-scoring answers (< 5)
    low_scoring = [f for f in feedback if f['score'] and f['score'] < 5]

    # Answers with notes
    answered_with_notes = [f for f in feedback if f['notes']]

    return {
        "status": "success",
        "summary": {
            "total_responses": len(feedback),
            "avg_score": round(avg_score, 2),
            "score_range": f"{min(scores) if scores else 0} - {max(scores) if scores else 0}",
            "score_distribution": dict(sorted(score_dist.items()))
        },
        "mode_analysis": {
            mode: {
                "count": stats['count'],
                "avg_score": round(stats['avg_score'], 2),
                "min_score": stats['min_score'],
                "max_score": stats['max_score']
            }
            for mode, stats in sorted(mode_stats.items())
        },
        "humanization_effectiveness": {
            "humanized": {
                "count": len(humanized_feedback),
                "avg_score": round(humanized_avg, 2),
                "responses": len(humanized_scores)
            },
            "templated": {
                "count": len(templated_feedback),
                "avg_score": round(templated_avg, 2),
                "responses": len(templated_scores)
            },
            # Only meaningful when both groups have scores.
            "humanization_benefit": (round(humanized_avg - templated_avg, 2)
                                     if humanized_scores and templated_scores else None)
        },
        "quality_indicators": {
            "excellent_count": len([s for s in scores if s >= 9]),
            "good_count": len([s for s in scores if 7 <= s < 9]),
            "fair_count": len([s for s in scores if 5 <= s < 7]),
            "poor_count": len([s for s in scores if s < 5])
        },
        "areas_for_improvement": {
            "low_scoring_answers": [
                {
                    "question": f['question'],
                    "score": f['score'],
                    "mode": f['mode'],
                    "humanized": f['humanized'],
                    "notes": f['notes']
                }
                for f in low_scoring[:5]  # Top 5 lowest-scoring
            ],
            "answers_with_feedback": len(answered_with_notes)
        },
        "recommendations": generate_recommendations(feedback, mode_stats, humanized_avg, templated_avg)
    }

def generate_recommendations(feedback, mode_stats, humanized_avg, templated_avg):
    """Generate actionable recommendations based on feedback."""
    recommendations = []

    # Mode-specific recommendations
    for mode, stats in mode_stats.items():
        if stats['avg_score'] < 6:
            recommendations.append({
                "priority": "HIGH",
                "category": f"{mode.upper()} Mode Quality",
                "issue": f"Average score in {mode} mode is {stats['avg_score']:.1f}/10",
                "action": f"Review template in {'prediction_answer()' if mode == 'prediction' else 'actual_answer()'} to clarify language or add missing context"
            })

    # Humanization recommendations (needs at least 5 scored answers in each group)
    humanized_n = len([f for f in feedback if f['humanized'] and f['score']])
    templated_n = len([f for f in feedback if not f['humanized'] and f['score']])
    if humanized_n < 5 or templated_n < 5:
        pass  # not enough evidence to compare humanised and templated answers
    elif humanized_avg > templated_avg + 0.5:
        recommendations.append({
            "priority": "MEDIUM",
            "category": "Humanization",
            "issue": f"Humanized answers score {humanized_avg - templated_avg:.1f} points higher",
            "action": "Humanization is effective; consider making it default or studying what phrases work best"
        })
    elif templated_avg > humanized_avg + 0.5:
        recommendations.append({
            "priority": "HIGH",
            "category": "Humanization",
            "issue": f"Templated answers score {templated_avg - humanized_avg:.1f} points higher",
            "action": "Review Claude Haiku constraint prompt in qa_with_humanization.py; may be too aggressive in rewording"
        })

    # Generic recommendations
    if not recommendations:
        recommendations.append({
            "priority": "LOW",
            "category": "General",
            "issue": "Scores are consistent across modes",
            "action": "Continue collecting feedback to identify patterns"
        })

    return recommendations

def export_csv(feedback, output_path="feedback.csv"):
    """Export feedback to CSV for stakeholder review."""
    if not feedback:
        print("No feedback to export")
        return

    keys = ['timestamp', 'question', 'score', 'mode', 'humanized', 'lad_clicked', 'metric', 'notes']

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()

        for row in feedback:
            filtered_row = {k: row.get(k, '') for k in keys}
            writer.writerow(filtered_row)

    print(f"✓ Exported {len(feedback)} feedback records to {output_path}")

def export_json(analysis, output_path="feedback_report.json"):
    """Export analysis report as JSON."""
    with open(output_path, 'w') as f:
        json.dump(analysis, f, indent=2)

    print(f"✓ Exported analysis report to {output_path}")

def print_report(analysis):
    """Pretty-print analysis report to console."""
    if analysis.get('status') != 'success':
        print(f"\n{analysis.get('message', 'Error')}\n")
        return

    print("\n" + "="*70)
    print(" CLEETS-CHAT Feedback Analysis Report")
    print("="*70)

    summary = analysis['summary']
    print(f"\n📊 SUMMARY")
    print(f"   Total Responses: {summary['total_responses']}")
    print(f"   Average Score: {summary['avg_score']}/10")
    print(f"   Score Range: {summary['score_range']}")
    print(f"   Distribution: ", end="")
    print(" | ".join([f"{score}: {count}✓" for score, count in sorted(summary['score_distribution'].items())]))

    print(f"\n📈 BY QUERY MODE")
    for mode, stats in analysis['mode_analysis'].items():
        print(f"   {mode.upper()}")
        print(f"      Responses: {stats['count']}")
        print(f"      Avg Score: {stats['avg_score']}/10 (min: {stats['min_score']}, max: {stats['max_score']})")

    print(f"\n🤖 HUMANIZATION IMPACT")
    humanization = analysis['humanization_effectiveness']
    print(f"   Humanized Answers: {humanization['humanized']['count']} ({humanization['humanized']['avg_score']}/10)")
    print(f"   Templated Answers: {humanization['templated']['count']} ({humanization['templated']['avg_score']}/10)")
    benefit = humanization['humanization_benefit']
    print(f"   Benefit: {benefit:+.1f} points" if benefit is not None
          else "   Benefit: n/a (need scored answers in both groups)")

    print(f"\n⭐ QUALITY BREAKDOWN")
    quality = analysis['quality_indicators']
    print(f"   Excellent (9-10): {quality['excellent_count']}")
    print(f"   Good (7-8):       {quality['good_count']}")
    print(f"   Fair (5-6):       {quality['fair_count']}")
    print(f"   Poor (< 5):       {quality['poor_count']}")

    print(f"\n🔧 AREAS FOR IMPROVEMENT")
    improvements = analysis['areas_for_improvement']
    if improvements['low_scoring_answers']:
        print(f"   Low-Scoring Answers:")
        for i, answer in enumerate(improvements['low_scoring_answers'], 1):
            print(f"\n   {i}. Q: {answer['question'][:60]}...")
            print(f"      Score: {answer['score']}/10 | Mode: {answer['mode']} | Humanized: {answer['humanized']}")
            if answer['notes']:
                print(f"      Feedback: {answer['notes'][:80]}...")

    print(f"\n💡 RECOMMENDATIONS")
    for i, rec in enumerate(analysis['recommendations'], 1):
        print(f"\n   {i}. [{rec['priority']}] {rec['category']}")
        print(f"      Issue: {rec['issue']}")
        print(f"      Action: {rec['action']}")

    print("\n" + "="*70 + "\n")

def main():
    parser = argparse.ArgumentParser(
        description="Analyze stakeholder feedback on CLEETS-CHAT answers"
    )
    parser.add_argument("--output", help="Output JSON report path", default="feedback_report.json")
    parser.add_argument("--export", help="Export feedback to CSV", default="feedback.csv")
    parser.add_argument("--db", help="Path to feedback database", default=FEEDBACK_DB)
    parser.add_argument("--no-csv", action="store_true", help="Skip CSV export")
    parser.add_argument("--no-json", action="store_true", help="Skip JSON export")

    args = parser.parse_args()

    # Load and analyze
    print("📖 Loading feedback...")
    feedback = load_feedback(args.db)

    if not feedback:
        print("⚠️  No feedback collected yet.")
        print("\nTo collect feedback:")
        print("1. Run: python app_dashboard_with_feedback.py")
        print("2. Ask questions and score answers (1-10)")
        print("3. Run this script again: python analyze_feedback.py")
        return

    print(f"✓ Loaded {len(feedback)} feedback records")

    # Analyze
    print("🔍 Analyzing feedback...")
    analysis = analyze_feedback(feedback)

    # Print to console
    print_report(analysis)

    # Export if requested
    if not args.no_csv:
        export_csv(feedback, args.export)

    if not args.no_json:
        export_json(analysis, args.output)

    print(f"\n📌 Next Steps:")
    print(f"   1. Share {args.export} with stakeholders for review")
    print(f"   2. Use recommendations above to improve prompts")
    print(f"   3. Re-run analysis after each batch of feedback: python analyze_feedback.py")

if __name__ == '__main__':
    main()
