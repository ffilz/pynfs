from xdrdef.nfs4_const import *
import nfs_ops
op = nfs_ops.NFS4ops()
from .environment import check, fail, use_obj, create_obj, rename_obj
from .environment import open_create_file_op, create_file, open_file, close_file
from xdrdef.nfs4_type import *
from testmod import FailureException
import datetime
from nfs4commoncode import cb_encode_status_by_name as encode_status_by_name
import threading
import logging
import nfs4lib
import uuid
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger("pynfs-custom")

# Ganesha has a thread that runs every 10 seconds (this is a parameter)
# that checks the state of waiting locks, and cancels or checks if they are
# eligible when needed
GANESHA_ASYNC_LOCK_CHECK_SLEEP_TIME = 10

# Ganesha uses a buffer to reduce the chance of a race between its actions and
# client response, which affects the worst-case time it takes to free the locks.
# We need to account for this buffer in tests sensitive to actions' duration.
GANESHA_BUFFER_TIME = 5

def init_client_upcall_handling(client):
    def handle_lock_notify_upcall(arg, env):
        with client.upcall_lock:
            client.num_upcalls_received = client.num_upcalls_received + 1

        return encode_status_by_name("cb_notify_lock", NFS4ERR_NOTSUPP)

    client.op_cb_notify_lock = handle_lock_notify_upcall
    client.num_upcalls_received = 0
    client.upcall_lock = threading.Lock()

def pynfs_assert(success, message):
    if not success:
        raise FailureException(message)

def get_num_upcalls_received(client):
    with client.upcall_lock:
        return client.num_upcalls_received

def wait_for_number_of_expected_upcalls(env, client, num_expected_upcalls, timeout_sec):
    end_time = datetime.datetime.now() + datetime.timedelta(seconds=timeout_sec)

    num_upcalls_received = get_num_upcalls_received(client)
    while num_upcalls_received != num_expected_upcalls and datetime.datetime.now() < end_time:
          env.sleep(0.1, "Waiting for upcall. Current value: {}, expected value: {}".
            format(num_upcalls_received, num_expected_upcalls))
          num_upcalls_received = get_num_upcalls_received(client)

    pynfs_assert(num_upcalls_received == num_expected_upcalls,
                 "Timed out waiting for up-call to be received")

def _getleasetime(sess):
    res = sess.compound([op.putrootfh(), op.getattr(1 << FATTR4_LEASE_TIME)])
    return res.resarray[-1].obj_attributes[FATTR4_LEASE_TIME]

def requestLock(client, session, file_handle, file_stateid, owner, lock_type,
             offset=0, len=NFS4_UINT64_MAX):
    open_to_lock_owner = open_to_lock_owner4(0, file_stateid, 0,
            lock_owner4(client.clientid, bytes(owner, "ascii")))
    lock_owner = locker4(open_owner=open_to_lock_owner, new_lock_owner=True)
    lock_op = [ op.lock(lock_type, False, offset, len, lock_owner)]
    res = session.compound([op.putfh(file_handle)] + lock_op)
    return res

def testLockReleaseOnVerifierChange(t, env):
    """

    FLAGS: pyNFS_custom_tests all
    CODE: EFS_VERCHANGE_1
    """
    c1 = env.c1.new_client(env.testname(t))
    sess1 = c1.create_session()
    sess1.compound([op.reclaim_complete(FALSE)])

    # create file
    open_op = open_create_file_op(sess1, env.testname(t), open_create=OPEN4_CREATE)
    res = sess1.compound(open_op)
    check(res)
    fh = res.resarray[-1].object
    stateid = res.resarray[-2].stateid

    # Take lock on the created file
    res = requestLock(c1, sess1, fh, stateid, "lock1", WRITE_LT)
    check(res)

    # Same client with new verifier (simulating a client reboot)
    c2 = env.c1.new_client(env.testname(t), verf=env.new_verifier())
    if c1.clientid == c2.clientid:
        fail("Expected clientid %i to change" % c1.clientid)

    # Old session state should not be discarded until c2 confirm
    res = sess1.compound([])
    check(res)

    # Try obtaining lock from new client cA on same file above, it should fail
    cA = env.c1.new_client(env.testname(t) + b"_new", verf=env.new_verifier())
    sessA = cA.create_session()
    sessA.compound([op.reclaim_complete(FALSE)])
    open_op = open_create_file_op(sessA, env.testname(t), open_create=OPEN4_NOCREATE)
    res = sessA.compound(open_op)
    check(res)
    fh = res.resarray[-1].object
    stateid = res.resarray[-2].stateid

    res = requestLock(cA, sessA, fh, stateid, "lockA", WRITE_LT)
    check(res, NFS4ERR_DENIED)

    # Confirm c2
    sess2 = c2.create_session()
    sess2.compound([op.reclaim_complete(FALSE)])

    # Old session state should now be discarded
    res = sess1.compound([])
    check(res, NFS4ERR_BADSESSION)

    # Try obtaining lock from cA on same file above, it should now pass
    res = requestLock(cA, sessA, fh, stateid, "lockA", WRITE_LT)
    check(res)

