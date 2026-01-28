#!/usr/bin/env bash
# =============================================================================
# Get GitHub Actions Runner Registration Token
# Esegui questo su una macchina con gh CLI configurato
# =============================================================================

REPO="dragfly/voxtype"

echo "Token di registrazione per $REPO:"
echo ""
gh api "repos/${REPO}/actions/runners/registration-token" -X POST --jq '.token'
echo ""
echo "Usa questo token con install-runner-macos.sh o install-runner-linux.sh"
echo "NOTA: Il token scade dopo 1 ora"
