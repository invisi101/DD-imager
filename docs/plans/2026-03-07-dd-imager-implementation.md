# DD-imager Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a GTK4 wizard GUI that safely writes ISO/IMG files to USB drives using dd.

**Architecture:** Single-file Python GTK4 app using Gtk.Stack for wizard pages. Device detection reads sysfs to filter removable drives only. dd runs via pkexec subprocess with progress parsed from stderr.

**Tech Stack:** Python 3, GTK4 (pygobject), libadwaita (for modern GNOME styling), pkexec for privilege elevation

---

### Task 1: Project Scaffold & Polkit Policy

**Files:**
- Create: `dd-imager.py` (entry point, empty app shell)
- Create: `com.invisi101.dd-imager.policy` (polkit policy)
- Create: `dd-imager.desktop` (desktop entry)

**Step 1: Create the polkit policy file**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC
 "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/PolicyKit/1.0/policyconfig.dtd">
<policyconfig>
  <vendor>DD-imager</vendor>
  <vendor_url>https://github.com/invisi101/DD-imager</vendor_url>
  <action id="com.invisi101.dd-imager.write">
    <description>Write disk image to USB device</description>
    <message>Authentication is required to write a disk image</message>
    <defaults>
      <allow_any>auth_admin</allow_any>
      <allow_inactive>auth_admin</allow_inactive>
      <allow_active>auth_admin_keep</allow_active>
    </defaults>
    <annotate key="org.freedesktop.policykit.exec.path">/usr/bin/dd</annotate>
    <annotate key="org.freedesktop.policykit.exec.allow_gui">true</annotate>
  </action>
</policyconfig>
```

**Step 2: Create minimal GTK4 app shell**

```python
#!/usr/bin/env python3
"""DD-imager — Safe USB image writer."""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw

class DDImagerApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.invisi101.dd-imager')
        self.connect('activate', self.on_activate)

    def on_activate(self, app):
        win = Adw.ApplicationWindow(application=app, title='DD-imager', default_width=600, default_height=500)
        label = Gtk.Label(label='DD-imager scaffold')
        win.set_content(label)
        win.present()

if __name__ == '__main__':
    app = DDImagerApp()
    app.run()
```

**Step 3: Create desktop entry**

```ini
[Desktop Entry]
Type=Application
Name=DD-imager
Comment=Safely write ISO/IMG files to USB drives
Exec=python3 /path/to/dd-imager.py
Icon=dd-imager
Categories=Utility;System;
StartupNotify=false
```

**Step 4: Run to verify app launches**

Run: `python3 dd-imager.py`
Expected: A window appears with "DD-imager scaffold" text.

**Step 5: Commit**

```bash
git add dd-imager.py com.invisi101.dd-imager.policy dd-imager.desktop
git commit -m "feat: project scaffold with app shell, polkit policy, desktop entry"
```

---

### Task 2: Wizard Navigation (Stack + Header Bar)

**Files:**
- Modify: `dd-imager.py`

**Step 1: Build the wizard skeleton with Gtk.Stack and navigation buttons**

Replace the on_activate method to create:
- An Adw.HeaderBar with title
- A Gtk.Stack with 4 named pages: "select-iso", "verify-checksum", "select-drive", "confirm-write"
- Back / Next / Skip buttons in the header bar
- Navigation logic: Next advances stack page, Back goes back
- Next button disabled by default (each page enables it when ready)
- Page 1 has no Back, Page 4 has "Write" instead of Next

Each page is a placeholder Gtk.Box with a label for now.

**Step 2: Run to verify navigation works**

Run: `python3 dd-imager.py`
Expected: Can click Next/Back through all 4 pages. Button states update correctly.

**Step 3: Commit**

```bash
git add dd-imager.py
git commit -m "feat: wizard navigation with stack pages and header buttons"
```

---

### Task 3: Page 1 — ISO File Selection

**Files:**
- Modify: `dd-imager.py`

**Step 1: Build the ISO selection page**

Replace the "select-iso" placeholder with:
- A "Browse" button that opens Gtk.FileDialog
- File filter for .iso and .img extensions
- Label showing selected filename and human-readable file size
- Store selected file path on the app/window object
- Enable Next button only when a file is selected
- Default browse path: ~/Downloads

**Step 2: Run and test file selection**

Run: `python3 dd-imager.py`
Expected: Browse opens ~/Downloads filtered to ISO/IMG. Selecting a file shows name+size, enables Next.

**Step 3: Commit**

```bash
git add dd-imager.py
git commit -m "feat: ISO file selection page with file dialog and filter"
```

---

### Task 4: Page 2 — Checksum Verification

**Files:**
- Modify: `dd-imager.py`

**Step 1: Build the checksum page**

Replace the "verify-checksum" placeholder with:
- Display selected ISO filename and size
- Gtk.Entry for pasting expected SHA-256 hash
- "Verify" button that computes SHA-256 in a background thread (GLib.Thread or asyncio)
- Spinner while computing
- Green checkmark label on match, red X on mismatch
- "Skip" button in header bar (visible only on this page) that advances to page 3
- Next button enabled after successful verify or if user clicks Skip

Use hashlib.sha256 with chunked reads (8MB chunks) for the hash computation to avoid blocking.

**Step 2: Test with a known file and hash**

Run: `python3 dd-imager.py`, select a small file, paste its sha256sum output, click Verify.
Expected: Spinner shows, then green match indicator. Wrong hash shows red mismatch.

**Step 3: Commit**

```bash
git add dd-imager.py
git commit -m "feat: optional SHA-256 checksum verification page"
```

---

### Task 5: Page 3 — Target Drive Selection

**Files:**
- Modify: `dd-imager.py`

**Step 1: Build the device detection function**

```python
def get_removable_drives():
    """Return list of removable block devices from sysfs."""
    drives = []
    for dev in Path('/sys/block').iterdir():
        # Skip loop, ram, zram, dm, sr, nvme, and other non-USB devices
        name = dev.name
        if any(name.startswith(p) for p in ('loop', 'ram', 'zram', 'dm-', 'sr', 'nvme')):
            continue
        removable = (dev / 'removable').read_text().strip()
        if removable != '1':
            continue
        size_sectors = int((dev / 'size').read_text().strip())
        size_bytes = size_sectors * 512
        if size_bytes == 0:
            continue
        device_path = f'/dev/{name}'
        # Get label from lsblk
        # ... lsblk -nro LABEL /dev/sdX
        drives.append({
            'device': device_path,
            'name': name,
            'size': size_bytes,
            'label': label,
            'mounted': mount_points,
        })
    return drives
