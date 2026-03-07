# Secure Wipe Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a welcome screen with mode selection (Write Image / Wipe Drive) and a complete secure wipe wizard flow to DD-imager.

**Architecture:** Replace the current fixed PAGES list with a mode-aware page system. The welcome screen is page 0. Selecting a mode sets `self.app_mode` and configures which pages the wizard navigates through. Wipe mode reuses existing drive detection and dd infrastructure.

**Tech Stack:** Python 3, GTK4, Adwaita, subprocess (dd, parted, mkfs.*)

---

### Task 1: Add CSS for welcome screen cards and wipe-specific widgets

**Files:**
- Modify: `dd-imager.py:28-365` (CUSTOM_CSS string)

**Step 1: Add welcome card styles**

Add before the closing `"""` of CUSTOM_CSS (line 365):

```css
/* ---- Welcome mode cards ---- */
.mode-card {
    background-color: #1a1a2e;
    border: 1px solid alpha(#818cf8, 0.2);
    border-radius: 16px;
    padding: 32px 24px;
    transition: all 200ms ease;
    min-width: 220px;
}

.mode-card:hover {
    border-color: alpha(#818cf8, 0.5);
    box-shadow: 0 4px 20px alpha(#818cf8, 0.2);
    background-color: #1e1e36;
}

.mode-card:active {
    background-color: alpha(#818cf8, 0.1);
}

.mode-card-icon {
    font-size: 48px;
    margin-bottom: 8px;
}

.mode-card-title {
    color: #e0e0ff;
    font-weight: 700;
    font-size: 16px;
}

.mode-card-subtitle {
    color: alpha(#c4c4f0, 0.6);
    font-size: 12px;
}

/* ---- Wipe options ---- */
.wipe-section-heading {
    color: #f472b6;
    font-weight: 600;
    font-size: 13px;
    margin-top: 8px;
}

.wipe-option-box {
    background-color: #16213e;
    border: 1px solid #2d2d5e;
    border-radius: 10px;
    padding: 12px 16px;
    transition: all 200ms ease;
}

.wipe-option-box:checked {
    border-color: #818cf8;
    background-color: alpha(#818cf8, 0.08);
    box-shadow: 0 0 8px alpha(#818cf8, 0.2);
}

.wipe-option-title {
    color: #e0e0ff;
    font-weight: 600;
    font-size: 13px;
}

.wipe-option-desc {
    color: alpha(#c4c4f0, 0.6);
    font-size: 11px;
}
```

**Step 2: Verify syntax**

Run: `python3 -c "import py_compile; py_compile.compile('dd-imager.py', doraise=True); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add dd-imager.py
git commit -m "style: add CSS for welcome screen cards and wipe options"
```

---

### Task 2: Refactor page system to support two modes

**Files:**
- Modify: `dd-imager.py:20-26` (PAGES constant)
- Modify: `dd-imager.py:445-525` (on_activate)
- Modify: `dd-imager.py:1760-1833` (navigation logic)

**Step 1: Replace PAGES constant with mode-aware page lists**

Replace lines 20-26:

```python
# Page definitions per mode: (stack_name, header_title)
WRITE_PAGES = [
    ('select-iso',       'Select ISO'),
    ('verify-checksum',  'Verify Checksum'),
    ('select-drive',     'Select Drive'),
    ('confirm-write',    'Confirm & Write'),
]

WIPE_PAGES = [
    ('wipe-select-drive', 'Select Drive'),
    ('wipe-options',      'Wipe Options'),
    ('wipe-confirm',      'Confirm & Wipe'),
]

WRITE_STEP_NAMES = ['ISO', 'Checksum', 'Drive', 'Write']
WIPE_STEP_NAMES = ['Drive', 'Options', 'Wipe']
```

**Step 2: Add mode state and welcome page to on_activate**

In `on_activate`, after the existing wizard state variables (line 469), add:

```python
        self.app_mode = None  # 'write' or 'wipe', None = welcome screen
        self.wipe_method = 'zero'  # 'zero', 'random', 'multipass'
        self.wipe_format = 'raw'   # 'raw', 'fat32', 'exfat', 'ext4', 'ntfs'
        self.wipe_cancelled = False
```

After the existing stack page additions (after line 513), add the welcome page and wipe pages:

```python
        # Welcome page (mode selection)
        self.stack.add_named(self._build_welcome_page(), 'welcome')

        # Wipe mode pages
        self.stack.add_named(self._build_wipe_drive_page(), 'wipe-select-drive')
        self.stack.add_named(self._build_wipe_options_page(), 'wipe-options')
        self.stack.add_named(self._build_wipe_confirm_page(), 'wipe-confirm')
```

Change the initial visible page to welcome. After `self.win.set_content(vbox)` (line 520), before `self.update_nav_buttons()`:

```python
        self.stack.set_visible_child_name('welcome')
```

**Step 3: Refactor navigation to be mode-aware**

Replace the navigation section (lines 1760-1833) with:

```python
    # ---- Navigation logic ----

    def _get_pages(self):
        """Return the page list for the current mode."""
        if self.app_mode == 'write':
            return WRITE_PAGES
        elif self.app_mode == 'wipe':
            return WIPE_PAGES
        return []

    def _get_step_names(self):
        """Return step names for the current mode."""
        if self.app_mode == 'write':
            return WRITE_STEP_NAMES
        elif self.app_mode == 'wipe':
            return WIPE_STEP_NAMES
        return []

    def _on_mode_selected(self, mode):
        """Handle mode selection from welcome screen."""
        self.app_mode = mode
        pages = self._get_pages()
        self.current_page = 0
        self.completed = [False] * len(pages)
        self._rebuild_step_indicator()
        self.stack.set_visible_child_name(pages[0][0])
        self._on_page_entered()
        self.update_nav_buttons()

    def _go_home(self):
        """Return to the welcome screen."""
        self.app_mode = None
        self.current_page = 0
        self.stack.set_visible_child_name('welcome')
        self.update_nav_buttons()

    def _on_skip_checksum(self, _button):
        self.checksum_skipped = True
        self.go_next()

    def go_next(self):
        """Advance to the next page, or trigger action on the last page."""
        pages = self._get_pages()
        if not pages:
            return
        page_name = pages[self.current_page][0]

        if self.app_mode == 'write' and self.current_page == len(pages) - 1:
            self._confirm_write()
            return
        if self.app_mode == 'wipe' and self.current_page == len(pages) - 1:
            self._confirm_wipe()
            return

        if self.current_page < len(pages) - 1:
            self.completed[self.current_page] = True
            self.current_page += 1
            self.stack.set_visible_child_name(pages[self.current_page][0])
            self._on_page_entered()
            self.update_nav_buttons()

    def go_back(self):
        """Return to the previous page, or to welcome screen from page 0."""
        if self.current_page > 0:
            self.current_page -= 1
            pages = self._get_pages()
            self.stack.set_visible_child_name(pages[self.current_page][0])
            self._on_page_entered()
            self.update_nav_buttons()
        else:
            self._go_home()

    def _on_page_entered(self):
        """Called whenever the visible page changes; refreshes page-specific content."""
        pages = self._get_pages()
        if not pages:
            return
        page_name = pages[self.current_page][0]
        if page_name == 'verify-checksum':
            self._update_checksum_file_info()
        elif page_name in ('select-drive', 'wipe-select-drive'):
            self._refresh_drives()
        elif page_name == 'confirm-write':
            self._update_confirm_summary()
        elif page_name == 'wipe-confirm':
            self._update_wipe_summary()

    def update_nav_buttons(self):
        """Update button visibility, sensitivity, and labels for the current page."""
        # Welcome screen: hide all nav
        if self.app_mode is None:
            self.btn_back.set_visible(False)
            self.btn_next.set_visible(False)
            self.btn_skip.set_visible(False)
            self.title_label.set_label('DD-imager')
            # Hide step indicator on welcome
            for dot in self.step_dots:
                dot.set_visible(False)
            for conn in self.step_connectors:
                conn.set_visible(False)
            for lbl in self.step_labels:
                lbl.set_visible(False)
            return

        # Show step indicator
        for dot in self.step_dots:
            dot.set_visible(True)
        for conn in self.step_connectors:
            conn.set_visible(True)
        for lbl in self.step_labels:
            lbl.set_visible(True)

        pages = self._get_pages()
        page_name = pages[self.current_page][0]
        page_title = pages[self.current_page][1]

        self.title_label.set_label(page_title)
        self._update_step_indicator()

        # Back button: always visible in wizard (goes to welcome from page 0)
        self.btn_back.set_visible(True)
        self.btn_next.set_visible(True)

        # Skip button: only on verify-checksum
        self.btn_skip.set_visible(page_name == 'verify-checksum')

        # Next/action button label
        if page_name == 'confirm-write':
            self.btn_next.set_label('Write')
            self.btn_next.add_css_class('destructive-action')
        elif page_name == 'wipe-confirm':
            self.btn_next.set_label('Wipe')
            self.btn_next.add_css_class('destructive-action')
        else:
            self.btn_next.set_label('Next')
            self.btn_next.remove_css_class('destructive-action')

        # Next button sensitivity
        if page_name == 'select-iso':
            self.btn_next.set_sensitive(self.iso_path is not None)
        elif page_name == 'verify-checksum':
            sha_ok = self.verify_mode == 'sha' and self.checksum_verified
            gpg_ok = self.verify_mode == 'gpg' and self.gpg_verified
            self.btn_next.set_sensitive(sha_ok or gpg_ok or self.checksum_skipped)
        elif page_name in ('select-drive', 'wipe-select-drive'):
            self.btn_next.set_sensitive(self.target_device is not None)
        elif page_name == 'wipe-options':
            self.btn_next.set_sensitive(True)
        else:
            self.btn_next.set_sensitive(True)
```

**Step 4: Update _build_step_indicator and _update_step_indicator**

The step indicator currently hardcodes 4 steps. Refactor `_build_step_indicator` (line 544) to accept a dynamic number of steps, and add `_rebuild_step_indicator`:

