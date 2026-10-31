import pytest
from counseling_engine import CounselingBookingEngine

def test_counselor_slot_lifecycle():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    slot = engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    assert slot["status"] == "AVAILABLE"
    
    engine.block_slot("C1", "2026-10-20T14:00:00+09:00")
    available = engine.query_available_slots("C1")
    assert len(available) == 0
    
    with pytest.raises(ValueError):
        engine.block_slot("C1", "2026-10-20T14:00:00+09:00")

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
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Bob", "client@test.com", "bkey1")
    assert booking["status"] == "CONFIRMED"
    assert engine.get_session_pass("client@test.com")["remaining_sessions"] == 0
    
    with pytest.raises(ValueError):
        engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Charlie", "other@test.com")

def test_booking_failure_insufficient_pass():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    
    with pytest.raises(ValueError):
        engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Bob", "client@test.com")
    
    available = engine.query_available_slots("C1")
    assert len(available) == 1

def test_atomic_rescheduling():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.register_counselor("C2", "Dave", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("C2", "2026-10-20T15:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Bob", "client@test.com")
    bid = booking["booking_id"]
    
    updated = engine.reschedule_booking(bid, "client@test.com", "C2", "2026-10-20T15:00:00+09:00")
    assert updated["counselor_id"] == "C2"
    assert updated["start_time"] == "2026-10-20T15:00:00+09:00"
    assert engine.get_session_pass("client@test.com")["remaining_sessions"] == 0
    
    # Verify old slot is available
    available = engine.query_available_slots("C1")
    assert len(available) == 1

def test_cancellation_and_restoration():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Bob", "client@test.com")
    engine.cancel_booking(booking["booking_id"], "client@test.com")
    
    assert engine.get_session_pass("client@test.com")["remaining_sessions"] == 1
    available = engine.query_available_slots("C1")
    assert len(available) == 1

def test_waitlist_auto_promotion():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client1@test.com", 1, "k1")
    engine.issue_session_pass("client2@test.com", 1, "k2")
    
    b1 = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Bob", "client1@test.com")
    engine.join_waitlist("C1", "2026-10-20T14:00:00+09:00", "Charlie", "client2@test.com")
    
    engine.cancel_booking(b1["booking_id"], "client1@test.com")
    
    # Client 2 should be promoted
    pass2 = engine.get_session_pass("client2@test.com")
    assert pass2["remaining_sessions"] == 0
    
    # Slot should still be BOOKED
    available = engine.query_available_slots("C1")
    assert len(available) == 0
    
    # Check if a new booking exists for client 2
    bookings = engine.conn.execute("SELECT * FROM bookings WHERE client_email='client2@test.com' AND status='CONFIRMED'").fetchall()
    assert len(bookings) == 1

def test_global_reconciliation():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("C1", "2026-10-20T15:00:00+09:00")
    engine.issue_session_pass("c1@test.com", 2, "k1")
    
    b1 = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Bob", "c1@test.com")
    engine.cancel_booking(b1["booking_id"], "c1@test.com")
    
    recon = engine.get_system_reconciliation()
    assert recon["is_balanced"] is True
