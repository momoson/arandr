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


import os
import stat
import locale

from . import callbacks

from ..gtktools import Pango, PangoCairo, Gtk, GObject, Gdk

from ..xrandr.constants import ConnectionStatus
from ..xrandr.server import Server
from ..xrandr.transition import Transition, FreezeLevel
from ..snap import Snap
from ..executions.contextbuilder import build_default_context
from ..auxiliary import Geometry, Position, InadequateConfiguration, ModeCollectionByName

import gettext
gettext.install('arandr')

class TransitionWidget(Gtk.DrawingArea):
    __gsignals__ = {
            'changed':(GObject.SignalFlags.RUN_LAST, GObject.TYPE_NONE, ()),
            }

    def __init__(self, factor=8, context=None, force_version=False, detailscallback=None):
        super().__init__()

        self._detailscallback = detailscallback

        self.force_version = force_version
        self.context = context or build_default_context()

        self._factor = factor

        self.set_size_request(1024//self.factor, 1024//self.factor) # best guess for now

        self.connect('button-press-event', self.click)
        self.set_events(Gdk.EventMask.BUTTON_PRESS_MASK)

        self.connect('changed', lambda widget: self._transition.predict_server()) # has to be registered first, so the other handlers can rely on having a current predicted_server present
        self.connect('changed', lambda widget: self._force_repaint())

        self.setup_draganddrop()

        self._transition = None

    #################### widget features ####################

    def _set_factor(self, f):
        self._factor = f
        self._update_size_request()
        self._force_repaint()

    factor = property(lambda self: self._factor, _set_factor)

    def abort_if_unsafe(self):
        if not len([x for x in self._transition.outputs.values() if not x.off]):
            d = Gtk.MessageDialog(None, Gtk.DialogFlags.MODAL, Gtk.MessageType.WARNING, Gtk.BUTTONS_YES_NO, _("Your configuration does not include an active monitor. Do you want to apply the configuration?"))
            result = d.run()
            d.destroy()
            if result == Gtk.ResponseType.YES:
                return False
            else:
                return True
        return False

    def error_message(self, message):
            d = Gtk.MessageDialog(None, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.BUTTONS_CLOSE, message)
            d.run()
            d.destroy()

    def _update_size_request(self):
        max_gapless = sum(max(max(m.width, m.height) for m in o.assigned_modes) if o.assigned_modes else 0 for o in self._transition.server.outputs.values()) # this ignores that some outputs might not support rotation, but will always err at the side of caution.
        # have some buffer
        usable_size = int(max_gapless * 1.1)
        # don't request too large a window, but make sure every possible combination fits
        xdim = min(self._transition.server.virtual.max[0], usable_size)
        ydim = min(self._transition.server.virtual.max[1], usable_size)
        self.set_size_request(xdim//self.factor, ydim//self.factor)

    #################### loading ####################

    '''
    def load_from_file(self, file):
        data = open(file).read()
        template = self._xrandr.load_from_string(data)
        self._xrandr_was_reloaded()
        return template
    '''

    def load_from_x(self):
        server = Server(context=self.context, force_version=self.force_version)
        self._transition = Transition(server)
        self._transition.freeze_state(FreezeLevel.DEFAULT)
        self._xrandr_was_reloaded()


    def _xrandr_was_reloaded(self):
        self.sequence = sorted(self._transition.outputs.values(), key=lambda o: o.name)
        self._lastclick = (-1,-1)

        self._update_size_request()
        if self.get_window():
            self._force_repaint()
        self.emit('changed')

    def save_to_x(self):
        self._transition.server.apply(self._transition)
        # FIXME: it would be cleaner to keep the transition and re-bind it to a
        # new server. thus, changes that don't round-trip cleanly are
        # preserved. possibly don't rebind transition, but load from
        # serialization again
        self.load_from_x()

    def save_to_string(self):
        from shlex import quote as shell_quote

        return " ".join(map(shell_quote, self._transition.serialize()))

    '''
    def save_to_file(self, file, template=None, additional=None):
        data = self._xrandr.save_to_shellscript_string(template, additional)
        open(file, 'w').write(data)
        os.chmod(file, stat.S_IRWXU)
        self.load_from_file(file)
    '''

    #################### painting ####################

    def do_draw(self, cr):
        cr.scale(1/self.factor, 1/self.factor)
        cr.set_line_width(self.factor*1.5)

        self._draw(self._transition, cr)

    def _draw(self, transition, cr):
        cr.set_source_rgb(0.25,0.25,0.25)
        cr.rectangle(0,0,*transition.server.virtual.max)
        cr.fill()

        # for most painting related stuff, it is easier to just access a

        cr.set_source_rgb(0.5,0.5,0.5)
        cr.rectangle(0,0,*transition.predicted_server.virtual.current)
        cr.fill()

        for output_transition in self.sequence:
            predicted = output_transition.predicted_server_output
            if not predicted.active:
                continue

            rect = predicted.geometry # FIXME: a bit of a long shot; i doubt .geometry() will hold for long
            center = rect[0]+rect[2]/2, rect[1]+rect[3]/2

            # paint rectangle
            cr.set_source_rgba(1,1,1,0.7)
            cr.rectangle(*rect)
            cr.fill()
            if predicted is transition.predicted_server.primary:
                # FIXME: better visual
                cr.set_source_rgba(1,1,1,1)
                cr.rectangle(rect[0] + 0.3 * rect[2], rect[1] + 0.9 * rect[3], 0.4 * rect[2], 0.1 * rect[3])
                cr.fill()
                cr.rectangle(rect[0], rect[1], rect[2], 0.05 * rect[3])
                cr.fill()
            cr.set_source_rgb(0,0,0)
            cr.rectangle(*rect)
            cr.stroke()

            bigtext = predicted.name
            if output_transition.auto or (not output_transition.named_mode or output_transition.precise_mode):
                ## painted below the output name, must not be too long
                smalltext = _("actual size may vary")
            else:
                smalltext = None

            # set up for text -- FIXME: there gotta be a better way...
            textwidth = rect[3 if predicted.rotation.is_odd else 2]
            widthperchar = textwidth/len(bigtext)
            textheight = int(widthperchar * 0.8) # i think this looks nice and won't overflow even for wide fonts

            newdescr = Pango.FontDescription("sans")
            newdescr.set_size(textheight * Pango.SCALE)

            if smalltext:
                st_widthperchar = textwidth/len(smalltext)
                st_textheight = int(st_widthperchar * 0.8)
                st_descr = Pango.FontDescription("sans")
                st_descr.set_size(st_textheight * Pango.SCALE)

            # create text
            layout = PangoCairo.create_layout(cr)
            layout.set_font_description(newdescr)
            layout.set_text(bigtext, -1)

            # create small text
            if smalltext:
                st_layout = PangoCairo.create_layout(cr)
                st_layout.set_font_description(st_descr)
                st_layout.set_text(smalltext, -1)

            # position text
            layoutsize = layout.get_pixel_size()
            if smalltext:
                st_layoutsize = st_layout.get_pixel_size()
                layoutoffset = -layoutsize[0]/2, -layoutsize[1]/2 - st_layoutsize[1]/2
            else:
                layoutoffset = -layoutsize[0]/2, -layoutsize[1]/2
            cr.save()
            cr.move_to(*center)
            cr.rotate(predicted.rotation.angle)
            cr.rel_move_to(*layoutoffset)

            # paint text
            PangoCairo.show_layout(cr, layout)
            cr.restore()

            if smalltext:
                layoutoffset = -st_layoutsize[0]/2, layoutsize[1]/2 - st_layoutsize[1]/2
                cr.save()
                cr.move_to(*center)
                cr.rotate(predicted.rotation.angle)
                cr.rel_move_to(*layoutoffset)
                PangoCairo.show_layout(cr, st_layout)
                cr.restore()

    def _force_repaint(self):
        # using self.allocation as rect is offset by the menu bar.
        if self.get_window() is None:
            return # event received before window swas allocated

        r = Gdk.Rectangle()
        r.width = self._transition.server.virtual.max[0]//self.factor
        r.height = self._transition.server.virtual.max[1]//self.factor
        self.get_window().invalidate_rect(r, False)
        # this has the side effect of not painting out of the available region on drag and drop

    #################### click handling ####################

    def click(self, widget, event):
        undermouse = self._get_point_outputs(event.x, event.y)
        if undermouse:
            target = self._get_point_active_output(event.x, event.y)
        if event.button == 1 and undermouse:
            old_sequence = self.sequence[:]
            if self._lastclick == (event.x, event.y): # this was the second click to that stack
                # push the highest of the undermouse windows below the lowest
                newpos = min(self.sequence.index(a) for a in undermouse)
                self.sequence.remove(target)
                self.sequence.insert(newpos,target)
                # sequence changed
                target = self._get_point_active_output(event.x, event.y)
            # pull the clicked window to the absolute top
            self.sequence.remove(target)
            self.sequence.append(target)

            if old_sequence != self.sequence:
                self._force_repaint()
        if event.button == Gdk.BUTTON_SECONDARY:
            m = self.get_contextmenu(undermouse)
            # Keep the menu item alive as a Python object to keep its children
            # alive; see _contextmenu_items_for_outputs
            self._last_menu_item = m
            m.popup_at_pointer(event)

        self._lastclick = (event.x, event.y)

    def _get_point_outputs(self, x, y):
        x,y = x*self.factor, y*self.factor
        outputs = set()
        for output in self._transition.outputs.values():
            if not output.predicted_server_output.active:
                continue
            poly = output.predicted_server_output.polygon
            if poly.point_distance(x, y) < 2*self.factor: # 2 pixels margin of error
                outputs.add(output)
        return outputs

    def _get_point_active_output(self, x, y):
        undermouse = self._get_point_outputs(x, y)
        if not undermouse: raise IndexError("No output here.")
        active = [a for a in self.sequence if a in undermouse][-1]
        return active

    #################### context menu ####################

    def get_contextmenu(self, outputs=()):
        """Note that due to Gtk menu retainment rules, the caller may need to
        keep the returned object around"""

        if len(outputs) == 1:
            output, = outputs
            return self._contextmenu_for_output(output)

        else:
            return self._contextmenu_items_for_outputs(outputs)

    def _contextmenu_items_for_outputs(self, outputs=None):
        """Clear a menu of all its children, then build menu items into it for all given outputs"""

        menu = Gtk.Menu()

        if not outputs:
            outputs = self._transition.outputs.values()

        # GTK does not keep menu items alive just because they are children of
        # another menu; keeping them close as children to ensure they outlive
        # the menu.
        menu._python_kept_children = []

        for output in sorted(
                outputs,
                key=lambda o: locale.strxfrm(o.name)
                ):
            child = self._contextmenu_item_for_output(output)
            menu._python_kept_children.append(child)
            menu.append(child)

        menu.show_all()

        return menu

    def _contextmenu_item_for_output(self, output):
        item = Gtk.MenuItem(label=output.name)
        item.props.submenu = self._contextmenu_for_output(output)

        if output.server_output.connection_status != ConnectionStatus.connected:
            item.props.sensitive = False

        return item

    def _contextmenu_for_output(self, output):
        m = Gtk.Menu()

        enabled = Gtk.CheckMenuItem.new_with_mnemonic(_("_Active"))
        enabled.props.active = output.named_mode or output.precise_mode
        enabled.connect('activate', callbacks.set_active(lambda: output, self))
        m.append(enabled)

        primary = Gtk.CheckMenuItem.new_with_mnemonic(_("_Primary"))
        primary.props.active = output.transition.primary is output
        primary.connect('activate', callbacks.set_primary(lambda: output, self))
        m.append(primary)

        resolution_menu = Gtk.Menu()
        for mode in ModeCollectionByName.list_from_modes(output.server_output.assigned_modes):
            # FIXME: can we use thge model from from the output widgets?
            label = mode.name
            if mode.is_preferred:
                label += " \N{BLACK STAR}"
            i = Gtk.CheckMenuItem(label=label)
            i.props.draw_as_radio = True
            i.props.active = output.predicted_server_output.mode in mode.modes
            def _res_set(menuitem, modename=mode.name):
                try:
                    output.named_mode = modename
                except InadequateConfiguration as e:
                    self.error_message(_("Setting this resolution is not possible here: %s")%e.message)
                finally:
                    self.emit('changed')
            i.connect('activate', _res_set)
            resolution_menu.add(i)

        '''
            or_m = Gtk.Menu()
            for r in ROTATIONS:
                i = Gtk.CheckMenuItem("%s"%r)
                i.props.draw_as_radio = True
                i.props.active = (oc.rotation == r)
                def _rot_set(menuitem, on, r):
                    try:
                        self.set_rotation(on, r)
                    except InadequateConfiguration as e:
                        self.error_message(_("This orientation is not possible here: %s")%e.message)
                i.connect('activate', _rot_set, on, r)
                if r not in os.rotations:
                    i.props.sensitive = False
                or_m.add(i)

            res_i = Gtk.MenuItem(_("Resolution"))
            res_i.props.submenu = res_m
            or_i = Gtk.MenuItem(_("Orientation"))
            or_i.props.submenu = or_m
        '''

        orientation_menu = Gtk.Menu()

        m.append(Gtk.MenuItem(
            label=_("Resolution"),
            submenu=resolution_menu,
            ))
        m.append(Gtk.MenuItem(
            label=_("Orientation"),
            submenu=orientation_menu,
            ))

        if self._detailscallback:
            details = Gtk.MenuItem.new_with_mnemonic(_("_Details..."))
            details.connect('activate', lambda widget: self._detailscallback(output.name))
            m.append(details)

        m.show_all()
        return m

    #################### drag&drop ####################

    def setup_draganddrop(self):
        self.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, [Gtk.TargetEntry.new('screenlayout-output', Gtk.TargetFlags.SAME_WIDGET, 0)], Gdk.DragAction.PRIVATE)
        self.drag_dest_set(0, [Gtk.TargetEntry.new('screenlayout-output', Gtk.TargetFlags.SAME_WIDGET, 0)], Gdk.DragAction.PRIVATE)

        self._draggingfrom = None
        self._draggingfrom_pos = None
        self._draggingoutput = None
        self.connect('drag-begin', self._dragbegin_cb)
        self.connect('drag-motion', self._dragmotion_cb)
        self.connect('drag-drop', self._dragdrop_cb)
        self.connect('drag-end', self._dragend_cb)

        self._lastclick = (0,0)

    def _dragbegin_cb(self, widget, context):
        try:
            output = self._get_point_active_output(*self._lastclick)
        except IndexError:
            from gi.repository import GLib
            # Still setting an icon because it flickers up
            self.drag_source_set_icon_name('gtk-cancel')
            # The cancellation would leave a floating window around if done in
            # the begin handler
            GLib.idle_add(lambda:
                context.emit('cancel', Gdk.DragCancelReason.ERROR)
                )
            return True

        self._draggingoutput = output
        self._draggingfrom = self._lastclick
        self._draggingfrom_pos = output.position or output.predicted_server_output.geometry.position
        self.drag_source_set_icon_name('gtk-fullscreen')

        self._transition.predict_server()

        self._draggingsnap = Snap(
                output.predicted_server_output.geometry.size,
                self.factor*5,
                [Geometry(0, 0, *self._transition.predicted_server.virtual.max)]+[
                    o.geometry for o in self._transition.predicted_server.outputs.values() if o.name!=self._draggingoutput.name and o.active
                ]
            )

    def _dragmotion_cb(self, widget, context,  x, y, time):
        if not 'screenlayout-output' in [x.name() for x in context.list_targets()]: # from outside
            return False
        if not self._draggingoutput: # from void; should be already aborted
            return False

        # needs to be set every time to keep sending the movements!
        Gdk.drag_status(context, Gdk.DragAction.MOVE, time)

        rel = x-self._draggingfrom[0], y-self._draggingfrom[1]

        newpos = Position((self._draggingfrom_pos[0]+self.factor*rel[0], self._draggingfrom_pos[1]+self.factor*rel[1]))
        self._draggingoutput.position = self._draggingsnap.suggest(newpos)
        # in this very particular case, we're really calling the output's
        # predict function. thus, no new objects or stuff are created, but we
        # only update the predicted state on top of the current prediction.
        # this is ok because there is only one thing we change, and we always
        # change it (position).
        self._draggingoutput.predict_server()
        self._force_repaint()

        return True

    def _dragdrop_cb(self, widget, context, x, y, time):
        if not self._draggingoutput:
            return

        # shove output in. shoving around will always work, so unconditionally:
        self._transition.shove_to_fit()
        self.emit('changed')
        context.finish(True, False, time)

    def _dragend_cb(self, widget, context):
        self._draggingoutput = None
        self._draggingfrom = None
        self._draggingfrom_pos = None
