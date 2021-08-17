#
# environment.py
#
# Requires python 3.2
#
# Written by Fred Isaman <iisaman@citi.umich.edu>
# Copyright (C) 2004 University of Michigan, Center for
#                    Information Technology Integration
#

import time
import testmod
from xdrdef.nfs3_const import *
from xdrdef.nfs3_type import *
import xdrdef.nfs3_type as type3
import rpc.rpc as rpc
import nfs3client
import sys
import os
import nfs3lib
from nfs3lib import use_obj
import logging
import struct
from rpc.security import AuthSys, AuthGss
from threading import Lock
import nfs_ops
op3 = nfs_ops.NFS3ops()

log = logging.getLogger("test.env")

class Environment(testmod.Environment):
    # STUB
    home = property(lambda s: use_obj(s.opts.home))

    def __init__(self, opts):
        self._lock = Lock()
        self.opts = opts
        self.c1 = nfs3client.NFS3Client(opts.server, opts.port)
        s1 = rpc.security.instance(opts.flavor)
        if opts.flavor == rpc.AUTH_NONE:
            self.cred1 = s1.init_cred()
        elif opts.flavor == rpc.AUTH_SYS:
            log.info("Machine name %s" % opts.machinename)
            self.cred1 = s1.init_cred(uid=opts.uid, gid=opts.gid, name=opts.machinename)
        elif opts.flavor == rpc.RPCSEC_GSS:
            call = self.c1.make_call_function(self.c1.c1, 0,
                                              self.c1.default_prog,
                                              self.c1.default_vers)
            krb5_cred = AuthGss().init_cred(call, target="nfs@%s" % opts.server)
            krb5_cred.service = opts.service
            self.cred1 = krb5_cred
        self.c1.set_cred(self.cred1)
        #self.cred2 = AuthSys().init_cred(uid=1111, gid=37, name=b"first")
        if opts.uid == 0:
            self.uid2 = 1001
            self.gid2 = 1001
        else:
            self.uid1 = opts.uid + 1
            self.uid2 = opts.gid + 1
        self.cred2 = AuthSys().init_cred(uid=self.uid2, gid=self.gid2, name=b"second")
        self.rootcred = AuthSys().init_cred(uid=0, gid=0, name=b"root")

        opts.home = opts.path + b'/tmp'
        self.c1.homedir = opts.home
        # Put this after client creation, to ensure _last_verf bigger than
        # any natural client verifiers
        self.timestamp = int(time.time())
        self._last_verf = self.timestamp + 1
        self.filedata = b"This is the file test data."
        self.linkdata = b"/etc/X11"

        log.info("Created client to %s, %i" % (opts.server, opts.port))

    def init(self):
        """Run once before any test is run"""

        """Everyone needs to mount"""
        log.info("Path %s", self.opts.path)
        self.rootfh = type3.nfs_fh3(self.c1.mntclnt.get_rootfh(self.opts.path))

        """Now see if there's any other initialization"""
        if self.opts.noinit:
            return

        if self.opts.maketree:
            self._maketree()

        # Make sure it is empty
        clean_dir(self)

    def _maketree(self):
        """Make test tree"""
        # ensure /tree exists and is empty
        tree = b'tree'
        path = make_path(self.opts.home, tree)
        log.info("About to setup %s" % path)
        res = self.lookup(self.rootfh, tree)
        if res.status == NFS3ERR_NOENT:
            res = self.mkdir(self.rootfh, tree)
            check(res, msg="Trying to create /%s," % path)
            tree_fh = res.resok.obj
        else:
            check(res, msg="Lookup for %s" % path)
            log.info("Path %s exists, cleaning" % path)
            tree_fh = res.resok.object
            clean_dir(self, tree_fh)

        name = b'socket'
        res = self.mknod(tree_fh, name, NF3SOCK)
        check(res, msg="Trying to create %s," % make_path2(self.opts.home, tree, name))
        name = b'fifo'
        res =  self.mknod(tree_fh, name, NF3FIFO)
        check(res, msg="Trying to create %s," % make_path2(self.opts.home, tree, name))
        name = b'link'
        res = self.symlink(tree_fh, name, data=self.linkdata)
        check(res, msg="Trying to create %s," % make_path2(self.opts.home, tree, name))
        name = b'block'
        res =  self.mknod(tree_fh, name, NF3BLK, major=1, minor=2)
        check(res, msg="Trying to create %s," % make_path2(self.opts.home, tree, name))
        name = b'char'
        res =  self.mknod(tree_fh, name, NF3CHR, major=1, minor=2)
        check(res, msg="Trying to create %s," % make_path2(self.opts.home, tree, name))
        name = b'dir'
        res = self.mkdir(tree_fh, name)
        check(res, msg="Trying to create %s," % make_path2(self.opts.home, tree, name))
        name = b'file'
        res = self.create(tree_fh, name)
        check(res, msg="Trying to create %s," % make_path2(self.opts.home, tree, name))

    def finish(self):
        """Run once after all tests are run"""
        if self.opts.nocleanup:
            return
        clean_dir(self)
        self.null()

    def startUp(self):
        """Run before each test"""
        log.debug("Sending pretest NULL")
        self.null()
        log.debug("Got pretest NULL response")

    def sleep(self, sec, msg=''):
        """Sleep for given seconds"""
        log.info("Sleeping for %i seconds: %s" % (sec, msg))
        time.sleep(sec)
        log.info("Woke up")

    def serverhelper(self, args):
        """Perform a special operation on the server side (such as
        rebooting the server)"""
        if self.opts.serverhelper is None:
            print("Manual operation required on server:")
            print(args + " and hit ENTER when done")
            sys.stdin.readline()
            print("Continuing with test")
        else:
            cmd = self.opts.serverhelper
            if self.opts.serverhelperarg:
                cmd += ' ' + self.opts.serverhelperarg
            cmd += ' ' + args
            os.system(cmd);

    def new_verifier(self):
        """Returns a never before used verifier"""
        candidate = int(time.time())
        self._lock.acquire()
        try:
            if candidate <= self._last_verf:
                candidate = self._last_verf + 1
            self._last_verf = candidate
        finally:
            self._lock.release()
        return struct.pack('>d', candidate)

    def testname(self, t):
        """Returns a name for the test that is unique between runs"""
        return b"%s_%i" % (os.fsencode(t.code), self.timestamp)


    def sattr3_helper(self, mode=None, uid=None, gid=None,
                      size=None, atime=None, mtime=None):
        if atime == 'server':
            ats = 1
            atime = type3.nfstime3(0, 0)
        elif atime is not None:
            ats = 2
        else:
            ats = 0
        if mtime == 'server':
            mts = 1
            mtime = type3.nfstime3(0, 0)
        elif mtime is not None:
            mts = 2
        else:
            mts = 0
        return type3.sattr3(
                type3.set_mode3(mode is not None, mode),
                type3.set_uid3(uid is not None, uid),
                type3.set_gid3(gid is not None, gid),
                type3.set_size3(size is not None, size),
                type3.set_atime(ats, atime),
                type3.set_mtime(mts, mtime))

    """
    BASIC NFS3 OPERATIONS
    """

    def null(self):
        return self.c1.null()

    def getattr(self, file_handle=None):
        return self.c1.proc(NFSPROC3_GETATTR, file_handle, 'GETATTR3res')

    def setattr(self, file_handle=None, mode=None, uid=None, gid=None,
                size=None, atime=None, mtime=None,
                guard_check=False, guard_time=None):
        arg = type3.SETATTR3args(file_handle,
            self.sattr3_helper(mode, uid, gid, size, atime, mtime),
            sattrguard3(guard_check, guard_time))
        return self.c1.proc(NFSPROC3_SETATTR, arg, 'SETATTR3res')

    def lookup(self, dir_fh=None, name=None):
        arg = type3.diropargs3(dir_fh, name)
        return self.c1.proc(NFSPROC3_LOOKUP, arg, 'LOOKUP3res')

    def access(self, file_handle=None, access=None):
        arg = type3.ACCESS3args(file_handle, access)
        return self.c1.proc(NFSPROC3_ACCESS, arg, 'ACCESS3res')

    def readlink(self, link_fh=None):
        arg = type3.nfs_fh3(link_fh)
        return self.c1.proc(NFSPROC3_READLINK, arg, 'READLINK3res')

    def read(self, file_handle=None, offset=0, count=0):
        arg = type3.READ3args(file_handle, offset, count)
        return self.c1.proc(NFSPROC3_READ, arg, 'READ3res')

    def write(self, file_handle=None, offset=0, count=0, stable=None,
              data=None):
        arg = type3.WRITE3args(file_handle, offset, count, stable, data)
        return self.c1.proc(NFSPROC3_WRITE, arg, 'WRITE3res')

    def create(self, dir_fh=None, name=None, nfs3_mode=UNCHECKED,
               mode=None, uid=None, gid=None, size=None,
               atime=None, mtime=None, exclusive_verf=0):
        arg = type3.CREATE3args(
            type3.diropargs3(dir_fh, name),
            type3.createhow3(nfs3_mode,
                self.sattr3_helper(mode, uid, gid, size, atime, mtime),
                exclusive_verf))
        return self.c1.proc(NFSPROC3_CREATE, arg, 'CREATE3res')

    def mkdir(self, parent_fh=None, name=None, mode=None, uid=None,
              gid=None, size=None, atime=None, mtime=None):
        arg = type3.MKDIR3args(type3.diropargs3(parent_fh, name),
            self.sattr3_helper(mode, uid, gid, size, atime, mtime))
        return self.c1.proc(NFSPROC3_MKDIR, arg, 'MKDIR3res')

    def symlink(self, dir_fh=None, link_name=None, mode=None, uid=None,
                gid=None, size=None, atime=None, mtime=None, data=None):
        arg = type3.SYMLINK3args(
            type3.diropargs3(dir_fh, link_name),
            type3.symlinkdata3(
                self.sattr3_helper(mode, uid, gid, size, atime, mtime),
                data))
        return self.c1.proc(NFSPROC3_SYMLINK, arg, 'SYMLINK3res')

    def mknod(self, dir_fh=None, name=None, type=None, mode=None, uid=None,
              gid=None, size=None, atime=None, mtime=None, major=1, minor=1):
        attr = self.sattr3_helper(mode, uid, gid, size, atime, mtime)
        devd = type3.specdata3(major, minor)
        arg = type3.MKNOD3args(type3.diropargs3(dir_fh, name),
                       type3.mknoddata3(type, type3.devicedata3(attr, devd),
                                        attr))
        return self.c1.proc(NFSPROC3_MKNOD, arg, 'MKNOD3res')

    def remove(self, dir_handle=None, file_name=None):
        arg = type3.diropargs3(dir_handle, file_name)
        return self.c1.proc(NFSPROC3_REMOVE, arg, 'REMOVE3res')

    def rmdir(self, parent_dir_handle=None, target_dir_name=None):
        arg=type3.diropargs3(parent_dir_handle, target_dir_name)
        return self.c1.proc(NFSPROC3_RMDIR, arg, 'RMDI3res')

    def rename(self, old_parent_fh=None, old_file=None, new_parent_fh=None,
               new_file=None):
        arg = type3.RENAME3args(type3.diropargs3(old_parent_fh, old_file),
                                type3.diropargs3(new_parent_fh, new_file))
        return self.c1.proc(NFSPROC3_RENAME, arg, 'RENAME3res')

    def link(self, target_file_fh=None, dir_fh=None, link_name=None):
        arg = type3.LINK3args(target_file_fh,
                              type3.diropargs3(dir_fh, link_name))
        return self.c1.proc(NFSPROC3_LINK, arg, 'LINK3res')

    def readdir(self, dir_fh=None, cookie=0, cookieverf='0', count=0):
        if type(cookieverf) is not str:
            cookieverf = cookieverf.__str__()
        arg = type3.READDIR3args(dir_fh, cookie, bytes(cookieverf, 'utf-8'),
                                 count)
        return self.c1.proc(NFSPROC3_READDIR, arg, 'READDIR3res')

    def readdirplus(self, dir_fh=None, cookie=0, cookieverf='0', dircount=0, maxcount=0):
        if type(cookieverf) is not str:
            cookieverf = cookieverf.__str__()
        arg = type3.READDIRPLUS3args(dir_fh, cookie, bytes(cookieverf, 'utf-8'),
                                     dircount, maxcount)
        return self.c1.proc(NFSPROC3_READDIRPLUS, arg, 'READDIRPLUS3res')

    def fsstat(self, file_fh=None):
        arg = type3.nfs_fh3(file_fh)
        return self.c1.proc(NFSPROC3_FSSTAT, arg, 'FSSTAT3res')

    def fsinfo(self, file_fh=None):
        arg = type3.nfs_fh3(file_fh)
        return self.c1.proc(NFSPROC3_FSINFO, arg, 'FSINFO3res')

    def pathconf(self, file_fh=None):
        arg = type3.nfs_fh3(file_fh)
        return self.c1.proc(NFSPROC3_PATHCONF, arg, 'PATHCONF3res')

    def commit(self, file_fh=None, offset=0, count=0):
        arg = type3.COMMIT3args(file_fh, offset, count)
        return self.c1.proc(NFSPROC3_COMMIT, arg, 'COMMIT3res')