def testCloseWithLocks(t, env):
    """

    FLAGS: pyNFS_custom_tests all
    CODE: EFS_CLOSE_WITH_LOCKS
    """
    # Create 2 clients
    c1 = env.c1.new_client(env.testname(t)+b"_1")
    sess1 = c1.create_session()
    sess1.compound([op.reclaim_complete(FALSE)])

    c2 = env.c1.new_client(env.testname(t)+b"_2")
    sess2 = c2.create_session()
    sess2.compound([op.reclaim_complete(FALSE)])

    # create file with client 1
    res = create_file(sess1, b"owner1", path=sess1.c.homedir + [env.testname(t)+b"file"])
    check(res)
    fh1 = res.resarray[-1].object
    stateid1 = res.resarray[-2].stateid

    # Open file with client 2
    res = open_file(sess2, b"owner1", path=sess2.c.homedir + [env.testname(t)+b"file"], access=OPEN4_SHARE_ACCESS_BOTH)
    check(res)
    fh2 = res.resarray[-1].object
    stateid2 = res.resarray[-2].stateid
    pynfs_assert(fh1 == fh2, "Open for the same file returned different "
                             "handles. {} != {}".format(fh1, fh2))

    # Take lock on the file from client 1
    res = requestLock(c1, sess1, fh1, stateid1, "process1", WRITE_LT, 0, 10)
    check(res)

    # Try to take a blocking lock from client 2 - should be denied, The lock is waiting
    res = requestLock(c2, sess2, fh2, stateid2, "process2", WRITEW_LT)
    check(res, stat=NFS4ERR_DENIED)

    # Close file from client 2 - This should release blocking locks
    res = close_file(sess2, fh2, stateid2)
    check(res)

    # Take another lock from client 1 to make sure client 2 locks released
    res = requestLock(c1, sess1, fh1, stateid1, "process3", WRITE_LT, 20, 30)
    check(res)

def testFreeNonPolledBlockingLocks(t, env):
    """

    FLAGS: pyNFS_custom_tests all
    CODE: EFS_FREE_NON_POLLED_BLOCKING_LOCKS
    """

    c1 = env.c1.new_client(env.testname(t)+b"_1")
    sess = c1.create_session()
    lease_time = _getleasetime(sess)

    # We add 1 second buffer to account for any delays since lock release was triggered
    wait_time = GANESHA_ASYNC_LOCK_CHECK_SLEEP_TIME + lease_time \
                + GANESHA_BUFFER_TIME + 1
    verifyFreeNonPolledBlockingLocks(t, env, wait_time)

def testFreeNonPolledBlockingLocksWithoutUpcall(t, env):
    """Test EFS freeing non-polled locks in case eligible lock upcall is never sent

    Note: this test is intended to be used with a feature that disables
    the up-call, and with the up-call is disabled it takes longer for the locks
    to be released. Due to this non-default behavior, the test is
    intended to be executed separately from other pyNFS_custom_tests.

    FLAGS: all
    CODE: EFS_FREE_NON_POLLED_BLOCKING_LOCKS_WITHOUT_UPCALL
    """

    c1 = env.c1.new_client(env.testname(t)+b"_1")
    sess = c1.create_session()
    lease_time = _getleasetime(sess)

    # We add 1 second buffer to account for any delays since lock release was triggered
    wait_time = GANESHA_ASYNC_LOCK_CHECK_SLEEP_TIME + 2 * lease_time + 1
    verifyFreeNonPolledBlockingLocks(t, env, wait_time)

