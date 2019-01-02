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

import sys
import os
import tempfile
import subprocess
import unittest
import zipfile
import logging
import functools

from .. import executions
from ..executions import context
from ..modifying import modifying

def create_statemachine(outfilename="statemachine.zip"):
    """Manually creates a pre-defined ZIP file with a reasonably elaborate
    state machine.

    The state machine represents the outputs of `ls` on a file named
    `testfile`, and what happens when it gets created with `touch` and removed
    with `rm`."""

    f = zipfile.ZipFile(outfilename, "w")

    f.writestr("ls testfile.out", "")
    f.writestr("ls testfile.err", "ls: cannot access 'testfile': No such file or directory\n")
    f.writestr("ls testfile.exit", "2")
    f.writestr("exists/ls testfile.out", "testfile\n")

    f.writestr("rm testfile.out", "")
    f.writestr("rm testfile.exit", "1")
    f.writestr("rm testfile.err", "rm: cannot remove 'testfile': No such file or directory\n")
    f.writestr("exists/rm testfile.out", "")
    f.writestr("exists/rm testfile.state", "")

    f.writestr("touch testfile.out", "")
    f.writestr("touch testfile.state", "exists/")
    f.writestr("exists/touch testfile.out", "")

class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        # the ssh tests need an automatic setup to localhost anyway. if the
        # setup requires a password, but uses ControlMaster, this will set the
        # control master up.
        subprocess.check_call(['ssh', 'localhost', 'true'])

    def test_chainedWithEnvironment(self):
        env1 = context.WithEnvironment({'x': '42'})
        env2 = context.WithEnvironment({'y': '23'}, underlying_context=env1)

        job = executions.ManagedExecution(['env'], context=env2)
        self.assertEqual(sorted(job.read().strip().split(b'\n')), [b"x=42", b"y=23"])

    def test_ssh_escapes(self):
        # when running this, make sure ssh to localhost works
        to_localhost = context.SSHContext("localhost")

        both_contexts = [to_localhost, context.local]

        self.AssertEqualJobs(['uname', '-a'], context=both_contexts)

        self.AssertEqualJobs(['echo', '"spam"', 'egg\\spam'], context=both_contexts)
        self.AssertEqualJobs(['echo', b''.join(bytes([x]) for x in range(32, 256))], context=both_contexts)
        self.AssertEqualJobs('''echo "hello world!\\nthis is" 'fun', really''', shell=True, context=both_contexts)

        complex_shell_expression = '''for x in a b `echo c`; do sh -c "(echo \\\\$x) && echo 1"; done; echo $x'''
        self.AssertEqualJobs(complex_shell_expression, shell=True, context=both_contexts)
        self.AssertEqualJobs(['sh', '-c', complex_shell_expression], context=both_contexts)

    def test_ssh_environment(self):
        base_context = context.SimpleLoggingContext()

        just_set_env = context.WithEnvironment({"x": "23"}, underlying_context=base_context)
        locally_set_env = context.SSHContext("localhost", underlying_context=just_set_env)

        plain_localhost = context.SSHContext("localhost", underlying_context=base_context)
        remotely_set_env = context.WithEnvironment({"x": "23"}, underlying_context=plain_localhost)

        # variable will not be forwarded over the ssh connection
        self.AssertEqualJobs('echo x = $x', context=[plain_localhost, locally_set_env], shell=True)
        self.AssertEqualJobs('echo x = $x', context=[just_set_env, remotely_set_env], shell=True)

    def test_zipfile_crafted(self):
        testdir = tempfile.mkdtemp()
        filename = os.path.join(testdir, "statemachine.zip")

        create_statemachine(filename)

        zip_context = context.ZipfileContext(filename)
        in_tempdir = context.InDirectory(testdir)

        both_contexts = [zip_context, in_tempdir]

        backuped_lang = os.environ.pop("LANG", None)
        os.environ['LANG'] = 'C' # required for crafted zipfile

        self.AssertEqualJobs(['ls', 'testfile'], context=both_contexts, accept_errors=True)
        self.AssertEqualJobs('ls testfile', shell=True, context=both_contexts, accept_errors=True)

        self.AssertEqualJobs(['touch', 'testfile'], context=both_contexts, accept_errors=True)
        self.AssertEqualJobs(['touch', 'testfile'], context=both_contexts, accept_errors=True)
        self.AssertEqualJobs(['ls', 'testfile'], context=both_contexts, accept_errors=True)
        self.AssertEqualJobs(['rm', 'testfile'], context=both_contexts, accept_errors=True)
        self.AssertEqualJobs(['rm', 'testfile'], context=both_contexts, accept_errors=True)
        self.AssertEqualJobs(['ls', 'testfile'], context=both_contexts, accept_errors=True)

        if backuped_lang is None:
            del os.environ['LANG']
        else:
            os.environ['LANG'] = backuped_lang

        os.unlink(filename)
        os.rmdir(testdir)

    def test_zipfile_creating(self):
        testdir = tempfile.mkdtemp()
        filename = os.path.join(testdir, "persistence.zip")

        in_tempdir = context.InDirectory(testdir)
        zip_creating_context = context.ZipfileLoggingContext(filename, underlying_context=in_tempdir)

        def run_some_commands(runner):
            runner('''echo  "spam" eggs 'spam spam';''', shell=True)
            runner(['false'])
            runner('ls testfile', shell=True)
            runner(['touch', 'testfile'])
            runner('ls testfile', shell=True)
            # as everything here is happening in the tempdir, we gotta clean up again because we'll run this twice
            runner('rm testfile', shell=True)

        # let everything just run through, don't check outputs
        run_some_commands(modifying(executions.ManagedExecution)(lambda super: super(context=zip_creating_context).read_with_error()))

        zip_creating_context.close()

        zip_reading_context = context.ZipfileContext(filename)

        both_contexts = [zip_reading_context, in_tempdir]
        run_some_commands(functools.partial(self.AssertEqualJobs, context=both_contexts, accept_errors=True))

    @modifying(executions.ManagedExecution, hide=['accept_errors'])
    def AssertEqualJobs(self, super, context, accept_errors=False):
        results = []
        for c in context:
            process = super(context=c)
            if accept_errors:
                result = process.read_with_error()
            else:
                result = process.read()
            results.append(result)
        first = results[0]
        for c, r in zip(context, results):
            self.assertEqual(first, r, "Disparity between contexts %s and %s: %r != %r"%(context[0], c, first, r))


def main(verbose=False):
    """Run the test suite of the executions package"""
    if verbose:
        logging.root.setLevel(logging.DEBUG)
    logging.info("Starting test suite")
    unittest.main()

if __name__ == "__main__":
    main(verbose='--verbose' in sys.argv)