#########################################
debug_fail = False

def fail(msg):
    raise testmod.FailureException(msg)

def check(res, stat=NFS3_OK, msg=None, warnlist=[]):

    if type(stat) is str:
        raise "You forgot to put 'msg=' in front of check's string arg"

    if msg is None:
        raise "You forgot to include msg"

    statlist = stat
    if type(statlist) == int:
        statlist = [stat]

    log.debug("checking %r == %r" % (res, statlist))
    if res.status in statlist:
        if not (debug_fail and msg):
            return

    statnames = [nfsstat3[stat] for stat in statlist]
    desired = ' or '.join(statnames)
    if not desired:
        desired = 'one of <none>'

    received = nfsstat3[res.status]
    failedop_name = msg
    msg = "%s should return %s, instead got %s" % \
          (failedop_name, desired, received)
    if res.status in warnlist:
        raise testmod.WarningException(msg)
    else:
        raise testmod.FailureException(msg)

def checkdict(expected, got, translate={}, failmsg=''):
    if failmsg: failmsg += ': '
    for k in expected:
        if k not in got:
            try:
                name = translate[k]
            except KeyError:
                name = str(k)
            raise testmod.FailureException(failmsg +
                          "For %s expected %s, but no value returned" %
                          (name, str(expected[k])))
        if expected[k] != got[k]:
            try:
                name = translate[k]
            except KeyError:
                name = str(k)
            raise testmod.FailureException(failmsg +
                          "For %s expected %s, got %s" %
                          (name, str(expected[k]), str(got[k])))

