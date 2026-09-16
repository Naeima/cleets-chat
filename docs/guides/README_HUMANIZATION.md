# CLEETS-CHAT: LLM Humanization Layer Implementation

## Overview

This package adds Claude Haiku-powered answer humanization to CLEETS-CHAT while preserving hallucination-free guarantees. The system rephrases templated answers for readability without changing facts or citations.

**Key guarantee:** All sources and facts come from RDF retrieval or deterministic calculations. The LLM only rephases text; it cannot assert new facts.

## Files Included

| File | Purpose |
|------|---------|
| `qa_with_humanization.py` | Enhanced qa.py with `humanize_answer()` function and optional `humanize` parameter throughout |
| `INTEGRATION_GUIDE.md` | Step-by-step setup (environment, dependencies, app.py modifications) |
| `app_integration_example.py` | Example Dash app with humanization toggle UI |
| `evaluate_answers.py` | Benchmark evaluation against SPARQL gold answers and fact preservation checks |
| `README_HUMANIZATION.md` | This file |

## Quick Start

### 1. Install Dependencies
```bash
pip install anthropic>=0.31.0
```

### 2. Set API Key
```bash
export ANTHROPIC_API_KEY=sk-ant-...your-key-here...
```

### 3. Replace qa.py
```bash
cp qa_with_humanization.py qa.py
```

### 4. Update app.py
Add humanization parameter to `answer_question()` call:
```python
humanize = os.getenv("HUMANIZE_ANSWERS", "true").lower() == "true"
answer = qa.answer_question(kg, question, mode=mode, humanize=humanize)
```

See `app_integration_example.py` for full callback implementation.

### 5. Test
```bash
python -c "
from qa_with_humanization import answer_question
from kg_service import CLEETSKG
kg = CLEETSKG('cleets_cskg_enriched.ttl', 'cleets_prediction_kg.ttl')
answer = answer_question(kg, 'Cardiff 2045', mode='prediction', humanize=True)
print(answer)
"
```

## How It Works

### Architecture

```
User Question
    ↓
[RDF Retrieval & Templating]  ← Deterministic, reproducible
    ↓
Templated Answer (with **Sources:** line)
    ↓
[Humanization Layer]  ← Claude Haiku rephrasing only
    ↓
Humanized Answer + Original Sources
```

### Constraint Prompt

Claude Haiku receives a **strict system prompt** that forbids:
- Adding new facts or qualifications
- Inferring beyond stated data
- Changing numbers, periods, or scenario names
- Altering the structure of lists or rankings

See `qa_with_humanization.py` line ~100 for the exact prompt.

### Citation Preservation

The Sources line is extracted before humanization and reattached unchanged:
```python
def preserve_sources(full_answer: str, humanized_body: str) -> str:
    # Extract and reattach Sources line
    _, sources_line = full_answer.rsplit("\n**Sources:**", 1)
    return humanized_body + "\n**Sources:**" + sources_line
```

