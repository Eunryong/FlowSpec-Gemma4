import pytest
from counseling_engine import CounselingBookingEngine

def test_counselor_slot_lifecycle():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    with pytest.raises(ValueError):
        engine.register_counselor("c1", "Alice", "Psychology")
    
    slot = engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    assert slot["status"] == "AVAILABLE"
    with pytest.raises(ValueError):
        engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    
    engine.block_slot("c1", "2026-10-20T14:00:00+09:00")
    slots = engine.query_available_slots("c1")
    assert len(slots) == 0

def test_session_pass_idempotency():
    engine = CounselingBookingEngine()
    engine.issue_session_pass("client@test.com", 5, "key1")
    pass_info = engine.get_session_pass("client@test.com")
    assert pass_info["remaining_sessions"] == 5
    
    engine.issue_session_pass("client@test.com", 5, "key1")
    pass_info = engine.get_session_pass("client@test.com")
    assert pass_info["remaining_sessions"] == 5

def test_booking_creation_and_double_booking():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client", "client@test.com", "bkey1")
    assert booking["status"] == "CONFIRMED"
    assert engine.get_session_pass("client@test.com")["remaining_sessions"] == 0
    
    with pytest.raises(ValueError):
        engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client2", "client2@test.com")

def test_booking_failure_insufficient_pass():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    
    with pytest.raises(ValueError):
        engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client", "client@test.com")
    
    slots = engine.query_available_slots("c1")
    assert len(slots) == 1

def test_atomic_rescheduling():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.register_counselor("c2", "Bob", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("c2", "2026-10-21T14:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client", "client@test.com")
    booking_id = booking["booking_id"]
    
    rescheduled = engine.reschedule_booking(booking_id, "client@test.com", "c2", "2026-10-21T14:00:00+09:00")
    assert rescheduled["counselor_id"] == "c2"
    assert rescheduled["start_time"] == "2026-10-21T14:00:00+09:00"
    
    # Check old slot is available
    slots = engine.query_available_slots("c1")
    assert len(slots) == 1
    
    # Try reschedule to booked slot
    engine.add_slot("c1", "2026-10-22T14:00:00+09:00")
    engine.issue_session_pass("client2@test.com", 1, "key2")
    engine.create_booking("c1", "2026-10-22T14:00:00+09:00", "Client2", "client2@test.com")
    
    with pytest.raises(ValueError):
        engine.reschedule_booking(booking_id, "client@test.com", "c1", "2026-10-22T14:00:00+09:00")

def test_cancellation_and_restoration():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client", "client@test.com")
    engine.cancel_booking(booking["booking_id"], "client@test.com")
    
    assert engine.get_session_pass("client@test.com")["remaining_sessions"] == 1
    assert len(engine.query_available_slots("c1")) == 1

def test_waitlist_auto_promotion():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client1@test.com", 1, "key1")
    engine.issue_session_pass("client2@test.com", 1, "key2")
    
    booking1 = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client1", "client1@test.com")
    engine.join_waitlist("c1", "2026-10-20T14:00:00+09:00", "Client2", "client2@test.com")
    
    engine.cancel_booking(booking1["booking_id"], "client1@test.com")
    
    # Client 2 should be promoted
    bookings = engine.conn.execute("SELECT * FROM bookings WHERE status = 'CONFIRMED'").fetchall()
    assert len(bookings) == 1
    assert bookings[0]["client_email"] == "client2@test.com"
    assert engine.get_session_pass("client2@test.com")["remaining_sessions"] == 0

def test_global_reconciliation():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("c1", "2026-10-21T14:00:00+09:00")
    engine.issue_session_pass("client1@test.com", 2, "key1")
    
    b1 = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client1", "client1@test.com")
    engine.cancel_booking(b1["booking_id"], "client1@test.com")
    
    recon = engine.get_system_reconciliation()
    assert recon["is_balanced"] is True
