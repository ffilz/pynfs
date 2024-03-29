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
from nfs4lib import NFS4Client, get_attrbitnum_dict
from xdrdef.nfs4_const import *
from xdrdef.nfs4_type import fsid4, nfsace4, fs_locations4, fs_location4, \
     specdata4, nfstime4, settime4, stateid4
import rpc.rpc as rpc
import sys
import os
import nfs_ops
op = nfs_ops.NFS4ops()

class AttrInfo(object):
    def __init__(self, name, access, sample):
        self.name = name
        self.bitnum = get_attrbitnum_dict()[name]
        self.mask = 2**self.bitnum
        self.access = access
        self.sample = sample

    def __str__(self):
        return '%s %i %s' % (self.name, self.bitnum, self.access)

    writable = property(lambda self: 'w' in self.access)
    readable = property(lambda self: 'r' in self.access)
    mandatory = property(lambda self: 'm' in self.access)
    readonly = property(lambda self: \
                         'r' in self.access and 'w' not in self.access)
    writeonly = property(lambda self: \
                         'w' in self.access and 'r' not in self.access)

class Environment(testmod.Environment):
    # STUB
    attr_info = [ \
        AttrInfo('supported_attrs', 'rm', []),
        AttrInfo('type', 'rm', 1),
        AttrInfo('fh_expire_type', 'rm', 0),
        AttrInfo('change', 'rm', 0),
        AttrInfo('size', 'rwm', 0),
        AttrInfo('link_support', 'rm', False),
        AttrInfo('symlink_support', 'rm', False),
        AttrInfo('named_attr', 'rm', False),
        AttrInfo('fsid', 'rm', fsid4(0, 0)),
        AttrInfo('unique_handles', 'rm', False),
        AttrInfo('lease_time', 'rm', 0),
        AttrInfo('rdattr_error', 'rm', 0),
        AttrInfo('filehandle', 'rm', b'nonsense'),
        AttrInfo('acl', 'rw', [nfsace4(0,0,0,b'EVERYONE@')]),
        AttrInfo('aclsupport', 'r', 0),
        AttrInfo('archive', 'rw', False),
        AttrInfo('cansettime', 'r', False),
        AttrInfo('case_insensitive', 'r', False),
        AttrInfo('case_preserving', 'r', False),
        AttrInfo('chown_restricted', 'r', False),
        AttrInfo('fileid', 'r', 0),
        AttrInfo('files_avail', 'r', 0),
        AttrInfo('files_free', 'r', 0),
        AttrInfo('files_total', 'r', 0),
        # FRED - packer did not complain about missing [] about server
        AttrInfo('fs_locations', 'r',
                 fs_locations4([b'root'],
                     [fs_location4([b'server'],[b'path'])])),
        AttrInfo('hidden', 'rw', False),
        AttrInfo('homogeneous', 'r', False),
        AttrInfo('maxfilesize', 'r', 0),
        AttrInfo('maxlink', 'r', 0),
        AttrInfo('maxname', 'r', 0),
        AttrInfo('maxread', 'r', 0),
        AttrInfo('maxwrite', 'r', 0),
        AttrInfo('mimetype', 'rw', b'nonsense'),
        AttrInfo('mode', 'rw', 0),
        AttrInfo('no_trunc', 'r', False),
        AttrInfo('numlinks', 'r', 0),
        AttrInfo('owner', 'rw', b'nonsense'),
        AttrInfo('owner_group', 'rw', b'nonsense'),
        AttrInfo('quota_avail_hard', 'r', 0),
        AttrInfo('quota_avail_soft', 'r', 0),
        AttrInfo('quota_used', 'r', 0),
        AttrInfo('rawdev', 'r', specdata4(0, 0)),
        AttrInfo('space_avail', 'r', 0),
        AttrInfo('space_free', 'r', 0),
        AttrInfo('space_total', 'r', 0),
        AttrInfo('space_used', 'r', 0),
        AttrInfo('system', 'rw', False),
        AttrInfo('time_access', 'r', nfstime4(0, 0)),
        AttrInfo('time_access_set', 'w', settime4(0)),
        AttrInfo('time_backup', 'rw', nfstime4(0, 0)),
        AttrInfo('time_create', 'rw', nfstime4(0, 0)),
        AttrInfo('time_delta', 'r', nfstime4(0, 0)),
        AttrInfo('time_metadata', 'r', nfstime4(0, 0)),
        AttrInfo('time_modify', 'r', nfstime4(0, 0)),
        AttrInfo('time_modify_set', 'w', settime4(0)),
        AttrInfo('mounted_on_fileid', 'r', 0),
        ]

    def __init__(self, opts):
        sec1, sec2 = self._get_security(opts)
