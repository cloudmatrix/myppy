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

from textwrap import dedent

import myppy
from myppy.util import md5file, do, bt, cd, relpath, tempdir, chstdin, \
                       prune_dir


class _RecipeMetaclass(type):

    DEPENDENCIES = []
    BUILD_DEPENDENCIES = []
    CONFLICTS_WITH = []

    def __new__(mcls,name,bases,attrs):
        mcls._merge_dep_attr("DEPENDENCIES",bases,attrs)
        mcls._merge_dep_attr("BUILD_DEPENDENCIES",bases,attrs)
        mcls._merge_dep_attr("CONFLICTS_WITH",bases,attrs)
        return super(_RecipeMetaclass,mcls).__new__(mcls,name,bases,attrs)

    @staticmethod
    def _merge_dep_attr(attrnm,bases,attrs):
        deps = list(attrs.get(attrnm,[]))
        for base in bases:
            if not isinstance(base,_RecipeMetaclass):
                continue
            for dep in getattr(base,attrnm):
                if dep not in deps:
                    deps.append(dep)
        attrs[attrnm] = deps

        

class Recipe(object):
    """Base class for installation recipes."""

    __metaclass__ = _RecipeMetaclass

    DEPENDENCIES = []
    BUILD_DEPENDENCIES = []
    CONFLICTS_WITH = []

    SOURCE_URL = "http://source.url.is/missing.txt"
    SOURCE_MD5 = None

    CONFIGURE_DIR = "."
    CONFIGURE_SCRIPT = "./configure"
    CONFIGURE_ARGS = []
    CONFIGURE_VARS = []

    MAKE_VARS = ()
    MAKE_RELPATH = "."

    @property
    def PREFIX(self):
        return self.target.PREFIX

    @property
    def INSTALL_PREFIX(self):
        return self.PREFIX

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
        self._generic_make(target="install")

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
        cmd.append("--prefix=%s" % (self.INSTALL_PREFIX,))
        for arg in args:
            cmd.append(arg)
        if vars is not None:
            for var in vars:
                cmd.append(var)
        workdir = self._get_builddir()
        workdir = os.path.join(workdir,self.CONFIGURE_DIR)
        with cd(workdir):
            self.target.do(*cmd,env=env)

    def _generic_make(self,vars=None,relpath=None,target=None,makefile=None,env={}):
        """Do a generic "make install" for this recipe."""
        workdir = self._get_builddir()
        if vars is None:
            vars = self.MAKE_VARS
        if relpath is None:
            relpath = self.MAKE_RELPATH
        cmd = ["make"]
        if vars is not None:
            cmd.extend(vars)
        if makefile is not None:
            cmd.extend(("-f",makefile))
        cmd.extend(("-C",os.path.join(workdir,relpath)))
        if target is not None:
            cmd.append(target)
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
            fpath = os.path.join(self.PREFIX,fpath)
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
    DEPENDENCIES = ["python27"]
    def build(self):
        """Build all of the files for this recipe."""
        self._unpack()
        self._patch()
    def install(self):
        """Install all of the files for this recipe."""
        self._generic_pyinstall()


class CMakeRecipe(Recipe):
    BUILD_DEPENDENCIES = ["cmake"]
    def _configure(self):
        self._generic_cmake()
    def _generic_cmake(self,relpath=".",args=[],env={}):
        cmd = ["cmake"]
        cmd.append("-DCMAKE_INSTALL_PREFIX=%s" % (self.INSTALL_PREFIX,))
        cmd.append("-DCMAKE_MODULE_PATH=%s" % (os.path.join(self.PREFIX,"share","cmake"),))
        cmd.append("-DCMAKE_VERBOSE_MAKEFILE=ON")
        cmd.append("-DBUILD_TESTS=False")
        cmd.append("-DCMAKE_BUILD_TYPE=MinSizeRel")
        for arg in args:
            cmd.append(arg)
        # Do an out-of-source build, required by some recipes.
        builddir = os.path.join(self._get_builddir(), "MYPPY-BUILD")
        os.makedirs(builddir)
        cmd.append("..")
        with cd(builddir):
            self.target.do(*cmd,env=env)


class PyCMakeRecipe(CMakeRecipe):
    DEPENDENCIES = ["python27"]
    def _configure(self):
        args = ("-DPYTHON_EXECUTABLE="+self.target.PYTHON_EXECUTABLE,
                "-DPYTHON_INCLUDE_DIR="+self.target.PYTHON_HEADERS,
                "-DPYTHON_LIBRARY="+self.target.PYTHON_LIBRARY,)
        self._generic_cmake(args=args)



