#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.

from __future__ import with_statement

import os
import stat
import subprocess

from myppy.envs import base

from myppy.recipes import linux as _linux_recipes


class MyppyEnv(base.MyppyEnv):

    DEPENDENCIES = ["bin_lsbsdk","patchelf"]
    DEPENDENCIES.extend(base.MyppyEnv.DEPENDENCIES)

    @property
    def CC(self):
        return "lsbcc -m32"

    @property
    def CXX(self):
        return "lsbc++ -m32"

    @property
    def LDFLAGS(self):
        flags = "-m32"
        for libdir in ("lib", "opt/lsb/lib"):
            flags += " -L" + os.path.join(self.PREFIX,libdir)
        return flags

    @property
    def CFLAGS(self):
        flags = "-Os -D_GNU_SOURCE -DNDEBUG -m32"
        for incdir in ("include", "opt/lsb/include"):
            flags += " -I" + os.path.join(self.PREFIX,incdir)
        return  flags

    @property
    def CXXFLAGS(self):
        flags = "-Os -D_GNU_SOURCE -DNDEBUG -m32"
        for incdir in ("include", "opt/lsb/include"):
            flags += " -I" + os.path.join(self.PREFIX,incdir)
        return  flags

    @property
    def LD_LIBRARY_PATH(self):
        return os.path.join(self.PREFIX,"lib")

    def __init__(self,rootdir):
        super(MyppyEnv,self).__init__(rootdir)
        if not os.path.exists(os.path.join(self.PREFIX,"lib")):
            os.makedirs(os.path.join(self.PREFIX,"lib"))
        self.env["CC"] = self.CC
        self.env["CXX"] = self.CXX
        self.env["LDFLAGS"] = self.LDFLAGS
        self.env["CFLAGS"] = self.CFLAGS
        self.env["CXXFLAGS"] = self.CXXFLAGS
        self._add_env_path("PATH",os.path.join(self.PREFIX,"opt/lsb/bin"),1)
        self._add_env_path("PKG_CONFIG_PATH",os.path.join(self.PREFIX,
                                                          "lib/pkgconfig"))
        self.env["LSBCC_LIBS"] = os.path.join(self.PREFIX,"opt/lsb/lib")
        self.env["LSBCC_INCLUDES"] = os.path.join(self.PREFIX,"opt/lsb/include")
        self.env["LSBCXX_INCLUDES"] = os.path.join(self.PREFIX,"opt/lsb/include")
        self.env["LSB_SHAREDLIBPATH"] = os.path.join(self.PREFIX,"lib")
        self.env["LSBCC_VERBOSE"] = os.path.join(self.PREFIX,"lib")

    def record_files(self,recipe,files):
        if recipe not in ("bin_lsbsdk",):
            for fpath in files:
                fpath = os.path.join(self.rootdir,fpath)
                fnm = os.path.basename(fpath)
                if fpath == os.path.realpath(fpath):
                    if fnm.endswith(".so") or ".so." in fnm:
                        self._check_glibc_symbols(fpath)
                        self._strip(fpath)
                        self._adjust_rpath(fpath)
                    elif "." not in fnm or os.access(fpath, os.X_OK):
                        fileinfo = self.bt("file",fpath)
                        if "executable" in fileinfo and "ELF" in fileinfo:
                            self._strip(fpath)
                            self._adjust_rpath(fpath)
                            self._adjust_interp_path(fpath)
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

    def _adjust_interp_path(self,fpath):
        #  Tweak executables so they use the normal linux loader, not
        #  the special lsb-specified one.  This trades lsb-compatability
        #  for ability to run out-of-the-box on more linuxen.
        if os.path.exists(os.path.join(self.PREFIX,"bin","patchelf")):
            try:
                interp = self.bt("patchelf", "--print-interpreter", fpath)
            except subprocess.CalledProcessError:
                raise
            else:
                if interp.strip() == "/lib/ld-lsb.so.3":
                    print "ADJUSTING INTERPRETER PATH", fpath
                    new_interp = "/lib/ld-linux.so.2"
                    self.do("patchelf", "--set-interpreter", new_interp, fpath)

    def load_recipe(self,recipe):
        return self._load_recipe_subclass(recipe,MyppyEnv,_linux_recipes)

