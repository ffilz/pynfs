from xdrdef.nfs3_const import *
from xdrdef.nfs3_type import *
import xdrdef.nfs3_type as type3
from .environment3 import check
from .environment3 import checkvalid
import nfs3lib

def testNfs3MkDir(t, env):
    """ Create a target dir and execute the LOOKUP RPC to verify success


    FLAGS: nfsv3 mkdir all
    DEPEND:
    CODE: MKDIR1
    """
    ### Setup Phase ###
    test_dir=t.name.encode('utf-8') + b"_dir_1"
    mnt_fh = env.rootfh
    
    ### Execution Phase ###
    res = env.mkdir(mnt_fh, test_dir, mode=0o0777)
    
    ### Verification Phase ###
    check(res, msg="MKDIR - dir %s" % test_dir)
    res = env.lookup(mnt_fh, test_dir)
    check(res, msg="LOOKUP - dir %s" % test_dir)
    
    
### ToDo: Add basic negative cases.  Beef up coverage

