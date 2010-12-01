#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.

from __future__ import with_statement

import os
import sys
import tempfile
import urlparse
import urllib2
import subprocess
import shutil

import myppy
from myppy.util import md5file, do, bt, cd, relpath, tempdir, chstdin


class _RecipeMetaclass(type):
    DEPENDENCIES = []
    def __new__(mcls,name,bases,attrs):
        DEPENDENCIES = list(attrs.get("DEPENDENCIES",[]))
        for base in bases:
            if not isinstance(base,_RecipeMetaclass):
                continue
            for dep in base.DEPENDENCIES:
                if dep not in DEPENDENCIES:
                    DEPENDENCIES.append(dep)
        attrs["DEPENDENCIES"] = DEPENDENCIES
        return super(_RecipeMetaclass,mcls).__new__(mcls,name,bases,attrs)

        

class Recipe(object):
    """Base class for installation recipes."""

    __metaclass__ = _RecipeMetaclass

    DEPENDENCIES = []
    SOURCE_URL = "http://source.url.is/missing.txt"
    SOURCE_MD5 = None

    CONFIGURE_DIR = "."
    CONFIGURE_SCRIPT = "./configure"
    CONFIGURE_ARGS = []
    CONFIGURE_VARS = []

    MAKE_VARS = ()
    MAKE_RELPATH = "."

    def __init__(self,target):
        self.target = target

    def fetch(self):
        """Download any files necessary to build this recipe."""
        self.target.fetch(self.SOURCE_URL,self.SOURCE_MD5)

    def build(self):
        """Build all of the files for this recipe."""
        self._unpack()
        self._patch()
        self._configure()
        self._make()

    def install(self):
        """Install all of the files for this recipe."""
        self._generic_makeinstall()

    def _unpack(self):
        """Do a generic "tar -x" on the downloaded source tarball."""
        src = self.target.fetch(self.SOURCE_URL)
        updir = os.path.join(self.target.builddir,os.path.basename(src))
        return self._unpack_tarball(src,updir)

    def _patch(self):
        pass

    def _configure(self):
        self._generic_configure()

    def _make(self):
        self._generic_make()

    def _unpack_tarball(self,src,workdir):
        """Unpack the given tarball into the specified workdir."""
        if not os.path.isdir(workdir):
            os.makedirs(workdir)
        if src.endswith(".bz2"):
            cmd = ["tar","-xjf"]
        elif src.endswith(".gz") or src.endswith(".tgz"):
            cmd = ["tar","-xzf"]
        else:
            cmd = ["tar","-xf"]
        cmd.extend([src,"-C",workdir])
        self.target.do(*cmd)
        return os.path.join(workdir,os.listdir(workdir)[0])

    def _generic_configure(self,script=None,vars=None,args=None,env={}):
        """Do a generic "./configure" for this recipe."""
        if script is None:
            script = self.CONFIGURE_SCRIPT
        if vars is None:
            vars = self.CONFIGURE_VARS
        if args is None:
            args = self.CONFIGURE_ARGS
        if isinstance(script,basestring):
            cmd = [script]
        else:
            cmd = list(script)
        cmd.append("--prefix=%s" % (self.target.PREFIX,))
        for arg in args:
            cmd.append(arg)
        if vars is not None:
            for var in vars:
                cmd.append(var)
        workdir = self._get_builddir()
        workdir = os.path.join(workdir,self.CONFIGURE_DIR)
        with cd(workdir):
            self.target.do(*cmd,env=env)

    def _generic_make(self,vars=None,relpath=None,env={}):
        """Do a generic "make" for this recipe."""
        workdir = self._get_builddir()
        if vars is None:
            vars = self.MAKE_VARS
        if relpath is None:
            relpath = self.MAKE_RELPATH
        cmd = ["make"]
        if vars is not None:
            cmd.extend(vars)
        cmd.extend(("-C",os.path.join(workdir,relpath)))
        self.target.do(*cmd,env=env)

    def _generic_makeinstall(self,vars=None,relpath=None,env={}):
        """Do a generic "make install" for this recipe."""
        workdir = self._get_builddir()
        if vars is None:
            vars = self.MAKE_VARS
        if relpath is None:
            relpath = self.MAKE_RELPATH
        cmd = ["make"]
        if vars is not None:
            cmd.extend(vars)
        cmd.extend(("-C",os.path.join(workdir,relpath),"install"))
        self.target.do(*cmd,env=env)

    def _generic_pyinstall(self,relpath="",args=[],env={}):
        """Do a generic "python setup.py install" for this recipe."""
        workdir = self._get_builddir()
        cmd = [self.target.PYTHON_EXECUTABLE,"setup.py","install"]
        cmd.extend(args)
        with cd(os.path.join(workdir,relpath)):
            self.target.do(*cmd,env=env)

    def _get_builddir(self):
        """Get the directory in which we build this recipe.

        This is always <builddir>/<sourcefilename>/<srcdirname>/
        """
        src = self.SOURCE_URL
        workdir = os.path.join(self.target.builddir,os.path.basename(src))
        return os.path.join(workdir,os.listdir(workdir)[0])

    def _patch_file(self,fpath,filter):
        """Apply a linewise patch function to the specified file."""
        if not os.path.isabs(fpath):
            fpath = os.path.join(self.target.PREFIX,fpath)
        mod = os.stat(fpath).st_mode
        (fd,tf) = tempfile.mkstemp()
        os.close(fd)
        with open(tf,"wt") as fOut:
            with open(fpath,"rt") as fIn:
                for ln in filter(fIn):
                    fOut.write(ln)
            fOut.flush()
        do("mv","-f",tf,fpath)
        os.chmod(fpath,mod)

    def _patch_build_file(self,relpath,filter):
        """Apply a linewise patch function to specified file in build dir."""
        workdir = self._get_builddir()
        self._patch_file(os.path.join(workdir,relpath),filter)


