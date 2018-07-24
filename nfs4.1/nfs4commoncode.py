"""Code that is 'almost' shared between client and server.

(As opposed to library routines, which would be in nfs4lib.py.)
"""

import nfs4lib
from xdrdef.nfs4_const import *
import sys
import xdrdef.nfs4_type, xdrdef.nfs4_const
from xdrdef.nfs4_type import *

_d = {"CompoundState" : "CompoundState",
      "PairedResults" : "PairedResults",
      "CompoundArgResults" : "CompoundArgResults",
      "encode_status" : "encode_status",
      "nfs_resop4" : "nfs_resop4",
      "nfs_opnum4" : "nfs_opnum4",
      "mangle" : '"op" + name_l',
      }

_cb_d = {"CompoundState" : "CBCompoundState",
         "PairedResults" : "CBPairedResults",
         "CompoundArgResults" : "CBCompoundArgResults",
         "encode_status" : "cb_encode_status",
         "nfs_resop4" : "nfs_cb_resop4",
         "nfs_opnum4" : "nfs_cb_opnum4",
         "mangle" : '"opcb" + name_l[3:]',
         }

code_str = '''\
def %(encode_status)s_by_name(name, status, *args, **kwargs):
    """ returns %(nfs_resop4)s(OP_NAME, opname=NAME4res(status, *args)) """
    tag = kwargs.pop("msg", None)
    name_l = name.lower()
    name_u = name.upper()
    try:
        res4 = getattr(xdrdef.nfs4_type, name_u + "4res")(status, *args, **kwargs)
        result = %(nfs_resop4)s(getattr(xdrdef.nfs4_const, "OP_" + name_u))
        setattr(result, %(mangle)s, res4)
        # STUB XXX 4.1 has messed with the naming conventions,
        #      and added prefixes to the "status" variable. Grrr.
        result.status = status # This is a HACK to deal.
        if tag:
            result.tag = tag
        return result
    except StandardError:
        raise
        pass
    raise RuntimeError("Problem with name %%r" %% name)
        
def %(encode_status)s(status, *args, **kwargs):
    """Called from function op_<name>, encodes the operations response.

    Basically, we want to find:
    result = nfs_resop4(OP_NAME, opname=NAME4res(status, *args))
    """
    funct_name = sys._getframe(1).f_code.co_name # Name of calling function
    if funct_name.startswith("op_"):
        return %(encode_status)s_by_name(funct_name[3:], status, *args, **kwargs)
    else:
        raise RuntimeError("Cannot call from %%r" %% funct_name)

class %(CompoundArgResults)s(object):
    size = property(lambda s: s._base_len + nfs4lib.xdrlen(s._env.tag))
    tag = property(lambda s: s.prefix + s._env.tag)
    
    def __init__(self, env, prefix=""):
        self.status = NFS4_OK # Generally == self.results[-1].status
        self.results = [] # Array of nfs_resop4 structures
        self.packed = [] # Corresponding XDR encoded nfs_resop4 structures
        self.prefix = prefix # String to prepend onto COMPOUND tag
        self._base_len = 8 # status + arraysize
        self._p = nfs4lib.FancyNFS4Packer()
        self._env = env

    def append(self, result):
        """Add an nfs_resop4 structure to our list"""
        self.status = result.status
        self.results.append(result)
        self._p.reset()
        self._p.pack_%(nfs_resop4)s(result)
        self.packed.append(self._p.get_buffer())
        self._base_len += len(self.packed[-1])

    def __getitem__(self, key):
        return self.results[key]

    def __len__(self):
        return len(self.results)

class %(PairedResults)s(object):
    """Deal with fact that sent result and cached result are not the same"""
    def __init__(self, env):
        self.env = env
        self.reply = %(CompoundArgResults)s(env)
        self.cache = %(CompoundArgResults)s(env, prefix="[REPLAY] ")

    def append(self, result):
        if hasattr(result, "tag"):
            self.env.tag_msg(result.tag)
        self.reply.append(result)
        # Basically, ignoring size checks, this does:
        #    if self.env.cacheing:
        #        self.cache = self.reply
        #    else:
        #        self.cache = self.reply[0:1] + [NFS4ERR_RETRY_UNCACHED_REP]
        #                        ^
        #                         \should be SEQ
        
        # STUB - do size checking on self.reply
        if self.env.caching or self.env.index == 0:
            self.cache.append(result)
            # STUB - do size checking on self.cache
        elif self.env.index == 1:
            name = %(nfs_opnum4)s[result.resop].lower()[3:]
            res = %(encode_status)s_by_name(name, NFS4ERR_RETRY_UNCACHED_REP)
            self.cache.append(res)
        else:
            pass

    def set_empty_return(self, status, tag=None):
        self.reply.status = self.cache.status = status
        if tag is not None:
            self.env.tag = tag
        
    # Generally make class behave like self.reply
    def __getitem__(self, key):
        return self.reply[key]

    def __len__(self):
        return len(self.reply)

class %(CompoundState)s(object):
    """ We hold here all the interim state the server needs to remember
    
    as it handles each operation in turn.
    """
    def __init__(self, args, cred):
        # Interim state generated by operations
        # XXX NOTE init fhs to something that if used raises NOFH error
        self.cfh = None # Current filehandle
        self.sfh = None # Saved filehandle
        self.cid = None # Current stateid
        self.sid = None # Saved stateid
        self.caching = True # Cache the response
        # XXX Do we want a setter funct, since resetting would be bad?
        self.cache = None # Where to cache it, of type Cache
        self.session = None

        # Access to args, since operations sometimes need access to others
        self.req_size = args.req_size
        self.argarray = args.argarray
        self.index = -1
        self.cred = cred # XXX pull out needed info?
        self.principal = self.get_principal(cred)
        self.mech = None
        self.connection = self.get_connection(cred)
        self.header_size = self.get_header_size(cred)
        # Access to results, needed by some ops, and of course by COMPOUND
        self.tag = args.tag # This will be the returned tag
        self.results = %(PairedResults)s(self)

    def tag_msg(self, msg):
        # STUB - put some sort of check here to enable/disable this funct
        self.tag = msg

    def get_principal(self, cred):
        """Pull principal from credential"""
        return nfs4lib.NFS4Principal(cred.credinfo.principal)

    def get_sec_triple(self, cred):
        """Pull security triple of (OID, QOP, service) from cred"""
        # STUB
        return 0
    
    def get_connection(self, cred):
        """Pull connection id from credential"""
        return cred.connection

    def get_header_size(self, cred):
        """Pull size of RPC header from credential"""
        return cred.header_size

    def set_cfh(self, fh, state=nfs4lib.state00):
        """Normally, need to clear cid when set cfh.

        See draft22 16.2.3.1.2.
        """
        self.cfh, self.cid = fh, state
'''

# Create normal code
exec(code_str % _d)

# Create callback code
exec(code_str % _cb_d)

