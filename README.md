<p align="center">
  <img src="icons/dd-imager.svg" width="128" height="128" alt="DD-imager">
</p>

<h1 align="center">DD-imager</h1>

<p align="center">A lightweight GTK4 wizard for safely writing ISO/IMG files to USB drives — and securely wiping them.</p>

## Features

- **Write Image** — step-by-step wizard to write ISO/IMG files to USB drives
- **Secure Wipe** — erase drives with zero fill, random fill, or multi-pass overwrite
- **Quick Erase** — fast partition table wipe for everyday reformatting
- **Post-wipe formatting** — format as FAT32, exFAT, ext4, or NTFS with custom drive label
- **SHA-256 checksum verification** — verify image integrity before writing
- **OpenPGP signature verification** — verify `.sig` files (e.g. Tails, Qubes) with GPG
- Only shows removable USB drives — internal drives are never exposed
- Real-time progress bar with speed display
- Double confirmation before any destructive operation
- Cross-distro: Arch, Debian, Ubuntu, Fedora, and more

## Safety

1. **Internal drives are filtered out** — only removable USB devices are shown
2. **No default drive selection** — you must explicitly choose a target
3. **Double confirmation** — a dialog warns you before any write or wipe
4. **Device re-verification** — the target is re-checked immediately before writing to guard against device changes
5. **Size check** — warns if the image is larger than the target drive
6. **Auto-unmount** — target partitions are unmounted before writing

## Install

```bash
git clone https://github.com/invisi101/DD-imager.git
cd DD-imager
chmod +x install.sh
./install.sh
```

Supports Arch Linux, Debian/Ubuntu, and Fedora. The script installs all dependencies and adds DD-imager to your app launcher.

## Uninstall

```bash
./uninstall.sh
```

## Usage

Launch from your app launcher, or:

```bash
dd-imager
```

A welcome screen lets you choose between **Write Image** and **Wipe Drive**.

### Write Image (4 steps)

1. **Select ISO** — browse for an `.iso` or `.img` file
2. **Verify Checksum** — verify with SHA-256 hash or OpenPGP signature (or skip)
3. **Select Drive** — pick from detected removable USB drives
4. **Confirm & Write** — review, confirm, and write with live progress

### Wipe Drive (3 steps)

1. **Select Drive** — pick the drive to wipe
2. **Wipe Options** — choose wipe method and optional post-wipe format with drive label
3. **Confirm & Wipe** — review, confirm, and wipe with live progress

## Dependencies

- Python 3, GTK 4, libadwaita, python-gobject
- udisks2, parted
- dosfstools, exfatprogs, ntfs-3g (for formatting)

All installed automatically by `install.sh`.

## License

MIT
