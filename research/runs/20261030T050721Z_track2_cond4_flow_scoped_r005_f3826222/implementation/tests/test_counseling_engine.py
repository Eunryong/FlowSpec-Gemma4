import pytest
from counseling_engine import CounselingBookingEngine

def test_counselor_slot_lifecycle():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    with pytest.raises(ValueError):
        engine.register_counselor("C1", "Alice", "Psychology")
    
    slot = engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    assert slot["status"] == "AVAILABLE"
    with pytest.raises(ValueError):
        engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    
    engine.block_slot("C1", "2026-10-20T14:00:00+09:00")
    available = engine.query_available_slots("C1")
    assert len(available) == 0

def test_session_pass_idempotency():
    engine = CounselingBookingEngine()
    email = "client@test.com"
    res1 = engine.issue_session_pass(email, 5, "key1")
    assert res1["remaining_sessions"] == 5
    res2 = engine.issue_session_pass(email, 5, "key1")
    assert res2["remaining_sessions"] == 5
    res3 = engine.issue_session_pass(email, 3, "key2")
    assert res3["remaining_sessions"] == 8

def test_booking_creation_and_double_booking():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    email = "client@test.com"
    engine.issue_session_pass(email, 1, "key1")
    
    booking = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client A", email, "bkey1")
    assert booking["status"] == "CONFIRMED"
    assert engine.get_session_pass(email)["remaining_sessions"] == 0
    
    with pytest.raises(ValueError):
        engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client B", "other@test.com", "bkey2")

def test_booking_failure_rollback():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    email = "client@test.com"
    # No sessions issued
    with pytest.raises(ValueError):
        engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client A", email)
    
    available = engine.query_available_slots("C1")
    assert len(available) == 1

def test_atomic_rescheduling():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.register_counselor("C2", "Bob", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("C2", "2026-10-20T15:00:00+09:00")
    email = "client@test.com"
    engine.issue_session_pass(email, 1, "key1")
    
    booking = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client A", email)
    bid = booking["booking_id"]
    
    rescheduled = engine.reschedule_booking(bid, email, "C2", "2026-10-20T15:00:00+09:00")
    assert rescheduled["counselor_id"] == "C2"
    assert rescheduled["start_time"] == "2026-10-20T15:00:00+09:00"
    assert engine.get_session_pass(email)["remaining_sessions"] == 0
    
    # Verify old slot is available
    available = engine.query_available_slots("C1")
    assert len(available) == 1

def test_cancellation_and_restoration():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    email = "client@test.com"
    engine.issue_session_pass(email, 1, "key1")
    
    booking = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client A", email)
    bid = booking["booking_id"]
    
    engine.cancel_booking(bid, email)
    assert engine.get_session_pass(email)["remaining_sessions"] == 1
    assert len(engine.query_available_slots("C1")) == 1

def test_waitlist_auto_promotion():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    
    email1 = "client1@test.com"
    email2 = "client2@test.com"
    engine.issue_session_pass(email1, 1, "k1")
    engine.issue_session_pass(email2, 1, "k2")
    
    booking1 = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client 1", email1)
    bid1 = booking1["booking_id"]
    
    engine.join_waitlist("C1", "2026-10-20T14:00:00+09:00", "Client 2", email2)
    
    engine.cancel_booking(bid1, email1)
    
    # Client 2 should be promoted
    assert engine.get_session_pass(email2)["remaining_sessions"] == 0
    assert engine.get_system_reconciliation()["active_confirmed_bookings"] == 1
    assert engine.get_system_reconciliation()["booked_slots_count"] == 1

def test_global_reconciliation():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("C1", "2026-10-20T15:00:00+09:00")
    
    email1 = "client1@test.com"
    email2 = "client2@test.com"
    engine.issue_session_pass(email1, 2, "k1")
    engine.issue_session_pass(email2, 1, "k2")
    
    b1 = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client 1", email1)
    b2 = engine.create_booking("C1", "2026-10-20T15:00:00+09:00", "Client 2", email2)
    
    engine.cancel_booking(b1["booking_id"], email1)
    
    recon = engine.get_system_reconciliation()
    assert recon["is_balanced"] is True
    assert recon["active_confirmed_bookings"] == 1
    assert recon["booked_slots_count"] == 1