def verifyFreeNonPolledBlockingLocks(t, env, max_lock_release_time_sec):

    init_client_upcall_handling(env.c1)

    # Create 2 clients
    c1 = env.c1.new_client(env.testname(t)+b"_1")
    sess1 = c1.create_session()
    sess1.compound([op.reclaim_complete(FALSE)])

    c2 = env.c1.new_client(env.testname(t)+b"_2")
    sess2 = c2.create_session()
    sess2.compound([op.reclaim_complete(FALSE)])

    # create file with client 1
    res = create_file(sess1, b"owner1", path=sess1.c.homedir + [env.testname(t)+b"polled_file"])
    check(res)
    fh1 = res.resarray[-1].object
    stateid1 = res.resarray[-2].stateid

    # Open file with client 2
    res = open_file(sess2, b"owner1", path=sess2.c.homedir + [env.testname(t)+b"polled_file"], access=OPEN4_SHARE_ACCESS_BOTH)
    check(res)
    fh2 = res.resarray[-1].object
    stateid2 = res.resarray[-2].stateid
    pynfs_assert(fh1 == fh2, "Open for the same file returned different "
                             "handles. {} != {}".format(fh1, fh2))

    # Take lock on the file from client 1
    res = requestLock(c1, sess1, fh1, stateid1, "process1", WRITE_LT, 0, 10)
    check(res)
    lock1_stateid = res.resarray[-1].oplock.resok4.lock_stateid

    # Try to take a blocking lock from client 2 - should be denied, The lock is waiting
    res = requestLock(c2, sess2, fh2, stateid2, "process2", WRITEW_LT)
    check(res, stat=NFS4ERR_DENIED)

    # continue to sleep for twice lease time while maintaining sessions alive
    lease_time = _getleasetime(sess1)
    sleep_while_maintaining_valid_sessions(env, [sess1, sess2], lease_time, max_lock_release_time_sec)

    # Try to take another lock with client 1 - should fail, make sure the client 2 lock is still waiting
    open_to_lock_owner = open_to_lock_owner4(0, stateid1, 0, lock_owner4(c1.clientid, b"process1"))
    lock_owner = locker4(open_owner=open_to_lock_owner, new_lock_owner=True)
    lock_op = [ op.lock(WRITE_LT, False, 20, 10, lock_owner)]
    res = sess1.compound([op.putfh(fh1)] + lock_op)
    check(res, stat=NFS4ERR_DENIED)

    upcall_count_expected = get_num_upcalls_received(env.c1) + 2

    # Unlock from client 1 - Lock for client 2 becomes eligible, but waits for it to be polled
    locku_op = [ op.locku(WRITE_LT, 0, lock1_stateid, 0, 10)]
    res = sess1.compound([op.putfh(fh1)] + locku_op)
    check(res)

    env.sleep(lease_time / 4, "lease period / 4")
    # Request another lock from client 1 to make sure client 2 locks are not
    # released prematurely.
    # We use a blocking lock to check that the up-call is sent.
    res = requestLock(c1, sess1, fh2, stateid1, "process4", WRITEW_LT, 20, 30)
    check(res, stat=NFS4ERR_DENIED)

    # Wait for the lock to be released by the server
    sleep_while_maintaining_valid_sessions(env, [sess1, sess2], lease_time, max_lock_release_time_sec)

    upcall_count_received = get_num_upcalls_received(env.c1)
    pynfs_assert(upcall_count_expected == upcall_count_received,
                 "Number of up-calls doesn't match the expected value"
                 "expected {}, got {}".format(upcall_count_expected, upcall_count_received))

    # Take another lock from client 1 to make sure client 2 locks released
    res = requestLock(c1, sess1, fh1, stateid1, "process4", WRITE_LT, 20, 30)
    check(res)

def testLockOrderFairness(t, env):
    """
    # For simplicity of the test, we don't handle the up-call from the server to notify
    # that a lock is available. In the future it could be nice to add that.

    FLAGS: pyNFS_custom_tests all
    CODE: EFS_LOCK_ORDER_FAIRNESS
    """

    init_client_upcall_handling(env.c1)

    # Create client
    c = env.c1.new_client(env.testname(t))
    sess = c.create_session()
    sess.compound([op.reclaim_complete(FALSE)])

    # create file
    res = create_file(sess, b"file_owner", path=sess.c.homedir + [env.testname(t)+b"file"])
    check(res)
    fh = res.resarray[-1].object
    file_stateid = res.resarray[-2].stateid

    NUM_LOCKS = 20
    # Take locks on the file
    lock_stateid = 0
    waiting_lock_owners = []
    for i in range(NUM_LOCKS):
        open_to_lock_owner = open_to_lock_owner4(0, file_stateid, 0, lock_owner4(c.clientid, bytes("process_"+str(i), "ascii")))
        lock_owner = locker4(open_owner=open_to_lock_owner, new_lock_owner=True)
        lock_op = [ op.lock(WRITEW_LT, False, 0, NFS4_UINT64_MAX, lock_owner)]
        res = sess.compound([op.putfh(fh)] + lock_op)

        if i == 0:
            check(res)
            lock_stateid = res.resarray[-1].oplock.resok4.lock_stateid
        else:
            check(res, stat = NFS4ERR_DENIED)
            waiting_lock_owners.append(lock_owner)

    # Unlock and make sure we get the locks in order
    num_expected_upcalls = 0
    for next_eligible_lock_owner in waiting_lock_owners:
        # Unlock
        locku_op = [ op.locku(WRITEW_LT, 0, lock_stateid, 0, NFS4_UINT64_MAX)]
        res = sess.compound([op.putfh(fh)] + locku_op)
        check(res)

        num_expected_upcalls = num_expected_upcalls + 1
        WAIT_FOR_UPCALL_TIMEOUT_SEC = 10
        wait_for_number_of_expected_upcalls(env, env.c1, num_expected_upcalls, WAIT_FOR_UPCALL_TIMEOUT_SEC)

        # Test another lock - to make sure waiters were not released
        res = requestLock(c, sess, fh, file_stateid, "different_process", WRITE_LT)
        check(res, stat=NFS4ERR_DENIED)

        # Ask for the next waiter
        lock_op = [ op.lock(WRITEW_LT, False, 0, NFS4_UINT64_MAX, next_eligible_lock_owner)]
        res = sess.compound([op.putfh(fh)] + lock_op)
        check(res)
        lock_stateid = res.resarray[-1].oplock.resok4.lock_stateid

