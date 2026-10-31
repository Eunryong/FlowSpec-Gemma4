import pytest
from counseling_engine import CounselingBookingEngine

def test_counselor_slot_lifecycle():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    
    # Block slot
    engine.block_slot("c1", "2026-10-20T14:00:00+09:00")
    slots = engine.query_available_slots("c1")
    assert len(slots) == 0
    
    # Try to block already blocked slot
    with pytest.raises(ValueError):
        engine.block_slot("c1", "2026-10-20T14:00:00+09:00")

def test_session_pass_idempotency():
    engine = CounselingBookingEngine()
    engine.issue_session_pass("client@test.com", 5, "key1")
    pass_info = engine.get_session_pass("client@test.com")
    assert pass_info['remaining_sessions'] == 5
    
    # Duplicate key
    engine.issue_session_pass("client@test.com", 5, "key1")
    pass_info = engine.get_session_pass("client@test.com")
    assert pass_info['remaining_sessions'] == 5

def test_booking_creation_and_double_booking():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client A", "client@test.com")
    assert booking['status'] == "CONFIRMED"
    assert engine.get_session_pass("client@test.com")['remaining_sessions'] == 0
    
    # Double booking
    with pytest.raises(ValueError):
        engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client B", "clientB@test.com")

def test_booking_failure_insufficient_pass():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    
    with pytest.raises(ValueError):
        engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client A", "client@test.com")
    
    slots = engine.query_available_slots("c1")
    assert len(slots) == 1

def test_atomic_rescheduling():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("c1", "2026-10-20T15:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client A", "client@test.com")
    b_id = booking['booking_id']
    
    rescheduled = engine.reschedule_booking(b_id, "client@test.com", "c1", "2026-10-20T15:00:00+09:00")
    assert rescheduled['start_time'] == "2026-10-20T15:00:00+09:00"
    assert engine.get_session_pass("client@test.com")['remaining_sessions'] == 0
    
    # Try to reschedule into booked slot
    engine.issue_session_pass("clientB@test.com", 1, "key2")
    engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client B", "clientB@test.com")
    
    with pytest.raises(ValueError):
        engine.reschedule_booking(b_id, "client@test.com", "c1", "2026-10-20T14:00:00+09:00")

def test_cancellation_and_restoration():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client A", "client@test.com")
    b_id = booking['booking_id']
    
    engine.cancel_booking(b_id, "client@test.com")
    assert engine.get_session_pass("client@test.com")['remaining_sessions'] == 1
    assert len(engine.query_available_slots("c1")) == 1

def test_waitlist_auto_promotion():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("clientA@test.com", 1, "key1")
    engine.issue_session_pass("clientB@test.com", 1, "key2")
    
    bookingA = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client A", "clientA@test.com")
    engine.join_waitlist("c1", "2026-10-20T14:00:00+09:00", "Client B", "clientB@test.com")
    
    engine.cancel_booking(bookingA['booking_id'], "clientA@test.com")
    
    # Client B should be promoted
    bookings = engine.conn.execute("SELECT * FROM bookings WHERE client_email='clientB@test.com' AND status='CONFIRMED'").fetchone()
    assert bookings is not None
    assert engine.get_session_pass("clientB@test.com")['remaining_sessions'] == 0

def test_global_reconciliation():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("c1", "2026-10-20T15:00:00+09:00")
    
    engine.issue_session_pass("clientA@test.com", 2, "key1")
    engine.issue_session_pass("clientB@test.com", 1, "key2")
    
    b1 = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client A", "clientA@test.com")
    b2 = engine.create_booking("c1", "2026-10-20T15:00:00+09:00", "Client B", "clientB@test.com")
    
    recon = engine.get_system_reconciliation()
    assert recon['is_balanced'] == True
    
    engine.cancel_booking(b1['booking_id'], "clientA@test.com")
    recon = engine.get_system_reconciliation()
    assert recon['is_balanced'] == True
