import pytest
from counseling_engine import CounselingBookingEngine

def test_counselor_slot_lifecycle():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "General")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    
    # Block slot
    engine.block_slot("c1", "2026-10-20T14:00:00+09:00")
    slots = engine.query_available_slots("c1")
    assert len(slots) == 0
    
    # Try to block again
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
    engine.register_counselor("c1", "Alice", "General")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client A", "client@test.com")
    assert booking['status'] == "CONFIRMED"
    assert engine.get_session_pass("client@test.com")['remaining_sessions'] == 0
    
    # Double booking
    engine.issue_session_pass("client2@test.com", 1, "key2")
    with pytest.raises(ValueError):
        engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client B", "client2@test.com")

def test_booking_failure_rollback():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "General")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    
    # No sessions
    with pytest.raises(ValueError):
        engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client A", "client@test.com")
    
    slots = engine.query_available_slots("c1")
    assert len(slots) == 1

def test_atomic_rescheduling():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "General")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("c1", "2026-10-20T15:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client A", "client@test.com")
    bid = booking['booking_id']
    
    engine.reschedule_booking(bid, "client@test.com", "c1", "2026-10-20T15:00:00+09:00")
    
    updated = engine.lookup_booking(bid, "client@test.com")
    assert updated['start_time'] == "2026-10-20T15:00:00+09:00"
    assert len(engine.query_available_slots("c1")) == 1 # 14:00 should be free

def test_cancellation_and_restoration():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "General")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client A", "client@test.com")
    engine.cancel_booking(booking['booking_id'], "client@test.com")
    
    assert engine.get_session_pass("client@test.com")['remaining_sessions'] == 1
    assert len(engine.query_available_slots("c1")) == 1

def test_waitlist_auto_promotion():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "General")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    
    engine.issue_session_pass("c1_email@test.com", 1, "k1")
    engine.issue_session_pass("c2_email@test.com", 1, "k2")
    
    b1 = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client 1", "c1_email@test.com")
    engine.join_waitlist("c1", "2026-10-20T14:00:00+09:00", "Client 2", "c2_email@test.com")
    
    engine.cancel_booking(b1['booking_id'], "c1_email@test.com")
    
    # Client 2 should be promoted
    assert engine.get_session_pass("c2_email@test.com")['remaining_sessions'] == 0
    # Slot should still be BOOKED
    assert len(engine.query_available_slots("c1")) == 0
    # There should be a new confirmed booking
    reconcile = engine.get_system_reconciliation()
    assert reconcile['active_confirmed_bookings'] == 1

def test_global_reconciliation():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "General")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("c1", "2026-10-20T15:00:00+09:00")
    
    engine.issue_session_pass("c1@test.com", 2, "k1")
    b1 = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "C1", "c1@test.com")
    
    engine.issue_session_pass("c2@test.com", 1, "k2")
    engine.join_waitlist("c1", "2026-10-20T14:00:00+09:00", "C2", "c2@test.com")
    
    engine.cancel_booking(b1['booking_id'], "c1@test.com")
    
    reconcile = engine.get_system_reconciliation()
    assert reconcile['is_balanced'] is True