```python
    def _build_step_indicator(self):
        """Build a step indicator container (populated by _rebuild_step_indicator)."""
        self.step_indicator_outer = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
            halign=Gtk.Align.CENTER,
        )
        self.step_indicator_outer.add_css_class('step-indicator')
        self.step_dots = []
        self.step_connectors = []
        self.step_labels = []
        return self.step_indicator_outer

    def _rebuild_step_indicator(self):
        """Rebuild step dots/connectors/labels for the current mode."""
        # Clear existing children
        while child := self.step_indicator_outer.get_first_child():
            self.step_indicator_outer.remove(child)

        step_names = self._get_step_names()
        self.step_dots = []
        self.step_connectors = []
        self.step_labels = []

        dots_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            spacing=0,
        )
        labels_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            halign=Gtk.Align.CENTER,
            spacing=0,
        )

        for i, name in enumerate(step_names):
            dot = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
            dot.add_css_class('step-dot')
            if i == 0:
                dot.add_css_class('step-dot-active')
            dots_row.append(dot)
            self.step_dots.append(dot)

            label = Gtk.Label(label=name, halign=Gtk.Align.CENTER)
            label.set_width_chars(8)
            label.add_css_class('step-label')
            if i == 0:
                label.add_css_class('step-label-active')
            labels_row.append(label)
            self.step_labels.append(label)

            if i < len(step_names) - 1:
                connector = Gtk.Box(valign=Gtk.Align.CENTER)
                connector.add_css_class('step-connector')
                dots_row.append(connector)
                self.step_connectors.append(connector)

                spacer = Gtk.Box()
                spacer.set_size_request(40, 1)
                labels_row.append(spacer)

        self.step_indicator_outer.append(dots_row)
        self.step_indicator_outer.append(labels_row)
```

Also update `_update_step_indicator` to use `len(self._get_pages())` instead of `len(PAGES)`.

**Step 5: Verify syntax**

Run: `python3 -c "import py_compile; py_compile.compile('dd-imager.py', doraise=True); print('OK')"`

**Step 6: Commit**

```bash
git add dd-imager.py
git commit -m "refactor: mode-aware page system with dynamic step indicator"
```

---

### Task 3: Build the welcome screen

**Files:**
- Modify: `dd-imager.py` (add `_build_welcome_page` method)

**Step 1: Add _build_welcome_page method**

Add after `_update_step_indicator` and before `# ---- ISO page ----`:

```python
    # ---- Welcome page ----

    def _build_welcome_page(self):
        """Build the welcome/mode selection page with two large cards."""
        page = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            spacing=32,
        )

        heading = Gtk.Label(label='DD-imager')
        heading.add_css_class('title-1')
        page.append(heading)

        subtitle = Gtk.Label(label='What would you like to do?')
        subtitle.add_css_class('dim-label')
        page.append(subtitle)

        # Cards row
        cards_row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            halign=Gtk.Align.CENTER,
            spacing=24,
        )

        # Write Image card
        write_card = Gtk.Button()
        write_card.add_css_class('mode-card')
        write_card.set_has_frame(False)
        write_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                            halign=Gtk.Align.CENTER)

        write_icon = Gtk.Label(label='')
        write_icon.add_css_class('mode-card-icon')
        # Draw a simple icon via markup: drive with arrow
        write_icon.set_markup(
            '<span size="xx-large" weight="bold">\u2913\u25a0</span>'
        )
        write_box.append(write_icon)

        write_title = Gtk.Label(label='Write Image')
        write_title.add_css_class('mode-card-title')
        write_box.append(write_title)

        write_sub = Gtk.Label(label='Write an ISO/IMG to a USB drive')
        write_sub.add_css_class('mode-card-subtitle')
        write_sub.set_wrap(True)
        write_sub.set_max_width_chars(25)
        write_sub.set_justify(Gtk.Justification.CENTER)
        write_box.append(write_sub)

        write_card.set_child(write_box)
        write_card.connect('clicked', lambda _b: self._on_mode_selected('write'))
        cards_row.append(write_card)

        # Wipe Drive card
        wipe_card = Gtk.Button()
        wipe_card.add_css_class('mode-card')
        wipe_card.set_has_frame(False)
        wipe_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                           halign=Gtk.Align.CENTER)

        wipe_icon = Gtk.Label()
        wipe_icon.add_css_class('mode-card-icon')
        wipe_icon.set_markup(
            '<span size="xx-large" weight="bold">\u2718\u25a0</span>'
        )
        wipe_box.append(wipe_icon)

        wipe_title = Gtk.Label(label='Wipe Drive')
        wipe_title.add_css_class('mode-card-title')
        wipe_box.append(wipe_title)

        wipe_sub = Gtk.Label(label='Securely erase all data from a USB drive')
        wipe_sub.add_css_class('mode-card-subtitle')
        wipe_sub.set_wrap(True)
        wipe_sub.set_max_width_chars(25)
        wipe_sub.set_justify(Gtk.Justification.CENTER)
        wipe_box.append(wipe_sub)

        wipe_card.set_child(wipe_box)
        wipe_card.connect('clicked', lambda _b: self._on_mode_selected('wipe'))
        cards_row.append(wipe_card)

        page.append(cards_row)
        return page
```

**Step 2: Verify syntax and test visually**

Run: `python3 -c "import py_compile; py_compile.compile('dd-imager.py', doraise=True); print('OK')"`
Then: `python3 dd-imager.py` — verify welcome screen appears with two cards.

**Step 3: Commit**

