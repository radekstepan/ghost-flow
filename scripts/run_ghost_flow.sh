#!/bin/bash
set -e

# ==========================================
# Ghost Flow - macOS Startup Script
# ==========================================

# 1. Resolve Project Root
# Get the directory where this script is actually located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if requirements.txt is in the parent dir (standard structure) or current dir
if [ -f "$SCRIPT_DIR/../requirements.txt" ]; then
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
elif [ -f "$SCRIPT_DIR/requirements.txt" ]; then
    PROJECT_ROOT="$SCRIPT_DIR"
else
    echo "❌ Error: Could not locate requirements.txt."
    echo "   Please ensure this script is inside 'scripts/' or the project root."
    exit 1
fi

# Navigate to Project Root to ensure relative paths work
cd "$PROJECT_ROOT"
echo "📂 Project Root: $PROJECT_ROOT"

# 2. Configuration
VENV_NAME="venv"
REQUIREMENTS="requirements.txt"

# 3. Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed."
    echo "   Please install it via Homebrew: brew install python"
    exit 1
fi

# 4. Create Virtual Environment if missing
if [ ! -d "$VENV_NAME" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv "$VENV_NAME"
fi

# 5. Activate Virtual Environment
source "$VENV_NAME/bin/activate"

# 6. Install Dependencies
echo "⬇️  Checking dependencies..."
pip install -r "$REQUIREMENTS" --quiet

# 7. Run the Application
echo "👻 Starting Ghost Flow..."
echo "   (Press Ctrl+C to stop)"

# Ensure src is in PYTHONPATH
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# Run main
python src/main.py
