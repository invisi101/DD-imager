#!/usr/bin/env python3
"""DD-imager — Safe USB image writer."""

import hashlib
import json
import subprocess
import threading
from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib


# Page definitions: (stack_name, header_title, placeholder_label)
PAGES = [
    ('select-iso',       'Select ISO',       'Step 1: Select ISO'),
    ('verify-checksum',  'Verify Checksum',  'Step 2: Verify Checksum'),
    ('select-drive',     'Select Drive',     'Step 3: Select Drive'),
    ('confirm-write',    'Confirm & Write',  'Step 4: Confirm & Write'),
]


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

        drives.append({
            'device': device_path,
            'name': name,
            'size': size_bytes,
            'label': label,
            'mounted': mounts,
        })
    return drives


class DDImagerApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.invisi101.dd-imager')
        self.connect('activate', self.on_activate)

    # ---- UI construction ----

    def on_activate(self, app):
        self.win = Adw.ApplicationWindow(
            application=app,
            title='DD-imager',
            default_width=600,
            default_height=500,
        )

        # Wizard state
        self.current_page = 0
        self.completed = [False] * len(PAGES)
        self.checksum_verified = False
        self.target_device = None

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
        self.btn_skip.connect('clicked', lambda _b: self.go_next())
        self.header.pack_end(self.btn_skip)

        # --- Stack with pages ---
        self.stack = Gtk.Stack()
        self.stack.set_vexpand(True)
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(200)

        # Page 0: Select ISO (real implementation)
        self.iso_path = None
        self.stack.add_named(self._build_iso_page(), 'select-iso')

        # Page 1: Verify Checksum (real implementation)
        self.stack.add_named(self._build_checksum_page(), 'verify-checksum')

        # Page 2: Select Drive (real implementation)
        self.stack.add_named(self._build_drive_page(), 'select-drive')

        # Pages 3+: placeholders
        for name, _title, label_text in PAGES[3:]:
            page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                               halign=Gtk.Align.CENTER,
                               valign=Gtk.Align.CENTER)
            page_label = Gtk.Label(label=label_text)
            page_label.add_css_class('title-1')
            page_box.append(page_label)
            self.stack.add_named(page_box, name)

        # --- Main layout: header on top, stack below ---
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.append(self.header)
        vbox.append(self.stack)
        self.win.set_content(vbox)

        # Set initial button states
        self.update_nav_buttons()

        self.win.present()

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
        """Build the Verify Checksum page with hash entry, verify button, and result label."""
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

        # SHA-256 entry field
        self.hash_entry = Gtk.Entry()
        self.hash_entry.set_placeholder_text('Paste expected SHA-256 hash here')
        self.hash_entry.set_width_chars(64)
        self.hash_entry.set_max_width_chars(64)
        page.append(self.hash_entry)

        # Row for Verify button and spinner
        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12,
                             halign=Gtk.Align.CENTER)

        self.btn_verify = Gtk.Button(label='Verify')
        self.btn_verify.add_css_class('pill')
        self.btn_verify.add_css_class('suggested-action')
        self.btn_verify.connect('clicked', self._on_verify_clicked)
        action_row.append(self.btn_verify)

        self.checksum_spinner = Gtk.Spinner()
        self.checksum_spinner.set_visible(False)
        action_row.append(self.checksum_spinner)

        page.append(action_row)

        # Result label (green/red)
        self.checksum_result_label = Gtk.Label(label='')
        self.checksum_result_label.set_wrap(True)
        self.checksum_result_label.set_max_width_chars(50)
        page.append(self.checksum_result_label)

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

    def _on_hash_error(self, error_msg):
        """Called on the main thread if hash computation fails."""
        self.btn_verify.set_sensitive(True)
        self.hash_entry.set_sensitive(True)
        self.checksum_spinner.stop()
        self.checksum_spinner.set_visible(False)
        self.checksum_result_label.set_label(f'Error: {error_msg}')
        self.checksum_result_label.remove_css_class('success')
        self.checksum_result_label.add_css_class('error')

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
        warning_box.add_css_class('warning')
        warning_label = Gtk.Label(
            label='\u26a0  All data on the selected drive will be destroyed',
            halign=Gtk.Align.CENTER,
            hexpand=True,
            margin_top=8,
            margin_bottom=8,
            margin_start=12,
            margin_end=12,
        )
        warning_label.add_css_class('warning')
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
        # Clear current selection
        self.target_device = None
        self.btn_next.set_sensitive(False)

        # Remove all existing rows
        while True:
            row = self.drive_listbox.get_row_at_index(0)
            if row is None:
                break
            self.drive_listbox.remove(row)

        # Detect drives
        drives = get_removable_drives()

        if not drives:
            self.drive_listbox.set_visible(False)
            self.drive_empty_label.set_visible(True)
            return

        self.drive_listbox.set_visible(True)
        self.drive_empty_label.set_visible(False)

        for drive in drives:
            row = self._make_drive_row(drive)
            self.drive_listbox.append(row)

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

        device_label = Gtk.Label(halign=Gtk.Align.START)
        device_label.set_markup(f'<b>{GLib.markup_escape_text(drive["device"])}</b>')
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

    # ---- Navigation logic ----

    def go_next(self):
        """Advance to the next page."""
        if self.current_page < len(PAGES) - 1:
            self.completed[self.current_page] = True
            self.current_page += 1
            self.stack.set_visible_child_name(PAGES[self.current_page][0])
            self._on_page_entered()
            self.update_nav_buttons()

    def go_back(self):
        """Return to the previous page."""
        if self.current_page > 0:
            self.current_page -= 1
            self.stack.set_visible_child_name(PAGES[self.current_page][0])
            self._on_page_entered()
            self.update_nav_buttons()

    def _on_page_entered(self):
        """Called whenever the visible page changes; refreshes page-specific content."""
        page_name = PAGES[self.current_page][0]
        if page_name == 'verify-checksum':
            self._update_checksum_file_info()
        elif page_name == 'select-drive':
            self._refresh_drives()

    def update_nav_buttons(self):
        """Update button visibility, sensitivity, and labels for the current page."""
        page_name = PAGES[self.current_page][0]
        page_title = PAGES[self.current_page][1]

        # Update header title to reflect the current step
        self.title_label.set_label(page_title)

        # Back button: hidden on first page
        self.btn_back.set_visible(self.current_page > 0)

        # Skip button: only visible on the verify-checksum page
        self.btn_skip.set_visible(page_name == 'verify-checksum')

        # Next / Write button
        if page_name == 'confirm-write':
            self.btn_next.set_label('Write')
            self.btn_next.add_css_class('destructive-action')
        else:
            self.btn_next.set_label('Next')
            self.btn_next.remove_css_class('destructive-action')

        # Next button sensitivity depends on page validation
        if page_name == 'select-iso':
            self.btn_next.set_sensitive(self.iso_path is not None)
        elif page_name == 'verify-checksum':
            self.btn_next.set_sensitive(self.checksum_verified)
        elif page_name == 'select-drive':
            self.btn_next.set_sensitive(self.target_device is not None)
        else:
            self.btn_next.set_sensitive(True)


if __name__ == '__main__':
    app = DDImagerApp()
    app.run()
