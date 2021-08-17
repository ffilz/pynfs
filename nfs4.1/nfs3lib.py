from __future__ import with_statement
import rpc.rpc as rpc
import xdrdef.nfs3_const
from xdrdef.nfs3_pack import NFS3Packer, NFS3Unpacker
import xdrdef.nfs3_type
import nfs_ops
import time
import collections
import hmac
import struct
import random
import re
import os
from locking import Lock
try:
    from Crypto.Cipher import AES
except ImportError:
    class AES(object):
        """Create a fake class to use as a placeholder.

        This will give an error only if actually used.
        """
        MODE_CBC = 0
        def new(self, *args, **kwargs):
            raise NotImplementedError("could not import Crypto.Cipher")

import hashlib # Note this requires 2.7 or higher

op3 = nfs_ops.NFS3ops()

def set_flags(name, search_string):
    """Make certain flag lists in nfs3.x easier to deal with.

    Several flags lists in nfs3.x are not enums, which means they are not
    grouped in any way within nfs3_const except by name.  Make a dictionary
    and a cumulative mask called <name>_flags and <name>_mask.
    """
    flag_dict = {}
    mask = 0
    for var in dir(xdrdef.nfs3_const):
        if var.startswith(search_string):
            value = getattr(xdrdef.nfs3_const, var)
            flag_dict[value] = var
            mask |= value
    # Now we need to set the appropriate module level variable
    d = globals()
    d["%s_flags" % name.lower()] = flag_dict
    d["%s_mask" % name.lower()] = mask

set_flags("access", "ACCESS3_")

class NFSException(rpc.RPCError):
    pass

class BadRes(NFSException):
    """The NFS procedure returned some kind of error, ie is not NFS3_OK"""
    def __init__(self, proc, errcode, msg=None):
        self.proc = proc
        self.errcode = errcode
        if msg:
            self.msg = msg + ': '
        else:
            self.msg = ''
    def __str__(self):
        return self.msg + \
               "operation %s should return NFS3_OK, instead got %s" % \
               (proc, nfsstat3[self.errcode])

class UnexpectedRes(NFSException):
    """The NFS procedure returned OK, but had unexpected data"""
    def __init__(self, msg=""):
        self.msg = msg

    def __str__(self):
        if self.msg:
            return "Unexpected NFS result: %s" % self.msg
        else:
            return "Unexpected NFS result"

class InvalidRes(NFSException):
    """The NFS return is invalid, ie response is not to spec"""
    def __init__(self, msg=""):
        self.msg = msg

    def __str__(self):
        if self.msg:
            return "Invalid NFS result: %s" % self.msg
        else:
            return "Invalid NFS result"

class FancyNFS3Packer(NFS3Packer):
    """Handle dirlist3 and dirlistplus3 more cleanly than auto-generated methods"""

    def filter_dirlistplus3(self, data):
        """Change simple list of entryplus3 into strange chain structure"""
        out = []
        for e in data.entries[::-1]:
            # print("handle", e)
            # This reverses the direction of the list, so start with reversed
            out = [xdrdef.nfs3_type.entry3(e.cookie, e.name, e.fileid, e.attrs, e.handle, out)]
        # Must not modify original data structure
        return xdrdef.nfs3_type.dirlistplus3(out, data.eof)

    def filter_dirlist3(self, data):
        """Change simple list of entry3 into strange chain structure"""
        out = []
        for e in data.entries[::-1]:
            # print("handle", e)
            # This reverses the direction of the list, so start with reversed
            out = [xdrdef.nfs3_type.entry3(e.cookie, e.name, e.fileid, out)]
        # Must not modify original data structure
        return xdrdef.nfs3_type.dirlist3(out, data.eof)

class FancyNFS3Unpacker(NFS3Unpacker):
    def filter_dirlist3(self, data):
        """Return as simple list, instead of strange chain structure"""
        chain = data.entries
        list = []
        while chain:
            # Pop first entry off chain
            e = chain[0]
            chain = e.nextentry
            # Add to list
            e.nextentry = None # XXX Do we really want to do this?
            list.append(e)
        data.entries = list
        return data

    def filter_dirlistplus3(self, data):
        """Return as simple list, instead of strange chain structure"""
        chain = data.entries
        list = []
        while chain:
            # Pop first entry off chain
            e = chain[0]
            chain = e.nextentry
            # Add to list
            e.nextentry = None # XXX Do we really want to do this?
            list.append(e)
        data.entries = list
        return data

##########################################################

def printhex(str, pretty=True):
    """Print string as hex digits"""
    if pretty:
        print("".join(["%02x " % ord(c) for c in str]))
    else:
        # Can copy/paste this string
        print("".join(["\\x%02x" % ord(c) for c in str]))