class PyRecipe(Recipe):
    DEPENDENCIES = ["python26"]
    def build(self):
        """Build all of the files for this recipe."""
        self._unpack()
        self._patch()
    def install(self):
        """Install all of the files for this recipe."""
        self._generic_pyinstall()


class CMakeRecipe(Recipe):
    DEPENDENCIES = ["cmake"]
    def _configure(self):
        self._generic_cmake()
    def _generic_cmake(self,relpath=".",args=[],env={}):
        cmd = ["cmake"]
        cmd.append("-DCMAKE_INSTALL_PREFIX=%s" % (self.target.PREFIX,))
        cmd.append("-DCMAKE_VERBOSE_MAKEFILE=ON")
        for arg in args:
            cmd.append(arg)
        with cd(self._get_builddir()):
            self.target.do(*cmd,env=env)


class PyCMakeRecipe(CMakeRecipe):
    DEPENDENCIES = ["python26"]
    def _configure(self):
        args = ("-DPYTHON_EXECUTABLE="+self.target.PYTHON_EXECUTABLE,
                "-DPYTHON_INCLUDE_DIR="+self.target.PYTHON_HEADERS,
                "-DPYTHON_LIBRARY="+self.target.PYTHON_LIBRARY,)
        self._generic_cmake(args=args)



class cmake(Recipe):
    SOURCE_URL = "http://www.cmake.org/files/v2.8/cmake-2.8.3.tar.gz"
    CONFIGURE_VARS = None
    MAKE_VARS = ["VERBOSE=1"]


