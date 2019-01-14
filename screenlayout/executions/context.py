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

"""Execution contexts

This module provides context objects, which define where and how to run a
program.

Contexts do not expose the full functionality of subprocess.Popen, but only
have a .run() method that accepts args and env, and returns the unchecked
CompletedProcess.

Contexts can be as trivial as adding environment variables, but can
just as well redirect execution to another machine by means of SSH (Secure
Shell).
"""

import logging
import string
import functools
import sys
import zipfile
import subprocess
import os.path
import io
import re
import binascii
import shlex

from .. import executions

def _shell_unsplit(args):
    """Merge a list of arguments into a command line

    This is like an inverse of shlex.split, and more precisely tries to behave
    in such a way that

    >>> subprocess.Popen(args) # doctest:+SKIP

    is equivalent to

    >>> subprocess.Popen(_shell_unsplit(args), shell=True) # doctest:+SKIP

    . It only accepts strings as argument types.
    """
    return " ".join(shlex.quote(s) for s in args)

# helper for zipfile names
def b2a(data):
    return binascii.b2a_qp(data.encode('utf8')).decode('ascii').replace('=\n', '').replace('/', '=2F')

class Context:
    """Interface definition for contexts"""

    def run(self, args, env=None):
        raise NotImplementedError

    def close(self):
        pass

class Local(Context):
    def run(self, args, env=None):
        return subprocess.run(args, env=env, capture_output=True)

local = Local()

class StackingContext(Context):
    """Base class for contexts that delegate execution to an
    `underlying_context`"""
    def __init__(self, underlying_context=local):
        self.underlying_context = underlying_context

    def __repr__(self):
        return '<%s at %x atop %r>'%(type(self).__name__, id(self), self.underlying_context)

class WithEnvironment(StackingContext):
    """Enforces preset environment variables upon executions"""
    def __init__(self, preset_environment, underlying_context=local):
        self.preset_environment = preset_environment
        super().__init__(underlying_context)

    def run(self, args, env=None):
        if env is not None:
            env = dict(env, **self.preset_environment)
        else:
            env = self.preset_environment
        return self.underlying_context.run(args, env)

class WithXEnvironment(WithEnvironment):
    """Context that, upon execution of the first command, tries to autodetect a
    running X session and sets environment variables on the commands in a way
    that X11 progams can be executed.

    This is particularly useful atop a SSH connection; in that context, it is
    not SSH X forwarding that is used, but the programs will be both executed
    and displayed remotely."""

    def __init__(self, underlying_context=local):
        self.preset_environment = None
        StackingContext.__init__(self, underlying_context)

    def run(self, args, env=None):
        if self.preset_environment is None:
            self.determine_environment()

        return self.underlying_context.run(args)

    def determine_environment(self):
        # FIXME
        displays = executions.ManagedExecution('grep --no-filename --text --null-data "^DISPLAY=" /proc/*/environ 2>/dev/null |sort --zero-terminated --unique', shell=True, context=self.underlying_context).read().decode('ascii').split("\0")

        displays = (line.split('=', 1)[1] for line in displays if line)

        # the DISPLAY variable is sometimes set with and sometimes without
        # screennumber. according to X(7), the screen number defaults to 0, so
        # stripping it off should provide sufficient normalization.
        displays = set(d[:-2] if d.endswith('.0') else d for d in displays)

        if not displays:
            raise self.NoEnvironmentFound()
        if len(displays) != 1:
            raise self.AmbiguousEnvironmentFound()

        (display, ) = displays

        self.preset_environment = {'DISPLAY': display}

    class NoEnvironmentFound(Exception): "No usable X11 display was found."

    class AmbiguousEnvironmentFound(Exception): "More than one X11 display found. (And hinting not yet implemented.)"

class InDirectory(StackingContext):
    """Enforce a working directory setting"""
    def __init__(self, cwd, underlying_context=local):
        self.cwd = cwd
        super().__init__(underlying_context)

    def run(self, args, env=None):
        return self.underlying_context.run(["sh", "-c", "cd " + shlex.quote(self.cwd) + " && " + _shell_unsplit(args)], env)

class SSHContext(StackingContext):
    """Context that executes the process on another machine.

    Caveats:
        * The SSH context relies on the remote system to have a POSIX like
          shell.
        * Environment variables can only be set or explicitly unset; passing
          them will not automatically unset all others (unlike with
          subprocess.Popen)

    The implementation does not use SSH multiplexing, because if it is enabled
    and the context becomes the master, the call to .communicate() does not
    return until the multiplexing master closes down. This could possibly be
    worked around using better understanding of the processes involved. (After
    all, an SSH master session in a terminal terminates as well).
    """
    ssh_executable = '/usr/bin/ssh'

    def __init__(self, host, ssh_args=('-o', 'BatchMode=yes', '-o', 'ControlMaster=no'), underlying_context=local):
        self.host = host
        self.ssh_args = ssh_args
        super().__init__(underlying_context)

    def run(self, args, env=None):
        args = _shell_unsplit(args)

        if env:
            prefix_args = []
            for (k, v) in env.items():
                # definition as given in dash man page:
                #     Variables set by the user must have a name consisting solely
                #     of alphabetics, numerics, and underscores - the first of
                #     which must not be numeric.
                if k[0] in string.digits or any(_k not in string.ascii_letters + string.digits + '_' for _k in k):
                    raise ValueError("The environment variable %r can not be set over SSH."%k)

                prefix_args.append(shlex.quote(k) + '=' + shlex.quote(v) + ' ')
            args = "".join(prefix_args) + args

        return self.underlying_context.run((self.ssh_executable,) + self.ssh_args + (self.host, '--', args))

