import pytest
from counseling_engine import CounselingBookingEngine

def test_counselor_slot_lifecycle():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    slot = engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    assert slot["status"] == "AVAILABLE"
    engine.block_slot("c1", "2026-10-20T14:00:00+09:00")
    assert len(engine.query_available_slots("c1")) == 0
    with pytest.raises(ValueError):
        engine.block_slot("c1", "2026-10-20T14:00:00+09:00")

def test_session_pass_idempotency():
    engine = CounselingBookingEngine()
    res = engine.issue_session_pass("client@test.com", 5, "key1")
    assert res["remaining_sessions"] == 5
    res2 = engine.issue_session_pass("client@test.com", 5, "key1")
    assert res2["remaining_sessions"] == 5
    res3 = engine.issue_session_pass("client@test.com", 3, "key2")
    assert res3["remaining_sessions"] == 8

def test_booking_creation_and_double_booking():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client", "client@test.com", "bkey1")
    assert booking["status"] == "CONFIRMED"
    assert engine.get_session_pass("client@test.com")["remaining_sessions"] == 0
    
    with pytest.raises(ValueError):
        engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Other", "other@test.com")

def test_booking_failure_insufficient_pass():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    
    with pytest.raises(ValueError):
        engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client", "client@test.com")
    
    assert len(engine.query_available_slots("c1")) == 1

def test_atomic_rescheduling():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.register_counselor("c2", "Bob", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("c2", "2026-10-20T15:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client", "client@test.com")
    bid = booking["booking_id"]
    
    rescheduled = engine.reschedule_booking(bid, "client@test.com", "c2", "2026-10-20T15:00:00+09:00")
    assert rescheduled["counselor_id"] == "c2"
    assert rescheduled["start_time"] == "2026-10-20T15:00:00+09:00"
    assert len(engine.query_available_slots("c1")) == 1
    assert engine.get_session_pass("client@test.com")["remaining_sessions"] == 0

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
    engine.issue_session_pass("c1_email@test.com", 1, "k1")
    engine.issue_session_pass("c2_email@test.com", 1, "k2")
    
    b1 = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client 1", "c1_email@test.com")
    engine.join_waitlist("c1", "2026-10-20T14:00:00+09:00", "Client 2", "c2_email@test.com")
    
    engine.cancel_booking(b1["booking_id"], "c1_email@test.com")
    
    # Client 2 should be promoted
    bookings = engine.conn.execute("SELECT * FROM bookings WHERE status='CONFIRMED'").fetchall()
    assert len(bookings) == 1
    assert bookings[0]['client_email'] == "c2_email@test.com"
    assert engine.get_session_pass("c2_email@test.com")["remaining_sessions"] == 0

def test_global_reconciliation():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("c1", "2026-10-20T15:00:00+09:00")
    engine.issue_session_pass("c1@test.com", 2, "k1")
    
    b1 = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client 1", "c1@test.com")
    engine.cancel_booking(b1["booking_id"], "c1@test.com")
    
    recon = engine.get_system_reconciliation()
    assert recon["is_balanced"] is True
