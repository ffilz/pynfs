import use_local # HACK so don't have to rebuild constantly
import rpc.rpc as rpc
from nfs3lib import FancyNFS3Unpacker
from xdrdef.sctrl_pack import SCTRLPacker, SCTRLUnpacker
from xdrdef.nfs3_type import *
from xdrdef.nfs3_const import *
from xdrdef.nfs3_pack import NFS3Packer, NFS3Unpacker
from xdrdef.mnt3_type import *
from xdrdef.mnt3_const import *
from xdrdef.mnt3_pack import MNT3Packer, MNT3Unpacker
from xdrdef.portmap_type import *
from xdrdef.portmap_const import *
from xdrdef.portmap_pack import PORTMAPPacker, PORTMAPUnpacker
import nfs_ops
import time, struct
import threading
import hmac
import os.path
import testmod

import traceback
import logging
logging.basicConfig(level=logging.INFO,
                    format="%(levelname)-7s:%(name)s:%(message)s")
log_cb = logging.getLogger("nfs.client.cb")

op3 = nfs_ops.NFS3ops()

class PORTMAPClient(rpc.Client):
    def __init__(self, host='localhost', port=PMAP_PORT):
        rpc.Client.__init__(self, PMAP_PROG, PMAP_VERS)
        self.server_address = (host, port)
        self._pipe = None

    def get_pipe(self):
        if not self._pipe or not self._pipe.is_active():
           self._pipe = self.connect(self.server_address)
        return self._pipe

    def proc_async(self, procnum, procarg, credinfo=None, pipe=None,
                   checks=True, packer=PORTMAPPacker):
        if credinfo is None:
            credinfo = self.default_cred
        if pipe is None:
            pipe = self.get_pipe()
        p = packer(check_enum=checks, check_array=checks)
        arg_packer = getattr(p, 'pack_%s' % procarg.__class__.__name__)
        arg_packer(procarg)
        return self.send_call(pipe, procnum, p.get_buffer(), credinfo)

    def proc(self, procnum, procarg, restypename, **kwargs):
        xid = self.proc_async(procnum, procarg, **kwargs)
        pipe = kwargs.get("pipe", None)
        res = self.listen(xid, restypename, pipe=pipe)
        return res

    def listen(self, xid, restypename, pipe=None, timeout=10.0):
        if pipe is None:
            pipe = self.get_pipe()
        header, data = pipe.listen(xid, timeout)
        if data:
            p = PORTMAPUnpacker(data)
            res_unpacker = getattr(p, 'unpack_%s' % restypename)
            data = res_unpacker()
        return data

    def get_port(self, prog, vers):
        arg = mapping(prog, vers, IPPROTO_TCP, 0)

        res = self.proc(PMAPPROC_GETPORT, arg, 'uint')
        return res

class Mnt3Client(rpc.Client):
    def __init__(self, host='localhost', port=None):
        rpc.Client.__init__(self, MOUNT_PROGRAM, MOUNT_V3)
        self.server_address = (host, port)
        self._pipe = None

    def get_pipe(self):
        if not self._pipe or not self._pipe.is_active():
            self._pipe = self.connect(self.server_address)
        return self._pipe

    def proc_async(self, procnum, procarg, credinfo=None, pipe=None,
                   checks=True, packer=MNT3Packer):
        if credinfo is None:
            credinfo = self.default_cred
        if pipe is None:
            pipe = self.get_pipe()
        p = packer(check_enum=checks, check_array=checks)
        arg_packer = getattr(p, 'pack_%s' % procarg.__class__.__name__)
        arg_packer(procarg)
        return self.send_call(pipe, procnum, p.get_buffer(), credinfo)

    def proc(self, procnum, procarg, restypename, **kwargs):
        xid = self.proc_async(procnum, procarg, **kwargs)
        pipe = kwargs.get("pipe", None)
        res = self.listen(xid, restypename, pipe=pipe)
        return res

    def listen(self, xid, restypename, pipe=None, timeout=10.0):
        if pipe is None:
            pipe = self.get_pipe()
        header, data = pipe.listen(xid, timeout)
        if data:
            p = MNT3Unpacker(data)
            res_unpacker = getattr(p, 'unpack_%s' % restypename)
            data = res_unpacker()
        return data

    def get_rootfh(self, export):

        class dirpath(str):
            pass

        log_cb.info("Mount Path %s", export)
        arg = export
        res = self.proc(MOUNTPROC3_MNT, arg, 'mountres3')
        check_mnt(res, msg="Mount failed on %s" % arg)
        return res.mountinfo.fhandle