def testAskAgainForGrantedLock(t, env):
    """
    # This test verifies that we handle the states properly when a granted lock is requested again

    FLAGS: pyNFS_custom_tests all
    CODE: EFS_ASK_AGAIN_FOR_GRANTED_LOCK
    """

    # Create client
    c = env.c1.new_client(env.testname(t))
    sess = c.create_session()
    sess.compound([op.reclaim_complete(FALSE)])

    # create file
    res = create_file(sess, b"file_owner", path=sess.c.homedir + [env.testname(t)+b"file"])
    check(res)
    fh = res.resarray[-1].object
    file_stateid = res.resarray[-2].stateid

    # Take lock
    res = requestLock(c, sess, fh, file_stateid, "process", WRITEW_LT)
    check(res)
    lock_stateid = res.resarray[-1].oplock.resok4.lock_stateid

    # Request the lock again with "new_lock_owner=True"
    res = requestLock(c, sess, fh, file_stateid, "process", WRITEW_LT)
    check(res)
    new_state_id = res.resarray[-1].oplock.resok4.lock_stateid

    '''
    State id is composed of "other", which represents the lock itself and should be identical for every op that
    handles with the same lock.
    In addition, it also includes the sequence id, which increments every time the server returns the state id, so
    it doesn't need to be equal
    '''
    pynfs_assert(lock_stateid.other == new_state_id.other,
                 "Requesting a lock again didn't produce the same lock state"
                 " id. {} != {}".format(lock_stateid.other, new_state_id.other))

    # Request the lock again with exist_lock_owner"
    exist_locks_owner = exist_lock_owner4(new_state_id, 0)
    lock_owner = locker4(lock_owner=exist_locks_owner, new_lock_owner=False)
    lock_op = [ op.lock(WRITEW_LT, False, 0, NFS4_UINT64_MAX, lock_owner)]
    res = sess.compound([op.putfh(fh)] + lock_op)
    check(res)
    new_state_id = res.resarray[-1].oplock.resok4.lock_stateid

    pynfs_assert(lock_stateid.other == new_state_id.other,
                 "Requesting a lock again didn't produce the same lock state"
                 " id. {} != {}".format(lock_stateid.other, new_state_id.other))

    # Request the lock again from a different open state
    res = open_file(sess, b"file_owner", path=sess.c.homedir + [env.testname(t)+b"file"], access=OPEN4_SHARE_ACCESS_BOTH)
    check(res)
    fh2 = res.resarray[-1].object
    file_stateid2 = res.resarray[-2].stateid
    pynfs_assert(fh == fh2, "Open for the same file returned different handles."
                            " {} != {}".format(fh, fh2))

    res = requestLock(c, sess, fh, file_stateid2, "process", WRITEW_LT)
    check(res)
    lock_stateid_other_open = res.resarray[-1].oplock.resok4.lock_stateid

    pynfs_assert(lock_stateid.other == lock_stateid_other_open.other,
                 "Requesting a lock again didn't produce the same lock state id. "
                 "{} != {}".format(lock_stateid.other, lock_stateid_other_open.other))

def testPollForBlockingLock(t, env):
    """
    # This test verifies that we don't panic when we poll for the same blocking lock several times

    FLAGS: pyNFS_custom_tests all
    CODE: EFS_POLL_FOR_BLOCKED_LOCK
    """

    # Create client 1
    c1 = env.c1.new_client(env.testname(t)+b"_1")
    sess1 = c1.create_session()
    sess1.compound([op.reclaim_complete(FALSE)])

    # Create client 2
    c2 = env.c1.new_client(env.testname(t)+b"_2")
    sess2 = c2.create_session()
    sess2.compound([op.reclaim_complete(FALSE)])

    # create file
    res = create_file(sess1, b"file_owner", path=sess1.c.homedir + [env.testname(t)+b"file"])
    check(res)
    fh1 = res.resarray[-1].object
    file_stateid1 = res.resarray[-2].stateid

    # Open file with client 2
    res = open_file(sess2, b"owner1", path=sess2.c.homedir + [env.testname(t)+b"file"], access=OPEN4_SHARE_ACCESS_BOTH)
    check(res)
    fh2 = res.resarray[-1].object
    file_stateid2 = res.resarray[-2].stateid
    pynfs_assert(fh1 == fh2, "Open for the same file returned different handles."
                             " {} != {}".format(fh1, fh2))

    # Take lock
    res = requestLock(c1, sess1, fh1, file_stateid1, "process1", WRITEW_LT)
    check(res)

    # Try to take another blocking lock and poll for it several times with the same client
    for i in range(10):
        res = requestLock(c1, sess1, fh1, file_stateid1, "process2", WRITEW_LT)
        check(res, stat=NFS4ERR_DENIED)

    # Try to take another blocking lock and poll for it several times with a different client
    for i in range(10):
        res = requestLock(c2, sess2, fh2, file_stateid2, "process2", WRITEW_LT)
        check(res, stat=NFS4ERR_DENIED)

