"""
ARandR -- Another XRandR GUI
Copyright (C) 2008 -- 2011 chrysn <chrysn@fsfe.org>
copyright (C) 2019 actionless <actionless.loveless@gmail.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
# pylint: disable=wrong-import-position,missing-docstring,fixme

from __future__ import division
import os
import stat

from math import isclose

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import GObject, Gtk, Pango, PangoCairo, Gdk, GLib
from cairo import LinearGradient
from cairo import Extend

from .snap import Snap
from .swayoutput import SwayOutput
from .auxiliary import Position, Transformation, InadequateConfiguration
from .i18n import _


class ARandRWidget(Gtk.DrawingArea):

    sequence = None
    _lastclick = None
    _draggingoutput = None
    _draggingfrom = None
    _draggingsnap = None

    __gsignals__ = {
        # 'expose-event':'override', # FIXME: still needed?
        'changed': (GObject.SIGNAL_RUN_LAST, GObject.TYPE_NONE, ()),
    }

    def __init__(self, window, factor=8, display=None):
        super(ARandRWidget, self).__init__()

        self.window = window
        self._factor = factor

        self.set_size_request(
            1024 // self.factor, 1024 // self.factor
        )  # best guess for now

        self.connect('button-press-event', self.click)
        self.set_events(Gdk.EventType.BUTTON_PRESS)

        self.setup_draganddrop()

        self._swayoutput = SwayOutput(display=display)

        self.connect('draw', self.do_expose_event)

    #################### widget features ####################

    def _set_factor(self, fac):
        self._factor = fac
        self._update_size_request()
        self._force_repaint()

    factor = property(lambda self: self._factor, _set_factor)

    def abort_if_unsafe(self):

        return False

        if not [x for x in self._swayoutput.configuration.outputs.values() if x.active]:
            dialog = Gtk.MessageDialog(
                None, Gtk.DialogFlags.MODAL, Gtk.MessageType.WARNING, Gtk.ButtonsType.YES_NO,
                _(
                    "Your configuration does not include an active monitor. "
                    "Do you want to apply the configuration?"
                )
            )
            result = dialog.run()
            dialog.destroy()
            if result == Gtk.ResponseType.YES:
                return False
            return True
        return False

    def error_message(self, message):  # pylint: disable=no-self-use
        dialog = Gtk.MessageDialog(
            None, Gtk.DialogFlags.MODAL,
            Gtk.MessageType.ERROR, Gtk.ButtonsType.CLOSE,
            message
        )
        dialog.run()
        dialog.destroy()

    def _update_size_request(self):
        # this ignores that some outputs might not support rotation,
        # but will always err at the side of caution.
        max_gapless = sum(
            max(output.size) if output.active else 0
            for output in self._swayoutput.configuration.outputs.values()
        )
        # have some buffer
        usable_size = int(max_gapless * 1.1)
        # don't request too large a window, but make sure every possible compination fits
        xdim = usable_size
        ydim = usable_size

        self.set_size_request(xdim // self.factor, ydim // self.factor)

    #################### loading ####################

    def load_from_file(self, file):
        data = open(file).read()
        template = self._swayoutput.load_from_string(data)
        self._swayoutput_was_reloaded()
        return template

    def load_from_x(self):
        self._swayoutput.load_from_x()
        self._swayoutput_was_reloaded()
        return self._swayoutput.DEFAULTTEMPLATE

    def _swayoutput_was_reloaded(self):
        self.sequence = sorted(self._swayoutput.outputs)
        self._lastclick = (-1, -1)

        self._update_size_request()
        if self.window:
            self._force_repaint()
        self.emit('changed')

    def save_to_x(self):
        self._swayoutput.save_to_x()
        self.load_from_x()

    def save_to_file(self, file, template=None, additional=None):
        data = self._swayoutput.save_to_shellscript_string(template, additional)
        open(file, 'w').write(data)
        os.chmod(file, stat.S_IRWXU)
        self.load_from_file(file)

    #################### doing changes ####################

    def _set_something(self, which, output_name, data):
        old = getattr(self._swayoutput.configuration.outputs[output_name], which)
        setattr(self._swayoutput.configuration.outputs[output_name], which, data)
        try:
            self._swayoutput.check_configuration()
        except InadequateConfiguration:
            setattr(self._swayoutput.configuration.outputs[output_name], which, old)
            raise

        self._force_repaint()
        self.emit('changed')

    def set_position(self, output_name, pos):
        self._set_something('position', output_name, pos)

    def set_rotation(self, output_name, rot):
        self._set_something('rotation', output_name, rot)

    def set_resolution(self, output_name, res):
        self._set_something('mode', output_name, res)

    def set_scale(self, output_name, scale):
        self._set_something('scale', output_name, scale)

    def set_active(self, output_name, active):
        output = self._swayoutput.configuration.outputs[output_name]

        if not active and output.active:
            output.active = False
            # don't delete: allow user to re-enable without state being lost
        if active and not output.active:
            if hasattr(output, 'position'):
                output.active = True  # nothing can go wrong, position already set
            else:
                pos = Position((0, 0))
                first_mode = self._swayoutput.state.outputs[output_name].modes[-1] # This is typical the largest one

                output.active = True
                output.position = pos
                output.mode = first_mode
                output.rotation = Rotation(0)

        self._force_repaint()
        self.emit('changed')

    def set_flipped(self, output_name, flipped):
        output = self._swayoutput.configuration.outputs[output_name]

        output.transform.flipped = flipped

        self._force_repaint()
        self.emit('changed')

    def set_dpms(self, output_name, dpms):
        output = self._swayoutput.configuration.outputs[output_name]

        output.dpms = dpms

        self._force_repaint()
        self.emit('changed')

    #################### painting ####################

    def do_expose_event(self, _event, context):
        allocation = self.get_allocation()

        context.rectangle(
            0, 0,
            allocation.width, allocation.height
        )
        context.clip()

        # clear

        context.set_source_rgb(0.25, 0.25, 0.25)
        context.rectangle(0, 0, allocation.width, allocation.height)
        context.fill()
        context.save()

        context.scale(1 / self.factor, 1 / self.factor)
        context.set_line_width(self.factor * 1.5)

        self._draw(self._swayoutput, context)

    def _draw(self, swayoutput, context):  # pylint: disable=too-many-locals
        cfg = swayoutput.configuration
        state = swayoutput.state

        for output_name in self.sequence:
            output = cfg.outputs[output_name]
            if not output.active:
                continue

            rect = (output.tentative_position if hasattr(
                output, 'tentative_position') else output.position) + tuple(output.size)
            center = rect[0] + rect[2] / 2, rect[1] + rect[3] / 2

            # paint rectangle
            context.rectangle(*rect)
            context.set_source_rgba(1, 1, 1, 0.7)
            context.fill()

            # show if it is blacked out
            if not output.dpms:
                context.rectangle(*rect)
                pattern = LinearGradient(0,0,5*self.factor,5*self.factor)
                pattern.add_color_stop_rgba(0.0,0,0,0,0.7)
                pattern.add_color_stop_rgba(0.47,0,0,0,0.7)
                pattern.add_color_stop_rgba(0.53,0,0,0,0)
                pattern.set_extend(Extend.REFLECT)
                context.set_source(pattern)
                context.fill()
                context.rectangle(*rect)
                pattern = LinearGradient(0,0,-5*self.factor,5*self.factor)
                pattern.add_color_stop_rgba(0.0,0,0,0,0.7)
                pattern.add_color_stop_rgba(0.47,0,0,0,0.7)
                pattern.add_color_stop_rgba(0.53,0,0,0,0)
                pattern.set_extend(Extend.REFLECT)
                context.set_source(pattern)
                context.fill()


            context.set_source_rgb(0, 0, 0)
            context.rectangle(*rect)
            context.stroke()

            # set up for text
            context.save()
            textwidth = rect[3 if output.rotation.is_odd else 2]
            widthperchar = textwidth / len(output_name)
            # i think this looks nice and won't overflow even for wide fonts
            textheight = int(widthperchar * 0.8)

            newdescr = Pango.FontDescription("sans")
            newdescr.set_size(textheight * Pango.SCALE)

            # create text
            output_name_markup = GLib.markup_escape_text(output_name)
            layout = PangoCairo.create_layout(context)
            layout.set_font_description(newdescr)

            layout.set_markup(output_name_markup, -1)

            # position text
            layoutsize = layout.get_pixel_size()
            layoutoffset = -layoutsize[0] / 2, -layoutsize[1] / 2
            context.move_to(*center)
            if output.transform.flipped:
                context.scale(-1,1)
            context.rotate(output.rotation.angle)
            context.rel_move_to(*layoutoffset)

            # paint text
            PangoCairo.show_layout(context, layout)
            context.restore()

    def _force_repaint(self):
        # using self.allocation as rect is offset by the menu bar.
        allocation = self.get_allocation()
        self.queue_draw_area(
            0, 0, allocation.width, allocation.height
        )

    #################### click handling ####################

    def click(self, _widget, event):
        undermouse = self._get_point_outputs(event.x, event.y)
        if event.button == 1 and undermouse:
            which = self._get_point_active_output(event.x, event.y)
            # this was the second click to that stack
            if self._lastclick == (event.x, event.y):
                # push the highest of the undermouse windows below the lowest
                newpos = min(self.sequence.index(a) for a in undermouse)
                self.sequence.remove(which)
                self.sequence.insert(newpos, which)
                # sequence changed
                which = self._get_point_active_output(event.x, event.y)
            # pull the clicked window to the absolute top
            self.sequence.remove(which)
            self.sequence.append(which)

            self._lastclick = (event.x, event.y)
            self._force_repaint()
        if event.button == 3:
            if undermouse:
                target = [a for a in self.sequence if a in undermouse][-1]
                menu = self._contextmenu(target)
                menu.popup(None, None, None, None, event.button, event.time)
            else:
                menu = self.contextmenu()
                menu.popup(None, None, None, None, event.button, event.time)

        # deposit for drag and drop until better way found to determine exact starting coordinates
        self._lastclick = (event.x, event.y)

    def _get_point_outputs(self, x, y):
        x, y = x * self.factor, y * self.factor
        outputs = set()
        for output_name, output in self._swayoutput.configuration.outputs.items():
            if not output.active:
                continue
            if (
                    output.position[0] - self.factor <= x <= output.position[0] + output.size[0] + self.factor
            ) and (
                output.position[1] - self.factor <= y <= output.position[1] + output.size[1] + self.factor
            ):
                outputs.add(output_name)
        return outputs

    def _get_point_active_output(self, x, y):
        undermouse = self._get_point_outputs(x, y)
        if not undermouse:
            raise IndexError("No output here.")
        active = [a for a in self.sequence if a in undermouse][-1]
        return active

    #################### context menu ####################

    def contextmenu(self):
        menu = Gtk.Menu()
        for output_name in self._swayoutput.outputs:
            output_config = self._swayoutput.configuration.outputs[output_name]
            output_state = self._swayoutput.state.outputs[output_name]

            i = Gtk.MenuItem(output_name)
            i.props.submenu = self._contextmenu(output_name)
            menu.add(i)

        menu.show_all()
        return menu

    def _contextmenu(self, output_name):  # pylint: disable=too-many-locals
        menu = Gtk.Menu()
        output_config = self._swayoutput.configuration.outputs[output_name]
        output_state = self._swayoutput.state.outputs[output_name]

        enabled = Gtk.CheckMenuItem(_("Active"))
        enabled.props.active = output_config.active
        enabled.connect('activate', lambda menuitem: self.set_active(
            output_name, menuitem.props.active))

        menu.add(enabled)

        if output_config.active:
            flipped = Gtk.CheckMenuItem(_("Flipped"))
            flipped.props.active = output_config.transform.flipped
            flipped.connect('activate', lambda menuitem: self.set_flipped(
                 output_name, menuitem.props.active))
            menu.add(flipped)

            blacked_out = Gtk.CheckMenuItem(_("Blacked out"))
            blacked_out.props.active = not output_config.dpms
            blacked_out.connect('activate', lambda menuitem: self.set_dpms(
                 output_name, not menuitem.props.active))
            menu.add(blacked_out)

            def _res_set(_menuitem, output_name, mode):
                try:
                    self.set_resolution(output_name, mode)
                except InadequateConfiguration as exc:
                    self.error_message(
                        _("Setting this resolution is not possible here: %s") % exc
                    )
            res_m = Gtk.Menu()
            for mode in output_state.modes:
                i = Gtk.CheckMenuItem(str(mode))
                i.props.draw_as_radio = True
                i.props.active = (output_config.mode == mode)

                i.connect('activate', _res_set, output_name, mode)
                res_m.add(i)

            def _rot_set(_menuitem, output_name, rotation):
                try:
                    self.set_rotation(output_name, rotation)
                except InadequateConfiguration as exc:
                    self.error_message(
                        _("This orientation is not possible here: %s") % exc
                    )
            or_m = Gtk.Menu()
            for rotation in output_state.rotations:
                i = Gtk.CheckMenuItem("%d" % rotation)
                i.props.draw_as_radio = True
                i.props.active = (output_config.rotation == rotation)

                i.connect('activate', _rot_set, output_name, rotation)
                if rotation not in output_state.rotations:
                    i.props.sensitive = False
                or_m.add(i)

            scale_values = [1,2,4,8]
            for scale in scale_values:
                if isclose(scale, output_config.scale):
                    break
            else:
                scale_values += [output_config.scale]
            scale_values.sort()

            def _scale_set(_menuitem, output_name, scale):
                try:
                    self.set_scale(output_name, scale)
                except InadequateConfiguration as exc:
                    self.error_message(
                        _("This scale is not possible here: %s") % exc
                    )

            def _scale_set_custom(_menuitem, output_name):
                dialog = Gtk.MessageDialog(None, Gtk.DialogFlags.MODAL, Gtk.MessageType.QUESTION, Gtk.ButtonsType.OK_CANCEL, _("New scaling for output %s" % output_name))
                dialog.set_title(_("Custom scale"))
                dialogBox = dialog.get_content_area()
                entry = Gtk.Entry()
                entry.set_size_request(100,0)
                dialogBox.pack_end(entry, False, False, 0)
                dialog.show_all()
                response = dialog.run()
                if response != Gtk.ResponseType.OK:
                    dialog.destroy()
                    return
                try:
                    scale = float(entry.get_text())
                except ValueError:
                    self.error_message(_("The entered scaling value is not acceptable"))
                    return
                finally:
                    dialog.destroy()
                _scale_set(_menuitem, output_name, scale)

            scale_m = Gtk.Menu()
            for scale in scale_values:
                i = Gtk.CheckMenuItem(str(scale))
                i.props.draw_as_radio = True
                i.props.active = isclose(output_config.scale, scale)
                i.connect('activate', _scale_set, output_name, scale)
                scale_m.add(i)
            i = Gtk.MenuItem(_("Custom"))
            i.connect('activate', _scale_set_custom, output_name)
            scale_m.add(i)

            res_i = Gtk.MenuItem(_("Resolution"))
            res_i.props.submenu = res_m
            or_i = Gtk.MenuItem(_("Orientation"))
            or_i.props.submenu = or_m
            scale_i = Gtk.MenuItem(_("Scale"))
            scale_i.props.submenu = scale_m

            menu.add(res_i)
            menu.add(or_i)
            menu.add(scale_i)

        menu.show_all()
        return menu

    #################### drag&drop ####################

    def setup_draganddrop(self):
        self.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK,
            [Gtk.TargetEntry.new('screenlayout-output',
                             Gtk.TargetFlags.SAME_WIDGET, 0)],
            Gdk.DragAction.PRIVATE
        )
        self.drag_dest_set(
            0,
            [Gtk.TargetEntry.new('screenlayout-output',
                             Gtk.TargetFlags.SAME_WIDGET, 0)],
            Gdk.DragAction.PRIVATE
        )

        self._draggingfrom = None
        self._draggingoutput = None
        self.connect('drag-begin', self._dragbegin_cb)
        self.connect('drag-motion', self._dragmotion_cb)
        self.connect('drag-drop', self._dragdrop_cb)
        self.connect('drag-end', self._dragend_cb)

        self._lastclick = (0, 0)

    def _dragbegin_cb(self, widget, context):
        try:
            output = self._get_point_active_output(*self._lastclick)
        except IndexError:
            # FIXME: abort?
            Gtk.drag_set_icon_stock(context, Gtk.STOCK_CANCEL, 10, 10)
            return

        self._draggingoutput = output
        self._draggingfrom = self._lastclick
        Gtk.drag_set_icon_stock(context, Gtk.STOCK_FULLSCREEN, 10, 10)

        self._draggingsnap = Snap(
            self._swayoutput.configuration.outputs[self._draggingoutput].size,
            self.factor * 5,
            [
                (other_output.position, other_output.size)
                for (k, other_output) in self._swayoutput.configuration.outputs.items()
                if k != self._draggingoutput and other_output.active
            ]
        )
        return True

    def _dragmotion_cb(self, widget, context, x, y, time):  # pylint: disable=too-many-arguments
        # if not 'screenlayout-output' in context.list_targets():  # from outside
            # return False
        if not self._draggingoutput:  # from void; should be already aborted
            return False

        Gdk.drag_status(context, Gdk.DragAction.MOVE, time)

        rel = x - self._draggingfrom[0], y - self._draggingfrom[1]

        oldpos = self._swayoutput.configuration.outputs[self._draggingoutput].position
        newpos = Position(
            (int(oldpos[0] + self.factor * rel[0]), int(oldpos[1] + self.factor * rel[1])))
        self._swayoutput.configuration.outputs[
            self._draggingoutput
        ].tentative_position = self._draggingsnap.suggest(newpos)
        self._force_repaint()

        return True

    def _dragdrop_cb(self, widget, context, x, y, time):  # pylint: disable=too-many-arguments
        if not self._draggingoutput:
            return

        try:
            self.set_position(
                self._draggingoutput,
                self._swayoutput.configuration.outputs[self._draggingoutput].tentative_position
            )
        except InadequateConfiguration:
            context.finish(False, False, time)
            # raise # snapping back to the original position should be enought feedback

        context.finish(True, False, time)

    def _dragend_cb(self, widget, context):
        try:
            del self._swayoutput.configuration.outputs[self._draggingoutput].tentative_position
        except (KeyError, AttributeError):
            pass  # already reloaded
        self._draggingoutput = None
        self._draggingfrom = None
        self._force_repaint()