class cmake(Recipe):
    SOURCE_URL = "http://www.cmake.org/files/v2.8/cmake-2.8.10.tar.gz"
    CONFIGURE_VARS = None
    MAKE_VARS = ["VERBOSE=1"]


class python27(Recipe):
    DEPENDENCIES = ["lib_zlib","lib_readline","lib_sqlite3","lib_bz2"]
    SOURCE_URL = "http://www.python.org/ftp/python/2.7.3/Python-2.7.3.tgz"
    CONFIGURE_ARGS = ("--enable-shared",)
    def _patch(self):
        #  Add some builtin modules:
        #    * fcntl  (handy for use with esky)
        #    * _md5, _sha*  (handy for use with signedimp)
        #    * time, zlib  (handy for use with zipimportx)
        #    * _functools, itertools  (they're tiny and frequently used)
        self._add_builtin_module("fcntl")
        self._add_builtin_module("_md5")
        self._add_builtin_module("_sha")
        self._add_builtin_module("zlib")
        self._add_builtin_module("time")
        self._add_builtin_module("_functools")
        self._add_builtin_module("itertools")
        def optimize_for_size(lines):
            for ln in lines:
                yield ln.replace("-O2","-Os").replace("-O3","-Os")
        self._patch_build_file("configure",optimize_for_size)
        self._patch_build_file("Modules/zlib/configure",optimize_for_size)

    def _add_builtin_module(self,modnm):
        def addit(lines):
            for ln in lines:
                if ln.startswith("#"+modnm):
                    yield ln[1:]
                else:
                    yield ln
        self._patch_build_file("Modules/Setup.dist",addit)

    def _configure(self):
        super(python27,self)._configure()
        self._post_config_patch()

    def _post_config_patch(self):
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
        return ("PREFIX=" + self.INSTALL_PREFIX,)
    def _configure(self):
        pass
    def _patch(self):
        super(lib_bz2,self)._patch()
        def optimize_for_size(lines):
            for ln in lines:
                yield ln.replace("-O2","-Os").replace("-O3","-Os")
        self._patch_build_file("Makefile",optimize_for_size)


class lib_readline(Recipe):
    SOURCE_URL = "ftp://ftp.cwru.edu/pub/bash/readline-6.2.tar.gz"
    SOURCE_MD5 = "67948acb2ca081f23359d0256e9a271c"
    CONFIGURE_ARGS = ("--disable-shared","--enable-static",)


class lib_zlib(Recipe):
    SOURCE_URL = "http://zlib.net/zlib-1.2.7.tar.gz"
    SOURCE_MD5 = "60df6a37c56e7c1366cca812414f7b85"
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
    SOURCE_URL = "http://downloads.sourceforge.net/project/libpng/libpng15/1.5.13/libpng-1.5.13.tar.gz"


class lib_jpeg(Recipe):
    SOURCE_URL = "http://www.ijg.org/files/jpegsrc.v8c.tar.gz"


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
    SOURCE_URL = "http://www.openssl.org/source/openssl-1.0.0d.tar.gz"
    SOURCE_MD5 = "40b6ea380cc8a5bf9734c2f8bf7e701e"
    CONFIGURE_SCRIPT = "./Configure"
    CONFIGURE_ARGS = ["linux-elf","shared"]
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
    SOURCE_URL = "http://www.sqlite.org/sqlite-autoconf-3070500.tar.gz"


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
        with open(os.path.join(self.PREFIX,"bin","myppy"),"w") as f:
            f.write(dedent("""
                #!/usr/bin/env python
                if __name__ == "__main__":
                    import sys
                    import myppy
                    res = myppy.main(sys.argv)
                    sys.exit(res)
            """))



class lib_wxwidgets_base(Recipe):
    SOURCE_URL = "http://downloads.sourceforge.net/project/wxpython/wxPython/2.8.11.0/wxPython-src-2.8.11.0.tar.bz2"
    CONFIGURE_ARGS = ("--with-opengl","--enable-unicode","--enable-optimize","--enable-debug_flag",)
    def _unpack(self):
        # clean up the workdir after building other qt versions
        try:
            workdir = self._get_builddir()
        except (IndexError,EnvironmentError,RuntimeError,):
            pass
        else:
            shutil.rmtree(workdir)
        super(lib_wxwidgets_base,self)._unpack()


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
        open(os.path.join(self.PREFIX,"lib","wxwidgets-installed"),"wb").close()


