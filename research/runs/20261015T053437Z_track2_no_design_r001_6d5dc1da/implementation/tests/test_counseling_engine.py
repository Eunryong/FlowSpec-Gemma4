import pytest
from counseling_engine import CounselingBookingEngine

def test_counselor_slot_lifecycle():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    
    # Block slot
    engine.block_slot("c1", "2026-10-20T14:00:00+09:00")
    assert len(engine.query_available_slots("c1")) == 0
    
    # Try to block again
    with pytest.raises(ValueError):
        engine.block_slot("c1", "2026-10-20T14:00:00+09:00")

def test_session_pass_idempotency():
    engine = CounselingBookingEngine()
    engine.issue_session_pass("client@test.com", 5, "key1")
    pass_info = engine.get_session_pass("client@test.com")
    assert pass_info["remaining_sessions"] == 5
    
    # Repeat with same key
    engine.issue_session_pass("client@test.com", 5, "key1")
    pass_info = engine.get_session_pass("client@test.com")
    assert pass_info["remaining_sessions"] == 5

def test_booking_creation_and_double_booking():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Bob", "client@test.com")
    assert booking["status"] == "CONFIRMED"
    assert engine.get_session_pass("client@test.com")["remaining_sessions"] == 0
    
    # Double booking
    with pytest.raises(ValueError):
        engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Charlie", "other@test.com")

def test_booking_failure_insufficient_pass():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    
    with pytest.raises(ValueError):
        engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Bob", "client@test.com")
    
    assert len(engine.query_available_slots("c1")) == 1

def test_atomic_rescheduling():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.register_counselor("c2", "Dave", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("c2", "2026-10-20T15:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Bob", "client@test.com")
    booking_id = booking["booking_id"]
    
    engine.reschedule_booking(booking_id, "client@test.com", "c2", "2026-10-20T15:00:00+09:00")
    
    updated = engine.lookup_booking(booking_id, "client@test.com")
    assert updated["counselor_id"] == "c2"
    assert updated["start_time"] == "2026-10-20T15:00:00+09:00"
    assert len(engine.query_available_slots("c1")) == 1

def test_cancellation_and_restoration():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Bob", "client@test.com")
    engine.cancel_booking(booking["booking_id"], "client@test.com")
    
    assert engine.get_session_pass("client@test.com")["remaining_sessions"] == 1
    assert len(engine.query_available_slots("c1")) == 1

def test_waitlist_auto_promotion():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client1@test.com", 1, "k1")
    engine.issue_session_pass("client2@test.com", 1, "k2")
    
    b1 = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Bob", "client1@test.com")
    engine.join_waitlist("c1", "2026-10-20T14:00:00+09:00", "Charlie", "client2@test.com")
    
    engine.cancel_booking(b1["booking_id"], "client1@test.com")
    
    # Check if client2 is promoted
    bookings = engine.conn.execute("SELECT * FROM bookings WHERE status = 'CONFIRMED'").fetchall()
    assert len(bookings) == 1
    assert bookings[0]["client_email"] == "client2@test.com"
    assert engine.get_session_pass("client2@test.com")["remaining_sessions"] == 0

def test_global_reconciliation():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("c1", "2026-10-20T15:00:00+09:00")
    engine.issue_session_pass("client1@test.com", 2, "k1")
    
    b1 = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Bob", "client1@test.com")
    engine.cancel_booking(b1["booking_id"], "client1@test.com")
    
    recon = engine.get_system_reconciliation()
    assert recon["is_balanced"] is True
