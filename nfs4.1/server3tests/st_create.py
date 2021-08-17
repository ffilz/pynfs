from xdrdef.nfs3_const import *
from xdrdef.nfs3_type import *
import xdrdef.nfs3_type as type3
from .environment3 import check
from .environment3 import checkvalid
import nfs3lib

def testNfs3Create_AllUnset(t, env):
    """ Create a file with all _set bits = 0
        Failure is expected due to bug #76982

    FLAGS: nfsv3 create all
    DEPEND:
    CODE: CREATE1
    """
    ### Setup Phase ###
    test_file=t.name.encode('utf-8') + b'_file_1'
    test_dir=t.name.encode('utf-8') + b'_dir_1'
    mnt_fh = env.rootfh

    res = env.mkdir(mnt_fh, test_dir, mode=0o0777)
    check(res, msg="MKDIR - test dir %s" % test_dir)
    test_dir_fh = type3.nfs_fh3(res.resok.obj.handle.data)
    
    ### Execution Phase ###
    res = env.create(test_dir_fh, test_file, mode=0o0777)
    #print "###DEBUG - CREATE_ALLUNSET RESULTS:", res, "\n"
    
    ### Verification Phase ###
    check(res, msg="CREATE - file %s" % test_file)
    res = env.lookup(test_dir_fh, test_file)
    check(res, msg="LOOKUP - file %s" % test_file)
    #test_file_fh = res.resok.obj.handle.data

def testNfs3Create_FileModeSet(t, env):
    """ Create a file with file mode set
        Use this as a work around until bug #76982 is closed 

    FLAGS: nfsv3 create all
    DEPEND:
    CODE: CREATE2
    """
    ### Setup Phase ###
    test_file=t.name.encode('utf-8') + b'_file_1'
    test_dir=t.name.encode('utf-8') + b'_dir_1'
    mnt_fh = env.rootfh
    res = env.mkdir(mnt_fh, test_dir, mode=0o0777)
    check(res, msg="MKDIR - test dir %s" % test_dir)
    test_dir_fh = type3.nfs_fh3(res.resok.obj.handle.data)
    
    ### Execution Phase ###
    res = env.create(test_dir_fh, test_file, mode=0o0777)
    test_file_fh = res.resok.obj.handle.data
    #print "###DEBUG - CREATE_FILEMODESET RESULTS:", res, "\n"
    
    ### Verification Phase ###
    check(res, msg="CREATE - file %s" % test_file)
    res = env.lookup(test_dir_fh, test_file)
    check(res, msg="LOOKUP - file %s" % test_file)
    res = env.getattr(test_file_fh)
    checkvalid(res.mode == 0o0777,
               "CREATE - file %s (mode=%d expected %d)" %
               (test_file, res.mode, 0o0777))

def testNfs3Create_FileModeReset(t, env):
    """ Create a file with one mode and then recreate it with another mode.
    Expect the first mode to remain. (Unchecked is the default creation type.)

    FLAGS: nfsv3 create all
    DEPEND:
    CODE: CREATE2R
    """
    ### Setup Phase ###
    test_file=t.name.encode('utf-8') + b'_file_1'
    test_dir=t.name.encode('utf-8') + b'_dir_1'
    mnt_fh = env.rootfh
    res = env.mkdir(mnt_fh, test_dir, mode=0o0777)
    check(res, msg="MKDIR - test dir %s" % test_dir)
    test_dir_fh = type3.nfs_fh3(res.resok.obj.handle.data)
    
    ### Execution Phase ###
    res = env.create(test_dir_fh, test_file,
                        mode=0o0321)
    check(res, msg="CREATE(1) - file %s" % test_file)
    #print "###DEBUG - CREATE_FILEMODESET RESULTS:", res, "\n"
    res = env.create(test_dir_fh, test_file,
                        mode=0o0654)
    check(res, msg="CREATE(2) - file %s" % test_file)
    test_file_fh = res.resok.obj.handle.data
    #print "###DEBUG - CREATE_FILEMODESET RESULTS:", res, "\n"
    
    ### Verification Phase ###
    res = env.lookup(test_dir_fh, test_file)
    check(res, msg="LOOKUP - file %s" % test_file)
    res = env.getattr(test_file_fh)
    checkvalid(res.mode == 0o0321,
               "CREATE - file %s (mode=%d expected %d)" %
               (test_file, res.mode, 0o0321))

