#!/bin/bash
set -e

echo "Uninstalling DD-imager..."

sudo rm -f /usr/local/bin/dd-imager
sudo rm -f /usr/share/polkit-1/actions/com.invisi101.dd-imager.policy
sudo rm -f /usr/share/icons/hicolor/scalable/apps/dd-imager.svg
rm -f "$HOME/.local/share/applications/dd-imager.desktop"

echo "Done!"
