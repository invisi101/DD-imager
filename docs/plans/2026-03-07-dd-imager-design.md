# DD-imager Design

## Overview

A lightweight GTK4 GUI wizard for writing ISO/IMG files to USB drives safely. Replaces Raspberry Pi Imager with a simpler, cross-distro tool that wraps `dd`.

## Requirements

- Wizard-style step-by-step flow
- Cross-distro: Arch, Kali, Debian, Ubuntu, etc.
- Safety: never expose internal drives as write targets
- Optional SHA-256 checksum verification
- Only `dd` runs as root (via pkexec), GUI stays unprivileged

## Tech Stack

- Python 3 + GTK4 (pygobject)
- Single main script + .desktop entry
- No external dependencies beyond GTK4 and Python (pre-installed on most distros)

## Wizard Flow

### Step 1: Select ISO
- Default browse location: ~/Downloads
- File filter: .iso, .img files
- Shows selected filename and size
- Next button disabled until file selected

### Step 2: Verify Checksum (Optional)
- Displays selected file name and size
- Text field to paste expected SHA-256
- Verify button computes and compares hash
- Green/red result indicator
- Skip button to proceed without verifying

### Step 3: Select Target Drive
- Lists only removable USB devices
- Filters out internal NVMe/SATA drives using /sys/block/*/removable
- Displays: device name, label, size, mount point
- Refresh button to rescan devices
- No default selection — user must explicitly choose
- Warning banner: "All data on the selected drive will be destroyed"

### Step 4: Confirm & Write
- Summary panel: ISO filename, target drive, sizes
- Red "Write" confirmation button
- Auto-unmounts target drive before writing
- Progress bar driven by dd status=progress output
- Cancel button during write
- Success/failure notification on completion

## Safety Features

1. Internal drives excluded (removable flag check in sysfs)
2. No default drive selection
3. Double confirmation before write
4. Auto-unmount before write
5. Only dd runs as root via pkexec

## Privilege Model

- GUI runs as user
- Write operation uses: pkexec dd if=<iso> of=<device> bs=4M status=progress oflag=sync
- Polkit policy file included for clean authentication

## File Structure

```
DD-imager/
  dd-imager.py          # Main application
  dd-imager.desktop     # Desktop entry
  com.invisi101.dd-imager.policy  # Polkit policy
  icons/dd-imager.svg   # App icon
  README.md
  LICENSE
```

## Target Repo

github.com/invisi101/DD-imager
