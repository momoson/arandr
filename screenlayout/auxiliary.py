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

"""Exceptions and generic classes"""

# pylint: disable=fixme

from math import pi

class FileLoadError(Exception):
    pass


class FileSyntaxError(FileLoadError):
    """A file's syntax could not be parsed."""


class InadequateConfiguration(Exception):
    """A configuration is incompatible with the current state of X."""


class BetterList(list):
    """List that can be split like a string"""

    def indices(self, item):
        i = -1
        while True:
            try:
                i = self.index(item, i + 1)
            except ValueError:
                break
            yield i

    def split(self, item):
        indices = list(self.indices(item))
        yield self[:indices[0]]
        for x in (self[a + 1:b] for (a, b) in zip(indices[:-1], indices[1:])):
            yield x
        yield self[indices[-1] + 1:]

class Mode(tuple):
    """3-tuple of width and height and rate"""
    def __new__(cls, width, height, rate=None):
        return super(Mode, cls).__new__(cls, (width, height, rate/1000 if rate is not None else None))

    def __repr__(self):
        return "{}x{}".format(self[0], self[1]) + "@{}Hz".format(self[2]) if self[2] is not None else ""

    width = property(lambda self: self[0])
    heigth = property(lambda self: self[1])
    rate = property(lambda self: self[2])

class Size(tuple):
    """2-tuple of width and height that can be created from a '<width>x<height>' string"""
    def __new__(cls, arg):
        if isinstance(arg, str):
            arg = [int(x) for x in arg.split("x")]
        arg = tuple(arg)
        assert len(arg) == 2
        return super(Size, cls).__new__(cls, arg)

    width = property(lambda self: self[0])
    height = property(lambda self: self[1])

    def __str__(self):
        return "%dx%d" % self


class NamedSize:
    """Object that behaves like a size, but has an additional name attribute"""

    def __init__(self, size, name):
        self._size = size
        self.name = name

    width = property(lambda self: self[0])
    height = property(lambda self: self[1])

    def __str__(self):
        if "%dx%d" % (self.width, self.height) in self.name:
            return self.name
        return "%s (%dx%d)" % (self.name, self.width, self.height)

    def __iter__(self):
        return self._size.__iter__()

    def __getitem__(self, i):
        return self._size[i]

    def __len__(self):
        return 2


class Position(tuple):
    """2-tuple of left and top that can be created from a '<left>x<top>' string"""
    def __new__(cls, arg):
        if isinstance(arg, str):
            arg = [int(x) for x in arg.split("x")]
        arg = tuple(arg)
        assert len(arg) == 2
        return super(Position, cls).__new__(cls, arg)

    left = property(lambda self: self[0])
    top = property(lambda self: self[1])

    def __str__(self):
        return "%dx%d" % self


class Rect(tuple):
    """4-tuple of width, height, left and top that can be created from an XParseGeometry style string"""
    def __new__(cls, width, height, left, top):
        return super(Rect, cls).__new__(cls, (int(width), int(height), int(left), int(top)))

    def __str__(self):
        return "%dx%d+%d+%d" % self

    width = property(lambda self: self[0])
    height = property(lambda self: self[1])
    left = property(lambda self: self[2])
    top = property(lambda self: self[3])

    position = property(lambda self: Position(self[2:4]))
    size = property(lambda self: Size(self[0:2]))


class Transformation:
    """Class to represent the transformation of an output"""

    def __init__(self, transform_str):
        if "flipped" in transform_str:
            self.flipped = True
            rotation_str = transform_str.split('-')[-1]
        else:
            self.flipped = False
            rotation_str = transform_str
        try:
            self.rotation = Rotation(int(rotation_str))
        except ValueError:
            self.rotation = Rotation(0)

    def __repr__(self):
        representation = ""
        if self.flipped:
            representation += "flipped"
            if self.rotation != 0:
                representation += "-"
        if self.rotation != 0:
            representation += "{:d}".format(self.rotation)
        elif not self.flipped:
            representation = "normal"
        return representation

class Rotation(int):
    def __new__(cls, rotation_deg):
        value = round(rotation_deg/90)*90
        assert 0 <= value < 360
        return super(Rotation, cls).__new__(cls, value)

    @property
    def angle(self):
        return self/180*pi

    @property
    def is_odd(self):
        return self%180 != 0
