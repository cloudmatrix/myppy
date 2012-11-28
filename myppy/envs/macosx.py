#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.

from __future__ import with_statement

import os
import stat
import subprocess
from textwrap import dedent

from myppy.envs import base

from myppy import util
from myppy.recipes import macosx as _macosx_recipes

class MyppyEnv(base.MyppyEnv):

    DB_NAME = os.path.join("Contents","myppy.db")

    TARGET_ARCHS = ["i386","x86_64"]

    MACOSX_SYSROOT = "/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX10.7.sdk"
    MACOSX_DEPLOYMENT_TARGET = "10.7"


    @property
    def PREFIX(self):
        return os.path.join(self.rootdir,"Contents","Frameworks","Python.framework","Versions","2.7")

    @property
    def PYTHON_LIBRARY(self):
        #return os.path.join(self.PREFIX,"lib","libpython2.7.dylib")
        return os.path.join(self.PREFIX,"Python")

    def __init__(self,rootdir):
        super(MyppyEnv,self).__init__(rootdir)
        self.env["CC"] = "/usr/bin/gcc"
        self.env["CXX"] = "/usr/bin/g++"
        self.env["MACOSX_DEPLOYMENT_TARGET"] = self.MACOSX_DEPLOYMENT_TARGET
        self.env["MACOSX_SYSROOT"] = self.MACOSX_SYSROOT

    def init(self):
        super(MyppyEnv,self).init()
        os.mkdir(os.path.join(self.rootdir,"Contents","MacOS"))
        os.symlink("../Frameworks/Python.framework/Versions/2.7/bin/python",os.path.join(self.rootdir,"Contents","MacOS","python"))
        os.symlink("Contents/Frameworks/Python.framework/Versions/2.7/bin/python",os.path.join(self.rootdir,"python"))
        os.symlink("Contents/Frameworks/Python.framework/Versions/2.7/bin/pythonw",os.path.join(self.rootdir,"pythonw"))
        with open(os.path.join(self.rootdir,"Contents","Info.plist"),"w") as f:
            with open(os.path.join(self.rootdir,"Contents","Frameworks","Python.framework","Resources","Python.app","Contents","Info.plist")) as fIn:
                info = fIn.read()
            info.replace("<string>Python</string>","<string>python</string>")
            f.write(info)
        os.symlink("Frameworks/Python.framework/Resources/Python.app/Contents/Resources",os.path.join(self.rootdir,"Contents","Resources"))

    def load_recipe(self,recipe):
        return self._load_recipe_subclass(recipe,MyppyEnv,_macosx_recipes)

    def record_files(self,recipe,files):
        #  Fix up linker paths for portability.
        #  Also guard against bad complication, e.g. linking with
        #  the wrong SDK or for the wrong archs.
        if recipe not in ("cmake,"):
            for fpath in files:
                fpath = os.path.join(self.rootdir,fpath)
                if os.path.islink(fpath):
                    continue
                fnm = os.path.basename(fpath)
                ext = fnm.rsplit(".",1)[-1]
                if ext == "a":
                    self._adjust_static_lib(recipe,fpath)
                elif ext in ("dylib","so",):
                    self._adjust_dynamic_lib(recipe,fpath)
                else:
                    try:
                        fdesc = self.bt("file",fpath) 
                    except subprocess.CalledProcessError:
                        # I've seen `file` choke on unexpected input.  Really.
                        fdesc = ""
                    if "Mach-O" in fdesc:
                        if "library" in fdesc:
                            self._adjust_dynamic_lib(recipe,fpath)
                        elif "executable" in fdesc:
                            self._adjust_executable(recipe,fpath)
        super(MyppyEnv,self).record_files(recipe,files)

    def _adjust_static_lib(self,recipe,fpath):
        self._check_lib_has_all_archs(fpath)

    def _adjust_dynamic_lib(self,recipe,fpath):
        mod = os.stat(fpath).st_mode
        os.chmod(fpath,mod | stat.S_IWUSR)
        self.do("strip","-S","-x",fpath)
        os.chmod(fpath,mod)
        self._check_lib_has_all_archs(fpath)
        self._check_lib_uses_correct_sdk(fpath)
        self._adjust_linker_paths(fpath)

    def _adjust_executable(self,recipe,fpath):
        self._check_lib_has_all_archs(fpath)
        if recipe not in ("py_py2app",):
            self._check_lib_uses_correct_sdk(fpath)
        self._adjust_linker_paths(fpath)

    def _check_lib_has_all_archs(self,fpath):
        print "CHECKING LIB ARCHS", fpath
        archs = self.bt("lipo","-info",fpath).strip()
        for arch in self.TARGET_ARCHS:
           #assert arch in archs, archs
           if arch not in archs:
                print "  WARNING: ", archs

    def _check_lib_uses_correct_sdk(self,fpath):
        print "CHECKING LIB SDK", fpath
        links = self.bt("otool","-L",fpath).strip().split("\n")
        for link in links:
            if "libSystem.B.dylib" in link:
                # This is ridiculous, I should just parse out the version
                # number and do a less-than check...
                ok_versions = ("159.1.0", "88.3.10", "88.3.11", "111.1.7",
                               "111.0.0")
                for ok_version in ok_versions:
                    if "current version " + ok_version in link:
                        break
                else:
                    assert False, fpath + ": wrong SDK\n" + link

    def _adjust_linker_paths(self,fpath):
        print "ADJUSTING LINKER PATHS", fpath
        if not os.path.isfile(fpath):
            return
        if os.path.realpath(fpath) != fpath:
            return
        loaderpath = os.path.dirname(fpath)
        links = self.bt("otool","-L",fpath).strip().split("\n")
        for link in links:
            if "compatibility version" not in link:
                continue
            deppath = link.strip().split()[0]
            if not os.path.isabs(deppath) and not deppath.startswith("@"):
                fulldeppath = os.path.join(self.PREFIX,"lib",deppath)
            else:
                fulldeppath = deppath
            if fulldeppath != fpath and fulldeppath.startswith(self.rootdir):
                relpath = util.relpath_from(loaderpath,fulldeppath)
                relpath = "@loader_path/" + relpath
                self.do("install_name_tool","-change",deppath,relpath,fpath)

