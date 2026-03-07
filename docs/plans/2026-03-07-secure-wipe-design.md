# Secure Wipe Mode — Design

## Welcome Screen (new Page 0)

Replace current "Select ISO" entry with a mode selection screen showing two large cards:

- **Write Image** — icon showing data flowing onto a drive, subtitle "Write an ISO/IMG to a USB drive"
- **Wipe Drive** — icon showing something being wiped clean, subtitle "Securely erase all data from a USB drive"

Clicking a card enters the respective wizard flow.

## Write Image Flow

Same as current (Select ISO → Verify Checksum → Select Drive → Confirm & Write), shifted by one page index.

## Wipe Drive Flow (3 steps)

### Step 1 — Select Drive
Reuses existing drive detection/listing UI.

### Step 2 — Wipe Options

**Wipe Method** (radio buttons):
- **Zero fill** — "Write zeros to every byte. Fast. Sufficient for flash/SSD drives." (default)
- **Random fill** — "Write random data from /dev/urandom. Preferred for magnetic hard drives."
- **Multi-pass** — "3 passes: zeros, ones, random. Maximum security. Slowest."

**After Wipe** (radio buttons):
- **Leave raw** — "No partition table or filesystem. Drive will appear unformatted." (default)
- **Format FAT32** — "Universal compatibility. Windows, Mac, Linux. Max file size: 4 GB."
- **Format exFAT** — "Modern USB drives. Windows, Mac, Linux. No file size limit."
- **Format ext4** — "Linux only. Best for Linux-exclusive drives. Supports permissions."
- **Format NTFS** — "Windows drives. Linux read/write with ntfs-3g. No Mac write support."

### Step 3 — Confirm & Wipe
Summary card showing drive, method, and post-wipe action. Destructive "Wipe" button with confirmation dialog. Progress bar with pass indicator (e.g. "Pass 2/3"). Result label on completion.

## Implementation

- `dd if=/dev/zero` or `dd if=/dev/urandom` via `pkexec` for wiping
- Multi-pass runs 3 sequential dd commands
- Post-wipe formatting via `pkexec parted` + `mkfs.*`
- Step indicator adapts per mode
- All in `dd-imager.py`
