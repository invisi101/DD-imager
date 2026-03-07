#!/usr/bin/env python3
"""DD-imager — Safe USB image writer."""

import hashlib
import json
import os
import re
import shlex
import signal
import stat
import subprocess
import threading
from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib


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

CUSTOM_CSS = """
/* ==== DD-imager Neon Theme ==== */

@define-color accent_bg_color #818cf8;
@define-color accent_fg_color #ffffff;
@define-color accent_color #a5b4fc;
@define-color window_bg_color #0f0f23;
@define-color view_bg_color #141428;
@define-color card_bg_color #1a1a2e;
@define-color headerbar_bg_color #12122a;
@define-color headerbar_fg_color #e0e0ff;
@define-color popover_bg_color #1a1a2e;
@define-color dialog_bg_color #1a1a2e;

/* Window background with subtle radial glow */
window.background {
    background-image:
        radial-gradient(ellipse at 50% 20%, alpha(#818cf8, 0.06) 0%, transparent 70%),
        linear-gradient(180deg, #0f0f23, #12122e);
}

/* Headerbar */
headerbar {
    background-image: linear-gradient(180deg, #1a1a2e, #12122a);
    border-bottom: 1px solid alpha(#818cf8, 0.2);
    box-shadow: 0 1px 8px alpha(#000000, 0.5);
}

headerbar .title {
    color: #e0e0ff;
    font-weight: bold;
    letter-spacing: 0.5px;
}

headerbar button {
    color: #c4c4f0;
}

headerbar button:hover {
    color: #e0e0ff;
    background-color: alpha(#818cf8, 0.15);
}

/* Suggested action — pink-purple gradient */
button.suggested-action {
    background-image: linear-gradient(135deg, #f472b6, #818cf8);
    color: #ffffff;
    border: none;
    box-shadow: 0 2px 10px alpha(#f472b6, 0.35);
    text-shadow: 0 1px 2px alpha(#000000, 0.3);
    font-weight: 600;
    transition: all 200ms ease;
}

button.suggested-action:hover {
    background-image: linear-gradient(135deg, #f9a8d4, #a5b4fc);
    box-shadow: 0 2px 20px alpha(#f472b6, 0.6);
}

button.suggested-action:active {
    background-image: linear-gradient(135deg, #ec4899, #6366f1);
}

/* Destructive action — red glow */
button.destructive-action {
    background-image: linear-gradient(135deg, #ef4444, #b91c1c);
    border: none;
    box-shadow: 0 2px 10px alpha(#ef4444, 0.35);
    font-weight: 600;
    transition: all 200ms ease;
}

button.destructive-action:hover {
    box-shadow: 0 2px 20px alpha(#ef4444, 0.6);
    background-image: linear-gradient(135deg, #f87171, #dc2626);
}

/* Pill buttons */
button.pill {
    border: 1px solid alpha(#818cf8, 0.3);
    transition: all 200ms ease;
}

button.pill:hover {
    border-color: alpha(#818cf8, 0.6);
    box-shadow: 0 0 10px alpha(#818cf8, 0.2);
}

/* Progress bar — cyan-green-purple gradient */
progressbar trough {
    background-color: #1a1a2e;
    border: 1px solid #2d2d5e;
    border-radius: 10px;
    min-height: 22px;
}

progressbar trough progress {
    background-image: linear-gradient(90deg, #34d399, #06b6d4, #818cf8);
    border-radius: 10px;
    box-shadow: 0 0 14px alpha(#34d399, 0.5);
    min-height: 22px;
}

progressbar text {
    color: #e0e0ff;
    font-weight: bold;
    font-size: 12px;
    text-shadow: 0 1px 3px alpha(#000000, 0.6);
}

/* Entry fields */
entry {
    background-color: #16213e;
    border: 1px solid #2d2d5e;
    color: #e0e0ff;
    border-radius: 8px;
    caret-color: #818cf8;
    transition: all 200ms ease;
}

entry:focus {
    border-color: #818cf8;
    box-shadow: 0 0 10px alpha(#818cf8, 0.35);
}

/* Cards */
.card {
    background-color: #1a1a2e;
    border: 1px solid alpha(#818cf8, 0.15);
    border-radius: 12px;
    box-shadow: 0 4px 12px alpha(#000000, 0.3);
}

/* Boxed list rows */
.boxed-list {
    background-color: transparent;
}

.boxed-list > row {
    background-color: #1a1a2e;
    border-bottom: 1px solid alpha(#818cf8, 0.08);
    transition: all 150ms ease;
}

.boxed-list > row:selected {
    background-image: linear-gradient(90deg, alpha(#818cf8, 0.15), alpha(#f472b6, 0.08));
    box-shadow: inset 3px 0 0 #818cf8;
}

.boxed-list > row:hover:not(:selected) {
    background-color: alpha(#818cf8, 0.06);
}

/* Titles */
.title-1 {
    color: #e0e0ff;
    font-weight: 800;
    letter-spacing: 0.3px;
}

.title-2 {
    color: #c4c4f0;
    font-weight: 700;
}

.heading {
    color: #f472b6;
    font-weight: 600;
}

.dim-label {
    color: alpha(#c4c4f0, 0.5);
}

.caption {
    font-size: 11px;
}

/* Success — neon green */
.success {
    color: #34d399;
    font-weight: 600;
}

/* Error — neon red */
.error {
    color: #f87171;
    font-weight: 600;
}

/* Warning banner */
.warning-banner {
    background-image: linear-gradient(90deg, alpha(#f59e0b, 0.12), alpha(#ef4444, 0.08));
    border-bottom: 1px solid alpha(#f59e0b, 0.25);
}

.warning-banner label {
    color: #fbbf24;
    font-weight: 600;
}

/* Separator */
separator {
    background-color: alpha(#818cf8, 0.12);
    min-height: 1px;
}

/* Scrollbar */
scrollbar slider {
    background-color: alpha(#818cf8, 0.25);
    border-radius: 4px;
    min-width: 6px;
}

scrollbar slider:hover {
    background-color: alpha(#818cf8, 0.45);
}

/* ---- Step Indicator ---- */
.step-indicator {
    padding: 14px 24px 10px 24px;
    border-bottom: 1px solid alpha(#818cf8, 0.08);
}

.step-dot {
    min-width: 10px;
    min-height: 10px;
    border-radius: 5px;
    background-color: #2d2d5e;
    transition: all 300ms ease;
}

.step-dot-active {
    min-width: 14px;
    min-height: 14px;
    border-radius: 7px;
    background-image: linear-gradient(135deg, #f472b6, #818cf8);
    box-shadow: 0 0 10px alpha(#f472b6, 0.6);
    animation: pulse-glow 2s ease-in-out infinite;
}

.step-dot-completed {
    background-image: linear-gradient(135deg, #34d399, #06b6d4);
    box-shadow: 0 0 6px alpha(#34d399, 0.4);
}

.step-connector {
    min-width: 40px;
    min-height: 2px;
    border-radius: 1px;
    background-color: #2d2d5e;
    transition: all 300ms ease;
}

.step-connector-done {
    background-image: linear-gradient(90deg, #34d399, #06b6d4);
    box-shadow: 0 0 4px alpha(#34d399, 0.3);
}

.step-label {
    color: alpha(#c4c4f0, 0.35);
    font-size: 10px;
    font-weight: 500;
    transition: all 300ms ease;
}

.step-label-active {
    color: #f472b6;
    font-weight: 700;
    font-size: 11px;
}

.step-label-completed {
    color: #34d399;
    font-weight: 600;
}

/* Pulse animation for active step */
@keyframes pulse-glow {
    0%   { box-shadow: 0 0 6px alpha(#f472b6, 0.4); }
    50%  { box-shadow: 0 0 18px alpha(#f472b6, 0.8); }
    100% { box-shadow: 0 0 6px alpha(#f472b6, 0.4); }
}

/* Alert dialog */
dialog {
    background-color: #1a1a2e;
}

/* ---- Verify mode toggle buttons ---- */
.verify-mode-toggle {
    margin-top: 4px;
    margin-bottom: 8px;
}

.verify-mode-toggle button {
    background-color: #16213e;
    color: #c4c4f0;
    border: 1px solid #2d2d5e;
    font-weight: 600;
    padding: 6px 18px;
    transition: all 200ms ease;
}

.verify-mode-toggle button:hover {
    background-color: alpha(#818cf8, 0.15);
    border-color: alpha(#818cf8, 0.4);
}

.verify-mode-toggle button:checked {
    background-image: linear-gradient(135deg, #f472b6, #818cf8);
    color: #ffffff;
    border-color: transparent;
    box-shadow: 0 2px 10px alpha(#f472b6, 0.35);
    text-shadow: 0 1px 2px alpha(#000000, 0.3);
}

/* GPG file info rows */
.gpg-file-row {
    margin-top: 4px;
    margin-bottom: 4px;
}

.gpg-file-label {
    color: #c4c4f0;
    font-size: 13px;
}

.gpg-file-label-set {
    color: #34d399;
    font-size: 13px;
    font-weight: 500;
}

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
"""


