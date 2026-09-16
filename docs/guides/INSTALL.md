# CLEETS-CHAT: Local Installation Guide

Complete instructions for downloading and running CLEETS-CHAT on your machine.

## Prerequisites

**Required:**
- Python 3.10 or later
- 2 GB free disk space
- Internet connection (for first install only)

**Optional:**
- Anthropic API key (for Claude Haiku humanization)
  - Get free at: https://console.anthropic.com
  - Sign up and generate an API key

## Installation: MacOS / Linux

### Step 1: Download Package

```bash
# Extract the downloaded tarball
tar -xzf cleets-chat.tar.gz
cd cleets-chat

# Or clone from GitHub
git clone https://github.com/yourusername/cleets-chat.git
cd cleets-chat
```

### Step 2: Run Quick Start

```bash
# Make script executable
chmod +x QUICKSTART.sh

# Run setup (creates venv, installs dependencies)
./QUICKSTART.sh
```

The script will:
- ✅ Check Python version (3.10+)
- ✅ Create virtual environment
- ✅ Install dependencies from requirements.txt
- ✅ Verify knowledge graphs are present
- ✅ Remind you to set ANTHROPIC_API_KEY

### Step 3: Set API Key (Optional but Recommended)

```bash
# Get your key from https://console.anthropic.com
export ANTHROPIC_API_KEY=sk-ant-your-key-here

# Or add to .env file
echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" > .env
```

### Step 4: Run Dashboard

```bash
# Make sure venv is activated (QUICKSTART.sh does this)
source venv/bin/activate

# Start dashboard
python app.py
```

Output:
```
============================================================
 CLEETS-CHAT Dashboard with Feedback
============================================================

✓ Knowledge graphs loaded
✓ Humanization: ENABLED
✓ Feedback database: cleets_feedback.db

→ Open http://localhost:8050 in your browser
============================================================
```

### Step 5: Open Dashboard

- Open browser: **http://localhost:8050**
- Map should load with Welsh LADs
- Try clicking on a district or asking a question

**To stop:** Press `Ctrl+C` in terminal

---

## Installation: Windows

### Step 1: Download Package

```
Extract downloaded cleets-chat.zip folder to Documents or Desktop
```

Or via Git:
```bash
git clone https://github.com/yourusername/cleets-chat.git
cd cleets-chat
```

### Step 2: Run Quick Start

**Option A: GUI (Recommended)**
1. Double-click `QUICKSTART.bat`
2. Wait for setup to complete (1-2 minutes)
3. Follow on-screen instructions

**Option B: Command Prompt**
```bash
cmd.exe
cd cleets-chat
QUICKSTART.bat
```

The script will:
- ✅ Check Python installation
- ✅ Create virtual environment
- ✅ Install all dependencies
- ✅ Verify knowledge graphs

### Step 3: Set API Key (Optional)

**Option A: Environment Variables (Persistent)**
1. Press `Win + X` → "System"
2. Click "Advanced system settings"
3. Click "Environment Variables"
4. Click "New" (User variables)
   - Name: `ANTHROPIC_API_KEY`
   - Value: `sk-ant-your-key-here`
5. Click OK
6. Restart Command Prompt / PowerShell

**Option B: Command Prompt (Temporary)**
```bash
set ANTHROPIC_API_KEY=sk-ant-your-key-here
python app.py
```

**Option C: .env File**
```
Create file: .env
Add line: ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### Step 4: Run Dashboard

```bash
# Activate virtual environment (QUICKSTART.bat does this)
venv\Scripts\activate.bat

# Start dashboard
python app.py
```

### Step 5: Open Dashboard

- Open browser: **http://localhost:8050**
- Map should load
- Try asking a question

**To stop:** Press `Ctrl+C` in Command Prompt

---

## Manual Installation (If Quick Start Fails)

### Step 1: Check Python

```bash
python --version  # or python3 --version
# Must be 3.10 or later
```

If Python not found:
1. Download from https://www.python.org/downloads/
2. Install (check "Add Python to PATH")

### Step 2: Create Virtual Environment

```bash
# macOS/Linux
python3 -m venv venv
source venv/bin/activate

# Windows (Command Prompt)
python -m venv venv
venv\Scripts\activate.bat

# Windows (PowerShell)
python -m venv venv
venv\Scripts\Activate.ps1
```

### Step 3: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt

# This will install:
# - dash (web framework)
# - plotly (maps & charts)
# - rdflib (RDF knowledge graphs)
# - anthropic (Claude Haiku API)
# - pandas (data handling)
# - python-dotenv (environment variables)
# Takes 1-2 minutes
```

### Step 4: Verify Installation

