#!/usr/bin/env python3
"""DD-imager — Safe USB image writer."""

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

        # Pages 1–3: placeholders
        for name, _title, label_text in PAGES[1:]:
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

    # ---- Navigation logic ----

    def go_next(self):
        """Advance to the next page."""
        if self.current_page < len(PAGES) - 1:
            self.completed[self.current_page] = True
            self.current_page += 1
            self.stack.set_visible_child_name(PAGES[self.current_page][0])
            self.update_nav_buttons()

    def go_back(self):
        """Return to the previous page."""
        if self.current_page > 0:
            self.current_page -= 1
            self.stack.set_visible_child_name(PAGES[self.current_page][0])
            self.update_nav_buttons()

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
        else:
            self.btn_next.set_sensitive(True)


if __name__ == '__main__':
    app = DDImagerApp()
    app.run()
