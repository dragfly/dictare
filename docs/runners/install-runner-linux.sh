#!/usr/bin/env bash
# =============================================================================
# Install GitHub Actions Runner - Linux x64
# =============================================================================
#
# Uso:
#   ./install-runner-linux.sh <TOKEN>
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
RUNNER_NAME="linux-$(hostname -s)"
RUNNER_VERSION="2.331.0"

echo "=== GitHub Actions Runner Setup (Linux x64) ==="
echo ""

# 1. Verifica architettura
echo "[1/5] Verifica architettura..."
ARCH=$(uname -m)
if [ "$ARCH" != "x86_64" ]; then
    echo "Errore: Questo script è per Linux x64, trovato: $ARCH"
    exit 1
fi
echo "✓ Linux x64 confermato"

# 2. Crea directory e scarica
echo "[2/5] Download runner..."
mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

RUNNER_TARBALL="actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
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
    --labels "self-hosted,Linux,X64" \
    --unattended
echo "✓ Runner configurato come: $RUNNER_NAME"

# 4. Installa servizio
echo "[4/5] Installazione servizio systemd..."
sudo ./svc.sh install
echo "✓ Servizio installato"

# 5. Avvia
echo "[5/5] Avvio servizio..."
sudo ./svc.sh start
echo "✓ Runner avviato"

echo ""
echo "=== Setup completato ==="
echo ""
echo "Comandi utili:"
echo "  Stato:  sudo systemctl status actions.runner.${REPO//\//-}.${RUNNER_NAME}"
echo "  Stop:   cd $RUNNER_DIR && sudo ./svc.sh stop"
echo "  Start:  cd $RUNNER_DIR && sudo ./svc.sh start"
echo "  Logs:   journalctl -u actions.runner.${REPO//\//-}.${RUNNER_NAME} -f"
