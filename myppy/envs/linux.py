#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.

from __future__ import with_statement

import os
import stat

from myppy.envs import base

from myppy.recipes import linux as _linux_recipes


class MyppyEnv(base.MyppyEnv):

    DEPENDENCIES = ["apbuild","patchelf"]
    DEPENDENCIES.extend(base.MyppyEnv.DEPENDENCIES)

    def __init__(self,rootdir):
        super(MyppyEnv,self).__init__(rootdir)
        self.env["APBUILD_STATIC_LIBGCC"] = "1"
        self.env["AUTOPACKAGE_FRONTEND"] = "apkg-ttyfe"
        self.env["CC"] = "apgcc"
        self.env["CXX"] = "apg++"
        self._add_env_path("PKG_CONFIG_PATH",os.path.join(self.PREFIX,
                                                          "lib/pkgconfig"))

    _RECIPES_WITH_APGCC_PROBLEMS = ("apbuild_base","apbuild", "bin_lsbsdk",
                                    "lib_apiextractor",)
    def record_files(self,recipe,files):
        for fpath in files:
            fpath = os.path.join(self.rootdir,fpath)
            fnm = os.path.basename(fpath)
            if fpath == os.path.realpath(fpath):
                if recipe not in self._RECIPES_WITH_APGCC_PROBLEMS:
                    if fnm.endswith(".so") or ".so." in fnm:
                        self._check_glibc_symbols(fpath)
                        self._strip(fpath)
                        self._adjust_rpath(fpath)
                    elif "." not in fnm:
                        fileinfo = self.bt("file",fpath)
                        if "executable" in fileinfo and "ELF" in fileinfo:
                            self._strip(fpath)
                            self._adjust_rpath(fpath)
        super(MyppyEnv,self).record_files(recipe,files)

    def _strip(self,fpath):
        mod = os.stat(fpath).st_mode
        os.chmod(fpath,stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        self.do("strip",fpath)
        os.chmod(fpath,mod)

    def _check_glibc_symbols(self,fpath):
        print "VERIFYING GLIBC SYMBOLS", fpath
        errors = []
        for ln in self.bt("objdump","-T",fpath).split("\n"):
            for field in ln.split():
                if field.startswith("GLIBC_"):
                    ver = field.split("_",1)[1].split(".")
                    ver = map(int,ver)
                    if ver >= [2,4,]:
                        errors.append(ln.strip())
                elif field.startswith("GLIBCXX_"):
                    ver = field.split("_",1)[1].split(".")
                    ver = map(int,ver)
                    if ver > [3,4,7]:
                        errors.append(ln.strip())
        assert not errors, "\n".join(errors)

    def _adjust_rpath(self,fpath):
        #  patchelf might not be installed if we're just initialising the env.
        if os.path.exists(os.path.join(self.PREFIX,"bin","patchelf")):
            print "ADJUSTING RPATH", fpath
            backrefs = []
            froot = os.path.dirname(fpath)
            while froot != self.PREFIX:
                backrefs.append("..")
                froot = os.path.dirname(froot)
            rpath = "/".join(backrefs) + "/lib"
            rpath = "${ORIGIN}:${ORIGIN}/" + rpath
            self.do("patchelf","--set-rpath",rpath,fpath)

    def load_recipe(self,recipe):
        return self._load_recipe_subclass(recipe,MyppyEnv,_linux_recipes)

