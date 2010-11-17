#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.

from __future__ import with_statement

import sys
import os
import unittest
from os.path import dirname

import myppy


class TestMyppy(unittest.TestCase):


  def test_README(self):
    """Ensure that the README is in sync with the docstring.

    This test should always pass; if the README is out of sync it just updates
    it with the contents of myppy.__doc__.
    """
    dirname = os.path.dirname
    readme = os.path.join(dirname(dirname(dirname(__file__))),"README.rst")
    if not os.path.isfile(readme):
        f = open(readme,"wb")
        f.write(myppy.__doc__.encode())
        f.close()
    else:
        f = open(readme,"rb")
        if f.read() != myppy.__doc__:
            f.close()
            f = open(readme,"wb")
            f.write(myppy.__doc__.encode())
            f.close()

