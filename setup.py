
import sys
setup_kwds = {}
if sys.version_info > (3,):
    from setuptools import setup
    setup_kwds["test_suite"] = "myppy.tests.test_myppy"
    setup_kwds["use_2to3"] = True
else:
    from distutils.core import setup

#  This awfulness is all in aid of grabbing the version number out
#  of the source code, rather than having to repeat it here.  Basically,
#  we parse out all lines starting with "__version__" and execute them.
try:
    next = next
except NameError:
    def next(i):
        return i.next()
info = {}
try:
    src = open("myppy/__init__.py")
    lines = []
    ln = next(src)
    while "__ver" not in ln:
        lines.append(ln)
        ln = next(src)
    while "__ver" in ln:
        lines.append(ln)
        ln = next(src)
    exec("".join(lines),info)
except Exception:
    pass


NAME = "myppy"
VERSION = info["__version__"]
DESCRIPTION = "Make You a Portable Python"
AUTHOR = "Ryan Kelly"
AUTHOR_EMAIL = "rfk@cloudmatrix.com.au"
URL = "http://github.com/cloudmatrix/myppy/"
LICENSE = "BSD"
KEYWORDS = "portable"
LONG_DESC = info["__doc__"]

PACKAGES = ["myppy","myppy.tests","myppy.envs","myppy.recipes"]
SCRIPTS = ["scripts/myppy"]
EXT_MODULES = []
PKG_DATA = {}

setup(name=NAME,
      version=VERSION,
      author=AUTHOR,
      author_email=AUTHOR_EMAIL,
      url=URL,
      description=DESCRIPTION,
      long_description=LONG_DESC,
      keywords=KEYWORDS,
      packages=PACKAGES,
      scripts=SCRIPTS,
      ext_modules=EXT_MODULES,
      package_data=PKG_DATA,
      license=LICENSE,
      **setup_kwds
     )

