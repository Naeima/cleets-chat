# CLEETS-CHAT: Stakeholder Feedback & Continuous Improvement Workflow

This guide explains how to collect stakeholder feedback, analyze it, and use it to improve the QA system over time.

## Overview

The feedback system enables:
- Stakeholders to score answers 1-10 directly in the dashboard
- Collection of optional notes on why scores are given
- Automated analysis of feedback patterns
- Data-driven recommendations for prompt/template improvements
- Tracking of humanization effectiveness

## Quick Start: Enable Feedback Collection

### 1. Switch to Feedback-Enabled Dashboard

```bash
# Use the new dashboard with feedback UI
python app.py
# Open http://localhost:8050
```

**What's New:**
- 1-10 scoring slider below each answer
- Optional notes field for suggestions
- Green "Submit Feedback" button
- Feedback status confirmation

### 2. Collect Feedback from Stakeholders

Share this URL with Welsh local authorities / policy stakeholders:
```
http://localhost:8050  (or your deployed URL)
```

**Each stakeholder should:**
1. Ask questions about their LAD
2. Read the answer
3. Rate 1-10 (1 = Poor, 10 = Excellent)
4. Optionally add notes
5. Click "Submit Feedback"

### 3. Analyze Feedback

Run the analysis script:
```bash
python analyze_feedback.py
```

**Output:**
- Console report (average scores, trends, recommendations)
- `feedback_report.json` (machine-readable analysis)
- `feedback.csv` (raw data for stakeholder sharing)

## Feedback System Architecture

### Storage: SQLite Database

All feedback stored in `cleets_feedback.db`:

```sql
CREATE TABLE feedback (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,              -- When feedback was submitted
    question TEXT,               -- The question asked
    answer TEXT,                 -- First 500 chars of answer
    score INTEGER,               -- 1-10 rating
    mode TEXT,                   -- 'actual' or 'prediction'
    humanized BOOLEAN,           -- Whether humanization was enabled
    lad_clicked TEXT,            -- Which LAD on map (if clicked)
    metric TEXT,                 -- Which metric was displayed
    notes TEXT                   -- Optional user notes
);
```

### Feedback Collection Code

**Dashboard** (`app.py`):
- Adds score slider and notes textarea
- Stores last answer in browser (`dcc.Store`)
- Sends feedback to `save_feedback()` on submit

**Backend** (`app.py`):
```python
def save_feedback(question, answer, score, mode, humanized, ...):
    """Save to cleets_feedback.db"""
```

## Analysis Workflow

### Phase 1: Collect Initial Batch

**Goal:** 50-100 feedback responses

```bash
# Run dashboard for 2-3 weeks
python app.py

# Stakeholders interact:
# - Ask 5-10 questions each
# - Rate answers
# - Optional notes
```

### Phase 2: Analyze Results

Run analysis after first batch:

```bash
python analyze_feedback.py

# Outputs:
# ✓ feedback_report.json
# ✓ feedback.csv
# ✓ Console report
```

**Key metrics to track:**

| Metric | Target | Action if Low |
|--------|--------|--------------|
| Avg Score | >= 7.5 | Review constraint prompt |
| Humanization Benefit | >= +0.5 | Effective; keep enabled |
| Poor Answers (< 5) | <= 10% | Review low-scoring questions |
| Mode Parity | Actual = Prediction | Ensure both modes equally good |

### Phase 3: Identify Improvements

**Common patterns in feedback:**

**Pattern A: Low scores on prediction questions**
```
Example: "Compare Cardiff across scenarios"
Avg Score: 4.2/10
Issue: Template doesn't show comparison clearly
Action: Refine prediction_answer() template to add side-by-side table
```

**Pattern B: Humanization not helping**
```
Humanized Avg: 6.1
Templated Avg: 7.2
Issue: Constraint prompt is too aggressive
Action: Review HUMANIZATION_PROMPT in qa_with_humanization.py
```

**Pattern C: LAD-specific issues**
```
Example: "Tell me about Powys"
Multiple scores: 3, 4, 5 (all low)
Issue: Sparse data for rural LAD
Action: Add data quality note in answer template
```

### Phase 4: Implement Improvements

Make targeted changes:

```python
# Example: Improve prediction_answer() template

# BEFORE:
def prediction_answer(kg, question, lad):
    keepership = kg.get_keepership(2045, lad)
    return f"In 2045, {lad} will have {keepership} BEVs."

# AFTER:
def prediction_answer(kg, question, lad):
    central = kg.get_keepership(2045, lad, 'central')
    high = kg.get_keepership(2045, lad, 'high')
    low = kg.get_keepership(2045, lad, 'low')
    return f"""
In 2045, {lad} is predicted to have:
- Central scenario: {central:,} BEVs
- High scenario: {high:,} BEVs
- Low scenario: {low:,} BEVs
    """.strip()
```

### Phase 5: Re-evaluate

After changes:

```bash
# Collect another 50-100 responses
python app.py

# Analyze again
python analyze_feedback.py

# Compare:
# Old report: avg 6.8/10
# New report: avg 7.4/10
# → Improvement: +0.6 points
```

## Strategies for Prompt Improvement

### Strategy 1: Refine Templates (qa.py)

**When:** Templated answers score consistently low

```python
# qa.py: actual_answer() or prediction_answer()

# Add:
- Clearer structure (bullet points, tables)
- Context (why this metric matters)
- Comparisons (vs other LADs, vs previous year)
- Disclaimers (data limitations, uncertainty)
```

### Strategy 2: Tune Humanization (qa_with_humanization.py)

**When:** Humanized scores are lower than expected