def format_file_size(size_bytes):
    """Return a human-readable file size string (e.g. '4.2 GB')."""
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size_bytes < 1024 or unit == 'TB':
            return f'{size_bytes:.1f} {unit}' if size_bytes != int(size_bytes) else f'{int(size_bytes)} {unit}'
        size_bytes /= 1024


def get_removable_drives():
    """Detect removable USB drives by reading sysfs and lsblk."""
    drives = []
    for dev in sorted(Path('/sys/block').iterdir()):
        name = dev.name
        if any(name.startswith(p) for p in ('loop', 'ram', 'zram', 'dm-', 'sr', 'nvme')):
            continue
        try:
            removable = (dev / 'removable').read_text().strip()
        except OSError:
            continue
        if removable != '1':
            continue
        size_sectors = int((dev / 'size').read_text().strip())
        size_bytes = size_sectors * 512
        if size_bytes == 0:
            continue
        device_path = f'/dev/{name}'
        # Get label and mount info from lsblk
        try:
            result = subprocess.run(
                ['lsblk', '-Jno', 'NAME,LABEL,SIZE,MOUNTPOINT', device_path],
                capture_output=True, text=True, timeout=5
            )
            info = json.loads(result.stdout)
            # Extract label and mount points from lsblk output
            label = ''
            mounts = []
            for bd in info.get('blockdevices', []):
                if bd.get('label'):
                    label = bd['label']
                if bd.get('mountpoint'):
                    mounts.append(bd['mountpoint'])
                for child in bd.get('children', []):
                    if child.get('label'):
                        label = label or child['label']
                    if child.get('mountpoint'):
                        mounts.append(child['mountpoint'])
        except Exception:
            label = ''
            mounts = []

        # Get vendor/model from sysfs
        vendor = ''
        model = ''
        try:
            vendor = (dev / 'device' / 'vendor').read_text().strip()
        except OSError:
            pass
        try:
            model = (dev / 'device' / 'model').read_text().strip()
        except OSError:
            pass

        drives.append({
            'device': device_path,
            'name': name,
            'size': size_bytes,
            'label': label,
            'vendor': vendor,
            'model': model,
            'mounted': mounts,
        })
    return drives


class DDImagerApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.invisi101.dd-imager')
        self.connect('activate', self.on_activate)

    # ---- UI construction ----

    def on_activate(self, app):
        # Force dark color scheme
        style_manager = Adw.StyleManager.get_default()
        style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)

        # Load custom neon CSS
        self._load_css()

        self.win = Adw.ApplicationWindow(
            application=app,
            title='DD-imager',
            default_width=640,
            default_height=540,
        )

        # Wizard state
        self.current_page = 0
        self.completed = [False] * 4
        self.checksum_verified = False
        self.checksum_skipped = False
        self.gpg_verified = False
        self.verify_mode = 'sha'  # 'sha' or 'gpg'
        self.sig_file_path = None
        self.key_file_path = None
        self.target_device = None

        # Mode state
        self.app_mode = None  # 'write' or 'wipe', None = welcome screen
        self.wipe_method = 'zero'  # 'zero', 'random', 'multipass'
        self.wipe_format = 'raw'   # 'raw', 'fat32', 'exfat', 'ext4', 'ntfs'
        self.wipe_cancelled = False

        # --- Header bar ---
        self.header = Adw.HeaderBar()
        self.title_label = Gtk.Label(label='DD-imager', css_classes=['title'])
        self.header.set_title_widget(self.title_label)

        # Back button (left side)
        self.btn_back = Gtk.Button(label='Back')
        self.btn_back.connect('clicked', lambda _b: self.go_back())
        self.header.pack_start(self.btn_back)

        # Next / Write button (right side)
        self.btn_next = Gtk.Button(label='Next')
        self.btn_next.connect('clicked', lambda _b: self.go_next())
        self.header.pack_end(self.btn_next)

        # Skip button (right side, only visible on verify-checksum page)
        self.btn_skip = Gtk.Button(label='Skip')
        self.btn_skip.connect('clicked', self._on_skip_checksum)
        self.header.pack_end(self.btn_skip)

        # --- Step indicator ---
        step_indicator = self._build_step_indicator()

        # --- Stack with pages ---
        self.stack = Gtk.Stack()
        self.stack.set_vexpand(True)
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(250)

        # Page 0: Select ISO (real implementation)
        self.iso_path = None
        self.stack.add_named(self._build_iso_page(), 'select-iso')

        # Page 1: Verify Checksum (real implementation)
        self.stack.add_named(self._build_checksum_page(), 'verify-checksum')

        # Page 2: Select Drive (real implementation)
        self.stack.add_named(self._build_drive_page(), 'select-drive')

        # Page 3: Confirm & Write (real implementation)
        self.dd_process = None
        self.write_cancelled = False
        self.stack.add_named(self._build_confirm_page(), 'confirm-write')

        # Welcome page (mode selection)
        self.stack.add_named(self._build_welcome_page(), 'welcome')

        # Wipe mode pages
        self.stack.add_named(self._build_wipe_drive_page(), 'wipe-select-drive')
        self.stack.add_named(self._build_wipe_options_page(), 'wipe-options')
        self.stack.add_named(self._build_wipe_confirm_page(), 'wipe-confirm')

        # --- Main layout: header, step indicator, stack ---
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.append(self.header)
        vbox.append(step_indicator)
        vbox.append(self.stack)
        self.win.set_content(vbox)

        self.stack.set_visible_child_name('welcome')

        # Set initial button states
        self.update_nav_buttons()

        self.win.present()

    # ---- CSS and step indicator ----

    def _load_css(self):
        """Load custom neon theme CSS."""
        from gi.repository import Gdk
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(CUSTOM_CSS.encode('utf-8'))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

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
        while child := self.step_indicator_outer.get_first_child():
            self.step_indicator_outer.remove(child)

        step_names = self._get_step_names()
        self.step_dots = []
        self.step_connectors = []
        self.step_labels = []

        dots_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, spacing=0)
        labels_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.CENTER, spacing=0)

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

    def _update_step_indicator(self):
        """Update step dots, connectors, and labels for the current page."""
        for i in range(len(self._get_pages())):
            dot = self.step_dots[i]
            label = self.step_labels[i]

            dot.remove_css_class('step-dot-active')
            dot.remove_css_class('step-dot-completed')
            label.remove_css_class('step-label-active')
            label.remove_css_class('step-label-completed')

            if i == self.current_page:
                dot.add_css_class('step-dot-active')
                label.add_css_class('step-label-active')
            elif i < self.current_page:
                dot.add_css_class('step-dot-completed')
                label.add_css_class('step-label-completed')

        for i, connector in enumerate(self.step_connectors):
            connector.remove_css_class('step-connector-done')
            if i < self.current_page:
                connector.add_css_class('step-connector-done')

    # ---- ISO page ----

    def _build_iso_page(self):
        """Build the Select ISO page with a browse button and file info label."""
        page = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            spacing=24,
        )

        heading = Gtk.Label(label='Select a disk image')
        heading.add_css_class('title-1')
        page.append(heading)

        self.btn_browse = Gtk.Button(label='Browse\u2026')
        self.btn_browse.add_css_class('pill')
        self.btn_browse.add_css_class('suggested-action')
        self.btn_browse.connect('clicked', self._on_browse_clicked)
        page.append(self.btn_browse)

        self.iso_info_label = Gtk.Label(label='No file selected')
        self.iso_info_label.add_css_class('dim-label')
        self.iso_info_label.set_wrap(True)
        self.iso_info_label.set_max_width_chars(50)
        page.append(self.iso_info_label)

        return page

    def _on_browse_clicked(self, _button):
        """Open a file dialog filtered to .iso / .img files."""
        dialog = Gtk.FileDialog()
        dialog.set_title('Select Disk Image')

        # File filter for disk images
        file_filter = Gtk.FileFilter()
        file_filter.set_name('Disk Images (*.iso, *.img)')
        file_filter.add_pattern('*.iso')
        file_filter.add_pattern('*.img')
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(file_filter)
        dialog.set_filters(filters)
        dialog.set_default_filter(file_filter)

        # Default to ~/Downloads if it exists
        downloads = GLib.build_filenamev([GLib.get_home_dir(), 'Downloads'])
        downloads_file = Gio.File.new_for_path(downloads)
        if GLib.file_test(downloads, GLib.FileTest.IS_DIR):
            dialog.set_initial_folder(downloads_file)

        dialog.open(self.win, None, self._on_file_chosen)

    def _on_file_chosen(self, dialog, result):
        """Callback for Gtk.FileDialog.open() async result."""
        try:
            gfile = dialog.open_finish(result)
        except GLib.Error:
            # User cancelled the dialog
            return

        path = gfile.get_path()
        self.iso_path = path

        # Get file size
        try:
            info = gfile.query_info('standard::size', Gio.FileQueryInfoFlags.NONE, None)
            size = info.get_size()
            size_str = format_file_size(size)
        except GLib.Error:
            size_str = 'unknown size'

        filename = GLib.path_get_basename(path)
        self.iso_info_label.set_label(f'{filename} \u2014 {size_str}')
        self.iso_info_label.remove_css_class('dim-label')

        # Enable Next button now that a file is selected
        self.btn_next.set_sensitive(True)

    # ---- Checksum page ----

    def _build_checksum_page(self):
        """Build the Verify Checksum page with mode toggle and SHA-256/OpenPGP content."""
        page = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            spacing=16,
        )

        heading = Gtk.Label(label='Verify Checksum')
        heading.add_css_class('title-1')
        page.append(heading)

        # File info label — updated when the page is entered
        self.checksum_file_label = Gtk.Label(label='No file selected')
        self.checksum_file_label.add_css_class('dim-label')
        self.checksum_file_label.set_wrap(True)
        self.checksum_file_label.set_max_width_chars(50)
        page.append(self.checksum_file_label)

        # --- Mode toggle: SHA-256 | OpenPGP ---
        toggle_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, halign=Gtk.Align.CENTER)
        toggle_box.add_css_class('linked')
        toggle_box.add_css_class('verify-mode-toggle')

        self.btn_mode_sha = Gtk.ToggleButton(label='SHA-256')
        self.btn_mode_sha.set_active(True)
        toggle_box.append(self.btn_mode_sha)

        self.btn_mode_gpg = Gtk.ToggleButton(label='OpenPGP')
        self.btn_mode_gpg.set_group(self.btn_mode_sha)
        toggle_box.append(self.btn_mode_gpg)

        self.btn_mode_sha.connect('toggled', self._on_verify_mode_changed)
        self.btn_mode_gpg.connect('toggled', self._on_verify_mode_changed)

        page.append(toggle_box)

        # === SHA-256 content ===
        self.sha_content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            halign=Gtk.Align.CENTER,
            spacing=16,
        )

        self.hash_entry = Gtk.Entry()
        self.hash_entry.set_placeholder_text('Paste expected SHA-256 hash here')
        self.hash_entry.set_width_chars(64)
        self.hash_entry.set_max_width_chars(64)
        self.sha_content.append(self.hash_entry)

        sha_action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12,
                                  halign=Gtk.Align.CENTER)

        self.btn_verify = Gtk.Button(label='Verify')
        self.btn_verify.add_css_class('pill')
        self.btn_verify.add_css_class('suggested-action')
        self.btn_verify.connect('clicked', self._on_verify_clicked)
        sha_action_row.append(self.btn_verify)

        self.checksum_spinner = Gtk.Spinner()
        self.checksum_spinner.set_visible(False)
        sha_action_row.append(self.checksum_spinner)

        self.sha_content.append(sha_action_row)

        self.checksum_result_label = Gtk.Label(label='')
        self.checksum_result_label.set_wrap(True)
        self.checksum_result_label.set_max_width_chars(50)
        self.sha_content.append(self.checksum_result_label)

        page.append(self.sha_content)

        # === OpenPGP content ===
        self.gpg_content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            halign=Gtk.Align.CENTER,
            spacing=12,
        )
        self.gpg_content.set_visible(False)

        # Sig file row
        sig_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
                          halign=Gtk.Align.CENTER)
        sig_row.add_css_class('gpg-file-row')

        self.btn_sig_browse = Gtk.Button(label='Signature file\u2026')
        self.btn_sig_browse.add_css_class('pill')
        self.btn_sig_browse.connect('clicked', self._on_sig_browse_clicked)
        sig_row.append(self.btn_sig_browse)

        self.sig_file_label = Gtk.Label(label='No .sig/.asc file selected')
        self.sig_file_label.add_css_class('gpg-file-label')
        self.sig_file_label.set_wrap(True)
        self.sig_file_label.set_max_width_chars(40)
        sig_row.append(self.sig_file_label)

        self.gpg_content.append(sig_row)

        # Key file row (optional)
        key_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
                          halign=Gtk.Align.CENTER)
        key_row.add_css_class('gpg-file-row')

        self.btn_key_browse = Gtk.Button(label='Signing key\u2026')
        self.btn_key_browse.add_css_class('pill')
        self.btn_key_browse.connect('clicked', self._on_key_browse_clicked)
        key_row.append(self.btn_key_browse)

        self.key_file_label = Gtk.Label(label='Optional — import if not in keyring')
        self.key_file_label.add_css_class('gpg-file-label')
        self.key_file_label.set_wrap(True)
        self.key_file_label.set_max_width_chars(40)
        key_row.append(self.key_file_label)

        self.gpg_content.append(key_row)

        # GPG verify button + spinner
        gpg_action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12,
                                  halign=Gtk.Align.CENTER)

        self.btn_gpg_verify = Gtk.Button(label='Verify Signature')
        self.btn_gpg_verify.add_css_class('pill')
        self.btn_gpg_verify.add_css_class('suggested-action')
        self.btn_gpg_verify.connect('clicked', self._on_gpg_verify_clicked)
        gpg_action_row.append(self.btn_gpg_verify)

        self.gpg_spinner = Gtk.Spinner()
        self.gpg_spinner.set_visible(False)
        gpg_action_row.append(self.gpg_spinner)

        self.gpg_content.append(gpg_action_row)

        # GPG result label
        self.gpg_result_label = Gtk.Label(label='')
        self.gpg_result_label.set_wrap(True)
        self.gpg_result_label.set_max_width_chars(50)
        self.gpg_content.append(self.gpg_result_label)

        page.append(self.gpg_content)

        return page

    def _update_checksum_file_info(self):
        """Update the file info label on the checksum page based on current iso_path."""
        if self.iso_path is None:
            self.checksum_file_label.set_label('No file selected')
            self.checksum_file_label.add_css_class('dim-label')
            return

        gfile = Gio.File.new_for_path(self.iso_path)
        filename = GLib.path_get_basename(self.iso_path)
        try:
            info = gfile.query_info('standard::size', Gio.FileQueryInfoFlags.NONE, None)
            size = info.get_size()
            size_str = format_file_size(size)
        except GLib.Error:
            size_str = 'unknown size'

        self.checksum_file_label.set_label(f'{filename} — {size_str}')
        self.checksum_file_label.remove_css_class('dim-label')

        # Auto-detect .sig/.asc file alongside the ISO
        if self.sig_file_path is None:
            for ext in ('.sig', '.asc'):
                candidate = self.iso_path + ext
                if os.path.isfile(candidate):
                    self.sig_file_path = candidate
                    sig_name = GLib.path_get_basename(candidate)
                    self.sig_file_label.set_label(sig_name)
                    self.sig_file_label.remove_css_class('gpg-file-label')
                    self.sig_file_label.add_css_class('gpg-file-label-set')
                    break

    def _on_verify_clicked(self, _button):
        """Start background SHA-256 computation."""
        expected = self.hash_entry.get_text().strip()
        if not expected:
            self.checksum_result_label.set_label('Please enter an expected hash.')
            self.checksum_result_label.remove_css_class('success')
            self.checksum_result_label.remove_css_class('error')
            return

        if self.iso_path is None:
            self.checksum_result_label.set_label('No file selected.')
            self.checksum_result_label.remove_css_class('success')
            self.checksum_result_label.remove_css_class('error')
            return

        # Disable controls during computation
        self.btn_verify.set_sensitive(False)
        self.hash_entry.set_sensitive(False)
        self.checksum_spinner.set_visible(True)
        self.checksum_spinner.start()
        self.checksum_result_label.set_label('')
        self.checksum_result_label.remove_css_class('success')
        self.checksum_result_label.remove_css_class('error')

        # Run hash computation in background thread
        thread = threading.Thread(target=self._compute_hash, args=(expected,), daemon=True)
        thread.start()

    def _compute_hash(self, expected):
        """Compute SHA-256 of the selected file in a background thread."""
        h = hashlib.sha256()
        try:
            with open(self.iso_path, 'rb') as f:
                while chunk := f.read(8 * 1024 * 1024):
                    h.update(chunk)
            computed = h.hexdigest()
        except OSError as e:
            GLib.idle_add(self._on_hash_error, str(e))
            return

        GLib.idle_add(self._on_hash_complete, computed, expected)

    def _on_hash_complete(self, computed, expected):
        """Called on the main thread when hash computation finishes."""
        self.btn_verify.set_sensitive(True)
        self.hash_entry.set_sensitive(True)
        self.checksum_spinner.stop()
        self.checksum_spinner.set_visible(False)

        if computed.lower() == expected.lower():
            self.checksum_result_label.set_label('Checksum verified')
            self.checksum_result_label.remove_css_class('error')
            self.checksum_result_label.add_css_class('success')
            self.checksum_verified = True
            self.btn_next.set_sensitive(True)
        else:
            self.checksum_result_label.set_label('Checksum mismatch')
            self.checksum_result_label.remove_css_class('success')
            self.checksum_result_label.add_css_class('error')
            self.checksum_verified = False
            self.btn_next.set_sensitive(False)
        return False

    def _on_hash_error(self, error_msg):
        """Called on the main thread if hash computation fails."""
        self.btn_verify.set_sensitive(True)
        self.hash_entry.set_sensitive(True)
        self.checksum_spinner.stop()
        self.checksum_spinner.set_visible(False)
        self.checksum_result_label.set_label(f'Error: {error_msg}')
        self.checksum_result_label.remove_css_class('success')
        self.checksum_result_label.add_css_class('error')
        return False

    # ---- OpenPGP verification ----

    def _on_verify_mode_changed(self, button):
        """Toggle visibility of SHA-256 vs OpenPGP content boxes."""
        if not button.get_active():
            return
        if button is self.btn_mode_sha:
            self.verify_mode = 'sha'
            self.sha_content.set_visible(True)
            self.gpg_content.set_visible(False)
        else:
            self.verify_mode = 'gpg'
            self.sha_content.set_visible(False)
            self.gpg_content.set_visible(True)
        self.update_nav_buttons()

    def _on_sig_browse_clicked(self, _button):
        """Open a file dialog for selecting a .sig/.asc signature file."""
        dialog = Gtk.FileDialog()
        dialog.set_title('Select Signature File')

        file_filter = Gtk.FileFilter()
        file_filter.set_name('Signature files (*.sig, *.asc)')
        file_filter.add_pattern('*.sig')
        file_filter.add_pattern('*.asc')
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(file_filter)
        dialog.set_filters(filters)
        dialog.set_default_filter(file_filter)

        if self.iso_path:
            parent_dir = os.path.dirname(self.iso_path)
            dialog.set_initial_folder(Gio.File.new_for_path(parent_dir))

        dialog.open(self.win, None, self._on_sig_file_chosen)

    def _on_sig_file_chosen(self, dialog, result):
        """Handle signature file selection."""
        try:
            gfile = dialog.open_finish(result)
        except GLib.Error:
            return
        self.sig_file_path = gfile.get_path()
        sig_name = GLib.path_get_basename(self.sig_file_path)
        self.sig_file_label.set_label(sig_name)
        self.sig_file_label.remove_css_class('gpg-file-label')
        self.sig_file_label.add_css_class('gpg-file-label-set')

    def _on_key_browse_clicked(self, _button):
        """Open a file dialog for selecting a signing key file."""
        dialog = Gtk.FileDialog()
        dialog.set_title('Select Signing Key')

        file_filter = Gtk.FileFilter()
        file_filter.set_name('Key files (*.key, *.asc, *.gpg)')
        file_filter.add_pattern('*.key')
        file_filter.add_pattern('*.asc')
        file_filter.add_pattern('*.gpg')
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(file_filter)
        dialog.set_filters(filters)
        dialog.set_default_filter(file_filter)

        if self.iso_path:
            parent_dir = os.path.dirname(self.iso_path)
            dialog.set_initial_folder(Gio.File.new_for_path(parent_dir))

        dialog.open(self.win, None, self._on_key_file_chosen)

    def _on_key_file_chosen(self, dialog, result):
        """Handle key file selection."""
        try:
            gfile = dialog.open_finish(result)
        except GLib.Error:
            return
        self.key_file_path = gfile.get_path()
        key_name = GLib.path_get_basename(self.key_file_path)
        self.key_file_label.set_label(key_name)
        self.key_file_label.remove_css_class('gpg-file-label')
        self.key_file_label.add_css_class('gpg-file-label-set')

    def _on_gpg_verify_clicked(self, _button):
        """Start GPG signature verification in background thread."""
        if self.sig_file_path is None:
            self.gpg_result_label.set_label('Please select a signature file.')
            self.gpg_result_label.remove_css_class('success')
            self.gpg_result_label.remove_css_class('error')
            return

        if self.iso_path is None:
            self.gpg_result_label.set_label('No image file selected.')
            self.gpg_result_label.remove_css_class('success')
            self.gpg_result_label.remove_css_class('error')
            return

        # Disable controls during verification
        self.btn_gpg_verify.set_sensitive(False)
        self.btn_sig_browse.set_sensitive(False)
        self.btn_key_browse.set_sensitive(False)
        self.gpg_spinner.set_visible(True)
        self.gpg_spinner.start()
        self.gpg_result_label.set_label('')
        self.gpg_result_label.remove_css_class('success')
        self.gpg_result_label.remove_css_class('error')

        thread = threading.Thread(target=self._gpg_verify_thread, daemon=True)
        thread.start()

    def _gpg_verify_thread(self):
        """Run gpg --import (if key provided) then gpg --verify in background."""
        # Import key if provided
        if self.key_file_path:
            try:
                result = subprocess.run(
                    ['gpg', '--import', self.key_file_path],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode != 0:
                    detail = result.stderr.strip() or 'Key import failed'
                    GLib.idle_add(self._on_gpg_verify_complete, False, f'Key import error: {detail}')
                    return
            except FileNotFoundError:
                GLib.idle_add(self._on_gpg_verify_complete, False,
                              'gpg not found — please install GnuPG')
                return
            except Exception as e:
                GLib.idle_add(self._on_gpg_verify_complete, False, f'Key import error: {e}')
                return

        # Verify signature
        try:
            result = subprocess.run(
                ['gpg', '--verify', self.sig_file_path, self.iso_path],
                capture_output=True, text=True, timeout=120,
            )
        except FileNotFoundError:
            GLib.idle_add(self._on_gpg_verify_complete, False,
                          'gpg not found — please install GnuPG')
            return
        except Exception as e:
            GLib.idle_add(self._on_gpg_verify_complete, False, f'Verification error: {e}')
            return

        # gpg --verify outputs to stderr
        output = result.stderr.strip()

        # Strip "gpg: " prefixes for cleaner display
        clean_lines = []
        for line in output.split('\n'):
            stripped = line.strip()
            if stripped.startswith('gpg: '):
                stripped = stripped[5:]
            if stripped:
                clean_lines.append(stripped)
        detail = '\n'.join(clean_lines) or ('Signature verified' if result.returncode == 0 else 'Verification failed')

        GLib.idle_add(self._on_gpg_verify_complete, result.returncode == 0, detail)

    def _on_gpg_verify_complete(self, success, detail):
        """Update UI with GPG verification result on main thread."""
        self.btn_gpg_verify.set_sensitive(True)
        self.btn_sig_browse.set_sensitive(True)
        self.btn_key_browse.set_sensitive(True)
        self.gpg_spinner.stop()
        self.gpg_spinner.set_visible(False)

        if success:
            self.gpg_result_label.set_label(f'{detail}\n\nVERIFIED GOOD')
            self.gpg_result_label.remove_css_class('error')
            self.gpg_result_label.add_css_class('success')
            self.gpg_verified = True
            self.btn_next.set_sensitive(True)
        else:
            self.gpg_result_label.set_label(f'{detail}\n\nUNVERIFIED BAD')
            self.gpg_result_label.remove_css_class('success')
            self.gpg_result_label.add_css_class('error')
            self.gpg_verified = False
            self.btn_next.set_sensitive(False)
        return False

    # ---- Drive selection page ----

    def _build_drive_page(self):
        """Build the Select Drive page with warning banner, drive list, and refresh button."""
        page = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
        )

        # Warning banner at the top
        warning_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            halign=Gtk.Align.FILL,
            margin_top=0,
            margin_start=0,
            margin_end=0,
        )
        warning_box.add_css_class('warning-banner')
        warning_label = Gtk.Label(
            label='\u26a0  All data on the selected drive will be destroyed',
            halign=Gtk.Align.CENTER,
            hexpand=True,
            margin_top=10,
            margin_bottom=10,
            margin_start=12,
            margin_end=12,
        )
        warning_label.add_css_class('warning-banner')
        warning_box.append(warning_label)
        page.append(warning_box)

        # Content area with margins
        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            margin_top=16,
            margin_bottom=16,
            margin_start=24,
            margin_end=24,
            vexpand=True,
        )

        heading = Gtk.Label(label='Select target drive', halign=Gtk.Align.START)
        heading.add_css_class('title-2')
        content.append(heading)

        # Scrolled window containing the ListBox
        scrolled = Gtk.ScrolledWindow(
            vexpand=True,
            hscrollbar_policy=Gtk.PolicyType.NEVER,
        )
        scrolled.add_css_class('card')

        self.drive_listbox = Gtk.ListBox()
        self.drive_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.drive_listbox.add_css_class('boxed-list')
        self.drive_listbox.connect('row-selected', self._on_drive_selected)
        scrolled.set_child(self.drive_listbox)
        content.append(scrolled)

        # Empty-state label (shown when no drives found)
        self.drive_empty_label = Gtk.Label(
            label='No removable USB drives detected. Insert a drive and click Refresh.',
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            vexpand=True,
            wrap=True,
            max_width_chars=50,
        )
        self.drive_empty_label.add_css_class('dim-label')
        self.drive_empty_label.set_visible(False)
        content.append(self.drive_empty_label)

        # Refresh button
        btn_refresh = Gtk.Button(label='Refresh', halign=Gtk.Align.CENTER)
        btn_refresh.add_css_class('pill')
        btn_refresh.connect('clicked', lambda _b: self._refresh_drives())
        content.append(btn_refresh)

        page.append(content)

        return page

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

        # Remove all existing rows
        while True:
            row = listbox.get_row_at_index(0)
            if row is None:
                break
            listbox.remove(row)

        # Detect drives
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

    def _make_drive_row(self, drive):
        """Create a ListBox row for a single drive."""
        row = Gtk.ListBoxRow()
        row.drive_info = drive  # stash drive info on the row

        hbox = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
            margin_top=10,
            margin_bottom=10,
            margin_start=12,
            margin_end=12,
        )

        # Left side: device path (bold) and label
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)

        # Device path + vendor/model
        vendor_model = ' '.join(filter(None, [drive.get('vendor', ''), drive.get('model', '')]))
        if vendor_model and vendor_model != 'Mass Storage':
            device_markup = f'<b>{GLib.markup_escape_text(drive["device"])}</b>  <small>{GLib.markup_escape_text(vendor_model)}</small>'
        else:
            device_markup = f'<b>{GLib.markup_escape_text(drive["device"])}</b>'
        device_label = Gtk.Label(halign=Gtk.Align.START)
        device_label.set_markup(device_markup)
        left.append(device_label)

        if drive['label']:
            label_text = Gtk.Label(
                label=drive['label'],
                halign=Gtk.Align.START,
            )
            label_text.add_css_class('dim-label')
            left.append(label_text)

        if drive['mounted']:
            mount_text = Gtk.Label(
                label='Mounted: ' + ', '.join(drive['mounted']),
                halign=Gtk.Align.START,
            )
            mount_text.add_css_class('dim-label')
            mount_text.add_css_class('caption')
            left.append(mount_text)

        hbox.append(left)

        # Right side: size
        size_label = Gtk.Label(
            label=format_file_size(drive['size']),
            halign=Gtk.Align.END,
            valign=Gtk.Align.CENTER,
        )
        size_label.add_css_class('dim-label')
        hbox.append(size_label)

        row.set_child(hbox)
        return row

    def _on_drive_selected(self, listbox, row):
        """Handle drive selection from the ListBox."""
        if row is not None:
            self.target_device = row.drive_info
            self.btn_next.set_sensitive(True)
        else:
            self.target_device = None
            self.btn_next.set_sensitive(False)

    # ---- Confirm & Write page ----

    def _build_confirm_page(self):
        """Build the Confirm & Write page with summary, progress bar, and result label."""
        page = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
        )

        # Content area with margins
        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=16,
            margin_top=24,
            margin_bottom=24,
            margin_start=24,
            margin_end=24,
            vexpand=True,
        )

        heading = Gtk.Label(label='Review & Write', halign=Gtk.Align.START)
        heading.add_css_class('title-2')
        content.append(heading)

        # --- Summary section ---
        summary_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
        )
        summary_box.add_css_class('card')
        summary_inner = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            margin_top=16,
            margin_bottom=16,
            margin_start=16,
            margin_end=16,
        )

        # Source ISO info
        source_heading = Gtk.Label(label='Source Image', halign=Gtk.Align.START)
        source_heading.add_css_class('heading')
        summary_inner.append(source_heading)

        self.confirm_iso_label = Gtk.Label(
            label='No file selected',
            halign=Gtk.Align.START,
            wrap=True,
            max_width_chars=60,
        )
        self.confirm_iso_label.add_css_class('dim-label')
        summary_inner.append(self.confirm_iso_label)

        # Separator
        summary_inner.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Target drive info
        target_heading = Gtk.Label(label='Target Drive', halign=Gtk.Align.START)
        target_heading.add_css_class('heading')
        summary_inner.append(target_heading)

        self.confirm_drive_label = Gtk.Label(
            label='No drive selected',
            halign=Gtk.Align.START,
            wrap=True,
            max_width_chars=60,
        )
        self.confirm_drive_label.add_css_class('dim-label')
        summary_inner.append(self.confirm_drive_label)

        summary_box.append(summary_inner)
        content.append(summary_box)

        # --- Progress section (hidden until write starts) ---
        self.write_progress_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
        )
        self.write_progress_box.set_visible(False)

        self.write_progress_bar = Gtk.ProgressBar()
        self.write_progress_bar.set_show_text(True)
        self.write_progress_box.append(self.write_progress_bar)

        self.write_progress_label = Gtk.Label(label='', halign=Gtk.Align.START)
        self.write_progress_label.add_css_class('dim-label')
        self.write_progress_label.set_wrap(True)
        self.write_progress_label.set_max_width_chars(60)
        self.write_progress_box.append(self.write_progress_label)

        # Cancel button
        self.btn_cancel_write = Gtk.Button(label='Cancel')
        self.btn_cancel_write.add_css_class('pill')
        self.btn_cancel_write.add_css_class('destructive-action')
        self.btn_cancel_write.set_halign(Gtk.Align.CENTER)
        self.btn_cancel_write.connect('clicked', self._on_cancel_write)
        self.write_progress_box.append(self.btn_cancel_write)

        content.append(self.write_progress_box)

        # --- Result label (shown after write completes or fails) ---
        self.write_result_label = Gtk.Label(label='', halign=Gtk.Align.CENTER)
        self.write_result_label.set_wrap(True)
        self.write_result_label.set_max_width_chars(60)
        self.write_result_label.set_visible(False)
        content.append(self.write_result_label)

        page.append(content)
        return page

    def _update_confirm_summary(self):
        """Populate the summary labels on the confirm page with current selections."""
        # Reset any previous error state
        self.write_result_label.set_visible(False)
        self.write_result_label.remove_css_class('error')

        # ISO info
        if self.iso_path:
            gfile = Gio.File.new_for_path(self.iso_path)
            filename = GLib.path_get_basename(self.iso_path)
            try:
                info = gfile.query_info('standard::size', Gio.FileQueryInfoFlags.NONE, None)
                size = info.get_size()
                self.iso_size = size
                size_str = format_file_size(size)
            except GLib.Error:
                self.iso_size = 0
                size_str = 'unknown size'
            self.confirm_iso_label.set_label(f'{filename}  ({size_str})')
            self.confirm_iso_label.remove_css_class('dim-label')
        else:
            self.confirm_iso_label.set_label('No file selected')
            self.confirm_iso_label.add_css_class('dim-label')

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
            self.confirm_drive_label.set_label(
                f'{" — ".join(parts)}  ({size_str})'
            )
            self.confirm_drive_label.remove_css_class('dim-label')
        else:
            self.confirm_drive_label.set_label('No drive selected')
            self.confirm_drive_label.add_css_class('dim-label')

        # Check ISO size vs drive size
        if self.iso_size and self.target_device and self.iso_size > self.target_device['size']:
            self.write_result_label.set_label(
                f'Image ({format_file_size(self.iso_size)}) is larger than '
                f'target drive ({format_file_size(self.target_device["size"])})')
            self.write_result_label.add_css_class('error')
            self.write_result_label.set_visible(True)
            self.btn_next.set_sensitive(False)
            return

    def _confirm_write(self):
        """Show a confirmation dialog before starting the write."""
        if not self.iso_path or not self.target_device:
            return

        dev = self.target_device
        label_part = f' ({dev["label"]})' if dev.get('label') else ''

        dialog = Adw.AlertDialog(
            heading='Confirm Write',
            body=(
                f'This will erase ALL data on {dev["device"]}{label_part}.\n\n'
                'Are you sure?'
            ),
        )
        dialog.add_response('cancel', 'Cancel')
        dialog.add_response('write', 'Write')
        dialog.set_response_appearance('write', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response('cancel')
        dialog.set_close_response('cancel')
        dialog.connect('response', self._on_confirm_response)
        dialog.present(self.win)

    def _on_confirm_response(self, dialog, response):
        """Handle the confirmation dialog response."""
        if response == 'write':
            self._start_write()

    def _unmount_device(self, device_path):
        """Unmount all partitions. Returns (success, error_message)."""
        try:
            result = subprocess.run(
                ['lsblk', '-nro', 'MOUNTPOINT', device_path],
                capture_output=True, text=True, timeout=10,
            )
            for mp in result.stdout.strip().split('\n'):
                if not mp:
                    continue
                # Try udisksctl first (works for user-mounted)
                r = subprocess.run(
                    ['udisksctl', 'unmount', '-b', device_path, '--no-user-interaction'],
                    capture_output=True, text=True, timeout=30,
                )
                if r.returncode != 0:
                    # Fallback to umount
                    r2 = subprocess.run(['umount', mp], capture_output=True, text=True, timeout=30)
                    if r2.returncode != 0:
                        return False, f'Failed to unmount {mp}'
        except Exception as e:
            return False, str(e)
        return True, ''

    def _start_write(self):
        """Begin the dd write process."""
        self.write_cancelled = False

        # Switch UI to progress mode
        self.write_progress_box.set_visible(True)
        self.write_progress_bar.set_fraction(0.0)
        self.write_progress_bar.set_text('0%')
        self.write_progress_label.set_label('Starting write...')
        self.btn_cancel_write.set_sensitive(True)
        self.btn_cancel_write.set_visible(True)

        self.write_result_label.set_visible(False)
        self.write_result_label.set_label('')
        self.write_result_label.remove_css_class('success')
        self.write_result_label.remove_css_class('error')

        # Disable navigation during write
        self.btn_next.set_visible(False)
        self.btn_back.set_sensitive(False)

        # Get ISO size for progress calculation
        try:
            self.iso_size = os.path.getsize(self.iso_path)
        except OSError:
            self.iso_size = 0

        # Unmount the device first, then start dd in a thread
        thread = threading.Thread(target=self._write_thread, daemon=True)
        thread.start()

    def _write_thread(self):
        """Run unmount + dd in a background thread."""
        device_path = self.target_device['device']
        iso_size = self.iso_size

        # Validate ISO is a regular file
        try:
            iso_stat = os.stat(self.iso_path)
            if not stat.S_ISREG(iso_stat.st_mode):
                GLib.idle_add(self._on_write_error, 'Selected path is not a regular file')
                return
        except OSError as e:
            GLib.idle_add(self._on_write_error, f'Cannot access ISO file: {e}')
            return

        # Validate device is a block device
        try:
            dev_stat = os.stat(device_path)
            if not stat.S_ISBLK(dev_stat.st_mode):
                GLib.idle_add(self._on_write_error, 'Target is not a block device')
                return
        except OSError as e:
            GLib.idle_add(self._on_write_error, f'Cannot access target device: {e}')
            return

        # Re-verify device at write time (TOCTOU fix)
        name = os.path.basename(device_path)
        sys_path = Path(f'/sys/block/{name}')
        if not sys_path.exists():
            GLib.idle_add(self._on_write_error, 'Device no longer exists')
            return
        try:
            removable = (sys_path / 'removable').read_text().strip()
            if removable != '1':
                GLib.idle_add(self._on_write_error, 'Device is no longer marked as removable')
                return
            current_size = int((sys_path / 'size').read_text().strip()) * 512
            if current_size != self.target_device['size']:
                GLib.idle_add(self._on_write_error, 'Device size changed — possibly a different device')
                return
        except OSError as e:
            GLib.idle_add(self._on_write_error, f'Cannot verify device: {e}')
            return

        # Unmount all partitions
        success, err = self._unmount_device(device_path)
        if not success:
            GLib.idle_add(self._on_write_error, f'Failed to unmount device: {err}')
            return

        # Build dd command via pkexec
        dd_cmd = [
            'pkexec', 'dd',
            f'if={self.iso_path}',
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
            GLib.idle_add(self._on_write_error, f'Failed to start dd: {e}')
            return

        # Parse progress from stderr (dd writes progress to stderr)
        # dd status=progress uses \r not \n, so we read raw bytes in chunks
        pattern = re.compile(r'(\d+)\s+bytes')
        stderr_lines = []
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
                    stderr_lines.append(line)
                    match = pattern.search(line)
                    if match and not self.write_cancelled:
                        bytes_written = int(match.group(1))
                        fraction = min(bytes_written / iso_size, 1.0) if iso_size > 0 else 0
                        GLib.idle_add(self._update_write_progress, fraction, bytes_written, line.strip())
        # Process any remaining buffer
        if buf.strip():
            stderr_lines.append(buf)

        self.dd_process.wait()
        returncode = self.dd_process.returncode
        self.dd_process = None

        if self.write_cancelled:
            GLib.idle_add(self._on_write_cancelled)
        elif returncode == 0:
            # Run sync
            try:
                subprocess.run(['sync'], timeout=60)
            except Exception:
                pass
            GLib.idle_add(self._on_write_success)
        else:
            error_text = ''.join(stderr_lines[-10:])  # last 10 lines of stderr
            GLib.idle_add(self._on_write_error, f'dd exited with code {returncode}\n{error_text}')

    def _update_write_progress(self, fraction, bytes_written, detail_line):
        """Update the progress bar and label from the main thread."""
        self.write_progress_bar.set_fraction(fraction)
        self.write_progress_bar.set_text(f'{fraction:.0%}')

        written_str = format_file_size(bytes_written)
        total_str = format_file_size(self.iso_size) if self.iso_size > 0 else '?'

        # Try to extract speed from detail line (e.g. "224 MB/s")
        speed_match = re.search(r'[\d.]+ [KMGT]?B/s', detail_line)
        speed_part = f'  —  {speed_match.group(0)}' if speed_match else ''

        self.write_progress_label.set_label(f'{written_str} / {total_str}{speed_part}')
        return False

    def _on_cancel_write(self, _button):
        """Cancel the running dd process."""
        self.write_cancelled = True
        self.btn_cancel_write.set_sensitive(False)
        self.write_progress_label.set_label('Cancelling...')
        proc = self.dd_process  # local snapshot to avoid race
        if proc is not None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, OSError, AttributeError):
                pass
            try:
                proc.terminate()
            except OSError:
                pass

    def _on_write_success(self):
        """Called on the main thread when dd completes successfully."""
        self.write_progress_bar.set_fraction(1.0)
        self.write_progress_bar.set_text('100%')
        self.write_progress_label.set_label('Write complete.')
        self.btn_cancel_write.set_visible(False)

        self.write_result_label.set_label('Image written successfully!')
        self.write_result_label.remove_css_class('error')
        self.write_result_label.add_css_class('success')
        self.write_result_label.set_visible(True)

        # Re-enable navigation
        self.btn_back.set_sensitive(True)
        # Don't re-show the Write button — the job is done
        return False

    def _on_write_error(self, error_msg):
        """Called on the main thread when dd fails."""
        self.write_progress_label.set_label('Write failed.')
        self.btn_cancel_write.set_visible(False)

        self.write_result_label.set_label(f'Error: {error_msg}')
        self.write_result_label.remove_css_class('success')
        self.write_result_label.add_css_class('error')
        self.write_result_label.set_visible(True)

        # Re-enable navigation
        self.btn_back.set_sensitive(True)
        self.btn_next.set_visible(True)
        return False

    def _on_write_cancelled(self):
        """Called on the main thread when the write was cancelled."""
        self.write_progress_label.set_label('Write cancelled.')
        self.btn_cancel_write.set_visible(False)

        self.write_result_label.set_label('Write was cancelled by user.')
        self.write_result_label.remove_css_class('success')
        self.write_result_label.add_css_class('error')
        self.write_result_label.set_visible(True)

        # Re-enable navigation
        self.btn_back.set_sensitive(True)
        self.btn_next.set_visible(True)
        return False

    # ---- Navigation logic ----

    def _get_pages(self):
        """Return the page list for the current mode."""
        if self.app_mode == 'wipe':
            return WIPE_PAGES
        return WRITE_PAGES

    def _get_step_names(self):
        """Return the step names for the current mode."""
        if self.app_mode == 'wipe':
            return WIPE_STEP_NAMES
        return WRITE_STEP_NAMES

    def _on_mode_selected(self, mode):
        """Set the app mode and navigate to the first wizard page."""
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
        """Advance to the next page, or trigger write/wipe on the last page."""
        pages = self._get_pages()
        if self.current_page == len(pages) - 1:
            if self.app_mode == 'wipe':
                self._confirm_wipe()
            else:
                self._confirm_write()
            return
        if self.current_page < len(pages) - 1:
            self.completed[self.current_page] = True
            self.current_page += 1
            self.stack.set_visible_child_name(pages[self.current_page][0])
            self._on_page_entered()
            self.update_nav_buttons()

    def go_back(self):
        """Return to the previous page, or go home from page 0."""
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
        page_name = pages[self.current_page][0]
        if page_name == 'verify-checksum':
            self._update_checksum_file_info()
        elif page_name == 'select-drive':
            self._refresh_drives()
        elif page_name == 'confirm-write':
            self._update_confirm_summary()
        elif page_name == 'wipe-select-drive':
            self._refresh_drives()
        elif page_name == 'wipe-confirm':
            self._update_wipe_summary()

    def update_nav_buttons(self):
        """Update button visibility, sensitivity, and labels for the current page."""
        # Welcome screen: hide all nav
        if self.app_mode is None:
            self.title_label.set_label('DD-imager')
            self.btn_back.set_visible(False)
            self.btn_next.set_visible(False)
            self.btn_skip.set_visible(False)
            self.step_indicator_outer.set_visible(False)
            return

        pages = self._get_pages()
        page_name = pages[self.current_page][0]
        page_title = pages[self.current_page][1]

        # Show step indicator and next button in wizard
        self.step_indicator_outer.set_visible(True)
        self.btn_next.set_visible(True)

        # Update header title to reflect the current step
        self.title_label.set_label(page_title)

        # Update step indicator
        self._update_step_indicator()

        # Back button: always visible in wizard (goes home from page 0)
        self.btn_back.set_visible(True)

        # Skip button: only visible on the verify-checksum page
        self.btn_skip.set_visible(page_name == 'verify-checksum')

        # Next / Write / Wipe button
        self.btn_next.remove_css_class('destructive-action')
        if page_name == 'confirm-write':
            self.btn_next.set_label('Write')
            self.btn_next.add_css_class('destructive-action')
        elif page_name == 'wipe-confirm':
            self.btn_next.set_label('Wipe')
            self.btn_next.add_css_class('destructive-action')
        else:
            self.btn_next.set_label('Next')

        # Next button sensitivity depends on page validation
        if page_name == 'select-iso':
            self.btn_next.set_sensitive(self.iso_path is not None)
        elif page_name == 'verify-checksum':
            sha_ok = self.verify_mode == 'sha' and self.checksum_verified
            gpg_ok = self.verify_mode == 'gpg' and self.gpg_verified
            self.btn_next.set_sensitive(sha_ok or gpg_ok or self.checksum_skipped)
        elif page_name == 'select-drive':
            self.btn_next.set_sensitive(self.target_device is not None)
        elif page_name == 'wipe-select-drive':
            self.btn_next.set_sensitive(self.target_device is not None)
        elif page_name == 'wipe-options':
            self.btn_next.set_sensitive(True)
        else:
            self.btn_next.set_sensitive(True)

    # ---- Welcome and wipe page stubs ----

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

        # Icon: downward arrow onto a rectangle (representing writing to drive)
        write_icon = Gtk.Label()
        write_icon.add_css_class('mode-card-icon')
        write_icon.set_markup('<span size="xx-large" weight="bold">\u2913\u25a0</span>')
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

        # Icon: X mark on a rectangle (representing wiping a drive clean)
        wipe_icon = Gtk.Label()
        wipe_icon.add_css_class('mode-card-icon')
        wipe_icon.set_markup('<span size="xx-large" weight="bold">\u2718\u25a0</span>')
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

    def _build_wipe_drive_page(self):
        """Build the wipe mode drive selection page."""
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

        self.wipe_confirm_method_label = Gtk.Label(label='', halign=Gtk.Align.START)
        summary_inner.append(self.wipe_confirm_method_label)

        summary_inner.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        format_heading = Gtk.Label(label='After Wipe', halign=Gtk.Align.START)
        format_heading.add_css_class('heading')
        summary_inner.append(format_heading)

        self.wipe_confirm_format_label = Gtk.Label(label='', halign=Gtk.Align.START)
        summary_inner.append(self.wipe_confirm_format_label)

        summary_box.append(summary_inner)
        content.append(summary_box)

        # Progress section (hidden until wipe starts)
        self.wipe_progress_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
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

        # Safety checks
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
                ('ones', 'Pass 2/3: Ones'),
                ('/dev/urandom', 'Pass 3/3: Random'),
            ]

        total_passes = len(passes)

        for pass_idx, (source, label) in enumerate(passes):
            if self.wipe_cancelled:
                GLib.idle_add(self._on_wipe_cancelled)
                return

            GLib.idle_add(self._update_wipe_pass_label, label, pass_idx + 1, total_passes)

            # For "ones" pass, use tr to convert zeros to 0xFF
            if source == 'ones':
                dd_cmd = [
                    'pkexec', 'bash', '-c',
                    f"tr '\\0' '\\377' < /dev/zero | dd of={shlex.quote(device_path)} bs=4M status=progress oflag=sync conv=fsync 2>&1"
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
            # Ones pass uses 2>&1 so progress arrives on stdout, not stderr
            progress_fd = self.dd_process.stdout.fileno() if source == 'ones' else self.dd_process.stderr.fileno()
            buf = ''
            while True:
                try:
                    chunk = os.read(progress_fd, 4096)
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
                            pass_fraction = min(bytes_written / device_size, 1.0) if device_size > 0 else 0
                            overall = (pass_idx + pass_fraction) / total_passes
                            GLib.idle_add(self._update_wipe_progress, overall, bytes_written, device_size, line.strip())

            self.dd_process.wait()
            returncode = self.dd_process.returncode
            remaining_err = ''
            try:
                remaining_err = self.dd_process.stderr.read().decode('utf-8', errors='replace') if self.dd_process.stderr else ''
            except Exception:
                pass
            self.dd_process = None

            if self.wipe_cancelled:
                GLib.idle_add(self._on_wipe_cancelled)
                return

            # dd exits non-zero when device is full (ENOSPC) — that's expected
            if returncode != 0:
                all_err = (buf + remaining_err).lower()
                if 'no space left' not in all_err:
                    GLib.idle_add(self._on_wipe_error, f'Wipe pass failed (exit code {returncode})')
                    return

        # Post-wipe formatting
        if self.wipe_format != 'raw':
            GLib.idle_add(self._update_wipe_pass_label, 'Formatting...', 0, 0)
            fmt_success = self._format_device(device_path)
            if not fmt_success:
                return

        try:
            subprocess.run(['sync'], timeout=60)
        except Exception:
            pass

        GLib.idle_add(self._on_wipe_success)

    def _format_device(self, device_path):
        """Create partition table and filesystem. Returns True on success."""
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

        partition = f'{device_path}1'

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
        if total > 0:
            self.wipe_progress_label.set_label(f'{label} ({pass_num}/{total})')
        else:
            self.wipe_progress_label.set_label(label)
        return False

    def _update_wipe_progress(self, fraction, bytes_written, total_size, detail_line):
        self.wipe_progress_bar.set_fraction(fraction)
        self.wipe_progress_bar.set_text(f'{fraction:.0%}')

        written_str = format_file_size(bytes_written)
        total_str = format_file_size(total_size) if total_size > 0 else '?'

        speed_match = re.search(r'[\d.]+ [KMGT]?B/s', detail_line)
        speed_part = f'  —  {speed_match.group(0)}' if speed_match else ''

        current_label = self.wipe_progress_label.get_label()
        pass_info = current_label.split('(')[0].strip() if '(' in current_label else current_label
        self.wipe_progress_label.set_label(f'{pass_info} — {written_str} / {total_str}{speed_part}')
        return False

    def _on_cancel_wipe(self, _button):
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
        self.wipe_progress_label.set_label('Wipe cancelled.')
        self.btn_cancel_wipe.set_visible(False)
        self.wipe_result_label.set_label('Wipe was cancelled by user.')
        self.wipe_result_label.remove_css_class('success')
        self.wipe_result_label.add_css_class('error')
        self.wipe_result_label.set_visible(True)
        self.btn_back.set_sensitive(True)
        self.btn_next.set_visible(True)
        return False

    def _update_wipe_summary(self):
        """Populate the summary labels on the wipe confirm page."""
        self.wipe_result_label.set_visible(False)
        self.wipe_result_label.remove_css_class('error')
        self.wipe_result_label.remove_css_class('success')

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

        method_names = {'zero': 'Zero fill', 'random': 'Random fill', 'multipass': 'Multi-pass (3 passes)'}
        self.wipe_confirm_method_label.set_label(method_names.get(self.wipe_method, self.wipe_method))

        format_names = {
            'raw': 'Leave raw (no filesystem)',
            'fat32': 'Format as FAT32',
            'exfat': 'Format as exFAT',
            'ext4': 'Format as ext4',
            'ntfs': 'Format as NTFS',
        }
        self.wipe_confirm_format_label.set_label(format_names.get(self.wipe_format, self.wipe_format))


if __name__ == '__main__':
    app = DDImagerApp()
    app.run()