def testCancelBlockingLock(t, env):
    """
    FLAGS: pyNFS_custom_tests all
    CODE: EFS_LOCK_CANCEL_BLOCKING_LOCK
    """

    # Create client
    c = env.c1.new_client(env.testname(t))
    sess = c.create_session()
    sess.compound([op.reclaim_complete(FALSE)])

    # create file
    res = create_file(sess, b"file_owner", path=sess.c.homedir + [env.testname(t)+b"file"])
    check(res)
    fh = res.resarray[-1].object
    file_stateid = res.resarray[-2].stateid

    # Take lock
    res = requestLock(c, sess, fh, file_stateid, "process1", WRITEW_LT, 0, 10)
    check(res)

    # Add waiter
    res = requestLock(c, sess, fh, file_stateid, "process2", WRITEW_LT)
    check(res, stat=NFS4ERR_DENIED)

    # Ask for another lock, make sure the blocking lock is in the way
    res = requestLock(c, sess, fh, file_stateid, "process1", WRITE_LT, 50, 10)
    check(res, stat=NFS4ERR_DENIED)

    # Ask for the waiter lock again as non-blocking, to cancel it
    res = requestLock(c, sess, fh, file_stateid, "process2", WRITE_LT)
    check(res, stat=NFS4ERR_DENIED)

    # Now we can take the other lock
    res = requestLock(c, sess, fh, file_stateid, "process1", WRITE_LT, 50, 10)
    check(res)

def testReleaseLockAfterLease(t, env):
    """
    FLAGS: pyNFS_custom_tests all
    CODE: EFS_RELEASE_LOCK_AFTER_LEASE
    """

    # Create client 1
    c1 = env.c1.new_client(env.testname(t)+b"_1")
    sess1 = c1.create_session()
    sess1.compound([op.reclaim_complete(FALSE)])

    # Create client 2
    c2 = env.c1.new_client(env.testname(t)+b"_2")
    sess2 = c2.create_session()
    sess2.compound([op.reclaim_complete(FALSE)])

    # create file
    res = create_file(sess1, b"file_owner", path=sess1.c.homedir + [env.testname(t)+b"file"])
    check(res)
    fh1 = res.resarray[-1].object
    file_stateid1 = res.resarray[-2].stateid

    # Open file with client 2
    res = open_file(sess2, b"owner1", path=sess2.c.homedir + [env.testname(t)+b"file"], access=OPEN4_SHARE_ACCESS_BOTH)
    check(res)
    fh2 = res.resarray[-1].object
    file_stateid2 = res.resarray[-2].stateid
    pynfs_assert(fh1 == fh2, "Open for the same file returned different handles."
                             " {} != {}".format(fh1, fh2))

    # Take lock
    res = requestLock(c1, sess1, fh1, file_stateid1, "process1", WRITEW_LT)
    check(res)

    # Add waiter
    res = requestLock(c1, sess1, fh1, file_stateid1, "process2", WRITEW_LT)
    check(res, stat=NFS4ERR_DENIED)

    # Try to take the lock with a different client, should be denied
    res = requestLock(c2, sess2, fh2, file_stateid2, "process3", WRITE_LT)
    check(res, stat=NFS4ERR_DENIED)

    # Wait more than least time for client entry to expire. Only renew lease for client 2
    lease_time = _getleasetime(sess1)
    wait_time = lease_time + GANESHA_ASYNC_LOCK_CHECK_SLEEP_TIME + 1
    sleep_while_maintaining_valid_sessions(env, [sess2], lease_time, wait_time)

    # Client 1 should have expired now. Check that we can take the lock with client 2
    res = requestLock(c2, sess2, fh2, file_stateid2, "process3", WRITE_LT)
    check(res)

def sleep_while_maintaining_valid_sessions(env, sessions, lease_time, duration_sec):
    end_time = datetime.datetime.now() + datetime.timedelta(seconds=duration_sec)
    max_compound_interval_sec = lease_time / 3
    while datetime.datetime.now() < end_time:
        for sess in sessions:
            res = sess.compound([])
            check(res)

        total_sleep_remainder = max(datetime.timedelta(0), end_time - datetime.datetime.now())
        delay_sec = min(max_compound_interval_sec, total_sleep_remainder.total_seconds())
        env.sleep(delay_sec, "Sleeping before renewing lease...")

