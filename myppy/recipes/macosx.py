#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.

from __future__ import with_statement

import os
import re
import sys
import tempfile
import urlparse
import urllib2
import subprocess
import shutil

from myppy.util import md5file, do, bt, cd, relpath, tempdir

from myppy.recipes import base


class Recipe(base.Recipe):

    TARGET_ARCHS = ["i386","ppc"]
    ISYSROOT = "/Developer/SDKs/MacOSX10.4u.sdk"

    @property
    def CC(self):
        return "/usr/bin/gcc-4.0"

    @property
    def CXX(self):
        return "/usr/bin/g++-4.0"

    @property
    def LOCAL_ARCH(self):
        return self.target.bt("/usr/bin/arch").strip()

    @property
    def LDFLAGS(self):
        return "-L" + os.path.join(self.target.PREFIX,"lib")

    @property
    def INCFLAGS(self):
        return "-I" + os.path.join(self.target.PREFIX,"include")

    @property
    def CFLAGS(self):
        archflags = " ".join("-arch "+arch for arch in self.TARGET_ARCHS)
        return "%s %s -mmacosx-version-min=10.4 -isysroot %s" % (archflags,self.INCFLAGS,self.ISYSROOT,))

    @property
    def CXXFLAGS(self):
        archflags = " ".join("-arch "+arch for arch in self.TARGET_ARCHS)
        return "%s %s -mmacosx-version-min=10.4 -isysroot %s" % (archflags,self.INCFLAGS,self.ISYSROOT,))

    @property
    def CONFIGURE_VARS(self):
        return ["CC="+self.CC,
                "CXX="+self.CXX,
                "LDFLAGS="+self.LDFLAGS,
                "CFLAGS="+self.CFLAGS,
                "CXXFLAGS="+self.CXXFLAGS,]
    @property
    def MAKE_VARS(self):
        return ["CC="+self.CC,"CXX="+self.CXX,"CFLAGS="+self.CFLAGS]

    @property
    def DYLB_FALLBACK_LIBRARY_PATH(self):
        return os.path.join(self.target.PREFIX,"lib")

    def _generic_configure(self,script=None,vars=None,args=None,env={}):
        if vars is None and self.CONFIGURE_VARS is None:
            env = env.copy()
            env.setdefault("LDFLAGS",self.LDFLAGS)
            env.setdefault("CFLAGS",self.CFLAGS)
            env.setdefault("CXXFLAGS",self.CXXFLAGS)
        super(Recipe,self)._generic_configure(script,vars,args,env)

    def _generic_make(self,vars=None,relpath=None,env={}):
        """Do a generic "make" for this recipe."""
        env = env.copy()
        env.setdefault("DYLD_FALLBACK_LIBRARY_PATH",self.DYLD_FALLBACK_LIBRARY_PATH)
        super(Recipe,self)._generic_make(vars,relpath,env)

    def _generic_makeinstall(self,vars=None,relpath=None,env={}):
        """Do a generic "make" for this recipe."""
        env = env.copy()
        env.setdefault("DYLD_FALLBACK_LIBRARY_PATH",self.DYLD_FALLBACK_LIBRARY_PATH)
        super(Recipe,self)._generic_make(vars,relpath,env)

    def _get_builddir(self,src):
        """Get the directory in which we build the given tarball.

        This is always <PREFIX>/tmp/build/<tarballname>/<srcdirname>/
        """
        src = self.SOURCE_URL
        workdir = os.path.join(self.target.builddir,os.path.basename(src))
        for nm in os.listdir(workdir):
            if nm in self.TARGET_ARCHS:
                continue
            if nm in ("fat",):
                continue
            return os.path.join(workdir,nm)
        raise RuntimeError("no build dir")