#        authsys1 = rpc.SecAuthSys(0, opts.machinename, opts.uid, opts.gid, [])
        authsys2 = rpc.SecAuthSys(0, opts.machinename, opts.uid+1, opts.gid+1, [])
        self.c1 = NFS4Client(b'client1_pid%i' % os.getpid(),
                             opts.server, opts.port, opts.path,
                             sec_list=[sec1], opts=opts)
        self.c2 = NFS4Client(b'client2_pid%i' % os.getpid(),
                             opts.server, opts.port, opts.path,
                             sec_list=[authsys2], opts=opts)
        self.longname = b"a"*512
        self.uid = 0
        self.gid = 0
        self.opts = opts
        self.filedata = b"This is the file test data."
        self.linkdata = b"/etc/X11"
        self.stateid0 = stateid4(0, b'')
        self.stateid1 = stateid4(0xffffffff, b'\xff'*12)

    def _get_security(self, opts):
        if opts.security == 'none':
            return [opts.flavor(), opts.flavor()]
        elif opts.security == 'sys':
            sec1 = opts.flavor(0, opts.machinename, opts.uid, opts.gid, [])
            sec2 = opts.flavor(0, opts.machinename, opts.uid+1, opts.gid+1, [])
            return [sec1, sec2]
        elif opts.security.startswith('krb5'):
            sec1 = opts.flavor(opts.service)
            sec2 = opts.flavor(opts.service)
            return [sec1, sec2]
        else:
            raise 'Bad security %s' % opts.security

    def init(self):
        """Run once before any test is run"""
        c = self.c1
        if self.opts.maketree:
            self._maketree()
        if self.opts.noinit:
            return
        # Make sure opts.path exists
        res = c.compound(c.use_obj(self.opts.path))
        check(res, msg="Could not LOOKUP /%s," % b'/'.join(self.opts.path))
        # Make sure it is empty
        c.clean_dir(self.opts.path)
        c.null()

    def _maketree(self):
        """Make testtree"""
        c = self.c1
        # make /tmp (and path leading up to it if necesary)
        path = []
        for comp in self.opts.path:
            path.append(comp)
            res = c.compound(c.use_obj(path))
            check(res, [NFS4_OK, NFS4ERR_NOENT],
                  "Could not LOOKUP /%s," % (b'/'.join(path)))
            if res.status == NFS4ERR_NOENT:
                res = c.create_obj(path)
                check(res, msg="Trying to create /%s," % b'/'.join(path))
        # remove /tree/*
        tree = self.opts.path[:-1] + [b'tree']
        res = c.compound(c.use_obj(tree))
        check(res, [NFS4_OK, NFS4ERR_NOENT])
        if res.status == NFS4ERR_NOENT:
            res = c.create_obj(tree)
            check(res, msg="Trying to create /%s," % b'/'.join(tree))
        else:
            c.clean_dir(tree)
        
        # make objects in /tree
        name = {NF4DIR: b'dir',
                NF4SOCK: b'socket',
                NF4FIFO: b'fifo',
                NF4LNK: b'link',
                NF4BLK: b'block',
                NF4CHR: b'char'}
        for type in name:
            path = tree + [name[type]]
            res = c.create_obj(path, type)
            if res.status != NFS4_OK:
                print("WARNING - could not create /%s" % b'/'.join(path))
        c.init_connection()
        fh, stateid = c.create_confirm(b'maketree', tree + [b'file'],
                                       deny=OPEN4_SHARE_DENY_NONE)
        ops = [op.putfh(fh),
               op.write(stateid, 0, FILE_SYNC4, self.filedata)]
        res = c.compound(ops)
        check(res, msg="Writing data to /%s/file" % b'/'.join(tree))
        res = c.close_file(b'maketree', fh, stateid )
        check(res)
            
    def finish(self):
        """Run once after all tests are run"""
        if self.opts.nocleanup:
            return
        c = self.c1
        c.null()
        c.null()
        c.clean_dir(self.opts.path)

    def startUp(self):
        """Run before each test"""
        self.c1.null()

    def sleep(self, sec, msg=''):
        """Sleep for given seconds"""
        print("Sleeping for %g seconds:" % sec, msg)
        time.sleep(sec)
        print("Woke up")

    def serverhelper(self, args):
        """Perform a special operation on the server side (such as
        rebooting the server)"""
        if self.opts.serverhelper is None:
            print("Manual operation required on server:")
            print(args.decode("utf8") + " and hit ENTER when done")
            sys.stdin.readline()
            print("Continuing with test")
        else:
            cmd = os.fsencode(self.opts.serverhelper)
            if self.opts.serverhelperarg:
                cmd += b' ' + os.fsencode(self.opts.serverhelperarg)
            cmd += b' ' + args
            os.system(cmd);

    def clean_clients(self):
        return

