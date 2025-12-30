#!/bin/bash
# Minimal sudo script - easy to review!
# Sets up permissions for voxtype

set -e

echo "Setting up permissions for voxtype..."

# Audio library + clipboard tool for X11
sudo apt-get install -y libportaudio2 xclip

# Add user to input group (for hotkey detection)
sudo usermod -aG input $USER

# Allow input group to access /dev/uinput (for ydotool)
echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | sudo tee /etc/udev/rules.d/99-ydotool.rules
sudo udevadm control --reload-rules
sudo udevadm trigger

echo ""
echo "Done. You need to log out and back in (or reboot) for changes to take effect."