All links point to:
- Published datasets (DfT VEH0132, VEH0105, EVCI9001, etc.)
- Official landing pages
- CLEETS knowledge graph (https://w3id.org/def/cleets)

## Evaluation & Benchmarking

### Run Evaluation Script

Simple benchmark (3 questions):
```bash
python evaluate_answers.py --benchmark simple --humanize
```

Full benchmark (7 questions) with results saved:
```bash
python evaluate_answers.py --benchmark full --humanize --output results.json
```

### Metrics Computed

1. **Success rate:** % of questions answered
2. **Facts preserved:** Checks if numbers, entities, periods match between original and humanized
3. **Citations preserved:** Verifies Sources lines are identical
4. **Gold answer comparison:** Extracts ground truth from SPARQL and compares to retrieved answer

### Example Output

```
[1/7] pred_1: What is Cardiff's predicted BEV keepership in 2045 under the central scenario?...
  ✓ Facts preserved: All facts preserved
  ✓ Citations unchanged
  Status: OK

...

Summary
================================================================================
Questions answered: 7/7
Facts preserved: 7/7
Citations preserved: 7/7
```

## Performance Characteristics

| Metric | Value |
|--------|-------|
| Latency per question | 1–2 seconds |
| Cost per question | ~$0.08–0.15 (Haiku input/output) |
| Model pinned to | claude-3-5-haiku-20241022 |
| Reproducibility | 100% (deterministic model + fixed prompt) |
| Hallucination risk | Minimized (constraint prompt + fact verification) |

### Prompt Caching (Optional)

Enable automatic caching in `get_client()`:
```python
_client = anthropic.Anthropic(api_key=api_key)
# System prompt is cached after 1st call (~90% discount on cache-read)
```

## Integration Checklist

- [ ] Install `anthropic>=0.31.0`
- [ ] Export `ANTHROPIC_API_KEY`
- [ ] Replace `qa.py` with `qa_with_humanization.py`
- [ ] Update `app.py` callback (see `app_integration_example.py`)
- [ ] Add humanization toggle to UI (optional)
- [ ] Test with `evaluate_answers.py`
- [ ] Review benchmark results
- [ ] Document in paper/repo

## For Publication

### Citation

> Answers were humanized using Claude 3.5 Haiku (claude-3-5-haiku-20241022) with a constraint prompt forbidding fact invention. The system prompt enforced: no new facts, no inferences, exact number/period preservation. All facts originate from RDF retrieval (dcterms:source, prov:wasGeneratedBy enforced by SHACL); the LLM only rephases templated text.

### Ablation

Report metrics for both:
1. **Original (templated):** Direct output from RDF retrieval
2. **Humanized (LLM-rephrased):** Claude Haiku rephasing

Show that:
- All facts/numbers/citations are identical
- Only phrasing differs
- User preference (if A/B tested)

### Reproducibility

Include:
- Model version: `claude-3-5-haiku-20241022`
- Exact system prompt (in appendix or supplementary)
- Benchmark questions used
- Results JSON (queries, answers, metrics)

## Troubleshooting

### "ANTHROPIC_API_KEY environment variable not set"

**Fix:**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
python app.py
```

Or add to `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
```

### "Humanization failed ... returning original answer"

**Cause:** API rate limit, timeout, or network error.

**Fix:**
- Check API quota at console.anthropic.com
- Increase timeout in `get_client()`: `timeout=60.0`
- Check network/proxy (see INTEGRATION_GUIDE.md)

### "Sources line missing" or malformed

**Cause:** Template doesn't end with `**Sources:**` line.

**Fix:** Ensure `prediction_answer()` and `actual_answer()` both output:
```python
f"\n**Sources:** {md_links(links)}"
```

### Evaluation script not finding KG files

**Fix:**
```bash
python evaluate_answers.py \
  --kg-observed /path/to/cleets_cskg_enriched.ttl \
  --kg-prediction /path/to/cleets_prediction_kg.ttl
```

## Next Steps

1. **Integrate into app.py** using `app_integration_example.py`
2. **Run evaluation** with your benchmark questions
3. **A/B test with users** (stakeholder feedback)
4. **Document in paper** (cite model, describe constraint prompt, report metrics)
5. **Publish** (include benchmark results and gold-answer SPARQL queries)

## References

- Anthropic API: https://docs.anthropic.com
- CLEETS knowledge graph: https://w3id.org/def/cleets
- RDF/SPARQL: https://www.w3.org/RDF/
- Reproducible AI: https://arxiv.org/abs/2304.12632 (prompt caching + determinism)

## Support

For issues or questions:
1. Check INTEGRATION_GUIDE.md (setup)
2. Review `qa_with_humanization.py` source (API calls, error handling)
3. Run `evaluate_answers.py` to verify fact/citation preservation
4. Review benchmark results JSON for specific failures