def compareTimes(time1, time2):
    """Compares nfstime4 values

    Returns -1 if time1 < time2
             0 if time1 ==time2
             1 if time1 > time2
    """

    if time1.seconds < time2.seconds:
        return -1
    elif time1.seconds > time2.seconds:
        return 1
    else: # time1.seconds == time2.seconds:
        if time1.nseconds < time2.nseconds:
            return -1
        elif time1.nseconds > time2.nseconds:
            return 1
        else:
            return 0

#############################################

def clean_dir(env, parent=None):
    if parent is None:
        parent = env.rootfh

    entries = do_readdirplus(env, parent)
    for e in entries:
        # don't delete entries starting with '.'
        t = str(e.name, 'utf-8')
        if t[0] is not '.':
            res = env.setattr(e.name_handle, mode=0o755)
            check(res, msg="Setting mode on %s" % repr(e.name))

            arg = type3.diropargs3(parent, e.name)
            if e.name_attributes.attributes.type is NF3DIR:
                prc = NFSPROC3_RMDIR
                rsp = 'RMDIR3res'
            else:
                prc = NFSPROC3_REMOVE
                rsp = 'REMOVE3res'
            res = env.c1.proc(prc, arg, rsp)
            if res.status == NFS3ERR_NOTEMPTY:
                clean_dir(env, e.name_handle)
                res = env.c1.proc(prc, arg, rsp)
            check(res, msg="Trying to remove %s" % str(e.name, 'utf-8'))