def testAtomicChangeInfo(t, env):
    """
    FLAGS: pyNFS_custom_tests all
    CODE: EFS_ATOMIC_CHANGE_INFO
    """

    # Create client
    c = env.c1.new_client(env.testname(t))
    sess = c.create_session()
    sess.compound([op.reclaim_complete(FALSE)])

    # Create file
    file_name = env.testname(t)+b"file"
    res = create_file(sess, b"file_owner", path=sess.c.homedir + [file_name])
    check(res)
    open_res = res.resarray[3]
    pynfs_assert(open_res.opopen.resok4.cinfo.atomic, "Open cinfo was not atomic")
    pynfs_assert(open_res.opopen.resok4.cinfo.before <
        open_res.opopen.resok4.cinfo.after, "Open cinfo invalid values")

    fh = res.resarray[-1].object
    stateid = open_res.stateid
    close_file(sess, fh, stateid)

    # Create dir
    dir_name = env.testname(t)+b"dir"
    res = create_obj(sess, sess.c.homedir + [dir_name])
    check(res)
    create_res = res.resarray[3]
    pynfs_assert(create_res.opcreate.resok4.cinfo.atomic, "Create cinfo was not atomic")
    pynfs_assert(create_res.opcreate.resok4.cinfo.before <
        create_res.opcreate.resok4.cinfo.after, "Create cinfo invalid values")
    prev_after = create_res.opcreate.resok4.cinfo.after

    # Remove dir
    res = sess.compound(use_obj(sess.c.homedir) + [op.remove(dir_name)])
    check(res)
    remove_res = res.resarray[-1]
    pynfs_assert(remove_res.opremove.resok4.cinfo.atomic, "Remove cinfo was not atomic")
    pynfs_assert(remove_res.opremove.resok4.cinfo.before <
        remove_res.opremove.resok4.cinfo.after, "Remove cinfo invalid values")
    pynfs_assert(prev_after == remove_res.opremove.resok4.cinfo.before,
        "Previous after doesn't match current before")
    prev_after = remove_res.opremove.resok4.cinfo.after

    # Rename file
    res = sess.compound(use_obj(sess.c.homedir) + [op.savefh(), op.rename(file_name, file_name+b"1")])
    check(res)
    rename_res = res.resarray[-1]
    pynfs_assert(rename_res.oprename.resok4.source_cinfo.atomic, "Rename source cinfo was not atomic")
    pynfs_assert(rename_res.oprename.resok4.source_cinfo.before <
        rename_res.oprename.resok4.source_cinfo.after, "Rename source cinfo invalid values")
    pynfs_assert(prev_after == rename_res.oprename.resok4.source_cinfo.before,
        "Previous after doesn't match current source before")

    pynfs_assert(rename_res.oprename.resok4.target_cinfo.atomic, "Rename target cinfo was not atomic")
    pynfs_assert(rename_res.oprename.resok4.target_cinfo.before <
        rename_res.oprename.resok4.target_cinfo.after, "Rename target cinfo invalid values")
    pynfs_assert(prev_after == rename_res.oprename.resok4.target_cinfo.before,
        "Previous after doesn't match current target before")

def testAutoGrantBlockingLock(t, env):
    """
    FLAGS: pyNFS_custom_tests all
    CODE: EFS_LOCK_AUTO_GRANT_LOCK

    This test checks that in case we have a granted nfsv4 lock, that was not
    yet claimed by client. that in the case we get another lock that is
    contained in that range from the same client, we do not auto claim the
    first lock on behalf of the client and that we do not auto grant the
    contained lock
    """

    # Create 2 clients
    c1 = env.c1.new_client(env.testname(t)+b"_1")
    sess1 = c1.create_session()
    sess1.compound([op.reclaim_complete(FALSE)])

    c2 = env.c1.new_client(env.testname(t)+b"_2")
    sess2 = c2.create_session()
    sess2.compound([op.reclaim_complete(FALSE)])

    # create file with client 1
    res = create_file(sess1, b"owner1", path=sess1.c.homedir + [env.testname(t)+b"polled_file"])
    check(res)
    fh1 = res.resarray[-1].object
    stateid1 = res.resarray[-2].stateid

    # Open file with client 2
    res = open_file(sess2, b"owner1", path=sess2.c.homedir + [env.testname(t)+b"polled_file"], access=OPEN4_SHARE_ACCESS_BOTH)
    check(res)
    fh2 = res.resarray[-1].object
    stateid2 = res.resarray[-2].stateid
    pynfs_assert(fh1 == fh2, "Open for the same file returned different "
                             "handles. {} != {}".format(fh1, fh2))


    # Take lock
    res = requestLock(c1, sess1, fh1, stateid1, "process1", WRITEW_LT, 0, 100)
    check(res)
    lock1_stateid = res.resarray[-1].oplock.resok4.lock_stateid

    # Add waiter
    res = requestLock(c2, sess2, fh2, stateid2, "process2", WRITEW_LT, 0, 1000)
    check(res, stat=NFS4ERR_DENIED)

    # Add 2nd waiter
    res = requestLock(c1, sess1, fh1, stateid1, "process3", WRITEW_LT, 200, 10)
    check(res, stat=NFS4ERR_DENIED)

    # Unlock, so that first waiter will becomes granted (not yet locked)
    locku_op = [ op.locku(WRITE_LT, 0, lock1_stateid, 0, 100)]
    res = sess1.compound([op.putfh(fh1)] + locku_op)
    check(res)

    # Check diffrent lock from same process is not auto granted (although
    # there is a waiter in range)
    res = requestLock(c2, sess2, fh2, stateid2, "process2", WRITE_LT, 200, 10)
    check(res, stat=NFS4ERR_DENIED)

    # Wait for unclaimed granted locks to be released
    lease_time = _getleasetime(sess2)
    wait_time = GANESHA_ASYNC_LOCK_CHECK_SLEEP_TIME + lease_time \
                + GANESHA_BUFFER_TIME + 1
    sleep_while_maintaining_valid_sessions(env, [sess1, sess2], lease_time, wait_time)

    # Check we did not actually grant the second lock, and it was released as
    # unclaimed. This lock does not clash with any other lock as it is in a
    # different range
    res = requestLock(c1, sess1, fh1, stateid1, "process4", WRITE_LT, 300, 10)
    check(res)

