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

import warnings
from collections import namedtuple
import re
from functools import reduce
import binascii

from .constants import Rotation, Reflection, ModeFlag, SubpixelOrder, ConnectionStatus
from .. import executions
from ..executions.contextbuilder import build_default_context
from ..auxiliary import Size, Geometry, XRandRParseError
from ..polygon import ConvexPolygon

from .helpers import Mode, asciibytes, utf8bytes

class Server:
    def __init__(self, context=None, force_version=False):
        """Create proxy object and check for xrandr at the given
        executions.context. Fail with untested versions unless `force_version`
        is True."""

        self.context = context or build_default_context()

        self.version = self.Version(self._output_help(), self._output('--version'))

        if not force_version and not self.version.program_version.startswith(('1.2', '1.3', '1.4', '1.5')):
            raise Exception("XRandR 1.2 to 1.5 required.")

        self.load(self._output('--query', '--verbose'))

    #################### calling xrandr ####################

    def _output(self, *args):
        # FIXME: the exception thrown should already be beautiful enough to be presentable
        try:
            return executions.ManagedExecution(("xrandr",) + args, context=self.context).read()
        except executions.CalledProcessError as e:
            raise Exception("XRandR returned error code %d: %s"%(e.returncode, e.output))

    def _output_help(self):
        out, err, code = executions.ManagedExecution(("xrandr", "--help"), context=self.context).read_with_error()

        return (out + err)

    def apply(self, transition):
        """Execute the transition on the connected server. The server
        object is probably not recent after this and should be recreated."""

        self._output(*transition.serialize())

    #################### loading ####################

    def load(self, verbose_output):
        lines = verbose_output.split(b'\n')

        screenline = lines.pop(0)

        self._load_parse_screenline(screenline)

        output_blocks = []

        if lines.pop(-1) != b"":
            raise XRandRParseError("Output doesn't end with a newline.")

        self.outputs = {}
        self.modes = {}

        self.primary = None

        while lines:
            line = lines.pop(0)
            if line.startswith((b' ', b'\t')):
                raise XRandRParseError("Expected new output section, got whitespace.")

            headline = line
            details = []
            modes = []

            while lines and lines[0].startswith(b'\t'):
                details.append(lines.pop(0)[1:])

            while lines and lines[0].startswith(b' '):
                modes.append(lines.pop(0)[2:])

            # headline, details and modes filled; interpret the data before
            # going through this again

            primary = [] # hack to get the information about an output being primary out and set it later
            def setpri(): primary.append(True)
            output = self.Output(headline, details, setpri, self.version)
            if primary:
                self.primary = output
            self.outputs[output.name] = output

            self._load_modes(modes, output)

    def _load_parse_screenline(self, screenline):
        ssplit = screenline.split(b" ")

        ssplit_expect = [b"Screen",None,b"minimum",None,b"x",None,b"current",None,b"x",None,b"maximum",None,b"x",None]

        if not all(a==b for (a,b) in zip(ssplit,ssplit_expect) if b is not None):
            raise XRandRParseError("Unexpected screen line: %r"%screenline)

        # the screen number ssplit[1] is discarded

        self.virtual = self.Virtual(
                min=Size((int(ssplit[3]),int(ssplit[5][:-1]))),
                current=Size((int(ssplit[7]),int(ssplit[9][:-1]))),
                max=Size((int(ssplit[11]),int(ssplit[13])))
                )

    def _load_modes(self, data, assign_to_output=None):
        if len(data) % 3 != 0:
            raise XRandRParseError("Unknown mode line format (not a multiple of 3)")

        for lines in zip(data[0::3], data[1::3], data[2::3]):
            mode = self.ServerMode.parse_xrandr(lines)

            if mode.id in self.modes:
                if mode != self.modes[mode.id]:
                    raise XRandRParseError("Mode shows up twice with different data: %s"%mode.id)
                else:
                    mode = self.modes[mode.id]
            else:
                self.modes[mode.id] = mode

            if assign_to_output is not None:
                assign_to_output.assigned_modes.append(mode)

            if assign_to_output is not None and assign_to_output.active == True and assign_to_output.mode_number == None:
                # old xrandr version (< 1.2.2) workaround
                if mode.width == assign_to_output.geometry.width and mode.height == assign_to_output.geometry.height:
                    assign_to_output.mode_number = mode.id

    #################### sub objects ####################

    class Version:
        """Parser and representation of xrandr versions, handling both program
        and server version."""

        server_version = None
        program_version = None

        def __init__(self, help_string, version_string):
            SERVERVERSION_PREFIX = b'Server reports RandR version'
            PROGRAMVERSION_PREFIX = b'xrandr program version'

            lines = [l for l in version_string.split(b'\n') if l]

            for l in lines[:]:
                if l.startswith(SERVERVERSION_PREFIX):
                    self.server_version = asciibytes(l[len(SERVERVERSION_PREFIX):].strip())
                    lines.remove(l)
                if l.startswith(PROGRAMVERSION_PREFIX):
                    self.program_version = asciibytes(l[len(PROGRAMVERSION_PREFIX):].strip())
                    lines.remove(l)

            if lines:
                warnings.warn("XRandR version interpretation has leftover lines: %s"%lines)

            if self.server_version is None:
                raise XRandRParseError("XRandR did not report a server version.")

            if not self.program_version:
                # before 1.3.1, the program version was not reported. it can be
                # distinguished from older versions by the the presence of
                # --output flag in help.
                if b'--output' in help_string:
                    if b'--primary' in help_string:
                        self.program_version = '1.3.0' # or 1.2.99.x
                    else:
                        self.program_version = '1.2.x'
                else:
                    self.program_version = '< 1.2'

        def at_least_program_version(self, major, minor, patch=0):
            if major < 1:
                return True

            if major > 1:
                return False

            if minor < 3:
                raise ValueError("Can't check for that early version numbers for lack of implementation")

            if '<' in self.program_version or 'x' in self.program_version:
                return False

            parsed_version = tuple(map(int, self.program_version.split(".")))

            return (major, minor, patch) <= parsed_version

        def __repr__(self):
            return "<Version server %r, program %r>"%(self.server_version, self.program_version)

    Virtual = namedtuple("Virtual", ['min', 'current', 'max'])

    class ServerMode(Mode):
        XRANDR_EXPRESSIONS = [
                re.compile(b"^(?P<name>.+) +"
                    b"\(0x(?P<mode_id>[0-9a-fA-F]+)\) +"
                    b"(?P<pixelclock>[0-9]+\.[0-9]+)MHz"
                    b"(?P<flags>( ([+-][HVC]Sync|Interlace|DoubleScan|CSync))*)"
                    b"(?P<serverflags>( (\\*current|\\+preferred))*)"
                    b"(?P<garbage>.*)$"),
                re.compile(b"^      h:"
                    b" +width +(?P<hwidth>[0-9]+)"
                    b" +start +(?P<hstart>[0-9]+)"
                    b" +end +(?P<hend>[0-9]+)"
                    b" +total +(?P<htotal>[0-9]+)"
                    b" +skew +(?P<hskew>[0-9]+)"
                    b" +clock +(?P<hclock>[0-9]+\.[0-9]+)KHz"
                    b"$"),
                re.compile(b"^      v:"
                    b" +height +(?P<vheight>[0-9]+)"
                    b" +start +(?P<vstart>[0-9]+)"
                    b" +end +(?P<vend>[0-9]+)"
                    b" +total +(?P<vtotal>[0-9]+)"
                    b" +clock +(?P<vclock>[0-9]+\.[0-9]+)Hz"
                    b"$"),
                ]

        @classmethod
        def parse_xrandr(cls, lines):
            matches = [r.match(l) for (r, l) in zip(cls.XRANDR_EXPRESSIONS, lines)]
            if any(m is None for m in matches):
                raise XRandRParseError("Can not parse mode line %r"%lines[matches.index(None)])
            matchdata = reduce(lambda a, b: dict(a, **b), (m.groupdict() for m in matches))

            ret = cls(
                    float(matchdata['pixelclock']),
                    int(matchdata['hwidth']),
                    int(matchdata['hstart']),
                    int(matchdata['hend']),
                    int(matchdata['htotal']),
                    int(matchdata['vheight']),
                    int(matchdata['vstart']),
                    int(matchdata['vend']),
                    int(matchdata['vtotal']),
                    [ModeFlag(asciibytes(x)) for x in matchdata['flags'].split()],
                    )

            if matchdata['garbage']:
                warnings.warn("Unparsed part of line: %r"%matchdata['garbage'])

            ret.is_preferred = b'+preferred' in matchdata['serverflags']
            ret.is_current = b'*current' in matchdata['serverflags']

            ret.name = utf8bytes(matchdata['name'])
            ret.id = int(matchdata['mode_id'], 16)

            # not comparing hclock and vclock values, as they can be rather
            # much off (>1%) due to rounded values being displayed by xrandr. 
            #
            # skew is dropped because i have no idea what it is or what it does
            # in the modeline.

            return ret

        def __repr__(self):
            return "<%s %r (%#x) %s%s%s>"%(type(self).__name__, self.name, self.id, tuple.__repr__(self), " preferred" if self.is_preferred else "", " current" if self.is_current else "")

    class Output:
        """Parser and representation of an output of a Server"""

        def __init__(self, headline, details, primary_callback, version):
            self.assigned_modes = [] # filled with modes by the server parser, as it keeps track of the modes
            self.properties = {}

            self.version = version

            self._parse_headline(headline, primary_callback)
            self._parse_details(details)

        HEADLINE_EXPRESSION = re.compile(
                b"^(?P<name>.*) (?P<connection>connected|disconnected|unknown connection) "
                b"(?P<primary>primary )?"
                b"((?P<current_geometry>[0-9-+x]+)( \(0x(?P<current_mode>[0-9a-fA-F]+)\))? (?P<current_rotation>normal|left|inverted|right) ((?P<current_reflection>none|X axis|Y axis|X and Y axis) )?)?"
                b"\("
                b"(?P<supported_rotations>((normal|left|inverted|right) ?)*)"
                b"(?P<supported_reflections>((x axis|y axis) ?)*)"
                b"\)"
                b"( (?P<physical_x>[0-9]+)mm x (?P<physical_y>[0-9]+)mm)?"
                b"$")

        @property
        def mode(self):
            if self.mode_number is False:
                return False
            for m in self.assigned_modes:
                if m.id == self.mode_number:
                    return m
            raise ValueError("Output in an inconsistent state: active mode is not assigned")

        def _parse_headline(self, headline, primary_callback):
            headline_parsed = self.HEADLINE_EXPRESSION.match(headline)
            if headline_parsed is None:
                raise XRandRParseError("Unmatched headline: %r."%headline)
            headline_parsed = headline_parsed.groupdict()

            self.name = utf8bytes(headline_parsed['name'])
            # the values were already checked in the regexp
            self.connection_status = ConnectionStatus(asciibytes(headline_parsed['connection']))

            if headline_parsed['primary']:
                primary_callback()

            if headline_parsed['current_geometry']:
                self.active = True
                if headline_parsed['current_mode']:
                    self.mode_number = int(headline_parsed['current_mode'], 16)
                else:
                    # current_mode is only shown since xrandr 1.2.2; for everything before that, we have to guess because there was no '*current' either
                    warnings.warn("Old xrandr version (< 1.2.2), guessing current mode")
                    self.mode_number = None
                try:
                    self.geometry = Geometry(asciibytes(headline_parsed['current_geometry']))
                except ValueError:
                    raise XRandRParseError("Can not parse geometry %r"%headline_parsed['current_geometry'])

                # the values were already checked for in the regexp
                self.rotation = Rotation(asciibytes(headline_parsed['current_rotation']))
                # the values were already checked, and the values are aliases in the Reflection class
                self.reflection = Reflection(asciibytes(headline_parsed['current_reflection'] or b'noaxis'))
            else:
                self.active = False
                self.mode_number = None
                self.rotation = None
                self.reflection = None

            self.supported_rotations = tuple(Rotation(asciibytes(x)) for x in headline_parsed['supported_rotations'].split())
            self.supported_reflections = [Reflection.noaxis]
            if b'x axis' in headline_parsed['supported_reflections']:
                self.supported_reflections.append(Reflection.xaxis)
            if b'y axis' in headline_parsed['supported_reflections']:
                self.supported_reflections.append(Reflection.yaxis)
            if b'x axis' in headline_parsed['supported_reflections'] and b'y axis' in headline_parsed['supported_reflections']:
                self.supported_reflections.append(Reflection.xyaxis)

            if headline_parsed['physical_x'] is not None:
                self.physical_x = int(headline_parsed['physical_x'])
                self.physical_y = int(headline_parsed['physical_y'])
            else:
                self.physical_x = self.physical_y = None

        def _parse_details(self, details):
            while details:
                current_detail = [details.pop(0)]
                while details and details[0].startswith((b' ', b'\t')):
                    current_detail.append(details.pop(0))
                self._parse_detail(current_detail)

        def _parse_detail(self, detail):
            if b':' not in detail[0]:
                raise XRandRParseError("Detail doesn't contain a recognizable label: %r."%detail[0])
            label = asciibytes(detail[0][:detail[0].index(b':')]) # they are atoms on protocol side, should be ok for ascii

            detail[0] = detail[0][len(label)+1:]

            if label.lower() in self.simple_details:
                mechanism = self.simple_details[label.lower()]
                if not self.version.at_least_program_version(1, 3):
                    # Technically that's older versions than 1.2.1, but they
                    # don't announce patch levels yet, and are really old
                    # anyway
                    warnings.warn("Old xrandr version (< 1.3.0), ignoring some details")
                    detail = detail[:1]
                try:
                    data, = detail
                    data = data.strip()
                    if isinstance(mechanism, tuple) and not mechanism[0](asciibytes(data)):
                        raise ValueError()

                    setattr(self, label, mechanism[1](asciibytes(data)) if isinstance(mechanism, tuple) else mechanism(asciibytes(data)))
                except ValueError:
                    raise XRandRParseError("Can not evaluate detail %s."%label)

            elif label == 'Transform':
                pass # FIXME
            elif label == 'Panning':
                pass # FIXME
            elif label == 'Tracking':
                pass # FIXME
            elif label == 'Border':
                pass # FIXME

            else:
                if self.version.at_least_program_version(1, 4, 1):
                    self._parse_property_detail(label, detail)
                else:
                    warnings.warn("Old xrandr version (< 1.4.1), ignoring properties")

        def _parse_property_detail(self, label, detail):
            # FIXME what about type=XA_ATOM format=32? (They were special back
            # in the \t times)

            if label == 'EDID':
                # special-case, pick out binary data without choice
                try:
                    data = binascii.a2b_hex("".join(d.decode('ascii').strip() for d in detail))
                except ValueError:
                    warnings.warn("Unable to deserialize data in %s" % label)
                    return
                self.properties[label] = (data, None)
                return

            data = detail[0].strip()
            try:
                data = data.decode('utf8')
            except UnicodeDecodeError:
                warnings.warn("Encoding error in detail %r" % label)
                return
            changable = None

            # This 13-byte stuffed format has been used until <1.4.0; 1.4.0
            # output was broken, and 1.4.1 is comma-separated. As 1.4.1 was
            # released in 2013, it's reasonable to not support properties
            # in older version.

            if len(detail) > 1:
                supported_string = b'\tsupported:'
                range_string = b'\trange: ('
                range_end = b')'

                if detail[1].startswith(supported_string):
                    detail[1] = detail[1][len(supported_string):]
                    detail[2:] = [x.lstrip('\t') for x in detail[2:]]

                    alldetail = b", ".join(detail[1:])

                    try:
                        changable = [d.strip().decode('utf8') for d in alldetail.split(b", ")]
                    except UnicodeDecodeError:
                        warnings.warn("Encoding error in supported items of %r" % label)
                elif detail[1].startswith(range_string) and \
                        detail[1].endswith(range_end) and len(detail) == 2:
                    lowhigh = detail[1][len(range_string):-len(range_end)]

                    try:
                        low, _, high = lowhigh.decode('ascii').partition(', ')
                        low = int(low)
                        high = int(high)
                    except (UnicodeDecodeError, ValueError) as e:
                        warnings.warn("Failed to decode range in %r" % label)
                    else:
                        changable = range(low, high + 1)
                else:
                    warnings.warn("Unhandled data in detail %r"%label)

            self.properties[label] = (data, changable)


        # simple patterns for _parse_detail
        #
        # this is matched against lowercased identifiers by _parse_detail for
        # bulk details that don't require more clever thinking. if the first
        # lambda doesn't return true or either of them throws a ValueError, an
        # XRandRParseError is raised. the second expression's return value is
        # assigned to the output object under the key's name. if just a single
        # lambda, it acts like the second one.
        #
        # simple_details requires the properties to only contain ascii
        # characters; those are decoded to str before being passed.
        simple_details = {
                'identifier': (lambda data: data[:2] == '0x', lambda data: int(data[2:], 16)),
                'timestamp': int,
                'subpixel': SubpixelOrder,
                'gamma': (lambda data: data.count(':') == 2, lambda data: [float(x) for x in data.split(':')]),
                'brightness': float,
                'clones': str, # FIXME, which values does that take?
                'crtc': int,
                'crtcs': lambda data: [int(x) for x in data.split()],
                }

        @property
        def polygon(self):
            """Return the output area's outlining polygon."""

            # winding clock-wise, as we're in "pc coordinates" (right, down
            # instead of right, up), so clock-wise is the new positive
            # direction
            return ConvexPolygon([
                    self.geometry.position,
                    (self.geometry.position[0] + self.geometry.size[0], self.geometry.position[1]),
                    tuple(p+s for (p, s) in zip(self.geometry.position, self.geometry.size)),
                    (self.geometry.position[0], self.geometry.position[0] + self.geometry.size[1]),
                    ])