#########################################
debug_fail = False

def check(res, stat=NFS4_OK, msg=None, warnlist=[]):

    if type(stat) is str:
        raise "You forgot to put 'msg=' in front of check's string arg"

    statlist = stat
    if type(statlist) == int:
        statlist = [stat]

    if res.status in statlist:
        if not (debug_fail and msg):
            return

    statnames = [nfsstat4[stat] for stat in statlist]
    desired = ' or '.join(statnames)
    if not desired:
        desired = 'one of <none>'
    received = nfsstat4[res.status]
    if msg:
        failedop_name = msg
    elif res.resarray:
        failedop_name = nfs_opnum4[res.resarray[-1].resop]
    else:
        failedop_name = 'Compound'
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

def get_invalid_utf8strings():
    """Return a list of invalid ISO10646-UTF-8 strings"""
    # FIXME: More invalid strings.
    return [b"\xc0\xc1", # starts two multibyte sequences
            b"\xe0\x8a", # terminates a multibyte sequence too early
            b"\xc0\xaf", # overlong character"
            b"\xfc\x80\x80\x80\x80\xaf", # overlong character
            b"\xfc\x80\x80\x80\x80\x80", # NULL
            b"\xed\xa0\x80", # UTF-16 surrogate
            b"\xed\xbf\xbf", # UTF-16 surrogate
            b"\xef\xbf\xbe", # Invalid character U+FFFE
            b"\xe3\xc0\xc0", # just mangled.
            b"\xc0\x90", # overlong character
            # byte sequences that should never appear at start
            b"\x80",
            b"\xbf",
            b"\xfe",
            b"\xff",
            # starts with no ends
            b"\xc0 ",
            b"\xdf ",
            b"\xe0 ",
            b"\xef ",
            b"\xf0 ",
            b"\xf7 ",
            b"\xf8 ",
            b"\xfb ",
            b"\xfc ",
            b"\xfd "
            ]

def get_invalid_clientid():
    """Return a (guessed) invalid clientid"""
    return 0

def makeStaleId(stateid):
    """Given a good stateid, makes it stale

    NOTE this looks into server opaque data, thus is very specific
    to the CITI linux server.  All tests which use this function have
    the flag 'staleid'. This is also valid for Ganesha (and probably
    other server implementations, putting a 32 bit epoch into the
    first 32 bits of the stateid is the easiest way to detect stale
    stateid after reboot).
    """
    # The first 4 bytes of the linux stateid correspond to a time.
    # Choose a value older than any reasonable time, without
    # risking the chance of conflict with the zero-stateid.
    staletime = b"\0\0\0\1"
    stale = stateid4(stateid.seqid , staletime+b"\0\0\0\0\0\0\0\0")
    return stale

def makeBadID(stateid):
    """Given a good stateid, makes it bad

    NOTE this looks into server opaque data, thus is very specific
    to server implementation. Consider this version of the function
    an example.
    """

    boottime = stateid.other[0:4]
    bad = stateid4(stateid.seqid , boottime+b"\07\07\07\07\07\07\07\07")
    return bad

def makeBadIDganesha(stateid):
    """Given a good stateid, makes it bad

    NOTE this looks into server opaque data, thus is very specific
    to the Ganesha server.  All tests which use this function have
    the flag 'ganesha'
    """

    # Ganesha encodes the clientid into the first 64 bits of the 96 bit
    # other field, and then a 32 bit counter. We set that counter to 0
    # to simulate a bad stateid.

    clientid = stateid.other[0:8]
    bad = stateid4(stateid.seqid , clientid+b"\0\0\0\0")
    return bad

def compareTimes(time1, time2):
    """Compares nfstime4 values

    Returns -1 if time1 < time2
             0 if time1 ==time2
             1 if time1 > time2
    """

    if time1.seconds < time2.seconds:
        return -1
    if time1.seconds > time2.seconds:
        return 1
    if time1.seconds == time2.seconds:
        if time1.nseconds < time2.nseconds:
            return -1
        if time1.nseconds > time2.nseconds:
            return 1
        return 0
