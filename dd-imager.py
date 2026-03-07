#!/usr/bin/env python3
"""DD-imager — Safe USB image writer."""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw


# Page definitions: (stack_name, header_title, placeholder_label)
PAGES = [
    ('select-iso',       'Select ISO',       'Step 1: Select ISO'),
    ('verify-checksum',  'Verify Checksum',  'Step 2: Verify Checksum'),
    ('select-drive',     'Select Drive',     'Step 3: Select Drive'),
    ('confirm-write',    'Confirm & Write',  'Step 4: Confirm & Write'),
]


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
        self.header.set_title_widget(Gtk.Label(label='DD-imager',
                                               css_classes=['title']))

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

        # --- Stack with placeholder pages ---
        self.stack = Gtk.Stack()
        self.stack.set_vexpand(True)
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(200)

        for name, _title, label_text in PAGES:
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
        self.header.set_title_widget(
            Gtk.Label(label=page_title, css_classes=['title']))

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

        # Next button is enabled (placeholder pages are always "ready")
        # Later tasks will disable it until the page validates its input.
        self.btn_next.set_sensitive(True)


if __name__ == '__main__':
    app = DDImagerApp()
    app.run()
