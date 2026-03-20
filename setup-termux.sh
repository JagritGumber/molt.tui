#!/bin/bash
# moltui - Termux (Android) setup script
# Run this inside Termux to install Bun and get moltui running

set -e

echo "⚡ moltui - Termux Setup"
echo "========================"
echo ""

# Check if we're in Termux
if [ -z "$TERMUX_VERSION" ]; then
  echo "⚠️  This script is designed for Termux on Android."
  echo "   On desktop, just run: bun run src/index.ts"
  echo ""
  read -p "Continue anyway? [y/N] " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
  fi
fi

# Update packages
echo "📦 Updating Termux packages..."
pkg update -y
pkg install -y git

# Install Bun via glibc-runner method (most reliable)
echo ""
echo "🔧 Installing Bun for Termux..."

if command -v bun &>/dev/null; then
  echo "   Bun already installed: $(bun --version)"
else
  # Method: bun-termux (no proot needed)
  echo "   Installing via bun-termux (aarch64, no proot)..."
  pkg install -y wget

  # Download latest bun-termux release
  if [ ! -d "$HOME/.bun-termux" ]; then
    git clone https://github.com/Happ1ness-dev/bun-termux.git "$HOME/.bun-termux"
  fi

  cd "$HOME/.bun-termux"
  bash install.sh
  cd -

  # Add to PATH if not already there
  if ! grep -q "bun" "$HOME/.bashrc" 2>/dev/null; then
    echo 'export PATH="$HOME/.bun/bin:$PATH"' >> "$HOME/.bashrc"
  fi

  export PATH="$HOME/.bun/bin:$PATH"

  if command -v bun &>/dev/null; then
    echo "   ✓ Bun installed: $(bun --version)"
  else
    echo "   ✗ Bun installation failed. Try manual install:"
    echo "     https://github.com/Happ1ness-dev/bun-termux"
    exit 1
  fi
fi

# Clone or update moltui
echo ""
echo "📂 Setting up moltui..."

MOLTUI_DIR="$HOME/moltui"

if [ -d "$MOLTUI_DIR" ]; then
  echo "   moltui directory exists, pulling latest..."
  cd "$MOLTUI_DIR"
  git pull 2>/dev/null || echo "   (not a git repo, skipping pull)"
else
  echo "   Copying moltui to $MOLTUI_DIR..."
  cp -r "$(dirname "$0")" "$MOLTUI_DIR"
fi

cd "$MOLTUI_DIR"

# Install deps (just types, no native modules)
echo ""
echo "📦 Installing dependencies..."
BUN_OPTIONS="--backend=copyfile" bun install

# Create launcher script
echo ""
echo "🚀 Creating launcher..."
cat > "$HOME/.local/bin/moltui" 2>/dev/null || cat > "$PREFIX/bin/moltui" << 'LAUNCHER'
#!/bin/bash
cd "$HOME/moltui"
exec bun run src/index.ts "$@"
LAUNCHER
chmod +x "$HOME/.local/bin/moltui" 2>/dev/null || chmod +x "$PREFIX/bin/moltui"

echo ""
echo "✅ Setup complete!"
echo ""
echo "   Run moltui with:  moltui"
echo "   Or:                cd ~/moltui && bun run start"
echo ""
echo "   First time? Set your API keys in Settings."
echo ""
