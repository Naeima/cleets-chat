#!/bin/bash
# CLEETS-CHAT: Quick Start Script
# Run this after downloading and extracting the package

set -e

echo "🚀 CLEETS-CHAT Quick Start Setup"
echo "=================================="
echo ""

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python version: $PYTHON_VERSION (3.10+ required)"

# Check for venv
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate venv
echo "🔌 Activating virtual environment..."
source venv/bin/activate || . venv/Scripts/activate

# Upgrade pip
echo "📦 Upgrading pip..."
pip install --upgrade pip > /dev/null 2>&1

# Install dependencies
echo "📦 Installing dependencies (this may take 1-2 minutes)..."
pip install -r requirements.txt > /dev/null 2>&1
echo "✓ Dependencies installed"

# Check for ANTHROPIC_API_KEY
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo ""
    echo "⚠️  ANTHROPIC_API_KEY not set"
    echo ""
    echo "To enable humanization, set:"
    echo "  export ANTHROPIC_API_KEY=sk-ant-your-key-here"
    echo ""
    echo "Get your key at: https://console.anthropic.com"
    echo ""
else
    echo "✓ ANTHROPIC_API_KEY is set"
fi

# Test KG files
echo ""
echo "📊 Checking knowledge graph files..."
if [ -f "cleets_cskg_enriched.ttl" ] && [ -f "cleets_prediction_kg.ttl" ]; then
    echo "✓ Knowledge graphs found"
else
    echo "⚠️  Knowledge graph files not found"
    echo "   Expected: cleets_cskg_enriched.ttl, cleets_prediction_kg.ttl"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. (Optional) Set API key: export ANTHROPIC_API_KEY=sk-ant-..."
echo "2. Run dashboard: python app.py"
echo "3. Open: http://localhost:8050"
echo ""
echo "Need help? See README.md or QUICK_REFERENCE.md"
echo ""