#  We offer two builds of Qt:
#    * a full-featured one for running various qt-related build tools
#    * a stripped-down one that can be used at runtime but not for builds

class _lib_qt4_base(Recipe):
    DEPENDENCIES = ["lib_jpeg","lib_png","lib_tiff","lib_zlib"]
    SOURCE_URL = "http://get.qt.nokia.com/qt/source/qt-everywhere-opensource-src-4.7.4.tar.gz"
    #SOURCE_MD5 = "6f88d96507c84e9fea5bf3a71ebeb6d7"
    #SOURCE_URL = "http://get.qt.nokia.com/qt/source/qt-trunk.tar.gz"
    CONFIGURE_VARS = None
    DISABLE_FEATURES = []
    @property
    def CFLAGS(self):
        flags = super(_lib_qt4_base,self).CFLAGS
        if "-static" in self.CONFIGURE_ARGS:
            flags += " -fdata-sections -ffunction-sections -Wl,--gc-sections"
        return flags
    @property
    def CXXFLAGS(self):
        flags = super(_lib_qt4_base,self).CXXFLAGS
        if "-static" in self.CONFIGURE_ARGS:
            flags += " -fdata-sections -ffunction-sections -Wl,--gc-sections"
        return flags
    @property
    def LDFLAGS(self):
        flags = super(_lib_qt4_base,self).LDFLAGS
        flags += " --gc-sections"
        return flags
    @property
    def CONFIGURE_ARGS(self):
        args = []
        for feature in self.DISABLE_FEATURES:
            args.append("-no-feature-" + feature.lower())
        args.extend(["-no-pch","-no-cups","-no-openssl","-no-declarative","-system-libpng","-system-libjpeg","-system-libtiff","-system-zlib","-no-phonon","-no-multimedia","-no-qt3support","-no-webkit","-no-opengl","-no-javascript-jit","-no-scripttools","-no-libmng","-no-dbus","-no-svg","-no-nis","-opensource","-release","-no-separate-debug-info","-nomake","examples","-nomake","demos","-nomake","docs","-nomake","tools","-I",os.path.join(self.PREFIX,"include"),"-L",os.path.join(self.PREFIX,"lib")])
        return args
    def _unpack(self):
        # clean up the workdir after building other qt versions
        try:
            workdir = self._get_builddir()
        except (IndexError,EnvironmentError,RuntimeError,):
            pass
        else:
            shutil.rmtree(workdir)
        super(_lib_qt4_base,self)._unpack()
    def _configure(self):
        # automatically accept the LGPL
        with chstdin("yes"):
            super(_lib_qt4_base,self)._configure()
    def _patch(self):
        super(_lib_qt4_base,self)._patch()
        def optimize_for_size(lines):
            for ln in lines:
                yield ln.replace("-O2","-Os").replace("-O3","-Os")
        workdir = self._get_builddir()
        for (dirnm,_,filenms) in os.walk(os.path.join(workdir,"mkspecs")):
            for filenm in filenms:
                filepath = os.path.join(dirnm,filenm)
                self._patch_file(filepath,optimize_for_size)


class lib_qt4_small(_lib_qt4_base):
    CONFLICTS_WITH = ["lib_qt4"]
    @property
    def CONFIGURE_ARGS(self):
        args = list(super(lib_qt4_small,self).CONFIGURE_ARGS)
        args.insert(1,"-shared")
        args.insert(2,"-no-exceptions")
        args.insert(3,"-no-xmlpatterns")
        return args


class lib_qt4(_lib_qt4_base):
    CONFLICTS_WITH = ["lib_qt4_small"]
    @property
    def CONFIGURE_ARGS(self):
        args = list(super(lib_qt4,self).CONFIGURE_ARGS)
        args.insert(1,"-shared")
        return args


class py_wxpython(PyRecipe):
    DEPENDENCIES = ["lib_wxwidgets"]
    SOURCE_URL = "http://downloads.sourceforge.net/project/wxpython/wxPython/2.8.11.0/wxPython-src-2.8.11.0.tar.bz2"
    def install(self):
        self._generic_pyinstall(relpath="wxPython")


class lib_shiboken(PyCMakeRecipe):
    DEPENDENCIES = ["lib_qt4", "lib_xslt"]
    SOURCE_URL = "http://qt-project.org/uploads/pyside/shiboken-1.1.2.tar.bz2"


