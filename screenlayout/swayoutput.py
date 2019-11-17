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
"""Wrapper around command line swaymsg"""
# pylint: disable=too-few-public-methods,wrong-import-position,missing-docstring,fixme

import os
import subprocess
import warnings
import json

from .auxiliary import (
    BetterList, Size, Position, Rect, Transformation, FileLoadError, FileSyntaxError, Mode,
    InadequateConfiguration, NamedSize, Rotation
)
from .i18n import _

SHELLSHEBANG = '#!/bin/sh'


class SwayOutput:
    DEFAULTTEMPLATE = [SHELLSHEBANG, '%(xrandr)s']

    configuration = None
    state = None

    def __init__(self, display=None):
        self.environ = dict(os.environ)
        if display:
            self.environ['DISPLAY'] = display

    def _get_outputs(self):
        assert self.state.outputs.keys() == self.configuration.outputs.keys()
        return self.state.outputs.keys()
    outputs = property(_get_outputs)

    #################### calling xrandr ####################

    def _output(self, *args):
        print('swaymsg is called with:')
        print(*args)
        proc = subprocess.Popen(
            ("swaymsg",) + args,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.environ
        )
        ret, err = proc.communicate()
        status = proc.wait()
        if status != 0:
            raise Exception("swaymsg returned error code %d: %s" %
                            (status, err))
        if err:
            warnings.warn(
                "swaymsg wrote to stderr, but did not report an error (Message was: %r)" % err)
        return ret.decode('utf-8')

    def _run(self, *args_sets):
        for args in args_sets:
            self._output(*args)

    #################### loading ####################

    def load_from_string(self, data):
        pass
        #data = data.replace("%", "%%")
        #lines = data.split("\n")
        #if lines[-1] == '':
        #    lines.pop()  # don't create empty last line

        #if lines[0] != SHELLSHEBANG:
        #    raise FileLoadError('Not a shell script.')

        #xrandrlines = [i for i, l in enumerate(
        #    lines) if l.strip().startswith('xrandr ')]
        #if not xrandrlines:
        #    raise FileLoadError('No recognized xrandr command in this shell script.')
        #if len(xrandrlines) > 1:
        #    raise FileLoadError('More than one xrandr line in this shell script.')
        #self._load_from_commandlineargs(lines[xrandrlines[0]].strip())
        #lines[xrandrlines[0]] = '%(xrandr)s'

        #return lines

    def _load_from_commandlineargs(self, commandline):
        pass
        #self.load_from_x()

        #args = BetterList(commandline.split(" "))
        #if args.pop(0) != 'xrandr':
        #    raise FileSyntaxError()
        ## first part is empty, exclude empty parts
        #options = dict((a[0], a[1:]) for a in args.split('--output') if a)

        #for output_name, output_argument in options.items():
        #    output = self.configuration.outputs[output_name]
        #    output_state = self.state.outputs[output_name]
        #    output.primary = False
        #    if output_argument == ['--off']:
        #        output.active = False
        #    else:
        #        if '--primary' in output_argument:
        #            if Feature.PRIMARY in self.features:
        #                output.primary = True
        #            output_argument.remove('--primary')
        #        if len(output_argument) % 2 != 0:
        #            raise FileSyntaxError()
        #        parts = [
        #            (output_argument[2 * i], output_argument[2 * i + 1])
        #            for i in range(len(output_argument) // 2)
        #        ]
        #        for part in parts:
        #            if part[0] == '--mode':
        #                for namedmode in output_state.modes:
        #                    if namedmode.name == part[1]:
        #                        output.mode = namedmode
        #                        break
        #                else:
        #                    raise FileLoadError("Not a known mode: %s" % part[1])
        #            elif part[0] == '--pos':
        #                output.position = Position(part[1])
        #            elif part[0] == '--rotate':
        #                if part[1] not in ROTATIONS:
        #                    raise FileSyntaxError()
        #                output.rotation = Rotation(part[1])
        #            else:
        #                raise FileSyntaxError()
        #        output.active = True

    def load_from_x(self):
        self.configuration = self.Configuration(self)
        self.state = self.State()

        output_dict = self._load_raw_lines()

        for output_el in output_dict:
            output = self.state.Output(output_el['name'])

            active = False
            if 'active' in output_el.keys():
                active = output_el['active']

            dpms = False
            if 'dpms' in output_el.keys():
                dpms = output_el['dpms']

            scale = 1.0
            if 'scale' in output_el.keys():
                scale = output_el['scale']

            subpixel_hinting = "unknown"
            if 'subpixel_hinting' in output_el.keys():
                subpixel_hinting = output_el['subpixel_hinting']

            if active:
                rect_dict = output_el['rect']
                rect = Rect(rect_dict['width'], rect_dict['height'], rect_dict['x'], rect_dict['y'])

                transform = Transformation(output_el['transform'])
            else:
                rect = None
                transform = None

            output.rotations = [Rotation(0), Rotation(90), Rotation(180), Rotation(270)]

            for mode_dict in output_el['modes']:
                mode = Mode(mode_dict['width'], mode_dict['height'], mode_dict['refresh'])

                for already_added_mode in output.modes:
                    if already_added_mode == mode:
                        break
                else: # add only if it is new
                    output.modes.append(mode)

            current_mode_dict = output_el['current_mode']
            current_mode = Mode(current_mode_dict['width'], current_mode_dict['height'], current_mode_dict['refresh'])

            self.state.outputs[output.name] = output
            self.configuration.outputs[output.name] = self.configuration.OutputConfiguration(
                active, dpms, scale, subpixel_hinting, rect, transform, current_mode
            )

    def _load_raw_lines(self):
        outputs = self._output("-t", "get_outputs", "-r")
        try:
            output_dict = json.loads(outputs)
        except json.decoder.JSONDecodeError:
            output_dict = {}
            raise Exception(
                "Output of swaymsg -t get_outputs -r not parsable as json"
            )
        return output_dict

    #################### saving ####################

    def save_to_shellscript_string(self, template=None, additional=None):
        """
        Return a shellscript that will set the current configuration.
        Output can be parsed by load_from_string.

        You may specify a template, which must contain a %(xrandr)s parameter
        and optionally others, which will be filled from the additional dictionary.
        """
        if not template:
            template = self.DEFAULTTEMPLATE
        template = '\n'.join(template) + '\n'

        data = {
            'xrandr': "xrandr " + " ".join(self.configuration.commandlineargs())
        }
        if additional:
            data.update(additional)

        return template % data

    def save_to_x(self):
        self.check_configuration()
        self._run(*self.configuration.commandlineargs())

    def check_configuration(self):
        for output_name in self.outputs:
            output_config = self.configuration.outputs[output_name]
            #output_state = self.state.outputs[output_name]

            if not output_config.active:
                continue

            # we trust users to know what they are doing
            # (e.g. widget: will accept current mode,
            # but not offer to change it lacking knowledge of alternatives)
            #
            # if output_config.rotation not in output_state.rotations:
            #    raise InadequateConfiguration("Rotation not allowed.")
            # if output_config.mode not in output_state.modes:
            #    raise InadequateConfiguration("Mode not allowed.")

    #################### sub objects ####################

    class State:
        """Represents everything that can not be set by swayoutput."""

        def __init__(self):
            self.outputs = {}

        def __repr__(self):
            return '<%s for %d Outputs>' % (
                type(self).__name__, len(self.outputs)
                )

        class Output:
            rotations = None

            def __init__(self, name):
                self.name = name
                self.modes = []

            def __repr__(self):
                return '<%s %r (%d modes)>' % (type(self).__name__, self.name, len(self.modes))

    class Configuration:
        """
        Represents everything that can be set by swayoutput
        (and is therefore subject to saving and loading from files)
        """

        def __init__(self, swayoutput):
            self.outputs = {}
            self._swayoutput = swayoutput

        def __repr__(self):
            return '<%s for %d Outputs, %d active>' % (
                type(self).__name__, len(self.outputs),
                len([x for x in self.outputs.values() if x.active])
            )

        def commandlineargs(self):
            args_sets = []
            for output_name, output in self.outputs.items():
                args = []
                args.append("output")
                args.append(output_name)
                if not output.active:
                    args.append("disable")
                else:
                    args.append("enable")

                    args.append("dpms")
                    args.append("on" if output.dpms else "off")

                    args.append("transform")
                    args.append(repr(output.transform))

                    if output.subpixel_hinting != 'unknown':
                        args.append("subpixel")
                        args.append(output.subpixel_hinting)

                    args.append("scale")
                    args.append(str(output.scale))

                    args.append("pos")
                    args.append(str(output.position.left))
                    args.append(str(output.position.top))

                    args.append("res")
                    args.append(repr(output.mode))
                args_sets.append(args)
            return args_sets

        class OutputConfiguration:

            def __init__(self, active, dpms, scale, subpixel_hinting, rect, transform, mode): # pylint: disable=too-many-arguments
                self.active = active
                self.dpms = dpms
                self.scale = scale
                self.subpixel_hinting = subpixel_hinting
                self.rect = rect
                self.transform = transform
                self.mode = mode

                if active:
                    self.position = rect.position
                    self.rotation = transform.rotation
                    self.size = rect.size