READDIR_ATTRS = nfs4lib.list2bitmap(
    [FATTR4_TYPE, FATTR4_CHANGE, FATTR4_SIZE])

def testReaddirMaxCount(t, env):
    """
    FLAGS: pyNFS_custom_tests all
    CODE: EFS_READDIR_MAX_SIZE

    This test tries to fill readdir result buffer as much as possible to make
    sure it is possible.
    """

    # Readdir defs
    cookie = 0
    verifier = b''
    dircount = 4008
    maxcount = 4008

    c = env.c1.new_client(env.testname(t))
    sess = c.create_session()
    sess.compound([op.reclaim_complete(FALSE)])

    # We create files until we no longer receive all of them in the readdir
    log.info("Creating more files than can fit in a single readdir request...")
    dir = sess.c.homedir + [str.encode(t.code)]
    res = create_obj(sess, dir)
    check(res)
    num_files = 0
    while True:
        num_files += 1
        file_name = env.testname(t)+bytes("file_{:03d}".format(num_files), "utf-8")
        res = create_file(sess, b"owner", path=dir + [file_name])
        check(res)
        fh = res.resarray[-1].object
        stateid = res.resarray[-2].stateid

        res = close_file(sess, fh, stateid)
        check(res)

        readdir_op = op.readdir(cookie, verifier, dircount, maxcount, READDIR_ATTRS)
        res = sess.compound(use_obj(dir) + [readdir_op])
        check(res)

        num_entries = len(res.resarray[-1].reply.entries)
        if num_entries != num_files:
            pynfs_assert(num_entries == num_files - 1,
                "Readdir entries is not as expected")
            break

        # Go to a point where not all the files fit in a single readdir

    # Delete the last create file, so now it should fit in a single readdir.
    log.info("Deleting the last file")
    res = sess.compound(use_obj(dir) + [op.remove(file_name)])
    check(res)
    num_files -= 1

    # Rename file and increase the size until a single readdir call doesn't fit
    # all the entries. This will get us to maximal use of the buffer
    log.info("Increasing file name until it no longer fits in a single readdir...")
    old_file_name = env.testname(t)+bytes("file_001", "utf-8")
    while True:
        new_file_name = old_file_name + b"_"
        res = rename_obj(sess, dir + [old_file_name], dir + [new_file_name])
        check(res)
        old_file_name = new_file_name

        readdir_op = op.readdir(cookie, verifier, dircount, maxcount, READDIR_ATTRS)
        res = sess.compound(use_obj(dir) + [readdir_op])
        check(res)

        num_entries = len(res.resarray[-1].reply.entries)
        if num_entries != num_files:
            pynfs_assert(num_entries == num_files - 1,
            "Readdir entries is not as expected")
            break

    # Return the file to the state where the readdir buffers are full
    new_file_name = old_file_name[:-1]
    res = rename_obj(sess, dir + [old_file_name], dir + [new_file_name])
    check(res)

    # Verify readdir fits all the entries
    readdir_op = op.readdir(cookie, verifier, dircount, maxcount, READDIR_ATTRS)
    res = sess.compound(use_obj(dir) + [readdir_op])
    check(res)
    pynfs_assert(len(res.resarray[-1].reply.entries) == num_files,
            "Readdir entries is not as expected")

    # Add another file, so that we don't reach EOD
    file_name = env.testname(t)+b"file_999"
    res = create_file(sess, b"owner", path=dir + [file_name])
    check(res)

    # Note that since we don't can't be sure that the file with the long name
    # will be included in the readdir, we can't guarantee we'll reach the max
    # readdir size here. For that case we have EFS_READDIR_MAX_SIZE_SINGLE_FILE,
    # which does guarantee it.

    # Call readdir again
    readdir_op = op.readdir(cookie, verifier, dircount, maxcount, READDIR_ATTRS)
    res = sess.compound(use_obj(dir) + [readdir_op])
    check(res)