```

**Step 2: Build the drive selection page**

Replace the "select-drive" placeholder with:
- Gtk.ListBox showing removable drives (device, label, size)
- Refresh button to rescan
- Warning banner: "All data on the selected drive will be destroyed"
- No drive selected by default
- Next button enabled only when a drive is selected
- If no drives found, show message: "No removable USB drives detected. Insert a drive and click Refresh."

**Step 3: Test with a USB drive inserted**

Run: `python3 dd-imager.py`, navigate to page 3.
Expected: USB drive appears in list. Internal NVMe/SATA drives do NOT appear. Selecting a drive enables Next.

**Step 4: Commit**

```bash
git add dd-imager.py
git commit -m "feat: removable drive detection and selection page"
```

---

### Task 6: Page 4 — Confirm & Write

**Files:**
- Modify: `dd-imager.py`

**Step 1: Build the confirmation and write page**

Replace the "confirm-write" placeholder with:
- Summary section: ISO name + size, target drive + size
- Red "Write" button (Gtk.Button with destructive-action CSS class)
- On click: show confirmation dialog "This will erase ALL data on /dev/sdX. Continue?"
- On confirm:
  1. Unmount all partitions on target device: subprocess umount /dev/sdX*
  2. Run: pkexec dd if=<iso> of=<device> bs=4M status=progress oflag=sync conv=fsync
  3. Parse dd stderr for bytes written, update Gtk.ProgressBar (fraction = bytes_written / iso_size)
  4. Run in subprocess with GLib.io_add_watch or threading to keep UI responsive
- Cancel button to kill the dd subprocess
- On success: green success message + sync
- On failure: red error message with stderr output

**Step 2: Test the write flow (use a sacrificial USB drive)**

Run: `python3 dd-imager.py`, go through all steps, write an ISO to a USB drive.
Expected: Progress bar updates, write completes successfully.

**Step 3: Commit**

```bash
git add dd-imager.py
git commit -m "feat: confirm and write page with progress bar and pkexec dd"
```

---

### Task 7: App Icon

**Files:**
- Create: `icons/dd-imager.svg`

**Step 1: Create a simple SVG icon**

A minimal icon: USB drive shape with an arrow pointing into it. Can be created programmatically or use a stock icon reference.

**Step 2: Update desktop entry with icon path**

**Step 3: Commit**

```bash
git add icons/dd-imager.svg dd-imager.desktop
git commit -m "feat: add app icon"
```

---

### Task 8: README & License

**Files:**
- Create: `README.md`
- Create: `LICENSE`

**Step 1: Write README**

Include:
- Project description and screenshot placeholder
- Features list
- Installation instructions (Arch, Debian/Ubuntu)
- Dependencies: python3, python-gobject, gtk4, libadwaita
- Usage
- Safety features explanation
- License

**Step 2: Add MIT LICENSE file**

**Step 3: Commit**

```bash
git add README.md LICENSE
git commit -m "docs: add README and MIT license"
```

---

### Task 9: GitHub Upload

**Step 1: Initialize repo and push**

```bash
cd /home/neil/dev/DD-imager
git init
git remote add origin git@github.com:invisi101/DD-imager.git
git branch -M main
git push -u origin main
```

---

### Task 10: Install on local system

**Step 1: Install files**

- Copy dd-imager.py to ~/.local/bin/dd-imager
- Copy desktop entry to ~/.local/share/applications/
- Copy polkit policy to /etc/polkit-1/actions/ (requires sudo)
- Copy icon to ~/.local/share/icons/

**Step 2: Test from launcher**

Launch from rofi, verify full flow works.

**Step 3: Commit any path fixes**
