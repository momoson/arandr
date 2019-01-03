# ARandR -- Another XRandR GUI
# Copyright (C) 2008 -- 2011 chrysn <chrysn@fsfe.org>
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Main GUI for ARandR"""

import os
import optparse
import inspect
from .executions import contextbuilder
from .executions import context as executions_context

from .gtktools import Gtk

from . import widget

from .meta import __version__, TRANSLATORS, COPYRIGHT, PROGRAMNAME, PROGRAMDESCRIPTION

#import os
#os.environ['DISPLAY']=':0.0'

import gettext
gettext.install('arandr')


def actioncallback(function):
    """Wrapper around a function that is intended to be used both as a callback from a Gtk.Action and as a normal function.

    Functions taking no arguments will never be given any, functions taking one argument (callbacks for radio actions) will be given the value of the action or just the argument.

    A first argument called 'self' is passed through."""
    argnames = inspect.getargspec(function)[0]
    if argnames[0] == 'self':
        has_self = True
        argnames.pop(0)
    else:
        has_self = False
    assert len(argnames) in (0,1)

    def wrapper(*args):
        args_in = list(args)
        args_out = []
        if has_self:
            args_out.append(args_in.pop(0))
        if len(argnames) == len(args_in): # called directly
            args_out.extend(args_in)
        elif len(argnames)+1 == len(args_in):
            if len(argnames):
                args_out.append(args_in[1].props.value)
        else:
            raise TypeError("Arguments don't match")

        return function(*args_out)

    wrapper.__name__ = function.__name__
    wrapper.__doc__ = function.__doc__
    return wrapper


class Application(object):
    uixml = """
    <ui>
        <menubar name="MenuBar">
            <menu action="Layout">
                <menuitem action="New" />
                <menuitem action="Open" />
                <menuitem action="SaveAs" />
                <separator />
                <menuitem action="Apply" />
                <menuitem action="LayoutSettings" />
                <separator />
                <menuitem action="Quit" />
            </menu>
            <menu action="View">
                <menuitem action="Zoom4" />
                <menuitem action="Zoom8" />
                <menuitem action="Zoom16" />
            </menu>
            <menu action="Outputs" name="Outputs">
                <menuitem action="OutputsDummy" />
            </menu>
            <menu action="Help">
                <menuitem action="About" />
            </menu>
        </menubar>
        <toolbar name="ToolBar">
            <toolitem action="Apply" />
            <separator />
            <toolitem action="New" />
            <toolitem action="Open" />
            <toolitem action="SaveAs" />
        </toolbar>
    </ui>
    """

    def __init__(self, file=None, context=None, force_version=False):
        self.window = window = Gtk.Window()
        window.props.title = "Screen Layout Editor"

        # actions
        actiongroup = Gtk.ActionGroup('default')
        actiongroup.add_actions([
            ("Layout", None, _("_Layout")),
            ("New", Gtk.STOCK_NEW, None, None, None, self.do_new),
            ("Open", Gtk.STOCK_OPEN, None, None, None, self.do_open),
            ("SaveAs", Gtk.STOCK_SAVE_AS, None, None, None, self.do_save_as),

            ("Apply", Gtk.STOCK_APPLY, None, '<Control>Return', None, self.do_apply),
            ("LayoutSettings", Gtk.STOCK_PROPERTIES, None, '<Alt>Return', None, self.do_open_properties),

            ("Quit", Gtk.STOCK_QUIT, None, None, None, Gtk.main_quit),


            ("View", None, _("_View")),

            ("Outputs", None, _("_Outputs")),
            ("OutputsDummy", None, _("Dummy")),

            ("System", None, _("_System")),

            ("Help", None, _("_Help")),
            ("About", Gtk.STOCK_ABOUT, None, None, None, self.about),
            ])
        actiongroup.add_radio_actions([
            ("Zoom4", None, _("1:4"), None, None, 4),
            ("Zoom8", None, _("1:8"), None, None, 8),
            ("Zoom16", None, _("1:16"), None, None, 16),
            ], 8, self.set_zoom)

        window.connect('destroy', Gtk.main_quit)

        # uimanager
        self.uimanager = Gtk.UIManager()
        accelgroup = self.uimanager.get_accel_group()
        window.add_accel_group(accelgroup)

        self.uimanager.insert_action_group(actiongroup, 0)

        self.uimanager.add_ui_from_string(self.uixml)

        # widget
        self.widget = widget.TransitionWidget(context=context, force_version=force_version)
        if file is None:
            self.filetemplate = self.widget.load_from_x()
        else:
            self.filetemplate = self.widget.load_from_file(file)

        self.widget.connect('changed', self._widget_changed)
        self._widget_changed(self.widget)

        # window layout
        vbox = Gtk.VBox()
        menubar = self.uimanager.get_widget('/MenuBar')
        vbox.pack_start(menubar, expand=False, fill=False, padding=0)
        toolbar = self.uimanager.get_widget('/ToolBar')
        vbox.pack_start(toolbar, expand=False, fill=False, padding=0)

        vbox.add(self.widget)

        window.add(vbox)
        window.show_all()

        self.gconf = None

    #################### actions ####################

    @actioncallback
    def set_zoom(self, value): # don't use directly: state is not pushed back to action group.
        self.widget.factor = value
        self.window.resize(1,1)

    @actioncallback
    def do_open_properties(self):
        d = Gtk.Dialog(_("Script Properties"), None, Gtk.DialogFlags.MODAL, (Gtk.STOCK_CLOSE, Gtk.ResponseType.ACCEPT))
        d.set_default_size(300,400)

        script_editor = Gtk.TextView()
        script_buffer = script_editor.get_buffer()
        script_buffer.set_text("\n".join(self.filetemplate))
        script_editor.props.editable = False

        #wacom_options = Gtk.Label("FIXME")

        nb = Gtk.Notebook()
        #nb.append_page(wacom_options, Gtk.Label(_("Wacom options")))
        nb.append_page(script_editor, Gtk.Label(_("Script")))

        d.vbox.pack_start(nb, expand=False, fill=False, padding=0)
        d.show_all()

        d.run()
        d.destroy()

    @actioncallback
    def do_apply(self):
        if self.widget.abort_if_unsafe():
            return

        try:
            self.widget.save_to_x()
        except Exception as e:
            d = Gtk.MessageDialog(None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.BUTTONS_OK, _("XRandR failed:\n%s")%e)
            d.run()
            d.destroy()

    @actioncallback
    def do_new(self):
        self.filetemplate = self.widget.load_from_x()

    @actioncallback
    def do_open(self):
        d = self._new_file_dialog(_("Open Layout"), Gtk.FILE_CHOOSER_ACTION_OPEN)

        result = d.run()
        filenames = d.get_filenames()
        d.destroy()
        if result == Gtk.ResponseType.ACCEPT:
            assert len(filenames) == 1
            f = filenames[0]
            self.filetemplate = self.widget.load_from_file(f)

    @actioncallback
    def do_save_as(self):
        d = self._new_file_dialog(_("Save Layout"), Gtk.FILE_CHOOSER_ACTION_SAVE)
        d.props.do_overwrite_confirmation = True

        result = d.run()
        filenames = d.get_filenames()
        d.destroy()
        if result == Gtk.ResponseType.ACCEPT:
            assert len(filenames) == 1
            f = filenames[0]
            if not f.endswith('.sh'): f = f + '.sh'
            self.widget.save_to_file(f, self.filetemplate)

    def _new_file_dialog(self, title, type):
        d = Gtk.FileChooserDialog(title, None, type)
        d.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        d.add_button(Gtk.STOCK_OPEN, Gtk.ResponseType.ACCEPT)

        layoutdir = os.path.expanduser('~/.screenlayout/')
        try:
            os.makedirs(layoutdir)
        except OSError:
            pass
        d.set_current_folder(layoutdir)

        f = Gtk.FileFilter()
        f.set_name('Shell script (Layout file)')
        f.add_pattern('*.sh')
        d.add_filter(f)

        return d

    #################### widget maintenance ####################

    def _widget_changed(self, widget):
        self._populate_outputs()

    def _populate_outputs(self):
        w = self.uimanager.get_widget('/MenuBar/Outputs')
        w.props.submenu = self.widget.get_main_contextmenu()

    #################### application related ####################

    def about(self, *args):
        d = Gtk.AboutDialog()
        d.props.program_name = PROGRAMNAME
        d.props.version = __version__
        d.props.translator_credits = "\n".join(TRANSLATORS)
        d.props.copyright = COPYRIGHT
        d.props.comments = PROGRAMDESCRIPTION
        d.props.license = open(os.path.join(os.path.dirname(__file__), 'data', 'gpl-3.txt')).read()
        d.props.logo_icon_name = 'video-display'
        d.run()
        d.destroy()

    def run(self):
        Gtk.main()

def main():
    p = optparse.OptionParser(usage="%prog [savedfile]", description="Another XRandrR GUI", version="%%prog %s"%__version__)
    p.add_option('--randr-display', help='Use D as display for xrandr (but still show the GUI on the display from the environment; e.g. `localhost:10.0`)', metavar='D')
    p.add_option('--remote-host', help="Connect to H using SSH for executing xrandr (remote control)", metavar='H')
    p.add_option('--force-version', help='Even run with untested XRandR versions', action='store_true')

    (options, args) = p.parse_args()
    if len(args) == 0:
        file_to_open = None
    elif len(args) == 1:
        file_to_open = args[0]
    else:
        p.usage()

    context = contextbuilder.build_default_context()

    if options.remote_host:
        context = executions_context.SSHContext(options.remote_host, underlying_context=context)
        if not options.randr_display:
            context = executions_context.WithXEnvironment(underlying_context=context)

    if options.randr_display:
        context = executions_context.WithEnvironment({'DISPLAY': options.randr_display}, underlying_context=context)

    a = Application(
            file=file_to_open,
            context=context,
            force_version=options.force_version
            )
    a.run()
