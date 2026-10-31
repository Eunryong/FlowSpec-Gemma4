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
    slots = engine.query_available_slots("C1")
    assert len(slots) == 0

def test_session_pass_idempotency():
    engine = CounselingBookingEngine()
    email = "client@test.com"
    pass_info = engine.issue_session_pass(email, 5, "key1")
    assert pass_info["remaining_sessions"] == 5
    
    pass_info2 = engine.issue_session_pass(email, 5, "key1")
    assert pass_info2["remaining_sessions"] == 5
    
    pass_info3 = engine.issue_session_pass(email, 3, "key2")
    assert pass_info3["remaining_sessions"] == 8

def test_booking_creation_and_double_booking():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    email = "client@test.com"
    engine.issue_session_pass(email, 1, "key1")
    
    booking = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client A", email, "book1")
    assert booking["status"] == "CONFIRMED"
    assert engine.get_session_pass(email)["remaining_sessions"] == 0
    
    with pytest.raises(ValueError):
        engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client B", "other@test.com")

def test_booking_failure_rollback():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    
    with pytest.raises(ValueError):
        engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client A", "no-pass@test.com")
    
    slots = engine.query_available_slots("C1")
    assert len(slots) == 1

def test_atomic_rescheduling():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("C1", "2026-10-20T15:00:00+09:00")
    email = "client@test.com"
    engine.issue_session_pass(email, 1, "key1")
    
    booking = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client A", email)
    bid = booking["booking_id"]
    
    rescheduled = engine.reschedule_booking(bid, email, "C1", "2026-10-20T15:00:00+09:00")
    assert rescheduled["start_time"] == "2026-10-20T15:00:00+09:00"
    assert engine.get_session_pass(email)["remaining_sessions"] == 0
    
    slots = engine.query_available_slots("C1")
    assert len(slots) == 1
    assert slots[0]["start_time"] == "2026-10-20T14:00:00+09:00"

def test_cancellation_and_restoration():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    email = "client@test.com"
    engine.issue_session_pass(email, 1, "key1")
    
    booking = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client A", email)
    engine.cancel_booking(booking["booking_id"], email)
    
    assert engine.get_session_pass(email)["remaining_sessions"] == 1
    slots = engine.query_available_slots("C1")
    assert len(slots) == 1

def test_waitlist_auto_promotion():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    
    email1 = "c1@test.com"
    email2 = "c2@test.com"
    engine.issue_session_pass(email1, 1, "k1")
    engine.issue_session_pass(email2, 1, "k2")
    
    b1 = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client 1", email1)
    engine.join_waitlist("C1", "2026-10-20T14:00:00+09:00", "Client 2", email2)
    
    engine.cancel_booking(b1["booking_id"], email1)
    
    assert engine.get_session_pass(email2)["remaining_sessions"] == 0
    bookings = engine.conn.execute("SELECT * FROM bookings WHERE status='CONFIRMED'").fetchall()
    assert len(bookings) == 1
    assert bookings[0]["client_email"] == email2

def test_global_reconciliation():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("C1", "2026-10-20T15:00:00+09:00")
    
    email1 = "c1@test.com"
    email2 = "c2@test.com"
    engine.issue_session_pass(email1, 2, "k1")
    engine.issue_session_pass(email2, 1, "k2")
    
    b1 = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client 1", email1)
    engine.join_waitlist("C1", "2026-10-20T14:00:00+09:00", "Client 2", email2)
    
    engine.cancel_booking(b1["booking_id"], email1)
    
    recon = engine.get_system_reconciliation()
    assert recon["is_balanced"] is True
    assert recon["total_issued_sessions"] == 3
    assert recon["active_confirmed_bookings"] == 1
    assert recon["booked_slots_count"] == 1
