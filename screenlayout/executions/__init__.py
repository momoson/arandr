# ARandR -- Another XRandR GUI
# Copyright (C) 2008 -- 2012 chrysn <chrysn@fsfe.org>
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

"""Executions module

The execution module provides the infrastructure for running external programs
that don't need data from stdin as executions context.

This will likely go away when its users are refactored to use
CompletedProcess.check_returncode()."""

import warnings
import subprocess
from subprocess import CalledProcessError # explicitly imported so users don't have to import subprocess to catch exceptions

class ManagedExecution:
    # not context=contexts.local, because that would create a circular dependency between the modules
    def __init__(self, argv, context):
        self.process = context.run(argv)

        self.argv = argv # only needed for __str__ and __repr__, but very useful there

    def read_paranoid(self):
        """Report the process' result, and assume that not only the return code
        was 0, but also that stderr was empty."""

        self.process.check_returncode()
        if self.process.stderr:
            raise CalledProcessError(self.process.returncode, self, self.process.stdout, self.process.stderr)

        return self.process.stdout

    def read(self):
        # currently, this does hardly more than subprocess.check_output.
        """Report the process' result, and assume that the return code was 0.
        If something was printed to stderr, a warning is issued."""

        self.process.check_returncode()

        if self.process.stderr:
            warnings.warn("%s had output to stderr, but did not report an error (Message was: %r)"%(self, self.process.stderr))

        return self.process.stdout

    def read_with_error(self):
        return self.process.stdout, self.process.stderr, self.process.returncode

    def __str__(self):
        return "Process %r"%(self.argv,)

    def __repr__(self):
        return "<ManagedExecution of %r>"%self.argv
