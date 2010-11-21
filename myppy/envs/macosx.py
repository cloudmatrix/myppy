#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.

from __future__ import with_statement

import os

from myppy.envs import base

from myppy.recipes import macosx as _macosx_recipes

class MyppyEnv(base.MyppyEnv):

    DB_NAME = os.path.join("Contents","myppy.db")

    TARGET_ARCHS = ["i386","ppc"]

    @property
    def PREFIX(self):
        return os.path.join(self.rootdir,"Contents","Frameworks","Python.framework","Versions","2.7")

    @property
    def PYTHON_LIBRARY(self):
        return os.path.join(self.PREFIX,"lib","libpython2.7.dylib")

    def __init__(self,rootdir):
        super(MyppyEnv,self).__init__(rootdir)
        self.env["CC"] = "/usr/bin/gcc-4.0"
        self.env["CXX"] = "/usr/bin/g++-4.0"
        self.env["MACOSX_DEPLOYMENT_TARGET"] = "10.4"

    def init(self):
        super(MyppyEnv,self).init()
        appc = "Frameworks/Python.framework/Resources/Python.app/Contents"
        for nm in os.listdir(os.path.join(self.rootdir,"Contents",appc)):
            os.symlink(os.path.join(appc,nm),
                       os.path.join(self.rootdir,"Contents",nm))
        os.symlink("Contents/MacOS/Python",os.path.join(self.rootdir,"python"))

    def load_recipe(self,recipe):
        try:
            r = getattr(_macosx_recipes,recipe)
        except AttributeError:
            rbase = super(MyppyEnv,self).load_recipe(recipe).__class__
            rsuprnm = rbase.__bases__[0].__name__
            rsupr = self.load_recipe(rsuprnm).__class__
            class r(rbase,rsupr):
                pass
            r.__name__ = rbase.__name__
            r.__module__ = _macosx_recipes.__name__
            setattr(_macosx_recipes,recipe,r)
        return r(self)

    def record_files(self,recipe,files):
        #  Fix up linker paths for portability.
        #  Also guard against bad complication, e.g. linking with
        #  the wrong SDK or for the wrong archs.
        for fpath in files:
            fpath = os.path.join(self.rootdir,fpath)
            fnm = os.path.basename(fpath)
            if fnm.endswith(".a"):
                self._check_lib_has_all_archs(fpath)
            elif fnm.endswith(".dylib") or fnm.endswith(".so"):
                self._check_lib_has_all_archs(fpath)
                self._check_lib_uses_correct_sdk(fpath)
                self._adjust_linker_paths(fpath)
        super(MyppyEnv,self).record_files(recipe,files)

    def _check_lib_has_all_archs(self,fpath):
        archs = self.bt("lipo","-info",fpath).strip()
        for arch in self.TARGET_ARCHS:
           assert arch in archs, archs

    def _check_lib_uses_correct_sdk(self,fpath):
        links = self.bt("otool","-L",fpath).strip().split("\n")
        for link in links:
            if "libSystem.B.dylib" in link:
                assert "current version 88.3.11" in link,\
                       fpath + ": wrong SDK\n" + link

    def _adjust_linker_paths(self,fpath):
        links = self.bt("otool","-L",fpath).strip().split("\n")
        for link in links:
            if "compatibility version" not in link:
                continue
            deppath = link.split()[0]
            if deppath.startswith(self.rootdir):
                relpath = deppath[len(self.rootdir)+1:]
                if relpath.startswith("Contents/"):
                    newpath = "@executable_path/../" + relpath
                else:
                    newpath = "@executable_path/../../" + relpath
                self.do("install_name_tool","-change",deppath,newpath,fpath)
        

