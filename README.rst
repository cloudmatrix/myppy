

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


