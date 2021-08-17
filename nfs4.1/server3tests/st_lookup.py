from xdrdef.nfs3_const import *
from xdrdef.nfs3_type import *
import xdrdef.nfs3_type as type3
from .environment3 import check
from .environment3 import checkvalid
import nfs3lib

def testNfs3Lookup(t, env):
    """ Get the handle for a file via the LOOKUP rpc
    

    FLAGS: nfsv3 lookup all
    DEPEND:
    CODE: LOOKUP1 
    """
    ### Setup Phase ###
    test_file=t.name.encode('utf-8') + b"_file_1"
    test_dir=t.name.encode('utf-8') + b"_dir_1"
    mnt_fh = env.rootfh
    
    res = env.mkdir(mnt_fh, test_dir, mode=0o0777)
    check(res, msg="MKDIR - dir %s" % test_dir)
    test_dir_fh = type3.nfs_fh3(res.resok.obj.handle.data)
    res = env.create(test_dir_fh, test_file, mode=0o0777)
    check(res, msg="CREATE - file %s " % test_file)
    test_file_fh = res.resok.obj.handle.data
    
    ### Execution Phase ###
    res = env.lookup(test_dir_fh, test_file)
    found_file_fh = res.resok.object.data
    
    check(res, msg="LOOKUP - file %s" % test_file)
    if found_file_fh != test_file_fh:
        t.fail_support(" ".join([
            "LOOKUP - file handle returned [%s]" % found_file_fh ,
            "is different than return of CREATE [%s]"  % test_file_fh]))


### ToDo: Add basic negative cases ... follow pattern set up in nfs4.  Beef up coverage
