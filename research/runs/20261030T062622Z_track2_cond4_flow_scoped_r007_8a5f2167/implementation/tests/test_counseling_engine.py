import pytest
from counseling_engine import CounselingBookingEngine

def test_counselor_slot_lifecycle():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    with pytest.raises(ValueError):
        engine.register_counselor("C1", "Bob", "Psychology")
    
    slot = engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    assert slot["status"] == "AVAILABLE"
    
    with pytest.raises(ValueError):
        engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    
    engine.block_slot("C1", "2026-10-20T14:00:00+09:00")
    assert engine.query_available_slots("C1") == []

def test_session_pass_idempotency():
    engine = CounselingBookingEngine()
    email = "client@test.com"
    engine.issue_session_pass(email, 5, "key1")
    pass_info = engine.get_session_pass(email)
    assert pass_info["remaining_sessions"] == 5
    
    engine.issue_session_pass(email, 5, "key1")
    pass_info = engine.get_session_pass(email)
    assert pass_info["remaining_sessions"] == 5

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

def test_booking_failure_insufficient_pass():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    
    with pytest.raises(ValueError):
        engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client A", "no-pass@test.com")
    
    assert len(engine.query_available_slots("C1")) == 1

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
    
    engine.reschedule_booking(bid, email, "C2", "2026-10-20T15:00:00+09:00")
    
    updated = engine.lookup_booking(bid, email)
    assert updated["counselor_id"] == "C2"
    assert updated["start_time"] == "2026-10-20T15:00:00+09:00"
    assert len(engine.query_available_slots("C1")) == 1
    assert len(engine.query_available_slots("C2")) == 0

def test_cancellation_and_restoration():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    email = "client@test.com"
    engine.issue_session_pass(email, 1, "key1")
    booking = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client A", email)
    
    engine.cancel_booking(booking["booking_id"], email)
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
    engine.join_waitlist("C1", "2026-10-20T14:00:00+09:00", "Client 2", email2)
    
    engine.cancel_booking(booking1["booking_id"], email1)
    
    assert engine.get_session_pass(email2)["remaining_sessions"] == 0
    assert engine.conn.execute("SELECT COUNT(*) FROM bookings WHERE status = 'CONFIRMED'").fetchone()[0] == 1
    assert engine.conn.execute("SELECT COUNT(*) FROM slots WHERE status = 'BOOKED'").fetchone()[0] == 1

def test_global_reconciliation():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("C1", "2026-10-20T15:00:00+09:00")
    
    email = "client@test.com"
    engine.issue_session_pass(email, 2, "k1")
    
    b1 = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client A", email)
    engine.cancel_booking(b1["booking_id"], email)
    
    recon = engine.get_system_reconciliation()
    assert recon["is_balanced"] is True
