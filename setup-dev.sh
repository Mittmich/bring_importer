#!/bin/zsh

# This script sets up the development environment for Recipe to Bring
# It creates the virtual environment and installs dependencies

BACKEND_DIR="$(pwd)/backend"

echo "Setting up Recipe to Bring development environment..."

# Create Python virtual environment
cd "$BACKEND_DIR" || { echo "Error: Could not change to backend directory"; exit 1; }

# Check for uv or fall back to venv
if command -v uv >/dev/null 2>&1; then
  echo "Creating virtual environment using uv..."
  uv venv
  source .venv/bin/activate
  echo "Installing dependencies with uv..."
  uv pip install -r requirements.txt
else
  echo "uv not found, using standard venv..."
  python3 -m venv .venv
  source .venv/bin/activate
  echo "Installing dependencies with pip..."
  pip install -r requirements.txt || pip install -e .
fi

echo 
echo "Development environment setup complete!"
echo "To activate the virtual environment:"
echo "  cd $BACKEND_DIR && source .venv/bin/activate"
echo 
echo "To start the application:"
echo "  ./start.sh"
