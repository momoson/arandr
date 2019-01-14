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

from . import base

class TransitionOutputForPrimary(base.BaseTransitionOutput):
    def serialize(self):
        if self.transition.primary is self:
            return ['--primary'] + super().serialize()
        else:
            return super().serialize()

    def unserialize(self, args):
        if 'primary' in args:
            if args.primary:
                self.transition.primary = self
            del args.primary

        super().unserialize(args)
class TransitionForPrimary(base.BaseTransition):
    def _initialize_empty(self):
        super()._initialize_empty()
        self.primary = None

    NO_PRIMARY = object()

    def serialize(self):
        if self.primary is self.NO_PRIMARY:
            return ['--noprimary'] + super().serialize()
        else:
            # if a primary output is explicitly set, it will be handled by the output serialization
            return super().serialize()

    def unserialize(self, args):
        if args.noprimary:
            self.primary = self.NO_PRIMARY
        del args.noprimary

        super().unserialize(args)

    def predict_server(self):
        super().predict_server()

        if self.primary == self.NO_PRIMARY:
            self.predicted_server.primary = None

        if self.primary not in (None, self.NO_PRIMARY):
            self.predicted_server.primary = self.predicted_server.outputs[self.primary.name]

    def freeze_state(self, level=base.FreezeLevel.ALL):
        super().freeze_state(level)

        if self.server.primary is not None:
            self.primary = self.outputs[self.server.primary.name]
        else:
            if self.server.version.at_least_program_version(1, 4):
                self.primary = self.NO_PRIMARY
            else:
                # earlier versions don't report a primary, so it's a safe default not to touch primary at all
                pass

    Output = TransitionOutputForPrimary
