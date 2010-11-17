#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  myppy.__main__:  allow myppy to be executed directly by python -m


This is a simple script that calls the myppy.main() function.

"""

if __name__ == "__main__":
    import sys
    import myppy
    res = myppy.main(sys.argv)
    sys.exit(res)

