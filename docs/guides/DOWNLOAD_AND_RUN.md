# CLEETS-CHAT: Download & Run Locally

Complete package ready for download. Choose your operating system and follow the steps.

## 📦 Download Packages

Two identical packages available (same contents, different formats):

**For macOS / Linux:**
- **cleets-chat.tar.gz** (361 KB)
- Contains 27 files: app, docs, config, knowledge graphs

**For Windows:**
- **cleets-chat.zip** (379 KB)
- Contains 27 files: app, docs, config, knowledge graphs

Both packages contain:
- ✅ Production dashboard (with & without feedback)
- ✅ QA engine with Claude Haiku humanization
- ✅ Feedback collection & analysis tools
- ✅ Complete documentation (11 guides)
- ✅ Configuration templates
- ✅ Knowledge graphs
- ✅ One-click setup scripts

---

## macOS / Linux: Quick Start (5 minutes)

### 1. Download & Extract

```bash
# Download cleets-chat.tar.gz
# Then extract:
tar -xzf cleets-chat.tar.gz
cd cleets-chat
```

### 2. Run Setup

```bash
# Make script executable
chmod +x QUICKSTART.sh

# Run setup (automatic)
./QUICKSTART.sh
```

Setup does:
- ✓ Checks Python 3.10+
- ✓ Creates virtual environment
- ✓ Installs dependencies (~1-2 min)
- ✓ Verifies knowledge graphs

### 3. Set API Key (Optional)

```bash
# Get key from https://console.anthropic.com
export ANTHROPIC_API_KEY=sk-ant-your-key-here

# Or create .env file
echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" > .env
```

### 4. Run Dashboard

```bash
# Activate virtual environment (QUICKSTART.sh does this)
source venv/bin/activate

# Start dashboard
python app.py
```

### 5. Open Browser

**http://localhost:8050**

You should see:
- Map of Welsh local authorities (LADs)
- Metric dropdown selector
- Question input box
- Feedback scoring slider (1-10)

---

## Windows: Quick Start (5 minutes)

### 1. Download & Extract

```
1. Download: cleets-chat.zip
2. Right-click → Extract All
3. Navigate into cleets-chat folder
```

Or via Command Prompt:

```bash
# If you have 7-Zip or WinRAR:
"C:\Program Files\7-Zip\7z" x cleets-chat.zip
cd cleets-chat
```

### 2. Run Setup (Easy Way)

```
1. Double-click: QUICKSTART.bat
2. Wait for setup to complete (1-2 minutes)
3. Follow on-screen instructions
4. Press Enter to close when done
```

**Or Command Prompt:**

```bash
cmd.exe
cd path\to\cleets-chat
QUICKSTART.bat
```

Setup does:
- ✓ Checks Python 3.10+
- ✓ Creates virtual environment
- ✓ Installs dependencies
- ✓ Verifies knowledge graphs

### 3. Set API Key (Optional)

**Easy way:**
```bash
# Command Prompt
set ANTHROPIC_API_KEY=sk-ant-your-key-here
```

**Permanent way:**
1. Press `Win + X` → System
2. Advanced system settings
3. Environment Variables
4. New variable:
   - Name: `ANTHROPIC_API_KEY`
   - Value: `sk-ant-your-key-here`
5. Restart Command Prompt

### 4. Run Dashboard

```bash
# Virtual environment should be active from QUICKSTART.bat
python app.py
```

### 5. Open Browser

**http://localhost:8050**

---

## What to Expect

### Dashboard Loads Successfully ✅

You'll see:
```
============================================================
 CLEETS-CHAT Dashboard with Feedback
============================================================

✓ Knowledge graphs loaded
✓ Humanization: ENABLED (if ANTHROPIC_API_KEY set)
✓ Feedback database: cleets_feedback.db

→ Open http://localhost:8050 in your browser
============================================================
```

Then browser opens with:
- Interactive map (Welsh LADs colored by metric)
- Metric selector dropdown
- Question input field
- Answer area (appears after question)
- Feedback slider (1-10) below answer

### Try These Questions

```
"Tell me about Cardiff"
"What's the predicted BEV keepership for Swansea in 2045?"
"Compare adoption rates across scenarios"
"Which LAD has the highest predicted keepership?"
```

### Rate an Answer

1. Ask a question
2. Read the answer
3. Move slider to 1-10 (1=Poor, 10=Excellent)
4. Optionally add notes in text box
5. Click green "Submit Feedback" button
6. See confirmation: "✓ Feedback recorded! (Score: 8/10)"

---

## After Setup: Next Steps

### Option 1: Try It Out (Recommended First)

```bash
# Just explore dashboard, ask questions, rate answers
# No additional setup needed
```

### Option 2: Analyze Feedback

After collecting some scores:

```bash
python analyze_feedback.py

# Outputs:
# - Console report (avg scores, trends, recommendations)
# - feedback_report.json (detailed metrics)
# - feedback.csv (raw data for stakeholders)
```

### Option 3: Evaluate Quality

```bash
# Run benchmark tests
python evaluate_answers.py --benchmark full --humanize

# Tests 7 questions, verifies facts are preserved
```

### Option 4: Publish to GitHub

See `GITHUB_PUBLICATION_READY.md`:
```bash
git init
git add .
git commit -m "Initial commit: CLEETS-CHAT"
git remote add origin https://github.com/yourusername/cleets-chat.git
git push -u origin main
```

---

## Troubleshooting

### "Python not found"

**macOS:**
```bash
brew install python3.10
```

**Windows:**
- Download from https://www.python.org/downloads/
- Run installer
- ✅ Check "Add Python to PATH"

**Linux:**
```bash
sudo apt-get install python3.10
```

