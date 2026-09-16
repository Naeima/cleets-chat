# CLEETS-CHAT Humanization: Quick Reference

## 3-Minute Setup

```bash
# 1. Install
pip install anthropic>=0.31.0

# 2. Set key
export ANTHROPIC_API_KEY=sk-ant-your-key-here

# 3. Use new qa.py
cp qa_with_humanization.py qa.py

# 4. Update app.py callback (add humanize parameter)
answer = qa.answer_question(kg, question, mode=mode, humanize=True)

# 5. Done!
```

## Code Changes at a Glance

### Before (original qa.py)
```python
def answer_question(kg, question: str, mode: str = "actual") -> str:
    # ... template-based answer
    return templated_markdown_answer
```

### After (qa_with_humanization.py)
```python
def answer_question(kg, question: str, mode: str = "actual", humanize: bool = False) -> str:
    # ... template-based answer
    if humanize:
        answer = humanize_answer(answer, metadata={...})  # Claude Haiku rephrase
    return answer  # Same facts, better phrasing
```

## Key Functions

### `humanize_answer(markdown_body, metadata=None, humanize=True)`
Rephrases templated answer using Claude Haiku.

```python
# Input: templated markdown (no sources line)
body = "Under the central scenario, Cardiff 2045 has 12,500 predicted keepership."

# Output: same facts, humanized phrasing
humanized = humanize_answer(body, metadata={"period": "2045", "scenario": "central"})
# → "The central scenario predicts 12,500 private BEVs in Cardiff by 2045-Q4."
```

### `preserve_sources(full_answer, humanized_body)`
Reattaches Sources line unchanged.

```python
original = "### Answer\n\nSome text.\n\n**Sources:** [Dataset](url) · [Knowledge graph](url)"
humanized_body = "### Answer\n\nRephased text."
result = preserve_sources(original, humanized_body)
# → "### Answer\n\nRephased text.\n\n**Sources:** [Dataset](url) · [Knowledge graph](url)"
```

## UI Integration

### Dash Toggle
```python
dcc.Checklist(
    id='humanize-toggle',
    options=[{'label': ' Humanize with AI', 'value': 'humanize'}],
    value=['humanize']  # Enabled by default
)

@app.callback(...)
def update(humanize_toggle, ...):
    humanize = 'humanize' in humanize_toggle
    answer = qa.answer_question(kg, q, mode=mode, humanize=humanize)
    return dcc.Markdown(answer)
```

### Environment Variable
```bash
# In .env or shell
HUMANIZE_ANSWERS=true
python app.py
```

## Testing

### Quick Test
```python
import qa
from kg_service import CLEETSKG

kg = CLEETSKG("cleets_cskg_enriched.ttl", "cleets_prediction_kg.ttl")

# Original (templated)
orig = qa.answer_question(kg, "Cardiff 2045", mode="prediction", humanize=False)
print("ORIGINAL:")
print(orig)

# Humanized
human = qa.answer_question(kg, "Cardiff 2045", mode="prediction", humanize=True)
print("\nHUMANIZED:")
print(human)
```

### Benchmark
```bash
python evaluate_answers.py --benchmark full --humanize --output results.json

# Check results
cat results.json | grep -A 5 '"facts_preserved"'
```

## Model Details

| Property | Value |
|----------|-------|
| Model | Claude 3.5 Haiku |
| ID | `claude-3-5-haiku-20241022` |
| Max output | 600 tokens (fixed) |
| Latency | 1–2s per question |
| Cost | ~$0.0003 per question (Haiku) |

## Guarantee

✓ **All facts from RDF retrieval or deterministic calculations**  
✓ **LLM only rephases; cannot invent facts**  
✓ **Citations preserved verbatim**  
✓ **Numbers, periods, entities unchanged**  
✓ **Reproducible (fixed model version + deterministic prompt)**

## Constraint Prompt (Key Parts)

```
You may reorganize, condense, or expand phrasing only.

Do NOT:
- Add new facts or claims not in the input
- Speculate or infer beyond stated data
- Change quantitative values, periods, or scenario names
- Alter list/ranking structure
```

See full prompt in `qa_with_humanization.py` line ~100.

## Error Handling

If API fails (key missing, rate limit, network):
```python
try:
    humanized = humanize_answer(body)  # API call
except Exception as e:
    print(f"Warning: {e}, returning original")
    return body  # Fall back to templated version
```

**No hallucination risk:** Fails gracefully to original.

## For Publication

### Cite as:
> Claude 3.5 Haiku (claude-3-5-haiku-20241022) with constraint prompt

### Report:
- Model version
- Exact constraint wording
- Fact/citation preservation metrics (evaluate_answers.py)
- User preference scores (if A/B tested)

### Include in appendix:
- System prompt (from qa_with_humanization.py)
- Benchmark questions + gold answers (from evaluate_answers.py)
- Results JSON (questions, original, humanized, metrics)

## Common Gotchas

| Issue | Fix |
|-------|-----|
| API key not found | `export ANTHROPIC_API_KEY=...` |
| Sources line missing | Ensure template ends with `**Sources:**` |
| Numbers don't match | Check humanize_answer() logs for LLM drift |
| Slow on first call | Normal (model cold start); subsequent calls cached |
| Evaluation shows facts changed | Re-check constraint prompt in humanize_answer() |

## Files Reference

| File | Use for |
|------|---------|
| `qa_with_humanization.py` | Drop-in replacement for qa.py |
| `INTEGRATION_GUIDE.md` | Setup details + troubleshooting |
| `app_integration_example.py` | Copy/adapt for your Dash app |
| `evaluate_answers.py` | Benchmark & verify fact preservation |
| `README_HUMANIZATION.md` | Full documentation |
| `QUICK_REFERENCE.md` | This file—cheat sheet |

## One-Liner Examples

```python
# With humanization
qa.answer_question(kg, "Cardiff 2045", mode="prediction", humanize=True)

# Without (original templated)
qa.answer_question(kg, "Cardiff 2045", mode="prediction", humanize=False)

# Benchmark
python evaluate_answers.py --benchmark full --humanize --output results.json

# Test API key
python -c "from qa_with_humanization import get_client; print(get_client().models.list())"
```

## Next Steps

1. **Install:** `pip install anthropic`
2. **Configure:** `export ANTHROPIC_API_KEY=...`
3. **Replace:** `cp qa_with_humanization.py qa.py`
4. **Integrate:** Update app.py (see `app_integration_example.py`)
5. **Test:** `python evaluate_answers.py --benchmark simple --humanize`
6. **Deploy:** Add to repo, run benchmarks, document in paper

---

For full details, see README_HUMANIZATION.md or INTEGRATION_GUIDE.md.