class python26(Recipe):
    DEPENDENCIES = ["lib_zlib","lib_readline","lib_sqlite3","lib_bz2"]
    SOURCE_URL = "http://www.python.org/ftp/python/2.6.6/Python-2.6.6.tgz"
    CONFIGURE_ARGS = ("--enable-shared",)
    def _patch(self):
        #  Add some builtin modules:
        #    * fcntl  (handy for use with esky)
        #    * _md5 and _sha*  (handy for use with signedimp)
        #    * time and zlib  (handy for use with zipimportx)
        def add_builtin_modules(lines):
            for ln in lines:
                if ln.startswith("#fcntl"):
                    yield ln[1:]
                elif ln.startswith("#_md5"):
                    yield ln[1:]
                elif ln.startswith("#_sha"):
                    yield ln[1:]
                elif ln.startswith("#zlib"):
                    yield ln[1:]
                elif ln.startswith("#time"):
                    yield ln[1:]
                else:
                    yield ln
        self._patch_build_file("Modules/Setup.dist",add_builtin_modules)
    def _configure(self):
        super(python26,self)._configure()
        #  Can't link epoll without symbols from a later libc.
        #  We'll have to settle for old-fashioned select().
        def remove_have_epoll(lines):
            for ln in lines:
                if "HAVE_EPOLL" not in ln:
                    yield ln
        self._patch_build_file("pyconfig.h",remove_have_epoll)
        #  Patch the zipimport module to accept zipfiles with comments.
        #  This is very handy when signing executables with appended zipfiles.
        def allow_zipfile_comments(lines):
            for ln in lines:
                if ln.strip() == "static PyObject *read_directory(char *archive);":
                    yield ln
                    yield "static int find_endof_central_dir(FILE* fp,char *eocd,long *header_pos);"
                elif ln.strip() == "/* Bad: End of Central Dir signature */":
                    lines.next()
                    lines.next()
                    lines.next()
                    lines.next()
                    yield """
      if(find_endof_central_dir(fp,endof_central_dir,&header_position) != 0) {
          fclose(fp);
          PyErr_Format(ZipImportError, "not a Zip file: "
                       "'%.200s'", archive);
         return NULL;
      }
"""
                elif ln.strip() == "/* Return the zlib.decompress function object, or NULL if zlib couldn't":
                    yield """

#define EOCD_MAX_SIZE ((1 << 16) + 22)
#define EOCD_CHUNK_SIZE (1024 * 16)

static int find_endof_central_dir(FILE* fp,char *eocd_out,long *header_pos) {
    long pos, size, count;
    char *eocd;
    char chunk[EOCD_CHUNK_SIZE + 32];
    struct stat st;

    if (fstat(fileno(fp), &st) != 0) {
        return -1;
    }

    eocd = NULL;
    count = 1; pos = 0; size = 0;
    while(eocd == NULL && pos < EOCD_MAX_SIZE && pos < st.st_size) {
        pos = count * EOCD_CHUNK_SIZE;
        size = EOCD_CHUNK_SIZE;
        /*  Overlap previous chunk, in case the EOCD record is in the gap */
        if(count > 1) {
            size += 32;
        }
        /*  Don't try to search past beginning of file */
        if(pos > st.st_size) {
            pos = st.st_size;
            if(size > st.st_size) {
                size = st.st_size;
            }
        }
        /*  Don't try to search past max comment size */
        if(pos > EOCD_MAX_SIZE) {
            pos = EOCD_MAX_SIZE;
        }
        /*  Read the next chunk */
        fseek(fp, -1*pos, SEEK_END);
        if(fread(chunk, 1, size, fp) != size) {
            return -1;
        }
        /*  Search backwards looking for EOCD signature */
        eocd = chunk + size - 4;
        while(get_long((unsigned char *)eocd) != 0x06054B50) {
            if(eocd == chunk) {
                eocd = NULL;
                break;
            }
            eocd -= 1;
        }
        count++;
    }

    if(eocd == NULL) {
        return -1;
    }

    memcpy(eocd_out,eocd,22);
    *header_pos = ftell(fp) - size + eocd - chunk;
    return 0;
}

"""
                    yield ln
                else:
                    yield ln
        self._patch_build_file("Modules/zipimport.c",allow_zipfile_comments)


class lib_bz2(Recipe):
    SOURCE_URL = "http://www.bzip.org/1.0.6/bzip2-1.0.6.tar.gz"
    SOURCE_MD5 = "00b516f4704d4a7cb50a1d97e6e8e15b"
    @property
    def MAKE_VARS(self):
        return ("PREFIX=" + self.target.PREFIX,)
    def _configure(self):
        pass


class lib_readline(Recipe):
    SOURCE_URL = "ftp://ftp.cwru.edu/pub/bash/readline-6.1.tar.gz"
    SOURCE_MD5 = "fc2f7e714fe792db1ce6ddc4c9fb4ef3"
    CONFIGURE_ARGS = ("--disable-shared","--enable-static",)