def testNfs3Create_SizeSet(t, env):
    """ Create a file with file mode set and Size

    FLAGS: nfsv3 create all
    DEPEND:
    CODE: CREATE3
    """
    ### Setup Phase ###
    test_file=t.name.encode('utf-8') + b'_file_1'
    test_dir=t.name.encode('utf-8') + b'_dir_1'
    mnt_fh = env.rootfh
    res = env.mkdir(mnt_fh, test_dir, mode=0o0777)
    check(res, msg="MKDIR - test dir %s" % test_dir)
    test_dir_fh = type3.nfs_fh3(res.resok.obj.handle.data)
    
    ### Execution Phase ###
    res = env.create(test_dir_fh, test_file, mode=0o0777, size=9876543210)
    test_file_fh = res.resok.obj.handle.data
    #print "###DEBUG - CREATE_FILEMODESET RESULTS:", res, "\n"
    
    ### Verification Phase ###
    check(res, msg="CREATE - file %s" % test_file)
    res = env.lookup(test_dir_fh, test_file)
    check(res, msg="LOOKUP - file %s" % test_file)
    res = env.getattr(test_file_fh)
    checkvalid(res.size == 9876543210,   \
      "CREATE - file %s (size=%d expected %d)" %    \
      (test_file, res.size, 9876543210))    

def testNfs3Create_SizeTruncate(t, env):
    """ Create a file with a specified size and then truncate it with
    another create. (Unchecked is the default creation type.)

    FLAGS: nfsv3 create all
    DEPEND:
    CODE: CREATE3T
    """
    ### Setup Phase ###
    test_file=t.name.encode('utf-8') + b'_file_1'
    test_dir=t.name.encode('utf-8') + b'_dir_1'
    mnt_fh = env.rootfh
    res = env.mkdir(mnt_fh, test_dir, mode=0o0777)
    check(res, msg="MKDIR - test dir %s" % test_dir)
    test_dir_fh = type3.nfs_fh3(res.resok.obj.handle.data)
    
    ### Execution Phase ###
    res = env.create(test_dir_fh, test_file, mode=0o0777, size=9876543210)
    check(res, msg="CREATE(1) - file %s" % test_file)
    #print "###DEBUG - CREATE_FILEMODESET RESULTS:", res, "\n"
    res = env.create(test_dir_fh, test_file, mode=0o0777, size=1234567890)
    check(res, msg="CREATE(2) - file %s" % test_file)
    test_file_fh = res.resok.obj.handle.data
    #print "###DEBUG - CREATE_FILEMODESET RESULTS:", res, "\n"
    
    ### Verification Phase ###
    res = env.lookup(test_dir_fh, test_file)
    check(res, msg="LOOKUP - file %s" % test_file)
    res = env.getattr(test_file_fh)
    checkvalid(res.size == 9876543210,
               "CREATE - file %s (size=%d expected %d)" %
               (test_file, res.size, 9876543210))

    ### Execution Phase 2 ###
    res = env.create(test_dir_fh, test_file, mode=0o0777, size=0)
    check(res, msg="CREATE(3) - file %s" % test_file)
    test_file_fh = res.resok.obj.handle.data
    #print "###DEBUG - CREATE_FILEMODESET RESULTS:", res, "\n"

    ### Verification Phase 2 ###
    res = env.lookup(test_dir_fh, test_file)
    check(res, msg="LOOKUP - file %s" % test_file)
    res = env.getattr(test_file_fh)
    checkvalid(res.size == 0,
               "CREATE - file %s (size=%d expected %d)" %
               (test_file, res.size, 0))

def testNfs3Create_MtimeSet(t, env):
    """ Create a file with mtime set to client time

    FLAGS: nfsv3 create all
    DEPEND:
    CODE: CREATE4
    """
    ### Setup Phase ###
    test_file=t.name.encode('utf-8') + b'_file_1'
    test_dir=t.name.encode('utf-8') + b'_dir_1'
    mnt_fh = env.rootfh
    res = env.mkdir(mnt_fh, test_dir, mode=0o0777)
    check(res, msg="MKDIR - test dir %s" % test_dir)
    test_dir_fh = type3.nfs_fh3(res.resok.obj.handle.data)
    
    ### Execution Phase ###
    res = env.create(test_dir_fh, test_file, mode=0o0777,
                        mtime=type3.nfstime3(1234, 5678))
    test_file_fh = res.resok.obj.handle.data
    #print "###DEBUG - CREATE_FILEMODESET RESULTS:", res, "\n"
    
    ### Verification Phase ###
    check(res, msg="CREATE - file %s" % test_file)
    res = env.lookup(test_dir_fh, test_file)
    check(res, msg="LOOKUP - file %s" % test_file)
    res = env.getattr(test_file_fh)
    checkvalid(res.mtime.seconds == 1234 and \
       res.mtime.nseconds == 5678,           \
      "CREATE - file %s (mtime=%s expected %s)"         \
      % (test_file, str(res.mtime),          \
      str(nfstime3(1234, 5678))))


