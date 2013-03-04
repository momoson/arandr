# This Python file uses the following encoding: utf-8

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

import weakref
from collections import OrderedDict
from math import sqrt

import gobject, gtk
import pango

from ..gtktools import CategoryDefinitionWidget
from ..xrandr.constants import ConnectionStatus, SubpixelOrder

import gettext
gettext.install('arandr')

class TransitionOutputWidget(gtk.Notebook):
    """A detail widget for a single output of a transition. Bound to (and
    constructed from) a TransitionWidget. This coupling is necessary as long as
    the transition widget wraps general server/transition handling like server
    re-creation after updates.

    The transition output widget is not bound to a transition output object,
    but only to an output name. This is done so that when the server is
    re-created after a transition is applied, the transition output widget can
    easily update itself from its main widget's new server.
    """

    __gsignals__ = {
            'changed':(gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
            }

    def __init__(self, main_widget, output_name):
        super(TransitionOutputWidget, self).__init__()

        self._main_widget = weakref.ref(main_widget)
        self.output_name = output_name

        self._create_tabs()

        self.update()

    def _create_tabs(self):
        self.tabs = OrderedDict([
            ('base', self.BaseTab()),
            ('edid', self.EDIDTab()),
            ])

        for t in self.tabs.values():
            self.insert_page(t, t.get_label())

    def update(self):
        for t in self.tabs.values():
            t.update_from(self)

    transition_output = property(lambda self: self._main_widget()._transition.outputs[self.output_name])
    server_output = property(lambda self: self.transition_output.server_output)

    class BaseTab(CategoryDefinitionWidget):
        def __init__(self):
            super(TransitionOutputWidget.BaseTab, self).__init__()

            OUTPUT = _("Output information")
            CONNECTED = _("Connected monitor")
            CONFIG = _("Base configuration")

            self.output_name = gtk.Label()
            self.connection_status = gtk.Label()

            self.physical_dimension = gtk.Label()
            self.physical_diagonal = gtk.Label()
            self.subpixels = gtk.Label()

            self.active = gtk.CheckButton()
            self.resolution = gtk.ComboBox()
            self.refreshrate = gtk.ComboBox()

            items = [
                    (OUTPUT, _("Output name:"), self.output_name),
                    (OUTPUT, _("Connection status:"), self.connection_status),
                    (CONNECTED, _("Physical dimension:"), self.physical_dimension),
                    (CONNECTED, _("Screen diagonal:"), self.physical_diagonal),
                    (CONNECTED, _("Subpixel order:"), self.subpixels),
                    (CONFIG, _("Output active:"), self.active),
                    (CONFIG, _("Resolution:"), self.resolution),
                    (CONFIG, _("Refresh rate:"), self.refreshrate),
                    ]

            self.set_items(items)

        @staticmethod
        def get_label():
            return gtk.Label(_("Basic"))

        def update_from(self, widget):
            self.output_name.props.label = widget.output_name

            self.connection_status.props.label = {
                    ConnectionStatus('connected'): _("connected"),
                    ConnectionStatus('disconnected'): _("disconnected"),
                    ConnectionStatus('unknown connection'): _("unknown"),
                    }[widget.server_output.connection_status]

            dimensions = (widget.server_output.physical_x, widget.server_output.physical_y)
            if any(x is None for x in dimensions):
                self.physical_dimension.props.label = _("–")
                self.physical_diagonal.props.label = _("–")
            else:
                diag = sqrt(sum(x**2 for x in dimensions))
                self.physical_dimension.props.label = _("%smm × %smm")%dimensions
                self.physical_diagonal.props.label = _('%.0fmm / %.1f"')%(diag, diag/25.4)
            self.subpixels.props.label = {
                    SubpixelOrder('unknown'): _('–'),
                    SubpixelOrder('horizontal rgb'): _('horizontal (RGB)'),
                    SubpixelOrder('horizontal bgr'): _('horizontal (BGR)'),
                    SubpixelOrder('vertical rgb'): _('vertical (RGB)'),
                    SubpixelOrder('vertical bgr'): _('vertical (BGR)'),
                    SubpixelOrder('no subpixels'): _('no subpixels'),
                    }[widget.server_output.Subpixel]


    class EDIDTab(gtk.Label):
        def __init__(self):
            super(TransitionOutputWidget.EDIDTab, self).__init__()
            self.props.wrap = True
            self.props.wrap_mode = pango.WRAP_CHAR

        def update_from(self, widget):
            if 'EDID' in widget.server_output.properties:
                self.props.label = widget.server_output.properties['EDID'][0].encode('hex')
            else:
                self.props.label = _("No EDID data available.")

        @staticmethod
        def get_label():
            return gtk.Label(_("EDID information"))