class py_pyside(PyCMakeRecipe):
    DEPENDENCIES = ["lib_shiboken","lib_qt4"]
    SOURCE_URL = "http://qt-project.org/uploads/pyside/pyside-qt4.8+1.1.2.tar.bz2"
    @property
    def CFLAGS(self):
        flags = super(py_pyside,self).CFLAGS
        flags += " -Wl,--gc-sections"
        return flags
    @property
    def CXXFLAGS(self):
        flags = super(py_pyside,self).CXXFLAGS
        flags += " -fno-exceptions -Wl,--gc-sections"
        return flags
    @property
    def LDFLAGS(self):
        flags = super(py_pyside,self).LDFLAGS
        flags += " --gc-sections"
        return flags
    def _patch(self):
        super(py_pyside,self)._patch()
        def dont_build_extra_modules(lines):
            EXTRA_MODS = ("QtSvg","QtXml","QtTest","QtSql",
                          "QtNetwok","QtScript")
            for ln in lines:
               for mod in EXTRA_MODS:
                   if mod in ln:
                       break
               else:
                   yield ln
        self._patch_build_file("PySide/CMakeLists.txt",dont_build_extra_modules)


class py_pyside_tools(CMakeRecipe):
    SOURCE_URL = "http://qt-project.org/uploads/pyside/pyside-tools-0.2.14.tar.bz2"


class py_pypy(Recipe):
    SOURCE_URL = "http://pypy.org/download/pypy-1.5-src.tar.bz2"
    SOURCE_MD5 = "cb9ada2c50666318c3a2863da1fbe487"
    def build(self):
        self._unpack()
        self._patch()
    def install(self):
        workdir = self._get_builddir()
        for dirnm in ("py","lib-python","pypy",):
            srcpath = os.path.join(workdir,dirnm)
            dstpath = os.path.join(self.target.SITE_PACKAGES,dirnm)
            if os.path.isdir(dstpath):
                shutil.rmtree(dstpath)
            shutil.copytree(srcpath,dstpath)
    def _patch(self):
        super(py_pypy,self)._patch()
        def make_readtimestamp_static(lines):
            for ln in lines:
              if ln.strip().startswith("static long long pypy_read_timestamp"):
                 yield ln.replace("static long long","long long")
              else:
                  yield ln
        self._patch_build_file("pypy/translator/c/src/debug_print.c",make_readtimestamp_static)




class lib_postgresql(Recipe):
    DEPENDENCIES = ["lib_openssl", "lib_zlib"]
    SOURCE_URL = "ftp://ftp.postgresql.org/pub/source/v9.0.2/postgresql-9.0.2.tar.gz"
    SOURCE_MD5 = "30e87e704e75c2c5b141182b0a37bbf0"
    @property
    def CONFIGURE_ARGS(self):
        return ("--disable-shared","--enable-depend","--without-tcl","--without-perl",
            "--without-python","--without-readline","--without-krb5","--without-gssapi",
            "--disable-nls","--without-pam","--enable-integer-datetimes","--with-openssl",
            "--enable-thread-safety","--with-zlib","--without-ldap", "--disable-debug",
            "--disable-coverage","--disable-profiling","--disable-cassert",)


class lib_mysql(Recipe):
    DEPENDENCIES = ["lib_openssl", "lib_zlib"]
    SOURCE_URL = "http://downloads.mysql.com/archives/mysql-5.0/mysql-5.0.91.tar.gz"
    SOURCE_MD5 = "e28f93b1a1b10b028135c1d51bbd4c46"
    # libmysql is statically linked
    @property
    def CONFIGURE_ARGS(self):
        return ("--libdir=%s" % os.path.join(self.target.PREFIX, 'lib'),
            "--without-server", "--without-embedded-server", "--without-docs",
            "--without-man", "--with-low-memory", "--with-extra-charsets=all",
            "--enable-thread-safe-client", "--without-libwrap", "--disable-shared", "--enable-static",
            "--without-debug", "--with-charset=utf8", "--with-collation=utf8_general_ci",
            "--without-embedded-privilege-control", "--without-embedded-server",
            "--without-bench", "--enable-assembler", "--without-isam", "--without-innodb",
            "--without-extra-tools", "--with-openssl=%s" % self.target.PREFIX,
            "--without-berkeley-db", "--with-geometry", "--disable-profiling",
            "--with-zlib-dir=%s"%self.target.PREFIX)

    def install(self):
        self._generic_makeinstall()
        # create symlinks in lib folder
        with cd(os.path.join(self.target.PREFIX,'lib')):
            os.system('ln -s mysql/libmysqlclient.a')
            os.system('ln -s mysql/libmysqlclient_r.a')