def testNfs3Create_AtimeSet(t, env):
    """ Create a file with atime to client time

    FLAGS: nfsv3 create all
    DEPEND:
    CODE: CREATE5
    """
    ### Setup Phase ###
    test_file=t.name.encode('utf-8') + b'_file_1'
    test_dir=t.name.encode('utf-8') + b'_dir_1'
    mnt_fh = env.rootfh
    res = env.mkdir(mnt_fh, test_dir, mode=0o0777)
    check(res, msg="MKDIR - test dir %s" % test_dir)
    test_dir_fh = type3.nfs_fh3(res.resok.obj.handle.data)
    
    ### Execution Phase ###
    res = env.create(test_dir_fh, test_file, mode=0o0777,
                        mtime=type3.nfstime3(1234, 5678),
                        atime=type3.nfstime3(1234, 5678))
    test_file_fh = res.resok.obj.handle.data
    #print "###DEBUG - CREATE_FILEMODESET RESULTS:", res, "\n"
    
    ### Verification Phase ###
    check(res, msg="CREATE - file %s" % test_file)
    res = env.lookup(test_dir_fh, test_file)
    check(res, msg="LOOKUP - file %s" % test_file)
    res = env.getattr(test_file_fh)
    checkvalid(res.atime.seconds == 1234 and \
       res.atime.nseconds == 5678,           \
      "CREATE - file %s (atime=%s expected %s)"         \
      % (test_file, str(res.atime),          \
      str(nfstime3(1234, 5678))))


def testNfs3Create_UidRoot(t, env):
    """ Create a file with uid set with root credentials

    FLAGS: nfsv3 create all
    DEPEND:
    CODE: CREATE6
    """
    ### Setup Phase ###
    test_file=t.name.encode('utf-8') + b'_file_1'
    test_dir=t.name.encode('utf-8') + b'_dir_1'
    mnt_fh = env.rootfh
    res = env.mkdir(mnt_fh, test_dir, mode=0o0777)
    check(res, msg="MKDIR - test dir %s" % test_dir)
    test_dir_fh = type3.nfs_fh3(res.resok.obj.handle.data)
    
    ### Execution Phase ###
    # set root cred
    env.c1.set_cred(env.rootcred)

    #execute
    res = env.create(test_dir_fh, test_file, mode=0o0777,
                     uid=1234, gid=5678)

    # restore c1 to cred1
    env.c1.set_cred(env.cred1)

    test_file_fh = res.resok.obj.handle.data
    #print "###DEBUG - CREATE_FILEMODESET RESULTS:", res, "\n"
    
    ### Verification Phase ###
    check(res, msg="CREATE - file %s" % test_file)
    res = env.lookup(test_dir_fh, test_file)
    check(res, msg="LOOKUP - file %s" % test_file)
    res = env.getattr(test_file_fh)
    # Allow maproot=nobody
    checkvalid(res.uid == 1234 or  \
      res.uid == 65534,            \
      "CREATE - file %s (uid=%d expected %d)" \
      % (test_file, res.uid, 1234))
    checkvalid(res.gid == 5678 or  \
      res.gid == 0,                \
      "CREATE - file %s (gid=%d expected %d)" \
      % (test_file, res.gid, 5678))


def testNfs3Create_UidAdmin(t, env):
    """ Create a file with uid set as second user credentials

    FLAGS: nfsv3 create all
    DEPEND:
    CODE: CREATE7
    """
    ### Setup Phase ###
    test_file=t.name.encode('utf-8') + b'_file_1'
    test_dir=t.name.encode('utf-8') + b'_dir_1'
    mnt_fh = env.rootfh
    res = env.mkdir(mnt_fh, test_dir, mode=0o0777)
    check(res, msg="MKDIR - test dir %s" % test_dir)
    test_dir_fh = type3.nfs_fh3(res.resok.obj.handle.data)
    
    ### Execution Phase ###
    # set second cred
    env.c1.set_cred(env.cred2)

    #execute
    res = env.create(test_dir_fh, test_file, mode=0o0777,
                     uid=env.uid2, gid=env.gid2)

    # restore c1 to cred1
    env.c1.set_cred(env.cred1)

    check(res, msg="CREATE - test file %s" % test_file)
    test_file_fh = res.resok.obj.handle.data
    #print "###DEBUG - CREATE_FILEMODESET RESULTS:", res, "\n"
    
    ### Verification Phase ###
    check(res, msg="CREATE - file %s" % test_file)

    # set second cred
    env.c1.set_cred(env.cred2)

    res = env.lookup(test_dir_fh, test_file)

    # restore c1 to cred1
    env.c1.set_cred(env.cred1)

    check(res, msg="LOOKUP - file %s" % test_file)

    # set second cred
    env.c1.set_cred(env.cred2)

    res = env.getattr(test_file_fh)

    # restore c1 to cred1
    env.c1.set_cred(env.cred1)

    note = "Is vfs.nfsrv.create_attributes_ids_enabled set?"
    checkvalid(res.uid == env.uid2,           \
      "CREATE - file %s (uid=%d expected %d) %s"   \
      % (test_file, res.uid, env.uid2, note))
    checkvalid(res.gid == env.gid2,           \
      "CREATE - file %s (gid=%d expected %d) %s"   \
      % (test_file, res.gid, env.gid2, note))