class lib_zlib(Recipe):
    SOURCE_URL = "http://zlib.net/zlib-1.2.5.tar.gz"
    SOURCE_MD5 = "c735eab2d659a96e5a594c9e8541ad63"
    CONFIGURE_ARGS = ("--static",)
    CONFIGURE_VARS = None
    def _configure(self):
        super(lib_zlib,self)._configure()
        def dont_copy_dylib(lines):
            for ln in lines:
                if not ln.strip().startswith("cp $(SHAREDLIBV)"):
                    yield ln
        self._patch_build_file("Makefile",dont_copy_dylib)


class lib_png(Recipe):
    SOURCE_URL = "http://sourceforge.net/projects/libpng/files/01-libpng-master/1.4.2/libpng-1.4.2.tar.gz/download"


class lib_jpeg(Recipe):
    SOURCE_URL = "http://www.ijg.org/files/jpegsrc.v8b.tar.gz"


class lib_tiff(Recipe):
    SOURCE_URL = "ftp://ftp.remotesensing.org/pub/libtiff/tiff-3.9.4.tar.gz"


class lib_xml2(Recipe):
    SOURCE_URL = "ftp://xmlsoft.org/libxml2/libxml2-2.7.8.tar.gz"
    SOURCE_MD5 = "8127a65e8c3b08856093099b52599c86"


class lib_xslt(Recipe):
    DEPENDENCIES = ["lib_xml2"]
    SOURCE_URL = "ftp://xmlsoft.org/libxml2/libxslt-1.1.26.tar.gz"
    SOURCE_MD5 = "e61d0364a30146aaa3001296f853b2b9"


class lib_openssl(Recipe):
    SOURCE_URL = "http://www.openssl.org/source/openssl-1.0.0a.tar.gz"
    SOURCE_MD5 = "e3873edfffc783624cfbdb65e2249cbd"
    CONFIGURE_SCRIPT = "./Configure"
    CONFIGURE_ARGS = ["linux-elf"]
    CONFIGURE_VARS = None
    def _patch(self):
        super(lib_openssl,self)._patch()
        def make_Configure_executable(lines):
            yield "#!/usr/bin/env perl\n"
            lines.next()
            for ln in lines:
                yield ln
        self._patch_build_file("Configure",make_Configure_executable)


class lib_sqlite3(Recipe):
    SOURCE_URL = "http://www.sqlite.org/sqlite-amalgamation-3.6.23.1.tar.gz"
    SOURCE_MD5 = "ed585bb3d4e5c643843ebb1e318644ce"


class py_setuptools(PyRecipe):
    SOURCE_URL = "http://pypi.python.org/packages/source/s/setuptools/setuptools-0.6c11.tar.gz"
    SOURCE_MD5 = "7df2a529a074f613b509fb44feefe74e"


class py_pip(PyRecipe):
    DEPENDENCIES = ["py_setuptools"]
    def fetch(self):
        pass
    def build(self):
        pass
    def install(self):
        self.target.do("env")
        self.target.do("easy_install","pip")


class py_myppy(Recipe):
    def fetch(self):
        pass
    def build(self):
        pass
    def install(self):
        myppy_root = os.path.dirname(myppy.__file__)
        spdir = self.target.SITE_PACKAGES
        if not os.path.exists(spdir):
            os.makedirs(spdir)
        if os.path.exists(os.path.join(spdir,"myppy")):
            shutil.rmtree(os.path.join(spdir,"myppy"))
        shutil.copytree(myppy_root,os.path.join(spdir,"myppy"))


class lib_wxwidgets_base(Recipe):
    SOURCE_URL = "http://downloads.sourceforge.net/project/wxpython/wxPython/2.8.11.0/wxPython-src-2.8.11.0.tar.bz2"
    CONFIGURE_ARGS = ("--with-opengl","--enable-unicode","--enable-optimize","--enable-debug_flag",)


class lib_wxwidgets_gizmos(lib_wxwidgets_base):
    DEPENDENCIES = ["lib_wxwidgets_base"]
    SOURCE_URL = "http://downloads.sourceforge.net/project/wxpython/wxPython/2.8.11.0/wxPython-src-2.8.11.0.tar.bz2"
    MAKE_RELPATH = "contrib/src/gizmos"