### "QUICKSTART script won't run"

**macOS/Linux:**
```bash
# Make executable
chmod +x QUICKSTART.sh

# Run directly
bash QUICKSTART.sh
```

**Windows:**
- Right-click QUICKSTART.bat → "Run as Administrator"

### "Port 8050 already in use"

```bash
# Start on another port (no code change needed)
PORT=8051 python app.py          # macOS/Linux
set PORT=8051 && python app.py   # Windows

# Then access: http://localhost:8051
```

### "ModuleNotFoundError"

```bash
# Reinstall dependencies
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### "ANTHROPIC_API_KEY not set" warning

This is **OK**—dashboard works fine without it:
- ✅ Answers still accurate (from RDF)
- ✅ Templated (not humanized)
- ✅ All sources linked

To enable humanization, set the key (see Step 3 above).

---

## File Structure After Extraction

```
cleets-chat/
├── QUICKSTART.sh                      Setup script (macOS/Linux)
├── QUICKSTART.bat                     Setup script (Windows)
├── INSTALL.md                         Detailed installation guide
├── QUICK_REFERENCE.md                 3-minute cheat sheet
├── README.md                          Main documentation
│
├── app.py                             Main dashboard: map + QA + scoring (RUN THIS)
├── assets/cleets_logo.png             Your logo (add it here; shown in the header)
├── app_dashboard_with_feedback.py     Older dashboard variant (reference only)
├── qa_with_humanization.py            QA engine
├── analyze_feedback.py                Feedback analysis
├── evaluate_answers.py                Benchmark tests
│
├── requirements.txt                   Python dependencies
├── .env.example                       Environment template
├── LICENSE                            MIT License
│
├── cleets_cskg_enriched.ttl           Observed knowledge graph (RDF)
├── cleets_prediction_kg.ttl           Prediction knowledge graph (diffusion scenarios)
├── cleets_prediction_families.ttl     Other prediction types from the paper (built from the notebook)
├── build_prediction_families.py       Rebuild the families file from the notebook / CSV exports
├── methods.py                         Text behind the ⓘ 'how was this predicted?' panels
├── PREDICTION_TYPES.md                Prediction types and custom-dataset guide
├── kg_service.py / qa.py              KG access layer and QA engine
└── [8 more documentation files]
```

---

## System Requirements

| Requirement | Minimum | Recommended |
|---|---|---|
| Python | 3.10 | 3.11+ |
| RAM | 1 GB | 2+ GB |
| Disk | 1.5 GB | 3 GB |
| Network | For install only | Broadband |
| API Key | Optional | Required for humanization |

---

## How Long Does Each Step Take?

| Step | Time | Notes |
|---|---|---|
| Download | 1 min | 361 KB file |
| Extract | 30 sec | Tar or ZIP |
| QUICKSTART | 2-3 min | Installs Python packages |
| First question | 5 sec | API calls to LLM |
| Humanization | +2 sec | If enabled |
| Feedback analysis | <1 min | After 50+ scores |

**Total time to first dashboard: ~5 minutes**

---

## Dashboard Features

### Map
- 🗺️ Click LAD → prefills question
- 📊 4 metrics to toggle (keepership 3 scenarios + adoption)
- 🎨 Color scale (darker = higher values)

### QA
- 💬 Ask natural language questions
- 🤖 Claude Haiku humanization (optional)
- 📎 Sources linked to official data
- 🔄 Two modes: Observed (actual) + Predictions (2045)

### Feedback
- 🎯 1-10 scoring slider
- 📝 Optional notes/suggestions
- 💾 Auto-saved to database
- 📊 Analyze with `python analyze_feedback.py`

---

## Common Commands

### Start Dashboard
```bash
python app.py
```

### Analyze Feedback
```bash
python analyze_feedback.py
```

### Run Benchmarks
```bash
python evaluate_answers.py --benchmark full --humanize
```

### Stop Dashboard
```
Ctrl+C in terminal
```

### View Database
```bash
sqlite3 cleets_feedback.db
> SELECT COUNT(*) FROM feedback;
```

---

## Getting Help

1. **Read:** `INSTALL.md` (detailed troubleshooting)
2. **Check:** `QUICK_REFERENCE.md` (common questions)
3. **Search:** GitHub Issues (if published)
4. **Email:** naeima.hamed@gmail.com

---

## Next: After Getting It Running

### Share with Stakeholders
1. Run dashboard locally
2. Collect feedback (aim for 50+ scores)
3. Analyze: `python analyze_feedback.py`
4. Iterate based on recommendations

### Publish to GitHub
See `GITHUB_PUBLICATION_READY.md`:
```bash
git init
git add .
git commit -m "Initial CLEETS-CHAT"
git remote add origin https://github.com/yourusername/cleets-chat.git
git push -u origin main
```

### Deploy to Cloud
See `DASHBOARD_GUIDE.md`:
- Docker: `docker build -t cleets-chat .`
- Heroku: `git push heroku main`
- AWS/GCP: Use Docker image

---

## Summary Checklist

- [ ] Downloaded cleets-chat package
- [ ] Extracted to local folder
- [ ] Ran QUICKSTART script (automatic setup)
- [ ] Set ANTHROPIC_API_KEY (optional but recommended)
- [ ] Started dashboard: `python app.py`
- [ ] Opened http://localhost:8050
- [ ] Tried asking a question
- [ ] Rated an answer
- [ ] Ran feedback analysis: `python analyze_feedback.py`

**Once all checked: You're ready to collect stakeholder feedback!** 🚀

---

**Questions?** See `INSTALL.md` for detailed troubleshooting, or email naeima.hamed@gmail.com.
