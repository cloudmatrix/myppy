#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  myppy.envs.base:  base MyppyEnv class definition.

"""

from __future__ import with_statement

import os
import sys
import subprocess
import shutil
import sqlite3
import errno
import urlparse
import urllib2
from functools import wraps

from myppy import util


from myppy.recipes import base as _base_recipes


class MyppyEnv(object):
    """A myppy environment.

    This class represents a myppy environment installed in the given root
    directory.  It's useful for running commands within that environment.
    Handy methods:

        * init():       initialize (or re-initialize) the myppy environment
        * clean():      clean up temporary and build-related files
        * do():         execute a subprocess within the environment
        * install():    install a given recipe into the environment
        * uninstall():  uninstall a recipe from the environment

    """
 
    DEPENDENCIES = ["python27","py_pip","py_myppy"]

    DB_NAME = os.path.join("local","myppy.db")

    def __init__(self,rootdir):
        if not isinstance(rootdir,unicode):
            rootdir = rootdir.decode(sys.getfilesystemencoding())
        self.rootdir = os.path.abspath(rootdir)
        self.builddir = os.path.join(self.rootdir,"build")
        self.cachedir = os.path.join(self.rootdir,"cache")
        self.env = os.environ.copy()
        self._old_files_cache = None
        self._add_env_path("PATH",os.path.join(self.PREFIX,"bin"))
        self._has_db_lock = 0
        if not os.path.exists(self.rootdir):
            os.makedirs(self.rootdir)
        dbpath = os.path.join(self.rootdir,self.DB_NAME)
        if not os.path.exists(os.path.dirname(dbpath)):
            os.makedirs(os.path.dirname(dbpath))
        self._db = sqlite3.connect(dbpath,isolation_level=None)
        self._initdb()

    def __enter__(self):
        if not self._has_db_lock:
            self._db.execute("BEGIN IMMEDIATE TRANSACTION")
        self._has_db_lock += 1

    def __exit__(self,exc_type,exc_value,exc_traceback):
        if exc_type is not None:
            self._has_db_lock -= 1
            if not self._has_db_lock:
                self._db.execute("ROLLBACK TRANSACTION")
        else:
            self._has_db_lock -= 1
            if not self._has_db_lock:
                self._db.execute("COMMIT TRANSACTION")

    def _add_env_path(self,key,path):
        """Add an entry to list of paths in an envionment variable."""
        PATH = self.env.get(key,"")
        if PATH:
            if sys.platform == "win32":
                self.env[key] = path + ";" + PATH
            else:
                self.env[key] = path + ":" + PATH
        else:
            self.env[key] = path

    @property
    def PREFIX(self):
        return os.path.join(self.rootdir,"local")

    @property
    def PYTHON_EXECUTABLE(self):
        return os.path.join(self.PREFIX,"bin","python")

    @property
    def PYTHON_HEADERS(self):
        return os.path.join(self.PREFIX,"include","python2.7")

    @property
    def PYTHON_LIBRARY(self):
        return os.path.join(self.PREFIX,"lib","libpython2.7.so")

    @property
    def SITE_PACKAGES(self):
        return os.path.join(self.PREFIX,"lib","python2.7","site-packages")

    def init(self):
        """Build the base myppy python environment."""
        for dep in self.DEPENDENCIES:
            self.install(dep,initialising=True,explicit=False)
        
    def clean(self):
        """Clean out temporary built files and the like."""
        if os.path.exists(self.builddir):
            shutil.rmtree(self.builddir)
        if os.path.exists(self.cachedir):
            shutil.rmtree(self.cachedir)
        q = "SELECT DISTINCT recipe FROM installed_files"
        for row in self._db.execute(q):
            if not self.is_explicitly_installed(row[0]):
                self.uninstall(row[0])
        for fpath in self.find_new_files():
            if os.path.isfile(fpath) or os.path.islink(fpath):
                os.unlink(fpath)

    def do(self,*cmdline,**kwds):
        """Execute the given command within this myppy environment."""
        env = self.env.copy()
        env.update(kwds.pop("env",{}))
        stdin = kwds.pop("stdin",None)
        if stdin is None:
            stdin = sys.stdin
        for (k,v) in env.iteritems():
            if not isinstance(v,basestring):
                raise ValueError("NONSTRING %r => %r " % (k,v,))
        subprocess.check_call(cmdline,env=env,stdin=stdin,**kwds)

    def bt(self,*cmdline,**kwds):
        """Execute the command within this myppy environment, return stdout.

        "bt" is short for "backticks"; hopefully its use is obvious to shell
        scripters and the like.
        """
        env = self.env.copy()
        env.update(kwds.pop("env",{}))
        stdin = kwds.pop("stdin",None)
        if stdin is None:
            stdin = sys.stdin
        stdout = subprocess.PIPE
        p = subprocess.Popen(cmdline,stdout=stdout,env=env,stdin=stdin,**kwds)
        output = p.stdout.read()
        retcode = p.wait()
        if retcode != 0:
            raise subprocess.CalledProcessError(retcode,cmdline)
        return output

    def is_initialised(self):
        for dep in self.DEPENDENCIES:
            if not self.is_installed(dep):
                return False
        return True

    def is_installed(self,recipe):
        q = "SELECT filepath FROM installed_files WHERE recipe=? LIMIT 1"
        return (self._db.execute(q,(recipe,)).fetchone() is not None)

    def is_explicitly_installed(self,recipe):
        if not self.is_installed(recipe):
            return False
        deps = set(self.DEPENDENCIES)
        for row in self._db.execute("SELECT recipe FROM installed_recipes"):
            deps.add(row[0])
        todo = list(deps)
        while todo:
            r = self.load_recipe(todo.pop(0))
            for dep in r.DEPENDENCIES:
                if dep not in deps:
                    deps.add(dep)
                    todo.append(dep)
        return recipe in deps
  
    def install(self,recipe,initialising=False,explicit=True):
        """Install the named recipe into this myppy env."""
        if not self.is_installed(recipe):
            r = self.load_recipe(recipe)
            if not initialising and not self.is_initialised():
                self.init()
            for conflict in r.CONFLICTS_WITH:
                if self.is_explicitly_installed(conflict):
                    msg = "Recipe %r conflicts with %r, "
                    msg += "which is already installed"
                    msg %= (recipe,conflict,)
                    raise RuntimeError(msg)
                self.uninstall(conflict)
            for dep in r.DEPENDENCIES:
                if dep != recipe:
                    self.install(dep,initialising=initialising,explicit=False)
            for dep in r.BUILD_DEPENDENCIES:
                if dep != recipe:
                    self.install(dep,initialising=initialising,explicit=False)
            print "FETCHING", recipe
            r.fetch()
            with self:
                print "BUILDING", recipe
                r.build()
                print "INSTALLING", recipe
                r.install()
                print "RECORDING INSTALLED FILES FOR", recipe
                files = list(self.find_new_files())
                self.record_files(recipe,files)
                print "INSTALLED", recipe
        if explicit and not self.is_explicitly_installed(recipe):
            q = "INSERT INTO installed_recipes VALUES (?)"
            self._db.execute(q,(recipe,))

    def uninstall(self,recipe):
        """Uninstall the named recipe from this myppy env."""
        # TODO: remove things depending on it
        with self:
            q = "DELETE FROM installed_recipes WHERE recipe=?"
            self._db.execute(q,(recipe,))
            q = "SELECT filepath FROM installed_files WHERE recipe=?"\
                " ORDER BY filepath DESC"
            files = [r[0] for r in self._db.execute(q,(recipe,))]
            q = "DELETE FROM installed_files WHERE recipe=?"
            self._db.execute(q,(recipe,))
            for file in files:
                assert util.relpath(file) == file
                if self._old_files_cache is not None:
                    self._old_files_cache.remove(file)
            for file in files:
                filepath = os.path.join(self.rootdir,file)
                if not os.path.exists(filepath):
                    continue
                if filepath.endswith(os.sep):
                    print "PRUNING", filepath
                    util.prune_dir(filepath)
                else:
                    print "REMOVING", filepath
                    os.unlink(filepath)
                    dirpath = os.path.dirname(filepath) + os.sep
                    if not os.listdir(dirpath):
                        q = "SELECT * FROM installed_files WHERE filepath=?"
                        if not self._is_oldfile(dirpath):
                            print "PRUNING", filepath
                            util.prune_dir(dirpath)
                
    def load_recipe(self,recipe):
        return getattr(_base_recipes,recipe)(self)

    def _load_recipe_subclass(self,recipe,MyppyEnv,submod):
        try:
            r = getattr(submod,recipe)
        except AttributeError:
            rbase = super(MyppyEnv,self).load_recipe(recipe).__class__
            rsuprnm = rbase.__bases__[0].__name__
            rsupr = self.load_recipe(rsuprnm).__class__
            class r(rbase,rsupr):
                pass
            r.__name__ = rbase.__name__
            r.__module__ = submod.__name__
            setattr(submod,recipe,r)
        return r(self)

    def _is_tempfile(self,path):
        for excl in (self.builddir,self.cachedir,):
            if path == excl or path.startswith(excl + os.sep):
                return True
        if os.path.basename(path) == "myppy.db":
            return True
        if os.path.basename(path) == "myppy.db-journal":
            return True
        return False

    def _is_oldfile(self,file):
        if self._old_files_cache is None:
            self._old_files_cache = set()
            for r in self._db.execute("SELECT filepath FROM installed_files"):
                self._old_files_cache.add(r[0])
        file = file[len(self.rootdir)+1:]
        assert util.relpath(file) == file
        if file in self._old_files_cache:
            return True
        q = "SELECT * FROM installed_files WHERE filepath=?"
        if self._db.execute(q,(file,)).fetchone():
            return True
        return False
 
    def find_new_files(self):
        #  os.walk has a bad habit of choking on unicode errors, so
        #  we do it by hand and get it right.  Anything that can't
        #  be decoded properly gets deleted.
        todo = [self.rootdir]
        while todo:
            dirpath = todo.pop(0)
            try:
                names = os.listdir(dirpath)
            except OSError, e:
                if e.errno not in (errno.ENOENT,):
                    raise
                continue
            if not names:
                if not self._is_oldfile(dirpath + os.sep):
                    yield dirpath + os.sep
            else:
                for nm in names:
                    try:
                        fpath = os.path.join(dirpath,nm)
                    except UnicodeDecodeError:
                        with util.cd(dirpath):
                            if util.isrealdir(nm):
                                shutil.rmtree(nm)
                            else:
                                os.unlink(nm)
                    else:
                        if not self._is_tempfile(fpath):
                            if util.isrealdir(fpath):
                                todo.append(fpath)
                            else:
                                if not self._is_oldfile(fpath):
                                    yield fpath

    def record_files(self,recipe,files):
        """Record the given list of files as installed for the given recipe."""
        files = list(files)
        assert files, "recipe '%s' didn't install any files" % (recipe,)
        for file in files:
            file = file[len(self.rootdir)+1:]
            assert util.relpath(file) == file
            self._db.execute("INSERT INTO installed_files VALUES (?,?)",
                             (recipe,file,))
            if self._old_files_cache is not None:
                self._old_files_cache.add(file)

    def _initdb(self):
        self._db.execute("CREATE TABLE IF NOT EXISTS installed_recipes ("
                         "  recipe STRING NOT NULL"
                         ")")
        self._db.execute("CREATE TABLE IF NOT EXISTS installed_files ("
                         "  recipe STRING NOT NULL,"
                         "  filepath STRING NOT NULL"
                         ")")

    def fetch(self,url,md5=None):
        """Fetch the file at the given URL, using cached version if possible."""
        cachedir = os.environ.get("MYPPY_DOWNLOAD_CACHE",self.cachedir)
        if cachedir:
            if not os.path.isabs(cachedir[0]):
                cachedir = os.path.join(self.rootdir,cachedir)
            if not os.path.isdir(cachedir):
                os.makedirs(cachedir)
        nm = os.path.basename(urlparse.urlparse(url).path)
        cachefile = os.path.join(cachedir,nm)
        if md5 is not None and os.path.exists(cachefile):
            if md5 != util.md5file(cachefile):
                print "BAD MD5 FOR", cachefile
                print md5, util.md5file(cachefile)
                os.unlink(cachefile)
        if not os.path.exists(cachefile):
            print "DOWNLOADING", url
            fIn = urllib2.urlopen(url)
            try:
                 with open(cachefile,"wb") as fOut:
                    shutil.copyfileobj(fIn,fOut)
            finally:
                fIn.close()
        if md5 is not None and md5 != util.md5file(cachefile):
            raise RuntimeError("corrupted download: %s" % (url,))
        return cachefile

