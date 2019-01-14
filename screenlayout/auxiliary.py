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

from math import pi
from collections import namedtuple

class FileLoadError(Exception): pass
class FileSyntaxError(FileLoadError):
    """A file's syntax could not be parsed."""

class XRandRParseError(Exception):
    """The output of XRandR didn't fulfill the program's expectations"""

class InadequateConfiguration(Exception):
    """A configuration is incompatible with the current state of X."""


class Size(tuple):
    """2-tuple of width and height that can be created from a '<width>x<height>' string

    >>> s = Size("100x200")
    >>> s.width
    100
    >>> print(s)
    100x200
    """
    def __new__(cls, arg):
        if isinstance(arg, str):
            arg = [int(x) for x in arg.split("x")]
        arg = tuple(arg)
        if len(arg) != 2:
            raise ValueError("Sizes use XxY format")
        return super().__new__(cls, arg)

    width = property(lambda self:self[0])
    height = property(lambda self:self[1])
    def __str__(self):
        return "%dx%d"%self

class NamedSize:
    """Object that behaves like a size, but has an additional name attribute"""
    def __init__(self, size, name):
        self._size = size
        self.name = name

    width = property(lambda self:self[0])
    height = property(lambda self:self[1])
    def __str__(self):
        if "%dx%d"%(self.width, self.height) in self.name:
            return self.name
        else:
            return "%s (%dx%d)"%(self.name, self.width, self.height)

    def __iter__(self):
        return self._size.__iter__()

    def __getitem__(self, i):
        return self._size[i]

    def __len__(self):
        return 2

class Position(tuple):
    """2-tuple of left and top that can be created from a '<left>x<top>' string

    >>> p = Position("100x200")
    >>> p.left
    100
    >>> p.top
    200
    >>> print(p)
    100x200
    """
    def __new__(cls, arg):
        if isinstance(arg, str):
            arg = [int(x) for x in arg.split("x")]
        arg = tuple(arg)
        if len(arg) != 2:
            raise ValueError("Positions use XxY format")
        return super().__new__(cls, arg)

    left = property(lambda self:self[0])
    top = property(lambda self:self[1])
    def __str__(self):
        return "%dx%d"%self

class Geometry(namedtuple("_Geometry", ['left', 'top', 'width', 'height'])):
    """4-tuple of width, height, left and top that can be created from an XParseGeometry style string

    >>> g = Geometry(100, 200, 300, 400)
    >>> g.left
    100
    >>> g.top
    200
    >>> g.width, g.height
    (300, 400)
    >>> print(g)
    300x400+100+200
    """
    # FIXME: use XParseGeometry instead of an own incomplete implementation
    def __new__(cls, left, top=None, width=None, height=None):
        if isinstance(left, str):
            width,rest = left.split("x")
            height,left,top = rest.split("+")
        return super().__new__(cls, left=int(left), top=int(top), width=int(width), height=int(height))

    def __str__(self):
        return "%dx%d+%d+%d"%(self[2:4]+self[0:2])

    position = property(lambda self:Position(self[0:2]))
    size = property(lambda self:Size(self[2:4]))

class FlagClass(type):
    def __init__(self, name, bases, dict):
        super().__init__(name, bases, dict)

        if 'values' in dict: # guard agains error on Flag class
            self.values = [super(FlagClass, self).__call__(x) for x in dict['values']]

            for v in self.values:
                setattr(self, str.__str__(v), v)

    def __call__(self, label):
        if label in self.values:
            return self.values[self.values.index(label)]

        if hasattr(self, 'aliases') and label in self.aliases:
            return self(self.aliases[label])

        raise ValueError("No such %s flag: %r"%(self.__name__, label))

class Flag(str, metaclass=FlagClass):
    """Enum-style flag group

    >>> class Color(Flag):
    ...     values = ['green', 'purple']
    ...     aliases = {'violet': 'purple'}
    >>> Color('green') is Color.green
    True
    >>> Color('violet')
    <Color "purple">
    >>> Color('red')
    Traceback (most recent call last):
    ...
    ValueError: No such Color flag: 'red'
    """
    # TODO: replace with Python 3.4 Enums
    def __repr__(self):
        return '<%s "%s">'%(type(self).__name__, self)
