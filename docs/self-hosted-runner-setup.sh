#!/usr/bin/env bash
# =============================================================================
# GitHub Actions Self-Hosted Runner Setup
# Repository: dragfly/voxtype
# Platform: macOS Apple Silicon (ARM64)
# =============================================================================
#
# Prerequisiti:
#   - gh CLI installata e autenticata (gh auth login)
#   - macOS su Apple Silicon
#
# Uso:
#   chmod +x docs/self-hosted-runner-setup.sh
#   ./docs/self-hosted-runner-setup.sh
#
# =============================================================================

set -e

REPO="dragfly/voxtype"
RUNNER_DIR="$HOME/actions-runner"
RUNNER_NAME="macbook-$(hostname -s)"
RUNNER_VERSION="2.331.0"

echo "=== GitHub Actions Self-Hosted Runner Setup ==="
echo ""

# 1. Verifica gh CLI
echo "[1/6] Verifica gh CLI..."
if ! command -v gh &> /dev/null; then
    echo "Errore: gh CLI non trovata. Installa con: brew install gh"
    exit 1
fi

if ! gh auth status &> /dev/null; then
    echo "Errore: gh non autenticata. Esegui: gh auth login"
    exit 1
fi
echo "✓ gh CLI autenticata"

# 2. Crea directory runner
echo "[2/6] Creazione directory runner..."
mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"
echo "✓ Directory: $RUNNER_DIR"

# 3. Download runner
echo "[3/6] Download runner v${RUNNER_VERSION}..."
RUNNER_TARBALL="actions-runner-osx-arm64-${RUNNER_VERSION}.tar.gz"
if [ ! -f "$RUNNER_TARBALL" ]; then
    curl -sL -o "$RUNNER_TARBALL" \
        "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${RUNNER_TARBALL}"
fi
tar xzf "$RUNNER_TARBALL"
echo "✓ Runner scaricato e estratto"

# 4. Ottieni token di registrazione
echo "[4/6] Ottenimento token di registrazione..."
TOKEN=$(gh api "repos/${REPO}/actions/runners/registration-token" -X POST --jq '.token')
echo "✓ Token ottenuto"

# 5. Configura runner
echo "[5/6] Configurazione runner..."
./config.sh \
    --url "https://github.com/${REPO}" \
    --token "$TOKEN" \
    --name "$RUNNER_NAME" \
    --labels "self-hosted,macOS,ARM64,apple-silicon" \
    --unattended
echo "✓ Runner configurato"

# 6. Installa e avvia come servizio
echo "[6/6] Installazione servizio launchd..."
./svc.sh install
./svc.sh start
echo "✓ Servizio avviato"

# Verifica finale
echo ""
echo "=== Verifica ==="
gh api "repos/${REPO}/actions/runners" --jq '.runners[] | "Runner: \(.name) - Status: \(.status)"'

echo ""
echo "=== Setup completato ==="
echo ""
echo "Comandi utili:"
echo "  Stato:    cd $RUNNER_DIR && ./svc.sh status"
echo "  Stop:     cd $RUNNER_DIR && ./svc.sh stop"
echo "  Start:    cd $RUNNER_DIR && ./svc.sh start"
echo "  Logs:     tail -f ~/Library/Logs/actions.runner.${REPO//\//-}.${RUNNER_NAME}/Runner_*.log"
echo "  Rimuovi:  cd $RUNNER_DIR && ./svc.sh uninstall && ./config.sh remove --token \$(gh api repos/${REPO}/actions/runners/remove-token -X POST --jq '.token')"