```python
# qa_with_humanization.py: HUMANIZATION_PROMPT

# Possible adjustments:
- "Only rephrase 30% of sentences" (keep more original wording)
- "Focus on clarity, not elegance" (simpler language)
- "Add exactly one sentence of practical context" (ground in reality)
```

### Strategy 3: Add Data Quality Indicators

**When:** Stakeholders complain about missing/outdated data

```python
# Add to answers:
def add_data_quality_notes(answer, lad, year):
    if not has_recent_data(lad):
        answer += "\n⚠️ Data for this LAD is >2 years old."
    return answer
```

### Strategy 4: Context from Feedback Notes

**Extract insights from optional notes:**

```bash
# Analyze notes field for themes:
grep "unclear" feedback.csv → Template clarity issue
grep "missing" feedback.csv → Data completeness issue
grep "too" feedback.csv     → Verbosity issue
```

## Automated Recommendations

The `analyze_feedback.py` script automatically suggests:

### High-Priority Issues
- Mode with avg < 6.0
- Humanization backfiring (templated > humanized by 0.5+)
- > 15% poor answers

### Medium-Priority Improvements
- Humanization working well (upgrade to default)
- Consistent mode-specific patterns
- Stakeholder feedback themes

### Low-Priority Observations
- Stable scores across modes
- Humanization neutral (mixed results)
- Data quality concerns

## A/B Testing with Feedback

### Setup: Compare Two Versions

```bash
# Version A: Current constraint prompt
python app.py
# Collect 50 responses over Week 1

# Analyze
python analyze_feedback.py > report_v1.json

# Version B: Modified prompt
# Edit qa_with_humanization.py
# Deploy new version
python app.py
# Collect 50 responses over Week 2

# Compare
python analyze_feedback.py > report_v2.json

# Result: Which version scored higher?
# Use this to decide which prompt to keep
```

### Track Changes

Create a changelog:

```
CHANGELOG.md:

## 2025-10-15
- Refined prediction_answer() template
- Avg score improved 6.8 → 7.4
- Feedback: "Much clearer comparison"

## 2025-09-30
- Adjusted humanization prompt (reduced rewriting)
- Humanized avg improved 6.1 → 7.0
- Feedback: "Less awkward phrasing"
```

## Metrics Dashboard (Optional)

For long-term tracking, create a live dashboard:

```python
# metrics_dashboard.py (optional)
import dash
import plotly.express as px
import pandas as pd

# Load feedback over time
df = load_feedback_as_dataframe()

# Plot:
- Score over time (trend)
- Score by mode (bar chart)
- Humanization effectiveness (histogram)
- Notes themes (word cloud)
```

## Stakeholder Communication

### Email Template: Share Results

```
Subject: CLEETS-CHAT Feedback Results - Help Shape EV Policy

Dear Stakeholders,

Thank you for scoring 75 CLEETS-CHAT answers! Here's what we learned:

📊 Your ratings: Avg 7.2/10 (75% rated 6+)
✓ Most helpful: Scenario comparisons (Avg 7.8)
⚠️  Needs work: LAD-specific trends (Avg 6.1)

We've updated the system based on your feedback:
- Clearer comparison tables
- More context on data age
- Better phrasing on uncertain predictions

Next steps: Test the improved version in 2-3 weeks.

Questions? Reply to this email or open an issue on GitHub.

Best,
Naeima
```

### Feedback Report: Share CSV

Share `feedback.csv` with stakeholders:
- Shows all questions + scores
- Identifies patterns they recognize
- Builds buy-in for iterative improvements

## Continuous Improvement Cycle

```
1. Deploy Dashboard
   ↓
2. Collect Feedback (50-100 responses)
   ↓
3. Analyze Results
   ↓
4. Identify Top Issues
   ↓
5. Implement Changes
   ↓
6. Re-test with Stakeholders
   ↓
7. Track Improvement → Go to 2
```

**Timeline:**
- Week 1-2: Initial collection
- Week 3: Analysis + recommendations
- Week 4: Implement changes
- Week 5: Re-test + measure improvement

## Troubleshooting

### "No feedback is being saved"

**Check:**
```bash
sqlite3 cleets_feedback.db "SELECT COUNT(*) FROM feedback;"
```

If empty:
1. Verify button click registered (browser console)
2. Check file permissions: `ls -la cleets_feedback.db`
3. Restart dashboard: `python app.py`

### "Scores don't match my expected quality"

**Possible causes:**
- Stakeholder confusion on scale (explain 1-10 range)
- Inconsistent rubric (provide scoring guidance)
- Data quality issues (add disclaimers to answers)

### "Humanization scores are inconsistent"

**Debug:**
```bash
sqlite3 cleets_feedback.db \
  "SELECT mode, humanized, AVG(score) FROM feedback GROUP BY mode, humanized;"
```

If humanized < templated:
1. Review HUMANIZATION_PROMPT in qa_with_humanization.py
2. Check if constraint is too strict
3. Try less aggressive rewording

## Best Practices

1. **Establish Baseline:** Collect 50+ responses before making changes
2. **Change One Thing at a Time:** Isolate effect of each improvement
3. **Document Changes:** Keep `CHANGELOG.md` for reproducibility
4. **Share Results:** Email stakeholders quarterly with improvements
5. **Celebrate Progress:** Highlight score improvements (6.8 → 7.4 is real progress!)

## Next Steps

1. ✅ Deploy feedback-enabled dashboard
2. ✅ Collect initial feedback batch (aim for 50+ responses)
3. ✅ Run analysis: `python analyze_feedback.py`
4. ✅ Review recommendations
5. ✅ Implement top 2-3 improvements
6. ✅ Re-collect feedback + measure improvement
7. ✅ Share results with stakeholders

---

**Questions?** See `README_HUMANIZATION.md` for prompt details or open an issue on GitHub.