class SimpleLoggingContext(StackingContext):
    """Logs only command execution, no results"""
    def __init__(self, underlying_context=local, logmethod=logging.root.info):
        self.logmethod = logmethod
        super().__init__(underlying_context)

    def run(self, args, env=None):
        self.logmethod("Execution started: %r within environment %r on %r"%(args, env, self.underlying_context))
        return self.underlying_context.run(args, env)

class ZipfileLoggingContext(StackingContext):
    """Logs all executed commands into a ZIP file state machine. For a
    description of the ZIP file format, see the ZipfileContext
    documentation.

    If store_states is False, commands will be assumed not to modify any state
    at all (resulting in a flat ZIP file). Otherwise, states will be
    continuously numbered, and the ZIP file can only be replayed in the same
    sequence. More fine-grained control is possible by passing a next_state
    argument to the run method."""

    def __init__(self, zipfilename, store_states=True, underlying_context=local):
        self.zipfile = zipfile.ZipFile(zipfilename, 'w')
        self.store_states = store_states
        self.current_state = ""
        self._incrementing_state_number = 0
        super().__init__(underlying_context)

    def run(self, args, env=None, *, next_state=None):
        base_state = self.current_state
        if next_state is None:
            if self.store_states:
                self._incrementing_state_number += 1
                next_state = "%d/"%self._incrementing_state_number
            else:
                next_state = self.current_state
        self.current_state = next_state

        real_result = self.underlying_context.run(args)

        condensed_args = _shell_unsplit(args)

        self.store(
                condensed_args,
                real_result.stdout,
                real_result.stderr,
                real_result.returncode,
                base_state,
                next_state,
                )

        return real_result

    def store(self, args, stdout, stderr, returncode, base_state, next_state):
        name = base_state + b2a(args)

        self.zipfile.writestr(name + ".out", stdout)
        if stderr:
            self.zipfile.writestr(name + ".err", stderr)
        if returncode:
            self.zipfile.writestr(name + ".exit", str(returncode))
        if next_state != base_state:
            self.zipfile.writestr(name + ".state", next_state)

    def close(self):
        self.zipfile.close()

class ZipfileContext(Context):
    """Looks up cached command results from a ZIP file state machine.

    File format description
    =======================

    ZIP files for ZipfileContexts represent machine states and the results of
    stored commands that take no standard input.

    Command results (stdout, stderr, exit code, state machine transition) are
    stored as the contents of individual files in the ZIP file, discerned by
    their suffixes (.out, .err, .exit, .state). The command line is stored in
    the first part of the file name, shell-escaped and in quoted-printable
    encoding that additionally escapes slashes. (As shell escaping is not a
    normalization, it might happen that even though a command was stored in the
    ZIP file, it can not be looked up if it is escaped differently).

    It is required for a .out file to exist, even if it is empty, as it
    indicates that a result of the command was stored. All other files can be
    absent and default to empty, 0, and no state change, respectively.

    If a state is set in a ZipfileContext, all successive commands are prefixed
    with that state, typically in a directory-structure-like fashion (i.e.
    states end with slashes). States must be ASCII-only strings.

    Caveats:

    * No environment variables can be set.
    * It is up to the user to make sure the commands of
      different machine states don't clash, e.g. if you use an executable in a
      relative path, `bin/ls`, and want to use the systems's `ls` in a machine
      state you call `bin/`, you might be in trouble.
    """

    def __init__(self, zipfilename):
        self.state_prefix = ""
        self.zipfile = zipfile.ZipFile(zipfilename)

    def run(self, args, env=None):
        if env is not None:
            raise ValueError("The ZipfileContext file format does not allow environments")

        filename = _shell_unsplit(args)

        filename = self.state_prefix + b2a(filename)

        stdout = self.zipfile.open(filename + ".out").read()
        try:
            stderr = self.zipfile.open(filename + ".err").read()
        except KeyError:
            stderr = b""
        try:
            returncode = int(self.zipfile.open(filename + ".exit").read())
        except KeyError:
            returncode = 0
        try:
            self.state_prefix = self.zipfile.open(filename + ".state").read().decode('ascii')
        except KeyError:
            # as specified, no change happened
            pass

        return self.VirtualProcess(stdout, stderr, returncode)

    class VirtualProcess:
        """Similar to subprocess.CompletedProcess"""
        def __init__(self, stdout, stderr, returncode):
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

        def check_returncode(self):
            # just like CompleteProcess.check_returncode
            if self.returncode:
                raise subprocess.CalledProcessError(self.returncode, None,
                        self.stdout, self.stderr)
