# CLEETS-CHAT Dashboard: Publication Guide

## Overview

**Published dashboard:** Interactive OSM map + humanized QA chatbot for EV adoption data in Wales.

Features:
- Full-width Leaflet/Plotly choropleth map (LAD boundaries color-coded by metric)
- Toggleable metrics: predicted keepership (3 scenarios), adoption share
- Click LAD → prefill chatbot question + show popup stats
- Natural-language answers powered by Claude Haiku (humanization optional)
- Citation layer: all sources linked to official datasets
- Responsive design: mobile-friendly

## Quick Start

### 1. Install Dependencies
```bash
pip install dash plotly pandas rdflib anthropic python-dotenv
```

### 2. Set Environment
```bash
export ANTHROPIC_API_KEY=sk-ant-your-key-here
export HUMANIZE_ANSWERS=true
```

### 3. Run Dashboard
```bash
python app.py
```

Open: http://localhost:8050

## Architecture

```
┌─────────────────────────────────────┐
│   Header: CLEETS-CHAT Dashboard     │
├─────────────────────────────────────┤
│  [Metric Dropdown] ↓                │
│  ┌───────────────────────────────┐  │
│  │   Leaflet Choropleth Map      │  │  ← OSM map
│  │   (LADs colored by metric)    │  │     Click LAD →
│  │   Celtic Sea                  │  │     prefill Q
│  │   [Click to ask]              │  │
│  └───────────────────────────────┘  │
├─────────────────────────────────────┤
│  ┌───── Chat Panel (Below) ─────┐   │
│  │ [Mode Radio] [Humanize]      │   │
│  │ [Question Input]             │   │
│  │ [Submit Button]              │   │
│  │ ┌──────────────────────────┐ │   │
│  │ │  Answer Output (MD)      │ │   │ ← qa.py + humanization
│  │ │  with active source links│ │   │
│  │ └──────────────────────────┘ │   │
│  │ [Data sources footer]        │   │
│  └──────────────────────────────┘   │
└─────────────────────────────────────┘
```

## Usage: End User

1. **Select metric** from dropdown (e.g., "Predicted BEV Keepership 2045 Central")
2. **View map:** LADs colored by metric value (darker = higher)
3. **Click a LAD** on the map → Chatbot input auto-fills with "Tell me about [LAD]"
4. **Ask a question** (or press Submit on auto-filled input)
5. **View answer** with active links to source datasets

### Example Flows

**Scenario 1: Browse then ask**
1. Click metric dropdown → select "Predicted... High Scenario"
2. Map updates to show high scenario predictions
3. Click "Cardiff" on map
4. Chatbot input: "Tell me about Cardiff"
5. Submit → see Cardiff's prediction

**Scenario 2: Direct question**
1. Type in question input: "Compare Cardiff across all scenarios"
2. Select mode: "Scenario Predictions"
3. Submit → see comparison table with sources

## File Structure

```
.
├── app.py                        # Main Dash app (run this)
├── qa_with_humanization.py       # Enhanced QA engine
├── kg_service.py                 # RDF KG interface
├── cleets_cskg_enriched.ttl       # Observed data KG
├── cleets_prediction_kg.ttl       # Prediction KG (Wales removed)
├── .env                          # ANTHROPIC_API_KEY
├── requirements.txt              # Dependencies
└── README.md
```

## Deployment

### Local (Development)
```bash
python app.py
# http://localhost:8050
```

### Production (Gunicorn + Nginx)

**Dockerfile:**
```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["gunicorn", "--bind", "0.0.0.0:8050", "app:server"]
```

**Run:**
```bash
docker build -t cleets-chat-dashboard .
docker run -e ANTHROPIC_API_KEY=sk-ant-... -p 8050:8050 cleets-chat-dashboard
```

### Heroku Deployment

1. Create `Procfile`:
```
web: gunicorn app:server
```

2. Deploy:
```bash
heroku login
heroku create cleets-chat-dashboard
git push heroku main
heroku config:set ANTHROPIC_API_KEY=sk-ant-...
```

Open: https://cleets-chat-dashboard.herokuapp.com

## Customization

### Change Map Appearance
Edit `app.py` (LAD_CENTROIDS / MAP_METRICS near the top):
```python
fig.update_layout(
    mapbox=dict(
        style="open-street-map",  # Try: "carto-positron", "carto-voyager", "streets"
        ...
    )
)
```

### Add More Metrics
1. Add to `METRICS` dict:
```python
METRICS["custom_metric"] = {
    "label": "My Metric",
    "unit": "units",
    "colorscale": "Viridis",
    "description": "Custom metric description"
}
```

