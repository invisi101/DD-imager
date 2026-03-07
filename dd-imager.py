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
