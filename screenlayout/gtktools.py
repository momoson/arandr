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

"""
GTK widgets that are used in one or more carddecoder.

This is only a temporary solution -- this stuff should either go up into pygtk
or form an own independent module in the style of sexy.
"""
# even worse so, i copy-pasted this from another project of mine, carddecoders.
# did i mention this should be split out?

# Import everything here to avoid having `import gi / gi.require / import` everywhere
import gi
gi.require_version('Gtk', '3.0') # API version; requiring 3.22 for Gtk.Menu.popup_at_pointer
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Pango, PangoCairo, Gdk, GObject

class CategoryDefinitionWidget(Gtk.Table):
    """Widget that displays a list of items grouped to categories in the style
    of the "Frames and Separators" chapter of the Gnome HIG.

    `items` is an iterable containing (catgory_label, label, data) triples.
    The latter two can be strings or widgets. Items will be displayed in the
    order in which they are given, items with equal category labels will be
    grouped under their caption.

    A CategoryDefinitionWidget(
        [
            ("some category", "What:", "Spam"),
            ("some category", "How much:", "very much"),
            ("another category", Gtk.Label(label="Widget:"), Gtk.Entry()),
            ]
    will look like this:

        *some category*
            What:      Spam
            How much:  very much
        *another category*
            Widget:    [Text field]
    """
    __gtype_name__ = "CategoryDefinitionWidget"

    def __init__(self, items=None):
        super(CategoryDefinitionWidget, self).__init__(n_columns=2)

        self.props.border_width = 6 # concerning paddings: the 6 pixels spread through the layouting should add up to the 12px left, 12px between, and 12px right of each column

        if items:
            self.set_items(items)

    def set_items(self, items):
        for c in self.get_children():
            self.remove(c)

        last_category = None
        row = 0
        for category_label, label, data in items:
            # category separator
            if category_label != last_category:
                clabel = Gtk.Label()
                clabel.set_markup('<b>%s</b>'%category_label) # FIXME: escape?
                clabel.props.xalign = 0
                self.attach(clabel, 0, 2, row, row+1)
                row += 1
                last_category = category_label

            # conversion to widgets if required
            if not isinstance(label, Gtk.Widget):
                label = Gtk.Label(label=label)
                label.props.xalign = 0
            if not isinstance(data, Gtk.Widget):
                data = Gtk.Label(label=data)
                data.props.xalign = 0

            label.props.margin_left = 12

            # adding to grid
            self.attach(label, 0, 1, row, row+1)
            self.attach(data, 1, 2, row, row+1)

            row += 1

        self.show_all()

if __name__ == "__main__":
    w = Gtk.Window()
    w.add(CategoryDefinitionWidget([
            ("some category", "What:", "Spam"),
            ("some category", "How much:", "very much"),
            ("another category", Gtk.Label(label="Widget:"), Gtk.Entry()),
            ]))
    w.show_all()
    w.connect('destroy', Gtk.main_quit)
    Gtk.main()