def str_xor(a, b):
    """xor two string which represent binary data"""
    # Note assumes they are the same length
    # XXX There has to be a library function somewhere that does this
    return ''.join(map(lambda x:chr(ord(x[0])^ord(x[1])), zip(a, b)))

def random_string(size):
    """Returns a random string of given length."""
    return "".join([chr(random.randint(0, 255)) for i in range(size)])

##########################################################

def inc_u32(i):
    """Increment a 32 bit integer, with wrap-around."""
    return int( (i+1) & 0xffffffff )

def dec_u32(i):
    """Decrement a 32 bit integer, with wrap-around."""
    return int( (i-1) & 0xffffffff )

def xdrlen(str):
    """returns length in bytes of xdr encoding of str"""
    return (1 + ((3 + len(str)) >> 2)) << 2

def verify_time(t):
    if t.nseconds >= 1000000000:
        raise NFS4Error(NFS4ERR_INVAL)

def get_nfstime(t=None):
    """Convert time.time() output to nfstime4 format"""
    if t is None:
        t = time.time()
    sec = int(t)
    nsec = int((t - sec) * 1000000000)
    return xdrdef.nfs4_type.nfstime4(sec, nsec)

def parse_nfs_url(url):
    """Parse [nfs://]host:port/path, format taken from rfc 2224
       multipath addr:port pair are as such:

      $ip1:$port1,$ip2:$port2..

    Returns triple server, port, path.
    """
    p = re.compile(r"""
    (?:nfs://)?               # Ignore an optionally prepended 'nfs://'
    (?P<servers>[^/]+)
    (?P<path>/.*)?            # set path=everything else, must start with /
    $
    """, re.VERBOSE)

    m = p.match(url)
    if m:
        servers = m.group('servers')
        server_list = []

        for server in servers.split(','):
            server = server.strip()

            idx = server.rfind(':')
            bracket_idx = server.rfind(']')

            # the first : is before ipv6 addr ] -> no port specified
            if bracket_idx > idx:
                idx = -1

            if idx >= 0:
                host = server[:idx]
                port = server[idx+1:]
            else:
                host = server
                port = None

            # remove brackets around IPv6 addrs, if they exist
            if host.startswith('[') and host.endswith(']'):
                host = host[1:-1]

            port = (2049 if not port else int(port))
            server_list.append((host, port))

        path = os.fsencode(m.group('path'))
 
        return tuple(server_list), path
    else:
        raise ValueError("Error parsing NFS URL: %s" % url)

def path_components(path, use_dots=True):
    """Convert a string '/a/b/c' into an array ['a', 'b', 'c']"""
    out = []
    for c in path.split(b'/'):
        if c == b'':
            pass
        elif use_dots and c == b'.':
            pass
        elif use_dots and c == b'..':
            del out[-1]
        else:
            out.append(c)
    return out

class NFS3Error(Exception):
    def __init__(self, status, attrs=0, check_msg=None):
        self.status = status
        self.name = xdrdef.nfs3_const.nfsstat3[status]
        if check_msg is None:
            self.msg = "NFS3 error code: %s" % self.name
        else:
            self.msg = check_msg
        self.attrs = attrs

    def __str__(self):
        return self.msg

class NFS3Principal(object):
    """Encodes information needed to determine access rights."""
    def __init__(self, name, system=False):
        self.name = name
        self.skip_checks = system

    def member_of(self, group):
        """Returns True if self.name is a memeber of given group."""
        # STUB
        return False

    def __str__(self):
        return self.name

    def __eq__(self, other):
        # STUB - ignores mappings
        return self.name == other.name

    def __ne__(self, other):
        return not self.__eq__(other)

def check(res, expect=xdrdef.nfs3_const.NFS3_OK, msg=None):
    if res.status == expect:
        return
    if type(expect) is str:
        raise RuntimeError("You forgot to put 'msg=' in front "
                           "of check()'s string arg")
    # Get text representations
    desired = xdrdef.nfs3_const.nfsstat3[expect]
    received = xdrdef.nfs3_const.nfsstat3[res.status]
    if msg:
        failedop_name = msg
    elif res.resarray:
        failedop_name = xdrdef.nfs3_const.nfs_opnum3[res.resarray[-1].resop]
    else:
        failedop_name = 'Compound'
    msg = "%s should return %s, instead got %s" % \
          (failedop_name, desired, received)
    raise NFS3Error(res.status, check_msg=msg)

def use_obj(file):
    """File is either None, a fh, or a list of path components"""
    if file is None or file == [None]:
        return []
    elif type(file) is bytes:
        return [op4.putfh(file)]
    else:
        return [op4.putrootfh()] + [op4.lookup(comp) for comp in file]
