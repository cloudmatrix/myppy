#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  myppy.util:  misc utility functions for myppy

"""

from __future__ import with_statement

import os
import sys
import errno
import tempfile
import subprocess
import shutil
import hashlib
import contextlib
from fnmatch import fnmatch


class tempdir:
    """Context manager for creating auto-removed temp dirs.

    This is a simple context manager for creating temporary directories, that
    are automatically cleaned up when the context exists successfully.
    Use it like this:

        with tempdir() as mydir:
            ...do stuff with the temp dir...

    """

    def __init__(self,suffix="",prefix="",dir=None):
        self.suffix = suffix
        self.prefix = prefix
        self.dir = dir

    def __enter__(self):
        self.path = tempfile.mkdtemp(self.suffix,self.prefix,self.dir)
        return self.path

    def __exit__(self,exc_type,exc_value,traceback):
        if exc_type is None:
            for _ in xrange(5):
                try:
                    shutil.rmtree(self.path)
                    break
                except EnvironmentError:
                    pass
            else:
                shutil.rmtree(self.path)


def which(name):
    """Just like the "which" shell command."""
    paths = os.environ.get("PATH","/bin:/usr/bin:/usr/local/bin").split(":")
    for path in paths:
        if os.path.exists(os.path.join(path,name)):
            return os.path.join(path,name)
    return None



def md5file(path):
    """Calculate md5 of given file."""
    hash = hashlib.md5()
    with open(path,"rb") as f:
        chunk = f.read(1024*512)
        while chunk:
            hash.update(chunk)
            chunk = f.read(1024*512)
    return hash.hexdigest()


def do(*cmdline):
    """Execute the given command as a new subprocess."""
    subprocess.check_call(cmdline)


def bt(*cmdline):
    """Execute the command, returning stdout.

    "bt" is short for "backticks"; hopefully its use is obvious to shell
    scripters and the like.
    """
    p = subprocess.Popen(cmdline,stdout=subprocess.PIPE)
    output = p.stdout.read()
    retcode = p.wait()
    if retcode != 0:
        raise subprocess.CalledProcessError(retcode,cmdline)
    return output


@contextlib.contextmanager
def cd(newdir):
    """Context manager for temporarily changing working directory."""
    olddir = os.getcwd()
    os.chdir(newdir)
    try:
        yield
    finally:
        os.chdir(olddir)


def relpath(path):
    while path.startswith("/"):
        path = path[1:]
    return path


def prune_dir(path):
    """Remove a directory if it's empty."""
    try:
        os.rmdir(path)
    except EnvironmentError, e:
        if e.errno != errno.ENOTEMPTY:
            raise



