#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

myppy:  make you a portable python
==================================

 
Myppy is a set of tools for building and managing a portable python environment.
The end result is something similar in spirit to `portable python`_ but can
be built for a variety of different platforms.

Currently targeted build environments are linux-i686 and OSX.  When I work out
how to build on win32 without firing up Visual Studio, I'll add that as well.

The secret sauce is basically:

  * Using the `autopackage build tools`_ to hide newer glibc symbols on Linux,
    so that compiled libs can be used unmodified on older boxen.

  * Setting MACOSX_DEPLOYMENT_TARGET=10.4 and building universal binaries
    on OSX.

  * Setting the rpath or loader_path on all shared libs to a sensible value,
    so that their deps can be found regardless of where the myppy env is
    located.

Some things haven't quite been sorted out yet:

  * Scripts installed by easy_install and pip embed the absolute path to the
    interpreter in the shebang line; they should be replaced by a loader stub
    that finds python at runtime.

  * distutils and sysconfig embed the absolute library paths as they were at
    build time, meaning you can't properly build C-extensions if you move the
    environment around.  They should be patched in a simlar way to virtualenv.


Building a myppy environment
----------------------------

To build a myppy environment, you'll need some basic command-line build tools
and a recent version of gcc.  Initialise a new myppy env with the following
command::

    #> myppy PATH/TO/ENV init

This will build and set up a basic python installation (currently python 2.6.6)
along with setuptools and pip.  Most python packages can be installed directly
using pip.  For packages with more complex needs a myppy "recipe" is provided,
and you can install them using e.g.::

    #> myppy PATH/TO/ENV install py_wxpython

This would build and install a custom wxPython version that is patched to 
be more portable.


Using a myppy environment
-------------------------

In the top level of a myppy environment there are three shell scripts named
"python", "myppy" and "shell".   These set up some relevant environment vars
and then chainload the appropriate command.

Here's how you might get a shell inside a myppy envionment, then install a
third-party package using pip::

    #>
    #> PATH/TO/ENV/shell
    myppy(ENV):$
    myppy(ENV):$ pip install esky
    ...lots of output as esky is installed...
    myppy(ENV):$
    myppy(ENV):$ <ctrl-D>
    #>
    

What is it good for?
--------------------

Why, everything that something like `portable python`_ is good for, but on
Linux or OSX instead of Windows!  Use it as a convenient portable scripting or
testing environment, or to run multiple python versions side-by-side.

One thing it's particularly good for (actually, the reason it was created) is
building frozen Python apps.  Myppy comes with recipes for patched of cx-freeze
and py2app that will build stand-alone applications having the same portability
as the myppy env itself - meaning they should run anywhere from ancient Red Hat
distros to the latest Ubuntu release.

Myppy also has a few modifications that make it play nicely with other tools
for building frozen applications, such as `esky`_ and `signedimp`_, mostly to
do with what modules are avilable as builtins.



References
----------

.. _autopackage build tools:   http://autopackage.org/aptools.html

.. _portable python:   http://www.portablepython.com/

.. _esky:   http://pypi.python.org/pypi/esky/

.. _signedimp:   http://pypi.python.org/pypi/signedimp/


"""

__ver_major__ = 0
__ver_minor__ = 1
__ver_patch__ = 0
__ver_sub__ = ""
__ver_tuple__ = (__ver_major__,__ver_minor__,__ver_patch__,__ver_sub__)
__version__ = "%d.%d.%d%s" % __ver_tuple__


import sys
import subprocess

if sys.platform == "darwin":
    from myppy.envs.macosx import MyppyEnv
elif sys.platform == "linux2":
    from myppy.envs.linux import MyppyEnv
#elif sys.platform == "win32":
#    from myppy.envs.win32 import MyppyEnv
else:
    raise ImportError("myppy not available on platform %r" % (sys.platform,))



def main(argv):
    """Main function implementing myppy's command-line interface."""
    if len(argv) < 2:
        argv = argv + [".","help"]
    elif len(argv) < 3:
        argv = argv + ["help"]
    target = MyppyEnv(argv[1])
    cmd = argv[2]
    args = argv[3:]
    if cmd == "help":
        print ""
        print "myppy: make you a portable python"
        print ""
        print "usage:      myppy <rootdir> <cmd> <args>"
        print "commands:"
        maxcmdlen = max(len(cls.__name__) for cls in _cmd.__subclasses__())
        for cls in _cmd.__subclasses__():
            nm = cls.__name__[1:]
            padding = " " * (maxcmdlen - len(nm)) + " "
            print "           ", nm+":", padding, cls.__doc__
        return 0
    try:
        cmd = globals()["_"+cmd]
    except KeyError:
        print "Unknown command:", cmd
        return 1
    if not issubclass(cmd,_cmd) or cmd is _cmd:
        print "Unknown command:", cmd
        return 1
    res = cmd.run(target,args) or 0
    return res
         

class _cmd(object):
    """command base class - help string goes here."""
    @staticmethod
    def run(target,args):
        pass

class _init(_cmd):
    """initialise a new portable python env"""
    @staticmethod
    def run(target,args):
        assert not args
        target.init()

class _clean(_cmd):
    """clean out temporary files (e.g. build files)"""
    @staticmethod
    def run(target,args):
        assert not args
        target.clean()

class _install(_cmd):
    """install recipes into the env"""
    @staticmethod
    def run(target,args):
        for arg in args:
            target.load_recipe(arg)
        for arg in args:
            target.install(arg)

class _uninstall(_cmd):
    """uninstall recipes from the env"""
    @staticmethod
    def run(target,args):
        for arg in args:
            target.uninstall(arg)

class _shell(_cmd):
    """start an interactive shell inside env"""
    @staticmethod
    def run(target,args):
        assert not args
        try:
            target.do("sh",shell=True)
        except subprocess.CalledProcessError, e:
            return e.returncode

class _do(_cmd):
    """run a subprocess inside the env"""
    @staticmethod
    def run(target,args):
        assert args
        try:
            target.do(*args,shell=True)
        except subprocess.CalledProcessError, e:
            return e.returncode

class _record(_cmd):
    """record files installed by hand"""
    @staticmethod
    def run(target,args):
        (recipe,) = args
        files = target.find_new_files()
        target.record_files(recipe,files)


