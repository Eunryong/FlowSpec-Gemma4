import pytest
from counseling_engine import CounselingBookingEngine

@pytest.fixture
def engine():
    return CounselingBookingEngine(":memory:")

def test_counselor_slot_lifecycle(engine):
    engine.register_counselor("c1", "Alice", "Psychology")
    slot = engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    assert slot["status"] == "AVAILABLE"
    
    engine.block_slot("c1", "2026-10-20T14:00:00+09:00")
    available = engine.query_available_slots("c1")
    assert len(available) == 0
    
    with pytest.raises(ValueError):
        engine.block_slot("c1", "2026-10-20T14:00:00+09:00")

def test_session_pass_idempotency(engine):
    engine.issue_session_pass("client@test.com", 5, "key1")
    pass_info = engine.get_session_pass("client@test.com")
    assert pass_info["remaining_sessions"] == 5
    
    engine.issue_session_pass("client@test.com", 5, "key1")
    pass_info = engine.get_session_pass("client@test.com")
    assert pass_info["remaining_sessions"] == 5

def test_booking_creation_and_double_booking(engine):
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Bob", "client@test.com", "bkey1")
    assert booking["status"] == "CONFIRMED"
    assert engine.get_session_pass("client@test.com")["remaining_sessions"] == 0
    
    with pytest.raises(ValueError):
        engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Charlie", "charlie@test.com")

def test_booking_failure_insufficient_pass(engine):
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    
    with pytest.raises(ValueError):
        engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Bob", "client@test.com")
    
    available = engine.query_available_slots("c1")
    assert len(available) == 1

def test_atomic_rescheduling(engine):
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.register_counselor("c2", "Dave", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("c2", "2026-10-20T15:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Bob", "client@test.com")
    bid = booking["booking_id"]
    
    rescheduled = engine.reschedule_booking(bid, "client@test.com", "c2", "2026-10-20T15:00:00+09:00")
    assert rescheduled["counselor_id"] == "c2"
    assert rescheduled["start_time"] == "2026-10-20T15:00:00+09:00"
    assert engine.get_session_pass("client@test.com")["remaining_sessions"] == 0
    
    available = engine.query_available_slots("c1")
    assert len(available) == 1 # old slot freed

def test_cancellation_and_restoration(engine):
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Bob", "client@test.com")
    bid = booking["booking_id"]
    
    engine.cancel_booking(bid, "client@test.com")
    assert engine.get_session_pass("client@test.com")["remaining_sessions"] == 1
    assert len(engine.query_available_slots("c1")) == 1

def test_waitlist_auto_promotion(engine):
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    
    engine.issue_session_pass("client1@test.com", 1, "k1")
    engine.issue_session_pass("client2@test.com", 1, "k2")
    
    booking1 = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Bob", "client1@test.com")
    bid1 = booking1["booking_id"]
    
    engine.join_waitlist("c1", "2026-10-20T14:00:00+09:00", "Charlie", "client2@test.com")
    
    engine.cancel_booking(bid1, "client1@test.com")
    
    # Client 2 should be promoted
    assert engine.get_session_pass("client2@test.com")["remaining_sessions"] == 0
    # Slot should still be BOOKED
    assert len(engine.query_available_slots("c1")) == 0
    # There should be a new confirmed booking
    recon = engine.get_system_reconciliation()
    assert recon["active_confirmed_bookings"] == 1

def test_global_reconciliation_and_audit(engine):
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("c1", "2026-10-20T15:00:00+09:00")
    
    engine.issue_session_pass("client1@test.com", 2, "k1")
    
    b1 = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Bob", "client1@test.com")
    bid1 = b1["booking_id"]
    
    engine.cancel_booking(bid1, "client1@test.com")
    
    recon = engine.get_system_reconciliation()
    assert recon["is_balanced"] is True
    
    logs = engine.get_booking_audit_log(bid1)
    assert len(logs) >= 2
    assert logs[0]["event_type"] == "BOOKING_CREATED"
    assert logs[-1]["event_type"] == "BOOKING_CANCELLED"
