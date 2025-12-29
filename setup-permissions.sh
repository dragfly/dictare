#!/bin/bash
# Minimal sudo script - easy to review!
# Installs audio library and grants input device access

sudo apt-get install -y libportaudio2
sudo usermod -aG input $USER

echo "Done. Log out and back in for group change to take effect."