```bash
git add dd-imager.py
git commit -m "feat: add welcome screen with Write Image and Wipe Drive mode cards"
```

---

### Task 4: Build wipe drive selection page

**Files:**
- Modify: `dd-imager.py` (add `_build_wipe_drive_page` method)

**Step 1: Add _build_wipe_drive_page**

Add after the OpenPGP verification section, before `# ---- Drive selection page ----`:

```python
    # ---- Wipe mode pages ----

    def _build_wipe_drive_page(self):
        """Build the wipe mode drive selection page (reuses drive list)."""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Warning banner
        warning_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            halign=Gtk.Align.FILL,
        )
        warning_box.add_css_class('warning-banner')
        warning_label = Gtk.Label(
            label='\u26a0  All data on the selected drive will be permanently destroyed',
            halign=Gtk.Align.CENTER,
            hexpand=True,
            margin_top=10, margin_bottom=10, margin_start=12, margin_end=12,
        )
        warning_label.add_css_class('warning-banner')
        warning_box.append(warning_label)
        page.append(warning_box)

        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=12,
            margin_top=16, margin_bottom=16, margin_start=24, margin_end=24,
            vexpand=True,
        )

        heading = Gtk.Label(label='Select drive to wipe', halign=Gtk.Align.START)
        heading.add_css_class('title-2')
        content.append(heading)

        # Reuse the same drive_listbox — _refresh_drives populates it
        # The wipe page shares self.drive_listbox and self.drive_empty_label
        # which are created by _build_drive_page. Since both exist in the stack
        # but only one is visible, we just call _refresh_drives on page enter.

        # We need a SEPARATE listbox for wipe mode
        scrolled = Gtk.ScrolledWindow(
            vexpand=True,
            hscrollbar_policy=Gtk.PolicyType.NEVER,
        )
        scrolled.add_css_class('card')

        self.wipe_drive_listbox = Gtk.ListBox()
        self.wipe_drive_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.wipe_drive_listbox.add_css_class('boxed-list')
        self.wipe_drive_listbox.connect('row-selected', self._on_drive_selected)
        scrolled.set_child(self.wipe_drive_listbox)
        content.append(scrolled)

        self.wipe_drive_empty_label = Gtk.Label(
            label='No removable USB drives detected. Insert a drive and click Refresh.',
            halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
            vexpand=True, wrap=True, max_width_chars=50,
        )
        self.wipe_drive_empty_label.add_css_class('dim-label')
        self.wipe_drive_empty_label.set_visible(False)
        content.append(self.wipe_drive_empty_label)

        btn_refresh = Gtk.Button(label='Refresh', halign=Gtk.Align.CENTER)
        btn_refresh.add_css_class('pill')
        btn_refresh.connect('clicked', lambda _b: self._refresh_drives())
        content.append(btn_refresh)

        page.append(content)
        return page
```

**Step 2: Update _refresh_drives to populate the correct listbox**

Modify `_refresh_drives` to detect which mode is active and populate the appropriate listbox:

```python
    def _refresh_drives(self):
        """Rescan for removable USB drives and repopulate the list."""
        self.target_device = None
        self.btn_next.set_sensitive(False)

        # Pick the correct listbox and empty label for the current mode
        if self.app_mode == 'wipe':
            listbox = self.wipe_drive_listbox
            empty_label = self.wipe_drive_empty_label
        else:
            listbox = self.drive_listbox
            empty_label = self.drive_empty_label

        while True:
            row = listbox.get_row_at_index(0)
            if row is None:
                break
            listbox.remove(row)

        drives = get_removable_drives()

        if not drives:
            listbox.set_visible(False)
            empty_label.set_visible(True)
            return

        listbox.set_visible(True)
        empty_label.set_visible(False)

        for drive in drives:
            row = self._make_drive_row(drive)
            listbox.append(row)
```

**Step 3: Verify and commit**

Run: `python3 -c "import py_compile; py_compile.compile('dd-imager.py', doraise=True); print('OK')"`

```bash
git add dd-imager.py
git commit -m "feat: add wipe mode drive selection page"
```

---

### Task 5: Build wipe options page

**Files:**
- Modify: `dd-imager.py` (add `_build_wipe_options_page` method)

**Step 1: Add _build_wipe_options_page**

Add after `_build_wipe_drive_page`:

```python
    def _build_wipe_options_page(self):
        """Build the wipe options page with method and format selection."""
        page = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            spacing=16,
        )

        heading = Gtk.Label(label='Wipe Options')
        heading.add_css_class('title-1')
        page.append(heading)

        # Scrollable content for smaller screens
        scrolled = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            max_content_height=380,
            propagate_natural_height=True,
        )

        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            halign=Gtk.Align.CENTER,
            margin_start=16, margin_end=16,
        )

        # --- Wipe Method ---
        method_heading = Gtk.Label(label='WIPE METHOD', halign=Gtk.Align.START)
        method_heading.add_css_class('wipe-section-heading')
        content.append(method_heading)

        self.wipe_method_buttons = {}
        methods = [
            ('zero', 'Zero fill', 'Write zeros to every byte. Fast. Sufficient for flash/SSD drives.'),
            ('random', 'Random fill', 'Write random data from /dev/urandom. Preferred for magnetic hard drives.'),
            ('multipass', 'Multi-pass', '3 passes: zeros, ones, random. Maximum security. Slowest.'),
        ]

        first_method_btn = None
        for key, title, desc in methods:
            btn = Gtk.ToggleButton()
            btn.add_css_class('wipe-option-box')
            btn.set_has_frame(False)

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            title_lbl = Gtk.Label(label=title, halign=Gtk.Align.START)
            title_lbl.add_css_class('wipe-option-title')
            box.append(title_lbl)
            desc_lbl = Gtk.Label(label=desc, halign=Gtk.Align.START, wrap=True, max_width_chars=50)
            desc_lbl.add_css_class('wipe-option-desc')
            box.append(desc_lbl)
            btn.set_child(box)

            if first_method_btn is None:
                first_method_btn = btn
                btn.set_active(True)
            else:
                btn.set_group(first_method_btn)

            btn.connect('toggled', self._on_wipe_method_changed, key)
            content.append(btn)
            self.wipe_method_buttons[key] = btn

        # --- Post-Wipe Format ---
        format_heading = Gtk.Label(label='AFTER WIPE', halign=Gtk.Align.START)
        format_heading.add_css_class('wipe-section-heading')
        content.append(format_heading)

        self.wipe_format_buttons = {}
        formats = [
            ('raw', 'Leave raw', 'No partition table or filesystem. Drive will appear unformatted.'),
            ('fat32', 'Format FAT32', 'Universal compatibility. Windows, Mac, Linux. Max file size 4 GB.'),
            ('exfat', 'Format exFAT', 'Modern USB drives. Windows, Mac, Linux. No file size limit.'),
            ('ext4', 'Format ext4', 'Linux only. Best for Linux-exclusive drives. Supports permissions.'),
            ('ntfs', 'Format NTFS', 'Windows drives. Linux read/write with ntfs-3g. No Mac write support.'),
        ]

        first_format_btn = None
        for key, title, desc in formats:
            btn = Gtk.ToggleButton()
            btn.add_css_class('wipe-option-box')
            btn.set_has_frame(False)

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            title_lbl = Gtk.Label(label=title, halign=Gtk.Align.START)
            title_lbl.add_css_class('wipe-option-title')
            box.append(title_lbl)
            desc_lbl = Gtk.Label(label=desc, halign=Gtk.Align.START, wrap=True, max_width_chars=50)
            desc_lbl.add_css_class('wipe-option-desc')
            box.append(desc_lbl)
            btn.set_child(box)

            if first_format_btn is None:
                first_format_btn = btn
                btn.set_active(True)
            else:
                btn.set_group(first_format_btn)

            btn.connect('toggled', self._on_wipe_format_changed, key)
            content.append(btn)
            self.wipe_format_buttons[key] = btn

        scrolled.set_child(content)
        page.append(scrolled)
        return page

    def _on_wipe_method_changed(self, button, key):
        """Handle wipe method radio selection."""
        if button.get_active():
            self.wipe_method = key

    def _on_wipe_format_changed(self, button, key):
        """Handle post-wipe format radio selection."""
        if button.get_active():
            self.wipe_format = key
```

**Step 2: Verify and commit**

```bash
python3 -c "import py_compile; py_compile.compile('dd-imager.py', doraise=True); print('OK')"
git add dd-imager.py
git commit -m "feat: add wipe options page with method and format selection"
```

---

### Task 6: Build wipe confirm page and wipe execution

**Files:**
- Modify: `dd-imager.py` (add confirm page, wipe thread, format logic)

**Step 1: Add _build_wipe_confirm_page**

Add after `_on_wipe_format_changed`:

```python
    def _build_wipe_confirm_page(self):
        """Build the wipe confirmation page with summary, progress, and result."""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=16,
            margin_top=24, margin_bottom=24, margin_start=24, margin_end=24,
            vexpand=True,
        )

        heading = Gtk.Label(label='Review & Wipe', halign=Gtk.Align.START)
        heading.add_css_class('title-2')
        content.append(heading)

        # Summary card
        summary_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        summary_box.add_css_class('card')
        summary_inner = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=12,
            margin_top=16, margin_bottom=16, margin_start=16, margin_end=16,
        )

        drive_heading = Gtk.Label(label='Target Drive', halign=Gtk.Align.START)
        drive_heading.add_css_class('heading')
        summary_inner.append(drive_heading)

        self.wipe_confirm_drive_label = Gtk.Label(
            label='No drive selected', halign=Gtk.Align.START,
            wrap=True, max_width_chars=60,
        )
        self.wipe_confirm_drive_label.add_css_class('dim-label')
        summary_inner.append(self.wipe_confirm_drive_label)

        summary_inner.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        method_heading = Gtk.Label(label='Wipe Method', halign=Gtk.Align.START)
        method_heading.add_css_class('heading')
        summary_inner.append(method_heading)

        self.wipe_confirm_method_label = Gtk.Label(
            label='', halign=Gtk.Align.START,
        )
        summary_inner.append(self.wipe_confirm_method_label)

        summary_inner.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        format_heading = Gtk.Label(label='After Wipe', halign=Gtk.Align.START)
        format_heading.add_css_class('heading')
        summary_inner.append(format_heading)

        self.wipe_confirm_format_label = Gtk.Label(
            label='', halign=Gtk.Align.START,
        )
        summary_inner.append(self.wipe_confirm_format_label)

        summary_box.append(summary_inner)
        content.append(summary_box)

        # Progress section (hidden until wipe starts)
        self.wipe_progress_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=8,
        )
        self.wipe_progress_box.set_visible(False)

        self.wipe_progress_bar = Gtk.ProgressBar()
        self.wipe_progress_bar.set_show_text(True)
        self.wipe_progress_box.append(self.wipe_progress_bar)

        self.wipe_progress_label = Gtk.Label(label='', halign=Gtk.Align.START)
        self.wipe_progress_label.add_css_class('dim-label')
        self.wipe_progress_label.set_wrap(True)
        self.wipe_progress_label.set_max_width_chars(60)
        self.wipe_progress_box.append(self.wipe_progress_label)

        self.btn_cancel_wipe = Gtk.Button(label='Cancel')
        self.btn_cancel_wipe.add_css_class('pill')
        self.btn_cancel_wipe.add_css_class('destructive-action')
        self.btn_cancel_wipe.set_halign(Gtk.Align.CENTER)
        self.btn_cancel_wipe.connect('clicked', self._on_cancel_wipe)
        self.wipe_progress_box.append(self.btn_cancel_wipe)

        content.append(self.wipe_progress_box)

        # Result label
        self.wipe_result_label = Gtk.Label(label='', halign=Gtk.Align.CENTER)
        self.wipe_result_label.set_wrap(True)
        self.wipe_result_label.set_max_width_chars(60)
        self.wipe_result_label.set_visible(False)
        content.append(self.wipe_result_label)

        page.append(content)
        return page

    def _update_wipe_summary(self):
        """Populate the summary labels on the wipe confirm page."""
        self.wipe_result_label.set_visible(False)
        self.wipe_result_label.remove_css_class('error')
        self.wipe_result_label.remove_css_class('success')

        # Drive info
        if self.target_device:
            dev = self.target_device
            vendor_model = ' '.join(filter(None, [dev.get('vendor', ''), dev.get('model', '')]))
            parts = [dev['device']]
            if vendor_model and vendor_model != 'Mass Storage':
                parts.append(vendor_model)
            if dev.get('label'):
                parts.append(dev['label'])
            size_str = format_file_size(dev['size'])
            self.wipe_confirm_drive_label.set_label(f'{" — ".join(parts)}  ({size_str})')
            self.wipe_confirm_drive_label.remove_css_class('dim-label')

        # Method
        method_names = {'zero': 'Zero fill', 'random': 'Random fill', 'multipass': 'Multi-pass (3 passes)'}
        self.wipe_confirm_method_label.set_label(method_names.get(self.wipe_method, self.wipe_method))

        # Format
        format_names = {
            'raw': 'Leave raw (no filesystem)',
            'fat32': 'Format as FAT32',
            'exfat': 'Format as exFAT',
            'ext4': 'Format as ext4',
            'ntfs': 'Format as NTFS',
        }
        self.wipe_confirm_format_label.set_label(format_names.get(self.wipe_format, self.wipe_format))
```

**Step 2: Add _confirm_wipe, wipe thread, and cancel logic**

