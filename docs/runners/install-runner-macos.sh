#!/usr/bin/env bash
# =============================================================================
# Install GitHub Actions Runner - macOS Apple Silicon
# =============================================================================
#
# Uso:
#   ./install-runner-macos.sh <TOKEN>
#
# Il token si ottiene con: ./get-runner-token.sh
# =============================================================================

set -e

TOKEN="$1"
if [ -z "$TOKEN" ]; then
    echo "Uso: $0 <TOKEN>"
    echo ""
    echo "Ottieni il token con: ./get-runner-token.sh"
    exit 1
fi

REPO="dragfly/voxtype"
RUNNER_DIR="$HOME/actions-runner"
RUNNER_NAME="mac-$(hostname -s)"
RUNNER_VERSION="2.331.0"

echo "=== GitHub Actions Runner Setup (macOS ARM64) ==="
echo ""

# 1. Verifica architettura
echo "[1/5] Verifica architettura..."
ARCH=$(uname -m)
if [ "$ARCH" != "arm64" ]; then
    echo "Errore: Questo script è per Apple Silicon (arm64), trovato: $ARCH"
    exit 1
fi
echo "✓ Apple Silicon confermato"

# 2. Crea directory e scarica
echo "[2/5] Download runner..."
mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

RUNNER_TARBALL="actions-runner-osx-arm64-${RUNNER_VERSION}.tar.gz"
if [ ! -f "$RUNNER_TARBALL" ]; then
    curl -sL -o "$RUNNER_TARBALL" \
        "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${RUNNER_TARBALL}"
fi
tar xzf "$RUNNER_TARBALL"
echo "✓ Runner scaricato in $RUNNER_DIR"

# 3. Configura
echo "[3/5] Configurazione..."
./config.sh \
    --url "https://github.com/${REPO}" \
    --token "$TOKEN" \
    --name "$RUNNER_NAME" \
    --labels "self-hosted,macOS,ARM64,apple-silicon" \
    --unattended
echo "✓ Runner configurato come: $RUNNER_NAME"

# 4. Installa servizio
echo "[4/5] Installazione servizio launchd..."
./svc.sh install
echo "✓ Servizio installato"

# 5. Avvia
echo "[5/5] Avvio servizio..."
./svc.sh start
echo "✓ Runner avviato"

echo ""
echo "=== Setup completato ==="
echo ""
echo "Comandi utili:"
echo "  Stato:  cd $RUNNER_DIR && ./svc.sh status"
echo "  Stop:   cd $RUNNER_DIR && ./svc.sh stop"
echo "  Start:  cd $RUNNER_DIR && ./svc.sh start"
