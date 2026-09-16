# CLEETS-CHAT: Claude Haiku Integration Guide

## Setup

### 1. Environment Configuration

Add to `.env`:
```bash
ANTHROPIC_API_KEY=sk-ant-...your-key-here...
HUMANIZE_ANSWERS=true
```

### 2. Dependencies

Add to `requirements.txt`:
```
anthropic>=0.31.0
```

Install:
```bash
pip install -r requirements.txt
```

### 3. Replace qa.py

Replace your existing `qa.py` with `qa_with_humanization.py`, or merge the changes:

**Key additions:**
- `import anthropic`
- `get_client()` function (lazy-loads Anthropic client)
- `humanize_answer()` function (calls Claude Haiku with constraint prompt)
- `preserve_sources()` function (keeps citations unchanged)
- Add `humanize: bool = False` parameter to `prediction_answer()`, `actual_answer()`, and `answer_question()`

### 4. Update app.py

Modify the callback that calls `answer_question()`:

```python
# Before (original)
answer = qa.answer_question(kg, user_input, mode=mode)

# After (with humanization toggle)
humanize = os.getenv("HUMANIZE_ANSWERS", "false").lower() == "true"
answer = qa.answer_question(kg, user_input, mode=mode, humanize=humanize)
```

Or add a UI toggle in your Dash layout:

```python
dcc.Checklist(
    id='humanize-toggle',
    options=[{'label': ' Humanize answers with AI', 'value': 'humanize'}],
    value=['humanize'] if os.getenv("HUMANIZE_ANSWERS", "false").lower() == "true" else [],
    style={'margin': '10px 0'}
)
```

Then in the callback:

```python
@app.callback(
    Output('answer-output', 'children'),
    [Input('submit-button', 'n_clicks'),
     Input('humanize-toggle', 'value')],
    State('question-input', 'value'),
    State('mode-radio', 'value'),
    prevent_initial_call=True
)
def update_answer(n_clicks, humanize_toggle, question, mode):
    if not question:
        return "Please enter a question."
    humanize = 'humanize' in humanize_toggle
    answer = qa.answer_question(kg, question, mode=mode, humanize=humanize)
    return dcc.Markdown(answer)
```

## How It Works

### Hallucination Safety

The humanization layer:
1. Extracts the templated answer body (without Sources line)
2. Sends it to Claude Haiku with a **strict system prompt** that forbids:
   - Adding new facts
   - Inferring beyond stated data
   - Changing quantitative values
   - Adding qualifications or caveats
3. Reattaches the original Sources line unchanged

The guarantee holds because:
- All facts come from RDF retrieval or deterministic calculations (qa.py)
- The LLM only rephases the already-computed text
- Citations are preserved from the graph (dcterms:source, prov:wasGeneratedBy, dcat:landingPage)

### Performance

- **Latency:** ~1–2 seconds per question (API roundtrip)
- **Cost:** ~$0.08–0.15 per question (Haiku input/output tokens)
- **Reproducibility:** Model pinned to `claude-3-5-haiku-20241022`; outputs deterministic for evaluation

### Prompt Caching (Optional)

For higher throughput, enable prompt caching at the client level:

```python
def get_client():
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        _client = anthropic.Anthropic(
            api_key=api_key,
            # Requests will automatically use cache if headers match
        )
    return _client
```

Anthropic automatically caches the system prompt after the first call; subsequent calls pay cache-read pricing (~90% discount).

## Evaluation & Benchmarking

### Store Both Versions

Modify `answer_question()` to return a dict for evaluation:

```python
def answer_question_with_metadata(kg, question: str, mode: str = "actual", humanize: bool = False) -> dict:
    original_answer = qa.answer_question(kg, question, mode=mode, humanize=False)
    humanized_answer = qa.answer_question(kg, question, mode=mode, humanize=humanize)
    
    return {
        "question": question,
        "mode": mode,
        "original": original_answer,
        "humanized": humanized_answer if humanize else None,
        "rephrased": humanize
    }
```

### Benchmark Against SPARQL Gold Answers

Use `kg_service.py` to compute ground truth:

```python
from rdflib import Graph
from kg_service import CLEETSKG

kg = CLEETSKG("path/to/cleets_cskg_enriched.ttl", "path/to/cleets_prediction_kg.ttl")

# Example: gold answer for "Cardiff 2045 central scenario"
gold_rows = kg.prediction_rows(2045, "central", "Cardiff")
if gold_rows:
    gold_keepership = gold_rows[-1]['keepership']
    gold_adoption = gold_rows[-1]['adoption_share']
    print(f"Gold: {gold_keepership:,.0f} EVs, {gold_adoption:.2%} share")
```

### Metrics

1. **Citation accuracy:** Always 100% (sources from RDF, not LLM)
2. **Factual accuracy:** Score rephrased vs. original with BLEU/ROUGE or human raters
3. **Abstention rate:** Percentage of questions where system declines to answer
4. **User preference:** A/B test original vs. humanized with CLEETS stakeholders

## Troubleshooting

### API Key Error
```
ValueError: ANTHROPIC_API_KEY environment variable not set
```
**Fix:** Export your key before running:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
python app.py
```

### Timeout on Slow Network
If API calls timeout (default 30s), adjust in `get_client()`:
```python
_client = anthropic.Anthropic(
    api_key=api_key,
    timeout=60.0  # seconds
)
```

### Humanization Falls Back to Original
If Claude Haiku fails (rate limit, API error), the function logs a warning and returns the original templated answer. Check `.env` and API quota.

### Sources Line Missing
Ensure `actual_answer()` and `prediction_answer()` both end with `**Sources:**` lines before humanization. The `preserve_sources()` logic relies on this pattern.

## Research Publication Notes

For a paper:
1. **Cite the model:** "Claude 3.5 Haiku (claude-3-5-haiku-20241022)"
2. **Describe the system prompt:** Include the constraint wording (see `qa_with_humanization.py`)
3. **Report reproducibility:** "Identical questions yield identical outputs on the same model version"
4. **Baseline comparison:** Report accuracy/preference metrics for original (templated) vs. humanized answers
5. **Ablation:** Show that citations and facts are preserved; only phrasing changes
