from xdrdef.nfs3_const import *
from xdrdef.nfs3_type import *
import xdrdef.nfs3_type as type3
from .environment3 import check
from .environment3 import checkvalid
from .environment3 import compare_fattr3
import nfs3lib

def testNfs3GetAttr(t, env):
    """ Get the attributes of a file via the GETATTR rpc
    

    FLAGS: nfsv3 getattr all
    DEPEND:
    CODE: GATTR1
    """
    ### Setup Phase ###
    test_file=t.name.encode('utf-8') + b"_file_1"
    test_dir=t.name.encode('utf-8') + b"_dir_1"
    mnt_fh = env.rootfh
    mode_c = 0o0777
    
    res = env.mkdir(mnt_fh, test_dir, mode=mode_c)
    check(res, msg="MKDIR - %s" % test_dir)
    test_dir_fh = type3.nfs_fh3(res.resok.obj.handle.data)
    res = env.create(test_dir_fh, test_file, mode=mode_c)
    check(res, msg="CREATE - file %s " % test_file)
    test_file_fh = type3.nfs_fh3(res.resok.obj.handle.data)
    attrs1p = res.resok.obj_attributes.attributes_follow
    if attrs1p:
        attrs1 = res.resok.obj_attributes.attributes

    ### Execution Phase ###
    res = env.getattr(test_file_fh)
    
    ### Verification Phase ###
    check(res, msg="GETATTR - %s" % test_file)
    attrs2 = res.resok.obj_attributes

    if attrs1p:
        if not compare_fattr3(attrs1, attrs2):
            t.fail(" ".join([
            "GETATTR - attributes returned [%s]" % attrs2 ,
            "is different than return of CREATE [%s]"  % attrs1]))

    if attrs2.mode != mode_c:
        t.fail(" ".join([
        "GETATTR - mode returned [%s]" % attrs2.mode ,
        "is different than passed to CREATE [%s]"  % mode_c]))