class lib_expat(Recipe):
    SOURCE_URL = "http://downloads.sourceforge.net/project/expat/expat/2.0.1/expat-2.0.1.tar.gz"
    SOURCE_MD5 = "ee8b492592568805593f81f8cdf2a04c"
    CONFIGURE_ARGS = ["--enable-static", "--enable-shared"]


class py_PIL(PyRecipe):
    DEPENDENCIES = ["lib_jpeg","lib_zlib"]
    SOURCE_URL = "http://effbot.org/media/downloads/PIL-1.1.7.tar.gz"


class py_mysql_python(PyRecipe):
    DEPENDENCIES = ["lib_mysql","py_setuptools"]
    SOURCE_URL = "http://downloads.sourceforge.net/project/mysql-python/mysql-python/1.2.3/MySQL-python-1.2.3.tar.gz"
    def install(self,relpath="",args=[],env={}):
        workdir = self._get_builddir()
        # link statically with libmysqlclient_r.so
        cmd_conf = [self.target.PYTHON_EXECUTABLE,"setup.py","setopt","-c","options","-o","static","-s","True","-f","site.cfg"]
        cmd_conf2 = [self.target.PYTHON_EXECUTABLE,"setup.py","setopt","-c","options","-o","mysql_config","-s", os.path.join(self.target.PREFIX,'bin','mysql_config'),"-f","site.cfg"]
        cmd = [self.target.PYTHON_EXECUTABLE,"setup.py","install_lib"]
        cmd.extend(args)
        with cd(os.path.join(workdir,relpath)):
            self.target.do(*cmd_conf,env=env)
            self.target.do(*cmd_conf2,env=env)
            self.target.do(*cmd,env=env)


class py_psycopg2(PyRecipe):
    DEPENDENCIES = ["lib_postgresql","py_setuptools"]
    SOURCE_URL = "http://pypi.python.org/packages/source/p/psycopg2/psycopg2-2.3.2.tar.gz"
    SOURCE_MD5 = "0104a756683138c644019c37744fe091"
    SETUP_CFG = """[build_ext]
define=PSYCOPG_EXTENSIONS,PSYCOPG_NEW_BOOLEAN,HAVE_PQFREEMEM

# Set to 1 to use Python datatime objects for default date/time representation.
use_pydatetime=1

# For Windows only:
# Set to 1 if the PostgreSQL library was built with OpenSSL.
# Required to link in OpenSSL libraries and dependencies.
have_ssl=0

# Statically link against the postgresql client library.
static_libpq=1

pg_config=%s/bin/pg_config

libraries=ssl
"""
    def install(self,relpath="",args=[],env={}):
        workdir = self._get_builddir()
        # link statically with libpg.so
        cmd = [self.target.PYTHON_EXECUTABLE,"setup.py","install_lib"]
        cmd.extend(args)
        with cd(os.path.join(workdir,relpath)):
            f = open('setup.cfg', 'w')
            f.write(self.SETUP_CFG % self.target.PREFIX)
            f.close()
            self.target.do(*cmd,env=env)


class py_pyxml(PyRecipe):
    DEPENDENCIES = ["lib_expat","py_setuptools"]
    SOURCE_URL = "http://sourceforge.net/projects/pyxml/files/pyxml/0.8.4/PyXML-0.8.4.tar.gz"



class py_m2crypto(PyRecipe):
    DEPENDENCIES = ["py_setuptools"]
    SOURCE_URL = "http://pypi.python.org/packages/source/M/M2Crypto/M2Crypto-0.21.1.tar.gz"
    SOURCE_MD5 = "f93d8462ff7646397a9f77a2fe602d17"
    def build(self,relpath="",args=[],env={}):
        super(py_m2crypto,self).build()
        workdir = self._get_builddir()
        cmd = [self.target.PYTHON_EXECUTABLE,"setup.py","build","build_ext",
            "--openssl=%s" % self.target.PREFIX]
        cmd.extend(args)
        with cd(os.path.join(workdir,relpath)):
            self.target.do(*cmd,env=env)
    def install(self,relpath="",args=[],env={}):
        workdir = self._get_builddir()
        cmd = [self.target.PYTHON_EXECUTABLE,"setup.py","install_lib"]
        cmd.extend(args)
        with cd(os.path.join(workdir,relpath)):
            self.target.do(*cmd,env=env)

