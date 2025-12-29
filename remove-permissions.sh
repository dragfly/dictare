#!/bin/bash
# Undo setup-permissions.sh
# Note: These changes are harmless and may be used by other tools

echo "This will:"
echo "  - Remove user from 'input' group"
echo "  - Remove libportaudio2 package"
echo ""
echo "Warning: Other tools may need these. Only run if you're sure."
echo ""
read -p "Continue? [y/N] " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo gpasswd -d $USER input
    sudo apt-get remove -y libportaudio2
    echo "Done. Log out and back in for group change to take effect."
else
    echo "Cancelled."
fi