def testNfs3Create_UidAdminFail(t, env):
    """ Create a file with uid set as second user credentials

    FLAGS: nfsv3 create all
    DEPEND:
    CODE: CREATE8
    """
    ### Setup Phase ###
    test_file=t.name.encode('utf-8') + b'_file_1'
    test_dir=t.name.encode('utf-8') + b'_dir_1'
    mnt_fh = env.rootfh
    res = env.mkdir(mnt_fh, test_dir, mode=0o0777)
    check(res, msg="MKDIR - test dir %s" % test_dir)
    test_dir_fh = type3.nfs_fh3(res.resok.obj.handle.data)
    
    ### Execution Phase ###
    # set second cred
    env.c1.set_cred(env.cred2)

    res = env.create(test_dir_fh, test_file, mode=0o0777,
                        uid=1234,
                        gid=5678)

    # restore c1 to cred1
    env.c1.set_cred(env.cred1)

    ### Verification Phase ###
    check(res, [NFS3ERR_ACCES, NFS3ERR_PERM],
          msg="CREATE - file %s" % test_file)

    res = env.lookup(test_dir_fh, test_file)
    check(res, [NFS3ERR_NOENT], msg="LOOKUP - file %s" % test_file)

def testNfs3Create_Exclusive(t, env):
    """ Create a file in exclusive mode

    FLAGS: nfsv3 create all
    DEPEND:
    CODE: CREATE9
    """
    ### Setup Phase ###
    #verf = '12345678'
    verf = str(0x3B9ACA01).encode('utf-8') + b'_file_1'
    wrongverf = '87654321'.encode('utf-8') + b'_file_1'
    test_file=t.name.encode('utf-8') + b'_file_1'
    test_dir=t.name.encode('utf-8') + b'_dir_1'
    mnt_fh = env.rootfh

    res = env.mkdir(mnt_fh, test_dir, mode=0o0777)
    check(res, msg="MKDIR - test dir %s" % test_dir)
    test_dir_fh = type3.nfs_fh3(res.resok.obj.handle.data)

    ### Execution Phase ###
    res = env.create(test_dir_fh, test_file,
        nfs3_mode=EXCLUSIVE, exclusive_verf=verf)
    check(res, msg="CREATE - file %s" % test_file)
    fh1 = res.resok.obj.handle.data

    res = env.lookup(test_dir_fh, test_file)
    check(res, msg="LOOKUP - file %s" % test_file)

    # Create with same verifier should return same object
    res = env.create(test_dir_fh, test_file,
        nfs3_mode=EXCLUSIVE, exclusive_verf=verf)
    check(res, msg="2nd CREATE with correct verifier")
    fh2 = res.resok.obj.handle.data

    # Compare file handles
    checkvalid(fh1 == fh2, "Filehandle changed on 2nd exclusive create"
        "(fh1 = %s, fh2 = %s)" % (fh1, fh2))

    # Create the file again, should return an error
    res = env.create(test_dir_fh, test_file,
        nfs3_mode=EXCLUSIVE, exclusive_verf=wrongverf)
    check(res, NFS3ERR_EXIST, msg="3rd CREATE with wrong verifier")

    # Create with same verifier should return same object
    res = env.create(test_dir_fh, test_file,
        nfs3_mode=EXCLUSIVE, exclusive_verf=verf)
    check(res, msg="3rd CREATE with correct verifier")
    fh2 = res.resok.obj.handle.data

    # Compare file handles
    checkvalid(fh1 == fh2, "Filehandle changed on 3rd exclusive create"
        "(fh1 = %s, fh2 = %s)" % (fh1, fh2))


def testNfs3Create_ExclusiveSupported(t, env):
    """ Test for support for exclusive mode

    FLAGS: nfsv3 create all
    DEPEND:
    CODE: CREATE9a
    """
    ### Setup Phase ###
    verf = '12345678'.encode('utf-8') + b'_file_1'
    verf = str(0x3B9ACA01).encode('utf-8') + b'_file_1'
    test_file=t.name.encode('utf-8') + b'_file_1'
    test_dir=t.name.encode('utf-8') + b'_dir_1'
    mnt_fh = env.rootfh

    ### Execution Phase ###
    res = env.create(mnt_fh, test_file,
        nfs3_mode=EXCLUSIVE, exclusive_verf=verf)
    check(res, msg="CREATE - file %s" % test_file)


### ToDo: Add basic negative cases.  Beef up coverage