class NWayRecipe(Recipe):

    @property
    def CC(self):
        return "/usr/bin/gcc-4.0 -mmacosx-version-min=10.4 -arch %s -isysroot %s" % (self.TARGET_ARCH,self.ISYSROOT,))

    @property
    def CXX(self):
        return "/usr/bin/g++-4.0 -mmacosx-version-min=10.4 -arch %s -isysroot %s" % (self.TARGET_ARCH,self.ISYSROOT,))

    @property
    def CFLAGS(self):
        return self.INCFLAGS

    @property
    def CXXFLAGS(self):
        return self.INCFLAGS

    def _configure(self):
        self._nway_configure()

    def _make(self):
        self._nway_make()
        self._nway_merge()

    def _nway_configure(self,script=None,vars=None,args=None,env={}):
        """Do a "./configure" for each architecure in a separate dir."""
        workdir = self._get_builddir()
        #  Create work dir for each additional arch.
        archdirs = []
        for arch in self.TARGET_ARCHS:
            if arch == self.LOCAL_ARCH:
                archdirs.append((arch,workdir))
            else:
                archdir = os.path.join(os.path.dirname(workdir),arch)
                if os.path.exists(archdir):
                    shutil.rmtree(archdir)
                shutil.copytree(workdir,archdir)
                archdirs.append((arch,archdir))
        #  Now run the appropriate ./configure in each arch dir.
        for (arch,archdir) in archdirs:
            if os.path.exists(os.path.join(archdir,"Makefile")):
                with cd(archdir):
                    self.target.do("make","clean")
            self.TARGET_ARCH = arch
            self.CONFIGURE_DIR = archdir
            self._generic_configure(script,vars,args,env)
        self.TARGET_ARCH = None

    def _nway_make(self,vars=[],relpath=""):
        """Do a generic "make" separate for each architecture."""
        workdir = self._get_builddir()
        for arch in self.TARGET_ARCHS:
            if arch == self.LOCAL_ARCH:
                archdir = workdir
            else:
                archdir = os.path.join(os.path.dirname(workdir),arch)
            self.TARGET_ARCH = arch
            nway_relpath = os.path.join(workdir,archdir)
            self._generic_make(vars,nway_relpath)

    def _nway_merge(self,src,relpath="."):
        """Merge separately-compiled archs into fat binaries."""
        workdir = self._get_builddir()
        #  Create the fat binaries in a separate dir
        fatdir = os.path.join(os.path.dirname(workdir),"fat")
        for (dirnm,_,filenms) in os.walk(os.path.join(workdir,relpath)):
            for nm in filenms:
                filepath = os.path.join(dirnm,nm)
                ext = nm.rsplit(".",1)[-1]
                if ext not in ("dylib","so","o","a"):
                    if "Mach-O" not in self.target.bt("file",filepath):
                        continue
                relfilepath = filepath[len(workdir):]
                if not os.path.isdir(os.path.dirname(fatdir+relfilepath)):
                    os.makedirs(os.path.dirname(fatdir+relfilepath))
                cmd = ["lipo","-create"]
                for arch in self.TARGET_ARCHS:
                    if arch == self.LOCAL_ARCH:
                        archdir = workdir
                    else:
                        archdir = os.path.join(os.path.dirname(workdir),arch)
                    cmd.append("-arch")
                    cmd.append(arch)
                    cmd.append(archdir+relfilepath)
                cmd.append("-output")
                cmd.append(fatdir+relfilepath)
                self.target.do(*cmd)
                shutil.copystat(workdir+relfilepath,fatdir+relfilepath)
        # Now copy them back into the main build dir
        for (dirnm,_,filenms) in os.walk(fatdir):
            for nm in filenms:
                filepath = os.path.join(dirnm,nm)
                relfilepath = filepath[len(fatdir):]
                print "NWAY MERGE", relfilepath
                shutil.copy2(filepath,workdir+relfilepath)


class CMakeRecipe(Recipe,base.CMakeRecipe):
    def _generic_cmake(self,src,relpath=".",args=[],env={}):
        """Do a generic "cmake" on the given source tarball."""
        archflags = " ".join("-arch "+arch for arch in self.TARGET_ARCHS)
        load_recipe("cmake",self.target).install()
        workdir = self._get_builddir(src)
        cmd = ["cmake"]
        cmd.append("-DCMAKE_INSTALL_PREFIX=%s" % (self.target.PREFIX,))
        cmd.append("-DCMAKE_VERBOSE_MAKEFILE=ON")
        for arg in args:
            cmd.append(arg)
        libdir = os.path.join(self.target.PREFIX,"lib")
        incdir = os.path.join(self.target.PREFIX,"include")
        env = env.copy()
        env.setdefault("LDFLAGS",self.LDFLAGS)
        env.setdefault("CFLAGS","%s %s -mmacosx-version-min=10.4 -isysroot %s" % (archflags,self.INCFLAGS,self.ISYSROOT,))
        env.setdefault("CXXFLAGS","%s %s -mmacosx-version-min=10.4 -isysroot %s" % (archflags,self.INCFLAGS,self.ISYSROOT,))
        with cd(workdir):
            self.target.do(*cmd,env=env)



class PyCMakeRecipe(CMakeRecipe,base.PyCMakeRecipe):
    pass


