#!/bin/bash
# Undo setup-permissions.sh
# Note: These changes are harmless and may be used by other tools

echo "This will:"
echo "  - Remove udev rule for /dev/uinput"
echo "  - Remove user from 'input' group"
echo "  - Remove libportaudio2 and xclip packages"
echo ""
echo "Warning: Other tools may need these. Only run if you're sure."
echo ""
read -p "Continue? [y/N] " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Remove udev rule
    sudo rm -f /etc/udev/rules.d/99-ydotool.rules
    sudo udevadm control --reload-rules
    sudo udevadm trigger

    # Remove from input group
    sudo gpasswd -d $USER input

    # Remove packages
    sudo apt-get remove -y libportaudio2 xclip

    echo ""
    echo "Done. Log out and back in for group change to take effect."
else
    echo "Cancelled."
fi
