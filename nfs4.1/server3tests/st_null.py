from xdrdef.nfs3_const import *
from xdrdef.nfs3_type import *
from .environment3 import check
import nfs3lib

def testNfs3Null(t, env):
    """ NFSPROC3_NULL

    FLAGS: nfsv3 all
    DEPEND:
    CODE: NULL1
    """
    ### Setup Phase ###
    mnt_fh = env.rootfh
    
    ### Execution Phase ###
    res = env.null()
    
    ### Verification Phase ###
    # No check needed since res = None?