def do_readdir(env, parent, cookie=0, cookieverf=b'', count=4096):
    # Since we may not get whole directory listing in one readdir request,
    # loop until we do. For each request result, create a flat list
    # with <entry4> objects.
    log.info("Called do_readdir()")
    entries = []

    while True:
        res = env.readdir(parent, cookie, cookieverf, count)
        check(res, msg="READDIR with cookie=%i, count=%i" % (cookie, count))
        reply = res.resok.reply
        if not reply.entries and not reply.eof:
            raise UnexpectedRes("READDIR had no entries")
        entries.extend(reply.entries)
        if reply.eof:
            break
        cookie = entries[-1].cookie
        cookieverf = res.resok.cookieverf
    # log.info("do_readdir() = %r" % entries)
    return entries

def do_readdirplus(env, parent, cookie=0, cookieverf=b'', dircount=4096,
                   maxcount=4096):
    # Since we may not get whole directory listing in one readdir request,
    # loop until we do. For each request result, create a flat list
    # with <entry4> objects.
    log.info("Called do_readdirplus()")
    entries = []

    while True:
        res = env.readdirplus(parent, cookie, cookieverf, dircount, maxcount)
        check(res, msg="READDIRPLUS with cookie=%i, dircount=%i, maxcount=%i" % (cookie, dircount, maxcount))
        reply = res.resok.reply
        if not reply.entries and not reply.eof:
            raise UnexpectedRes("READDIRPLUS had no entries")
        entries.extend(reply.entries)
        if reply.eof:
            break
        cookie = entries[-1].cookie
        cookieverf = res.resok.cookieverf
    # log.info("do_readdirplus() = %r" % entries)
    return entries