class NFS3Client(rpc.Client):
    def __init__(self, host='localhost', port=None, ctrl_proc=16, summary=None):
        rpc.Client.__init__(self, 100003, 3)
        self.portmap = PORTMAPClient(host=host)
        self.mntport = self.portmap.get_port(MOUNT_PROGRAM, MOUNT_V3)
        if not port:
            self.port = self.portmap.get_port(100003, 3)
        else:
            self.port = port

        self.verifier = struct.pack('>d', time.time())
        self.server_address = (host, self.port)
        self.ctrl_proc = ctrl_proc
        self.summary = summary
        self._pipe = None
        self.mntclnt = Mnt3Client(host=host, port=self.mntport)

    def get_pipe(self):
        if not self._pipe or not self._pipe.is_active():
            self._pipe = self.connect(self.server_address)
        return self._pipe

    def set_cred(self, credinfo):
        self.default_cred = credinfo

    def null_async(self, data=b''):
        return self.send_call(self.get_pipe(), 0, data)

    def null(self, *args, **kwargs):
        xid = self.null_async(*args, **kwargs)
        return self.listen(xid)

    def proc_async(self, procnum, procarg, credinfo=None, pipe=None,
                   checks=True, packer=NFS3Packer):
        if credinfo is None:
            credinfo = self.default_cred
        if pipe is None:
            pipe = self.get_pipe()
        p = packer(check_enum=checks, check_array=checks)
        arg_packer = getattr(p, 'pack_%s' % procarg.__class__.__name__)
        arg_packer(procarg)
        return self.send_call(pipe, procnum, p.get_buffer(), credinfo)


    def proc(self, procnum, procarg, restypename, **kwargs):
        xid = self.proc_async(procnum, procarg, **kwargs)
        pipe = kwargs.get("pipe", None)
        res = self.listen(xid, restypename, pipe=pipe)
        if self.summary:
            self.summary.show_op('call v3 %s:%s' % self.server_address,
                [ procarg.__class__.__name__.lower()[:-1 * len('3args')] ],
                nfsstat3[res.status])
        return res

    def listen(self, xid, restypename=None, pipe=None, timeout=10.0):
        if pipe is None:
            pipe = self.get_pipe()
        header, data = pipe.listen(xid, timeout)
        if data and restypename is not None:
            p = FancyNFS3Unpacker(data)
            res_unpacker = getattr(p, 'unpack_%s' % restypename)
            data = res_unpacker()
        return data

#########################################
debug_fail = False

def check_mnt(res, stat=MNT3_OK, msg=None, warnlist=[]):

    if type(stat) is str:
        raise "You forgot to put 'msg=' in front of check's string arg"

    if msg is None:
        raise "You forgot to include msg"

    statlist = stat
    if type(statlist) == int:
        statlist = [stat]

    log_cb.debug("checking %r == %r" % (res, statlist))
    if res.fhs_status in statlist:
        if not (debug_fail and msg):
            return

    statnames = [mountstat3[stat] for stat in statlist]
    desired = ' or '.join(statnames)
    if not desired:
        desired = 'one of <none>'

    received = mountstat3[res.fhs_status]
    failedop_name = msg
    msg = "%s should return %s, instead got %s" % \
          (failedop_name, desired, received)
    if res.fhs_status in warnlist:
        raise testmod.WarningException(msg)
    else:
        raise testmod.FailureException(msg)