class python27(Recipe,base.python27):
    """Install the basic Python interpreter, with myppy support."""

    @property
    def CC(self):
        return "/usr/bin/gcc-4.0 -lz -mmacosx-version-min=10.4 -isysroot " + self.ISYSROOT


class lib_sqlite3(NWayRecipe,base.lib_sqlite3):

    @property
    def MAKE_VARS(self):
        return ["CC="+self.CC,"CXX="+self.CXX,"CFLAGS=-DSQLITE_ENABLE_LOCKING_STYLE=0"]


class lib_wxwidgets_base(Recipe,base.lib_wxwidgets_base):
    def _patch(self):
        def add_explicit_casts(lines):
            for ln in lines:
                ln = re.sub(r"\[(\d+)u\]",r"[(size_t)\1u]",ln)
                ln = re.sub(r"\[(\d+)U\]",r"[(size_t)\1U]",ln)
                ln = re.sub(r"\[\(unsigned int\)([^\]]+)\]",r"[(int)\1]",ln)
                ln = re.sub(r"\[i]",r"[(size_t)i]",ln)
                yield ln
        workdir = self._get_builddir()
        for (dirnm,_,filenms) in os.walk(workdir):
            for nm in filenms:
                if nm.rsplit(".",1)[-1] not in ("h","cpp"):
                    continue
                filepath = os.path.join(dirnm,nm)[len(workdir)+1:]
                self.patch_build_file(filepath,add_explicit_casts)


class lib_wxwidgets_gizmos(lib_wxwidgets_base,base.lib_wxwidgets_base):
    pass


class lib_wxwidgets_stc(lib_wxwidgets_stc,base.lib_wxwidgets_stc):
    pass


class py_wxpython(Recipe,base.py_wxpython):
    def install(self):
        wxconfig = os.path.join(self.target.PREFIX,"bin","wx-config")
        self._generic_pyinstall(src,relpath="wxPython"args=["WX_CONFIG="+wxconfig])


class lib_jpeg(NWayRecipe,base.lib_jpeg):
    pass


class lib_png(NWayRecipe,base.lib_png):
    pass


class lib_tiff(NWayRecipe,base.lib_tiff):
    pass


class lib_qt4(Recipe,base.lib_qt4):
    DEPENDENCIES = ["lib_icu"]
    CONFIGURE_ARGS = ["-no-framework","-universal"]
    CONFIGURE_ARGS.extend(base.lib_qt4.CONFIGURE_ARGS)
    CONFIGURE_VARS = None
    def install(self):
        super(lib_qt4,self).install()
        workdir = self._get_builddir()
        menunib_in = os.path.join(workdir,"src/gui/mac/qt_menu.nib")
        menunib_out = os.path.join(self.target.rootdir,"Python.framework","Resources","Python.app","Contents","Resources","qt_menu.nib")
        shutil.copytree(menunib_in,menunib_out)


# TODO: hardcode charset to utf8 for extra performance
class lib_icu(Recipe):
    SOURCE_URL = "http://download.icu-project.org/files/icu4c/4.4.2/icu4c-4_4_2-src.tgz"
    CONFIGURE_SCRIPT = "./source/configure"


class lib_xml2(NWayRecipe,base.lib_xml2):
    pass

class lib_xslt(NWayRecipe,base.lib_xslt):
    pass


class lib_shiboken(PyCMakeRecipe,base.lib_shiboken):
    pass


class py_pyside(PyCMakeRecipe,base.py_pyside):
    pass
#        for nm in os.listdir(os.path.join(spdir,"PySide")):
#            if nm.endswith(".so"):
#                sopath = os.path.join(spdir,"PySide",nm)
#                self.target.do("install_name_tool","-change","libshiboken.0.5.dylib",os.path.join(self.target.PREFIX,"lib","libshiboken.0.5.dylib"),sopath)
#                self.target.do("install_name_tool","-change","libpyside.0.4.dylib",os.path.join(self.target.PREFIX,"lib","libpyside.0.4.dylib"),sopath)
#        for nm in os.listdir(os.path.join(self.target.PREFIX,"lib")):
#            if nm.endswith(".dylib"):
#                sopath = os.path.join(self.target.PREFIX,"lib",nm)
#                self.target.do("install_name_tool","-change","libshiboken.0.5.dylib",os.path.join(self.target.PREFIX,"lib","libshiboken.0.5.dylib"),sopath)
#                self.target.do("install_name_tool","-change","libpyside.0.4.dylib",os.path.join(self.target.PREFIX,"lib","libpyside.0.4.dylib"),sopath)