```bash
# Check each key package
python -c "import dash; print('✓ dash')"
python -c "import plotly; print('✓ plotly')"
python -c "import rdflib; print('✓ rdflib')"
python -c "import anthropic; print('✓ anthropic')"

# If any fail, run: pip install <package-name>
```

### Step 5: Run Dashboard

```bash
python app.py
# Open http://localhost:8050
```

---

## Verification Checklist

After installation, verify everything works:

```bash
# 1. Knowledge graphs present?
ls -la data/cleets_cskg_enriched.ttl data/cleets_prediction_kg.ttl
# Should show both files

# 2. Python packages installed?
pip list | grep -E "dash|plotly|rdflib|anthropic"
# Should show all four

# 3. Dashboard starts?
python app.py
# Should see "Open http://localhost:8050"

# 4. Can you access the dashboard?
# Open browser → http://localhost:8050
# Map should load with Welsh districts
```

---

## Troubleshooting

### "Python not found"
```bash
# Install Python 3.10+
# macOS (Homebrew): brew install python3.10
# Windows: https://www.python.org/downloads/
# Linux: sudo apt-get install python3.10
```

### "ModuleNotFoundError: No module named 'dash'"
```bash
# Reinstall dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### "Address already in use" (Port 8050)
```bash
# Another app is using port 8050
# Option 1: Kill other app using port 8050
# Option 2: start on another port
PORT=8051 python app.py        # macOS/Linux
set PORT=8051 && python app.py # Windows
```

### "No such file or directory: cleets_cskg_enriched.ttl"
```bash
# Knowledge graph files missing
# Make sure you're in the cleets-chat directory
cd cleets-chat
ls -la data/*.ttl  # Should show 3 files
```

### "ANTHROPIC_API_KEY not set" (Humanization disabled)
```bash
# This is OK - dashboard works without it
# Answers won't be humanized, but will still be accurate
# To enable: export ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### "Dashboard won't load on http://localhost:8050"
```bash
# 1. Check if script is still running (should say "Running on")
# 2. Try refreshing browser (Ctrl+R or Cmd+R)
# 3. Check no firewall blocking port 8050
# 4. Try a different port: PORT=8051 python app.py
```

---

## First Run: Getting Started

### 1. Map Navigation
- **Zoom:** Scroll wheel
- **Pan:** Click and drag
- **Click LAD:** Highlights and prefills question

### 2. Try These Questions
```
"Tell me about Cardiff"
"What's the predicted keepership for Swansea in 2045?"
"Compare adoption rates across scenarios"
"Which LAD has the highest predicted keepership?"
```

### 3. Score Answers
- Rate each answer 1-10
- Add optional notes ("Too technical", "Unclear", etc.)
- Click "Submit Feedback"

### 4. Analyze Feedback
```bash
python analyze_feedback.py
# Shows avg scores, recommendations, areas for improvement
```

---

## Next Steps

### For Testing
```bash
# Run evaluation benchmarks
python evaluate_answers.py --benchmark full --humanize

# Expected output: 7 questions answered with fact checks
```

### For Development
```bash
# Edit templates in qa.py
# Edit constraint prompt in qa_with_humanization.py
# Restart dashboard to see changes (Ctrl+C, then python app_...)
```

### For Deployment
See `DASHBOARD_GUIDE.md` for:
- Docker deployment
- Heroku cloud deployment
- GitHub Actions CI/CD

### For Publication
See `GITHUB_SETUP.md` for publishing to GitHub

---

## System Requirements by OS

| OS | Python | Disk | RAM | Browser |
|----|--------|------|-----|---------|
| macOS 10.14+ | 3.10+ | 2GB | 2GB | Any |
| Windows 10/11 | 3.10+ | 2GB | 2GB | Any |
| Linux (Ubuntu 20.04+) | 3.10+ | 2GB | 2GB | Any |

---

## Getting Help

1. **Read Documentation**
   - `README.md` — Overview
   - `QUICK_REFERENCE.md` — Common tasks
   - `INTEGRATION_GUIDE.md` — API setup

2. **Check Existing Issues**
   - GitHub Issues: https://github.com/yourusername/cleets-chat/issues

3. **Troubleshoot**
   - This file (INSTALL.md)
   - Error messages often contain solutions

4. **Contact**
   - Email: naeima.hamed@gmail.com
   - GitHub Issues: Report bugs there

---

## Uninstall

To remove CLEETS-CHAT:

```bash
# macOS/Linux
cd ..
rm -rf cleets-chat

# Windows
rmdir /s cleets-chat
```

Virtual environment can also be deleted:
```bash
rm -rf venv  # or delete venv folder on Windows
```

---

**Ready to start?** Run `./QUICKSTART.sh` (or `QUICKSTART.bat` on Windows) and open http://localhost:8050