def testReaddirMaxCountSingleFile(t, env):
    """
    FLAGS: pyNFS_custom_tests all
    CODE: EFS_READDIR_MAX_SIZE_SINGLE_FILE

    This test tries to fill readdir result buffer as much as possible to make
    sure it is possible. It is similar to EFS_READDIR_MAX_SIZE, but reaches
    the maximum readdir size with a single file.
    """

    # Readdir defs.
    # We set samll maxcount and many attributes, so we can fill a whole readdir
    # request with a single file.
    cookie = 0
    verifier = b''
    dircount = 128
    maxcount = 128

    c = env.c1.new_client(env.testname(t))
    sess = c.create_session()
    sess.compound([op.reclaim_complete(FALSE)])

    dir = sess.c.homedir + [str.encode(t.code)]
    res = create_obj(sess, dir)
    check(res)
    file_name = env.testname(t)+b"file"
    log.info("Creating a file {}".format(file_name))

    res = create_file(sess, b"owner", path=dir + [file_name])
    check(res)
    fh = res.resarray[-1].object
    stateid = res.resarray[-2].stateid

    res = close_file(sess, fh, stateid)
    check(res)

    # Verify that the file initially fits in a readdir request
    readdir_op = op.readdir(cookie, verifier, dircount, maxcount, READDIR_ATTRS)
    res = sess.compound(use_obj(dir) + [readdir_op])
    check(res)
    pynfs_assert(len(res.resarray[-1].reply.entries) == 1,
        "Not able to initially readdir create file")

    log.info("Making the file name longer, until it can't fit in a readddir request...")
    while True:
        readdir_op = op.readdir(cookie, verifier, dircount, maxcount, READDIR_ATTRS)
        res = sess.compound(use_obj(dir) + [readdir_op])
        if res.status == NFS4ERR_TOOSMALL:
            # Passed the readdir limit
            break

        check(res)
        pynfs_assert(len(res.resarray[-1].reply.entries) == 1,
            "Invalid number of entries for readdir")

        # Make the file name larger
        new_file_name = file_name + b'_'
        res = rename_obj(sess, dir + [file_name], dir + [new_file_name])
        check(res)
        file_name = new_file_name

    # File name no longer fits in a single readdir, return to previous state
    new_file_name = file_name[:-1]
    res = rename_obj(sess, dir + [file_name], dir + [new_file_name])
    check(res)
    file_name = new_file_name

    log.info("Found max name length that fits in a single readdir: " + str(len(file_name)))

    # We now create another file with the same name length. This means that the
    # next readdir will be comepltely full, but also not reach EOF
    log.info("Creating another file with the same name length")
    file2_name = file_name[:-1] + b'z'

    res = create_file(sess, b"owner", path=dir + [file2_name])
    check(res)
    fh = res.resarray[-1].object
    stateid = res.resarray[-2].stateid

    res = close_file(sess, fh, stateid)
    check(res)

    log.info("Calling readdir with larges possible request...")
    readdir_op = op.readdir(cookie, verifier, dircount, maxcount, READDIR_ATTRS)
    res = sess.compound(use_obj(dir) + [readdir_op])
    check(res)

def create_files_until_session_destroyed(session, owner_id):
    while True:
        file_name = bytes("file_" + str(uuid.uuid4()), "utf-8")
        res = create_file(session, owner_id, path=session.c.homedir + [file_name])
        if res.status == NFS4_OK:
            continue
        if res.status == NFS4ERR_BADSESSION or res.status == NFS4ERR_EXPIRED:
            # Session was destroyed.
            break
        else:
            raise FailureException("Create file failed with unexpected error: " + str(res.status))

def testSameOwnerId(t, env):
    """
    FLAGS: pyNFS_custom_tests all
    CODE: EFS_SAME_OWNER_ID

    This Tests what happens when two clients use the same owner id (usually it means
    they have the same hostname).
    This runs open operations, which create an open state, while starting a session
    from a different client with the same owner id.
    Starting a new session with the same owner id causes the previous state to expire.
    This test makes sure the experiation is handled properly, Ganesha doesn't crash,
    and that no state is leaked (leaked states should cause the create session op to
    get stuck).

    For more info on the issue that prompted us to write this test, see b/374334061.
    """

    shared_owner_id = b"test_owner_id"
    verf1 = b"verf1"
    verf2 = b"verf2"

    # Create session an get 2 open states
    c1 = env.c1.new_client(shared_owner_id, verf=verf1)
    sess1 = c1.create_session()
    sess1.compound([op.reclaim_complete(FALSE)])

    # pyNFS by default creates a session with 8 slots. We can't run more than 8
    # operations at the same time.
    NUM_CREATE_WORKERS = 7
    with ThreadPoolExecutor(NUM_CREATE_WORKERS) as executor:
        futures = [executor.submit(create_files_until_session_destroyed, sess1, shared_owner_id)
            for x in range(NUM_CREATE_WORKERS)]

        # Create another session with the same owner id and a different verifier.
        # This will cause the previous session to become stale
        c2 = env.c1.new_client(shared_owner_id, verf=verf2)
        sess2 = c2.create_session()
        sess2.compound([op.reclaim_complete(FALSE)])

        # Wait for all threads to end.
        for future in futures:
            future.result()

    # Try to use the previous session and client - should be stale.
    res = create_file(sess1, shared_owner_id, path=sess1.c.homedir + [env.testname(t)+b"file"])
    check(res, stat=NFS4ERR_BADSESSION)

    # Note that we use "_create_session" here, and not "create_session". This version
    # of the function doesn't assert that it succeeds.
    res = c1._create_session()
    check(res, stat=NFS4ERR_STALE_CLIENTID)