class lib_wxwidgets_stc(lib_wxwidgets_base):
    DEPENDENCIES = ["lib_wxwidgets_base"]
    SOURCE_URL = "http://downloads.sourceforge.net/project/wxpython/wxPython/2.8.11.0/wxPython-src-2.8.11.0.tar.bz2"
    MAKE_RELPATH = "contrib/src/stc"
    

class lib_wxwidgets(Recipe):
    DEPENDENCIES = ["lib_wxwidgets_base","lib_wxwidgets_gizmos",
                    "lib_wxwidgets_stc"]
    def fetch(self):
        pass
    def build(self):
        pass
    def install(self):
        open(os.path.join(self.target.PREFIX,"lib","wxwidgets-installed"),"wb").close()


class lib_qt4(Recipe):
    DEPENDENCIES = ["lib_jpeg","lib_png","lib_tiff","lib_zlib"]
    SOURCE_URL = "http://get.qt.nokia.com/qt/source/qt-everywhere-opensource-src-4.7.1.tar.gz"
    SOURCE_MD5 = "6f88d96507c84e9fea5bf3a71ebeb6d7"
    CONFIGURE_VARS = None
    @property
    def CONFIGURE_ARGS(self):
        return ("-no-pch","-no-cups","-no-openssl","-no-declarative","-system-libpng","-system-libjpeg","-system-libtiff","-system-zlib","-system-sqlite","-no-phonon","-no-multimedia","-no-qt3support","-no-webkit","-no-libmng","-shared","-opensource","-release","-nomake","examples","-nomake","demos","-nomake","docs","-I",os.path.join(self.target.PREFIX,"include"),"-L",os.path.join(self.target.PREFIX,"lib"))
    def _configure(self):
        # automatically accept the LGPL
        with chstdin("yes"):
            super(lib_qt4,self)._configure()


class py_wxpython(PyRecipe):
    DEPENDENCIES = ["lib_wxwidgets"]
    SOURCE_URL = "http://downloads.sourceforge.net/project/wxpython/wxPython/2.8.11.0/wxPython-src-2.8.11.0.tar.bz2"
    def install(self):
        self._generic_pyinstall(relpath="wxPython")


class lib_apiextractor(CMakeRecipe):
    DEPENDENCIES = ["lib_xslt","lib_qt4"]
    SOURCE_URL = "http://www.pyside.org/files/apiextractor-0.9.0.tar.bz2"


class lib_generatorrunner(CMakeRecipe):
    DEPENDENCIES = ["lib_qt4"]
    SOURCE_URL = "http://www.pyside.org/files/generatorrunner-0.6.3.tar.bz2"


class lib_shiboken(PyCMakeRecipe):
    DEPENDENCIES = ["lib_apiextractor","lib_generatorrunner"]
    SOURCE_URL = "http://www.pyside.org/files/shiboken-1.0.0~beta1.tar.bz2"


class py_pyside(PyCMakeRecipe):
    DEPENDENCIES = ["lib_shiboken",]
    SOURCE_URL = "http://www.pyside.org/files/pyside-qt4.7+1.0.0~beta1.tar.bz2"


class py_pyside_tools(CMakeRecipe):
    SOURCE_URL = "http://www.pyside.org/files/pyside-tools-0.2.2.tar.bz2"
    SOURCE_MD5 = "5fe207cd8cd16ddbb033533fe7528011"


class py_pypy(Recipe):
    SOURCE_URL = "http://pypy.org/download/pypy-1.4-src.tar.bz2"
    def build(self):
        self._unpack()
    def install(self):
        workdir = self._get_builddir()
        shutil.copytree(os.path.join(workdir,"py"),
                        os.path.join(self.target.SITE_PACKAGES,"py"))
        shutil.copytree(os.path.join(workdir,"lib-python"),
                        os.path.join(self.target.SITE_PACKAGES,"lib-python"))
        shutil.copytree(os.path.join(workdir,"pypy"),
                        os.path.join(self.target.SITE_PACKAGES,"pypy"))

