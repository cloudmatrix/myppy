#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.

from __future__ import with_statement

import os

from myppy.envs import base

from myppy.recipes import macosx as _macosx_recipes

class MyppyEnv(base.MyppyEnv):

    DB_NAME = os.path.join("Python.framework","myppy.db")

    TARGET_ARCHS = ["i386","ppc"]

    @property
    def PREFIX(self):
        return os.path.join(self.rootdir,"Python.framework","Versions","2.7")

    def __init__(self,rootdir):
        super(MyppyEnv,self).__init__(rootdir)
        self.env["CC"] = "/usr/bin/gcc-4.0"
        self.env["CXX"] = "/usr/bin/g++-4.0"
        self.env["MACOSX_DEPLOYMENT_TARGET"] = "10.4"

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
        for fpath in files:
            fpath = os.path.join(self.rootdir,fpath)
            fnm = os.path.basename(fpath)
            #  Verify that all dylibs are fat files
            if fnm.endswith(".a") or fnm.endswith(".dylib"):
                archs = self.bt("lipo","-info",fpath).strip()
                for arch in self.TARGET_ARCHS:
                   assert arch in archs, archs
        super(MyppyEnv,self).record_files(recipe,files)