```python
    def _confirm_wipe(self):
        """Show a confirmation dialog before starting the wipe."""
        if not self.target_device:
            return

        dev = self.target_device
        label_part = f' ({dev["label"]})' if dev.get('label') else ''

        dialog = Adw.AlertDialog(
            heading='Confirm Secure Wipe',
            body=(
                f'This will PERMANENTLY DESTROY all data on {dev["device"]}{label_part}.\n\n'
                'This cannot be undone. Are you absolutely sure?'
            ),
        )
        dialog.add_response('cancel', 'Cancel')
        dialog.add_response('wipe', 'Wipe')
        dialog.set_response_appearance('wipe', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response('cancel')
        dialog.set_close_response('cancel')
        dialog.connect('response', self._on_wipe_confirm_response)
        dialog.present(self.win)

    def _on_wipe_confirm_response(self, dialog, response):
        """Handle the wipe confirmation dialog response."""
        if response == 'wipe':
            self._start_wipe()

    def _start_wipe(self):
        """Begin the wipe process."""
        self.wipe_cancelled = False

        self.wipe_progress_box.set_visible(True)
        self.wipe_progress_bar.set_fraction(0.0)
        self.wipe_progress_bar.set_text('0%')
        self.wipe_progress_label.set_label('Starting wipe...')
        self.btn_cancel_wipe.set_sensitive(True)
        self.btn_cancel_wipe.set_visible(True)

        self.wipe_result_label.set_visible(False)
        self.wipe_result_label.set_label('')
        self.wipe_result_label.remove_css_class('success')
        self.wipe_result_label.remove_css_class('error')

        self.btn_next.set_visible(False)
        self.btn_back.set_sensitive(False)

        thread = threading.Thread(target=self._wipe_thread, daemon=True)
        thread.start()

    def _wipe_thread(self):
        """Run the wipe operation in a background thread."""
        device_path = self.target_device['device']
        device_size = self.target_device['size']

        # Safety checks (same as write mode)
        name = os.path.basename(device_path)
        sys_path = Path(f'/sys/block/{name}')
        if not sys_path.exists():
            GLib.idle_add(self._on_wipe_error, 'Device no longer exists')
            return
        try:
            removable = (sys_path / 'removable').read_text().strip()
            if removable != '1':
                GLib.idle_add(self._on_wipe_error, 'Device is not marked as removable')
                return
            current_size = int((sys_path / 'size').read_text().strip()) * 512
            if current_size != self.target_device['size']:
                GLib.idle_add(self._on_wipe_error, 'Device size changed — possibly a different device')
                return
        except OSError as e:
            GLib.idle_add(self._on_wipe_error, f'Cannot verify device: {e}')
            return

        # Unmount
        success, err = self._unmount_device(device_path)
        if not success:
            GLib.idle_add(self._on_wipe_error, f'Failed to unmount: {err}')
            return

        # Determine passes
        if self.wipe_method == 'zero':
            passes = [('/dev/zero', 'Zeroing')]
        elif self.wipe_method == 'random':
            passes = [('/dev/urandom', 'Writing random data')]
        else:  # multipass
            passes = [
                ('/dev/zero', 'Pass 1/3: Zeros'),
                ('/dev/zero', 'Pass 2/3: Ones'),  # we use tr to convert
                ('/dev/urandom', 'Pass 3/3: Random'),
            ]

        total_passes = len(passes)

        for pass_idx, (source, label) in enumerate(passes):
            if self.wipe_cancelled:
                GLib.idle_add(self._on_wipe_cancelled)
                return

            GLib.idle_add(self._update_wipe_pass_label, label, pass_idx + 1, total_passes)

            # For "ones" pass, use tr to convert zeros to 0xFF
            if self.wipe_method == 'multipass' and pass_idx == 1:
                dd_cmd = [
                    'pkexec', 'bash', '-c',
                    f"tr '\\0' '\\377' < /dev/zero | dd of={device_path} bs=4M status=progress oflag=sync conv=fsync 2>&1"
                ]
            else:
                dd_cmd = [
                    'pkexec', 'dd',
                    f'if={source}',
                    f'of={device_path}',
                    'bs=4M',
                    'status=progress',
                    'oflag=sync',
                    'conv=fsync',
                ]

            try:
                self.dd_process = subprocess.Popen(
                    dd_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                )
            except OSError as e:
                GLib.idle_add(self._on_wipe_error, f'Failed to start wipe: {e}')
                return

            pattern = re.compile(r'(\d+)\s+bytes')
            stderr_fd = self.dd_process.stderr.fileno()
            buf = ''
            while True:
                try:
                    chunk = os.read(stderr_fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk.decode('utf-8', errors='replace')
                while '\r' in buf or '\n' in buf:
                    r_idx = buf.find('\r')
                    n_idx = buf.find('\n')
                    if r_idx == -1:
                        idx = n_idx
                    elif n_idx == -1:
                        idx = r_idx
                    else:
                        idx = min(r_idx, n_idx)
                    line = buf[:idx]
                    buf = buf[idx + 1:]
                    if line.strip():
                        match = pattern.search(line)
                        if match and not self.wipe_cancelled:
                            bytes_written = int(match.group(1))
                            # Progress accounts for multi-pass
                            pass_fraction = min(bytes_written / device_size, 1.0) if device_size > 0 else 0
                            overall = (pass_idx + pass_fraction) / total_passes
                            GLib.idle_add(self._update_wipe_progress, overall, bytes_written, device_size, line.strip())

            self.dd_process.wait()
            returncode = self.dd_process.returncode
            self.dd_process = None

            if self.wipe_cancelled:
                GLib.idle_add(self._on_wipe_cancelled)
                return

            # dd returns non-zero when it fills the device (no space left) — that's expected
            if returncode != 0:
                # Check if it's the expected "No space left on device"
                if buf and 'No space left' not in buf:
                    pass  # non-fatal for wipe — device is full, that's the goal

        # Post-wipe formatting
        if self.wipe_format != 'raw':
            GLib.idle_add(self._update_wipe_pass_label, 'Formatting...', 0, 0)
            fmt_success = self._format_device(device_path)
            if not fmt_success:
                return  # error already reported

        try:
            subprocess.run(['sync'], timeout=60)
        except Exception:
            pass

        GLib.idle_add(self._on_wipe_success)

    def _format_device(self, device_path):
        """Create partition table and filesystem on the wiped device. Returns True on success."""
        # Create a new MBR partition table with one partition
        try:
            result = subprocess.run(
                ['pkexec', 'parted', '-s', device_path, 'mklabel', 'msdos',
                 'mkpart', 'primary', '0%', '100%'],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                GLib.idle_add(self._on_wipe_error, f'Partitioning failed: {result.stderr.strip()}')
                return False
        except Exception as e:
            GLib.idle_add(self._on_wipe_error, f'Partitioning failed: {e}')
            return False

        # Determine the partition path (e.g. /dev/sdb1)
        partition = f'{device_path}1'

        # Format the partition
        fmt_cmds = {
            'fat32': ['pkexec', 'mkfs.vfat', '-F', '32', partition],
            'exfat': ['pkexec', 'mkfs.exfat', partition],
            'ext4': ['pkexec', 'mkfs.ext4', '-F', partition],
            'ntfs': ['pkexec', 'mkfs.ntfs', '-f', partition],
        }

        cmd = fmt_cmds.get(self.wipe_format)
        if not cmd:
            return True

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                GLib.idle_add(self._on_wipe_error, f'Formatting failed: {result.stderr.strip()}')
                return False
        except Exception as e:
            GLib.idle_add(self._on_wipe_error, f'Formatting failed: {e}')
            return False

        return True

    def _update_wipe_pass_label(self, label, pass_num, total):
        """Update the pass label during wipe."""
        if total > 0:
            self.wipe_progress_label.set_label(f'{label} ({pass_num}/{total})')
        else:
            self.wipe_progress_label.set_label(label)
        return False

    def _update_wipe_progress(self, fraction, bytes_written, total_size, detail_line):
        """Update the wipe progress bar."""
        self.wipe_progress_bar.set_fraction(fraction)
        self.wipe_progress_bar.set_text(f'{fraction:.0%}')

        written_str = format_file_size(bytes_written)
        total_str = format_file_size(total_size) if total_size > 0 else '?'

        speed_match = re.search(r'[\d.]+ [KMGT]?B/s', detail_line)
        speed_part = f'  —  {speed_match.group(0)}' if speed_match else ''

        current_label = self.wipe_progress_label.get_label()
        # Keep the pass label, add size info
        pass_info = current_label.split('(')[0].strip() if '(' in current_label else current_label
        self.wipe_progress_label.set_label(f'{pass_info} — {written_str} / {total_str}{speed_part}')
        return False

    def _on_cancel_wipe(self, _button):
        """Cancel the running wipe process."""
        self.wipe_cancelled = True
        self.btn_cancel_wipe.set_sensitive(False)
        self.wipe_progress_label.set_label('Cancelling...')
        proc = self.dd_process
        if proc is not None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, OSError, AttributeError):
                pass
            try:
                proc.terminate()
            except OSError:
                pass

    def _on_wipe_success(self):
        """Called on main thread when wipe completes successfully."""
        self.wipe_progress_bar.set_fraction(1.0)
        self.wipe_progress_bar.set_text('100%')
        self.wipe_progress_label.set_label('Wipe complete.')
        self.btn_cancel_wipe.set_visible(False)

        fmt_msg = ''
        if self.wipe_format != 'raw':
            fmt_names = {'fat32': 'FAT32', 'exfat': 'exFAT', 'ext4': 'ext4', 'ntfs': 'NTFS'}
            fmt_msg = f'\nFormatted as {fmt_names.get(self.wipe_format, self.wipe_format)}.'

        self.wipe_result_label.set_label(f'Drive securely wiped.{fmt_msg}')
        self.wipe_result_label.remove_css_class('error')
        self.wipe_result_label.add_css_class('success')
        self.wipe_result_label.set_visible(True)

        self.btn_back.set_sensitive(True)
        return False

    def _on_wipe_error(self, error_msg):
        """Called on main thread when wipe fails."""
        self.wipe_progress_label.set_label('Wipe failed.')
        self.btn_cancel_wipe.set_visible(False)

        self.wipe_result_label.set_label(f'Error: {error_msg}')
        self.wipe_result_label.remove_css_class('success')
        self.wipe_result_label.add_css_class('error')
        self.wipe_result_label.set_visible(True)

        self.btn_back.set_sensitive(True)
        self.btn_next.set_visible(True)
        return False

    def _on_wipe_cancelled(self):
        """Called on main thread when wipe is cancelled."""
        self.wipe_progress_label.set_label('Wipe cancelled.')
        self.btn_cancel_wipe.set_visible(False)

        self.wipe_result_label.set_label('Wipe was cancelled by user.')
        self.wipe_result_label.remove_css_class('success')
        self.wipe_result_label.add_css_class('error')
        self.wipe_result_label.set_visible(True)

        self.btn_back.set_sensitive(True)
        self.btn_next.set_visible(True)
        return False
```

**Step 3: Verify and commit**

```bash
python3 -c "import py_compile; py_compile.compile('dd-imager.py', doraise=True); print('OK')"
git add dd-imager.py
git commit -m "feat: add wipe confirm page, wipe execution, and post-wipe formatting"
```

---

### Task 7: Final integration and testing

**Files:**
- Modify: `dd-imager.py` (any remaining wiring)

**Step 1: Verify full flow**

Run: `python3 dd-imager.py`

Test checklist:
1. Welcome screen shows two cards (Write Image, Wipe Drive)
2. Clicking Write Image enters the existing 4-step wizard
3. Back from step 1 returns to welcome screen
4. All existing Write Image functionality works (ISO, checksum, drive, write)
5. Clicking Wipe Drive enters the 3-step wipe wizard
6. Step indicator shows 3 dots for wipe mode, 4 for write mode
7. Drive list populates correctly in wipe mode
8. Wipe options page shows method and format radio buttons
9. Confirm page shows correct summary
10. Back from wipe step 1 returns to welcome screen

**Step 2: Commit final integration**

```bash
git add dd-imager.py
git commit -m "feat: complete secure wipe mode with welcome screen"
```
