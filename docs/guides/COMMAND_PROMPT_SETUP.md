# CLEETS-CHAT: Command Prompt Setup Instructions

Copy & paste these commands into your terminal/command prompt. No other steps needed.

---

## Windows Command Prompt

### Step 1: Navigate to Package
```cmd
cd path\to\cleets-chat
```
Replace `path\to\cleets-chat` with your actual folder path.

**Example:**
```cmd
cd C:\Users\YourName\Downloads\cleets-chat
```

### Step 2: Create Virtual Environment
```cmd
python -m venv venv
```

### Step 3: Activate Virtual Environment
```cmd
venv\Scripts\activate.bat
```

You should see `(venv)` appear at the start of your prompt.

### Step 4: Upgrade pip
```cmd
python -m pip install --upgrade pip
```

### Step 5: Install Libraries
```cmd
pip install -r requirements.txt
```

⏱️ This takes 2-3 minutes.

### Step 6: Set API Key (Optional but Recommended)
```cmd
set ANTHROPIC_API_KEY=sk-ant-your-key-here
```

Get key from: https://console.anthropic.com

### Step 7: Run Dashboard
```cmd
python app.py
```

### Step 8: Open Browser
```
http://localhost:8050
```

### Step 9: Stop Dashboard
```
Ctrl+C
```

---

## macOS Terminal

### Step 1: Navigate to Package
```bash
cd ~/Downloads/cleets-chat
```

Or wherever you extracted the folder.

### Step 2: Create Virtual Environment
```bash
python3 -m venv venv
```

### Step 3: Activate Virtual Environment
```bash
source venv/bin/activate
```

You should see `(venv)` at the start of your prompt.

### Step 4: Upgrade pip
```bash
pip install --upgrade pip
```

### Step 5: Install Libraries
```bash
pip install -r requirements.txt
```

⏱️ This takes 2-3 minutes.

### Step 6: Set API Key (Optional but Recommended)
```bash
export ANTHROPIC_API_KEY=sk-ant-your-key-here
```

Get key from: https://console.anthropic.com

### Step 7: Run Dashboard
```bash
python app.py
```

### Step 8: Open Browser
```
http://localhost:8050
```

### Step 9: Stop Dashboard
```
Ctrl+C
```

---

## Linux Terminal

### Step 1: Navigate to Package
```bash
cd ~/Downloads/cleets-chat
```

### Step 2: Create Virtual Environment
```bash
python3 -m venv venv
```

### Step 3: Activate Virtual Environment
```bash
source venv/bin/activate
```

### Step 4: Upgrade pip
```bash
pip install --upgrade pip
```

### Step 5: Install Libraries
```bash
pip install -r requirements.txt
```

⏱️ This takes 2-3 minutes.

### Step 6: Set API Key (Optional but Recommended)
```bash
export ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### Step 7: Run Dashboard
```bash
python app.py
```

### Step 8: Open Browser
```
http://localhost:8050
```

### Step 9: Stop Dashboard
```
Ctrl+C
```

---

## All-in-One Copy & Paste

### Windows (Copy all at once)
```cmd
python -m venv venv && venv\Scripts\activate.bat && python -m pip install --upgrade pip && pip install -r requirements.txt && echo Setup complete! Run: python app.py
```

### macOS/Linux (Copy all at once)
```bash
python3 -m venv venv && source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt && echo "Setup complete! Run: python app.py"
```

---

## What Gets Installed

The `pip install -r requirements.txt` command installs:

```
✓ dash              2.14.0+    (web framework)
✓ plotly            5.14.0+    (interactive maps)
✓ pandas            2.0.0+     (data handling)
✓ rdflib            7.0.0+     (knowledge graphs)
✓ anthropic         0.31.0+    (Claude API)
✓ python-dotenv     1.0.0+     (environment variables)
✓ gunicorn          21.0.0+    (production server)
```

---

## Verification: Check Installation

After `pip install -r requirements.txt`, verify everything worked:

```bash
# Windows
python -c "import dash; import plotly; import rdflib; import anthropic; print('✓ All packages installed successfully')"

# macOS/Linux
python3 -c "import dash; import plotly; import rdflib; import anthropic; print('✓ All packages installed successfully')"
```

If you see `✓ All packages installed successfully`, you're good to go!

---

## Troubleshooting

### "Python not found"
```bash
# macOS (Homebrew)
brew install python3.10

# Windows: Download from https://www.python.org/downloads/
# Linux: sudo apt-get install python3.10
```

### "pip: command not found"
```bash
# Use python -m pip instead
python -m pip install -r requirements.txt
```

### "Permission denied" (macOS/Linux)
```bash
# Run with sudo
sudo pip install -r requirements.txt
```

### "venv command not found"
```bash
# macOS/Linux
python3 -m venv venv

# Windows
python -m venv venv
```

### "Address already in use" (Port 8050)
Another app is using port 8050. Start on a different port:
```cmd
set PORT=8051 && python app.py        (Windows)
PORT=8051 python app.py               (macOS/Linux)
```
Then open http://localhost:8051

---

## Logo and API key

- **Logo:** copy your `cleets_logo.png` into the `assets` folder inside `cleets-chat` (create the folder if it is missing). The header shows it automatically; without it a plain CLEETS wordmark is shown.
- **API key:** create a file named `.env` in `cleets-chat` containing `ANTHROPIC_API_KEY=sk-ant-...` (or use the `set` / `export` commands above). This switches on the "Humanise the wording" option.

---

## Next: After Installation

Once dashboard is running:

1. **Ask a question:** "Tell me about Cardiff"
2. **Rate the answer:** Use 1-10 slider
3. **Submit feedback:** Click green button
4. **Analyze feedback:** Run in new terminal
   ```bash
   # New terminal window/tab
   python analyze_feedback.py
   ```

---

## Commands Summary (Quick Reference)

| Task | Command |
|------|---------|
| Navigate to folder | `cd path/to/cleets-chat` |
| Create venv | `python -m venv venv` |
| Activate venv | `source venv/bin/activate` (Mac/Linux) or `venv\Scripts\activate.bat` (Windows) |
| Install libraries | `pip install -r requirements.txt` |
| Set API key | `export ANTHROPIC_API_KEY=sk-ant-...` (Mac/Linux) or `set ANTHROPIC_API_KEY=sk-ant-...` (Windows) |
| Run dashboard | `python app.py` |
| Stop dashboard | `Ctrl+C` |
| Analyze feedback | `python analyze_feedback.py` |

---

## Getting Help

If you get stuck:
1. Read `INSTALL.md` (detailed troubleshooting)
2. Check error message — usually tells you what's wrong
3. See `QUICK_REFERENCE.md` for common issues
4. Email: naeima.hamed@gmail.com

---

**Ready? Start with Step 1 above!** 🚀
