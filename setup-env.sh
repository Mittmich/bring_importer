#!/bin/zsh

# This script installs the requirements for environment variable substitution in nginx

# Check if running on macOS
if [[ "$(uname)" != "Darwin" ]]; then
  echo "This script is designed for macOS. Please adapt it for your operating system."
  exit 1
fi

# Check if Homebrew is installed
if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required but not installed. Please install Homebrew first."
  echo "Visit https://brew.sh for installation instructions."
  exit 1
fi

echo "Installing gettext for envsubst utility..."
brew install gettext

if [ $? -ne 0 ]; then
  echo "Failed to install gettext. Please try manually: brew install gettext"
  exit 1
fi

# Check if PATH needs to be updated for gettext
if ! command -v envsubst >/dev/null 2>&1; then
  echo "Adding gettext to your PATH..."
  
  # Get the gettext path from Homebrew
  GETTEXT_PATH=$(brew --prefix gettext)/bin
  
  # Check which shell configuration file to update
  SHELL_RC="$HOME/.zshrc"
  
  echo "export PATH=\"$GETTEXT_PATH:\$PATH\"" >> "$SHELL_RC"
  echo "Added gettext to $SHELL_RC"
  echo "Please run 'source $SHELL_RC' or restart your terminal to apply changes."
else
  echo "envsubst is already in your PATH"
fi

echo "Installation complete!"
echo "You can now use './start.sh' to start the application with environment variable support."