def make_path(dir, file):
    return str(dir, 'utf-8') + '/' + str(file, 'utf-8')

def make_path2(dir, file1, file2):
    return str(dir, 'utf-8') + '/' + str(file1, 'utf-8') + \
                               '/' + str(file2, 'utf-8')

def checkvalid(cond, failmsg):
    if not cond: raise testmod.FailureException(failmsg)

def compare_fattr3(attr1, attr2):
    return attr1.type           == attr2.type and \
           attr1.mode           == attr2.mode and \
           attr1.nlink          == attr2.nlink and \
           attr1.uid            == attr2.uid and \
           attr1.gid            == attr2.gid and \
           attr1.size           == attr2.size and \
           attr1.used           == attr2.used and \
           attr1.rdev.specdata1 == attr2.rdev.specdata1 and \
           attr1.rdev.specdata2 == attr2.rdev.specdata2 and \
           attr1.fsid           == attr2.fsid and \
           attr1.fileid         == attr2.fileid and \
           attr1.atime.seconds  == attr2.atime.seconds and \
           attr1.atime.nseconds == attr2.atime.nseconds and \
           attr1.mtime.seconds  == attr2.mtime.seconds and \
           attr1.mtime.nseconds == attr2.mtime.nseconds and \
           attr1.ctime.seconds  == attr2.ctime.seconds and \
           attr1.ctime.nseconds == attr2.ctime.nseconds