2. Update `create_choropleth_figure()` to compute it from KG

### Upgrade to Real GeoJSON Choropleth
Current version uses `Scattermapbox` (simplified). For publication with real LAD boundaries:

```python
# Fetch LAD GeoJSON from ONS
import geopandas as gpd

lads_geojson = gpd.read_file("https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/.../geojson")

fig = go.Figure(data=go.Choroplethmapbox(
    geojson=lads_geojson,
    locations=df['LAD'],
    z=df['metric_value'],
    colorscale=metric_info['colorscale'],
    featureidkey="properties.name",  # LAD name property in GeoJSON
    hovertemplate='<b>%{location}</b><br>%{z:,.0f}<extra></extra>',
    showscale=True
))
```

## Publication Checklist

### For Web Hosting
- [ ] Test all metrics on production server
- [ ] Verify API key is set and working (humanization enabled)
- [ ] Check all source links resolve (datasets, knowledge graph)
- [ ] Mobile responsiveness verified
- [ ] Load time <3s on 4G
- [ ] Error handling displays gracefully

### For Academic Paper
- [ ] Screenshot dashboard (map + Q&A side-by-side)
- [ ] Report metrics: response latency, humanization accuracy
- [ ] Cite model: "Claude 3.5 Haiku (claude-3-5-haiku-20241022)"
- [ ] Document dashboard URL (if publicly hosted)
- [ ] Include benchmark results (evaluate_answers.py)

### For Dataset Publication
- [ ] Update source URLs in KG to resolvable DOI/landing pages
- [ ] Export both graphs: observed + prediction
- [ ] Include changelog: "Wales removed, predictions updated to [date]"
- [ ] Publish to: Zenodo, Figshare, or data.gov.uk

## Source Links: Make Them Active

### Current Status
KG already has landing pages for:
- DfT VEH0132: [UK Vehicle Licensing Statistics](https://www.data.gov.uk/)
- DfT VEH0105: [Licensed vehicles](https://www.data.gov.uk/)
- DfT EVCI9001: [Public charging points](https://www.data.gov.uk/)
- StatsWales: [Population data](https://statswales.gov.wales/)
- ONS: [Geography lookup](https://geoportal.statistics.gov.uk/)
- CLEETS knowledge graph: https://w3id.org/def/cleets

### Verify Links
```python
from rdflib import Graph, Namespace

kg = Graph()
kg.parse("cleets_cskg_enriched.ttl", format="turtle")
DCAT = Namespace("http://www.w3.org/ns/dcat#")

for ds in kg.subjects():
    landing_page = next(kg.objects(ds, DCAT.landingPage), None)
    if landing_page:
        print(f"{ds} → {landing_page}")
        # Verify URL is HTTPS and resolves
```

## Performance Tuning

### Optimize Map Rendering
- Limit map points to 22 LADs (already optimal)
- Pre-compute metric values on startup (done in `get_lad_stats()`)
- Cache Plotly figures (if using callbacks memoization)

### Optimize Answer Generation
- Enable Anthropic prompt caching (automatic with `anthropic>=0.31.0`)
- Batch questions (if serving multiple users)
- Cache KG queries with `functools.lru_cache`

### Monitor Performance
```bash
# Check response times
curl -w "Total: %{time_total}s\n" http://localhost:8050

# Check API usage
python -c "import anthropic; c = anthropic.Anthropic(); print(c.messages.list())" # Billing API
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Map doesn't load | Check Plotly + Dash versions; clear browser cache |
| Click doesn't prefill | Verify `clickData` callback; check browser console |
| Answer shows error | Ensure KG files exist; check ANTHROPIC_API_KEY |
| Slow humanization | Normal (1–2s per question); check network/API quota |
| Sources aren't clickable | Ensure markdown links render: `[text](url)` |

## Citation for Publication

```bibtex
@online{cleets_chat_dashboard,
  title={CLEETS-CHAT: Interactive QA Dashboard for EV Adoption in Wales},
  author={Hamed, Naeima},
  year={2025},
  url={https://w3id.org/def/cleets},
  note={Published dashboard with OSM choropleth and humanized answers via Claude 3.5 Haiku}
}
```

## Next Steps

1. **Update prediction data** (keepership + chargers) ← Awaiting your input
2. **Get real LAD GeoJSON** for proper choropleth (optional, current version works)
3. **Host on cloud** (Heroku, AWS, GCP)
4. **A/B test with stakeholders** (template vs. humanized answers)
5. **Publish paper** with dashboard link + benchmark results

---

Questions? See README_HUMANIZATION.md for QA integration details, or INTEGRATION_GUIDE.md for API setup.
