#!/bin/bash
set -e

echo "Installing DD-imager..."

# Detect distro and install dependencies
install_deps() {
    if command -v pacman &>/dev/null; then
        echo "Detected Arch Linux"
        sudo pacman -S --needed --noconfirm python python-gobject gtk4 libadwaita udisks2
    elif command -v apt &>/dev/null; then
        echo "Detected Debian/Ubuntu"
        sudo apt install -y python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 udisks2
    elif command -v dnf &>/dev/null; then
        echo "Detected Fedora"
        sudo dnf install -y python3 python3-gobject gtk4 libadwaita udisks2
    else
        echo "Could not detect package manager. Please install these manually:"
        echo "  python3, python-gobject, gtk4, libadwaita, udisks2"
        exit 1
    fi
}

install_deps

# Install the app
sudo install -Dm755 dd-imager.py /usr/local/bin/dd-imager
sudo install -Dm644 com.invisi101.dd-imager.policy /usr/share/polkit-1/actions/com.invisi101.dd-imager.policy
install -Dm644 dd-imager.desktop "$HOME/.local/share/applications/dd-imager.desktop"
sudo install -Dm644 icons/dd-imager.svg /usr/share/icons/hicolor/scalable/apps/dd-imager.svg
gtk-update-icon-cache -f /usr/share/icons/hicolor/ 2>/dev/null || true

# Update desktop entry with installed path
sed -i 's|^Exec=.*|Exec=dd-imager|' "$HOME/.local/share/applications/dd-imager.desktop"
sed -i 's|^Icon=.*|Icon=dd-imager|' "$HOME/.local/share/applications/dd-imager.desktop"

echo "Done! Launch 'DD-imager' from your app launcher or run: dd-imager"
