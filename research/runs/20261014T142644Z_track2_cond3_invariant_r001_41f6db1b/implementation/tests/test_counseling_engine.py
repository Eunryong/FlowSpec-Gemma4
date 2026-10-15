import pytest
from counseling_engine import CounselingBookingEngine

def test_counselor_and_slot_lifecycle():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Dr. Smith", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    
    slots = engine.query_available_slots("C1")
    assert len(slots) == 1
    assert slots[0]['status'] == "AVAILABLE"
    
    engine.block_slot("C1", "2026-10-20T14:00:00+09:00")
    assert len(engine.query_available_slots("C1")) == 0
    
    with pytest.raises(ValueError):
        engine.block_slot("C1", "2026-10-20T14:00:00+09:00")

def test_session_pass_idempotency():
    engine = CounselingBookingEngine()
    engine.issue_session_pass("client@test.com", 5, "key1")
    pass_info = engine.get_session_pass("client@test.com")
    assert pass_info['remaining_sessions'] == 5
    
    engine.issue_session_pass("client@test.com", 5, "key1")
    pass_info = engine.get_session_pass("client@test.com")
    assert pass_info['remaining_sessions'] == 5

def test_booking_creation_and_double_booking():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Dr. Smith", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client1@test.com", 1, "key1")
    
    booking = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client 1", "client1@test.com", "bkey1")
    assert booking['status'] == "CONFIRMED"
    
    pass_info = engine.get_session_pass("client1@test.com")
    assert pass_info['remaining_sessions'] == 0
    
    with pytest.raises(ValueError):
        engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client 2", "client2@test.com")

def test_booking_failure_insufficient_pass():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Dr. Smith", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    
    with pytest.raises(ValueError):
        engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client 1", "client1@test.com")
    
    slots = engine.query_available_slots("C1")
    assert len(slots) == 1

def test_atomic_rescheduling():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Dr. Smith", "Psychology")
    engine.register_counselor("C2", "Dr. Jones", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("C2", "2026-10-21T14:00:00+09:00")
    engine.issue_session_pass("client1@test.com", 1, "key1")
    
    booking = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client 1", "client1@test.com")
    bid = booking['booking_id']
    
    updated = engine.reschedule_booking(bid, "client1@test.com", "C2", "2026-10-21T14:00:00+09:00")
    assert updated['counselor_id'] == "C2"
    assert updated['start_time'] == "2026-10-21T14:00:00+09:00"
    
    assert len(engine.query_available_slots("C1")) == 1
    assert len(engine.query_available_slots("C2")) == 0

def test_cancellation_and_restoration():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Dr. Smith", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client1@test.com", 1, "key1")
    
    booking = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client 1", "client1@test.com")
    engine.cancel_booking(booking['booking_id'], "client1@test.com")
    
    pass_info = engine.get_session_pass("client1@test.com")
    assert pass_info['remaining_sessions'] == 1
    assert len(engine.query_available_slots("C1")) == 1

def test_waitlist_auto_promotion():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Dr. Smith", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client1@test.com", 1, "k1")
    engine.issue_session_pass("client2@test.com", 1, "k2")
    
    b1 = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client 1", "client1@test.com")
    engine.join_waitlist("C1", "2026-10-20T14:00:00+09:00", "Client 2", "client2@test.com")
    
    engine.cancel_booking(b1['booking_id'], "client1@test.com")
    
    pass_info2 = engine.get_session_pass("client2@test.com")
    assert pass_info2['remaining_sessions'] == 0
    
    slots = engine.query_available_slots("C1")
    assert len(slots) == 0

def test_global_reconciliation():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Dr. Smith", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("C1", "2026-10-21T14:00:00+09:00")
    engine.issue_session_pass("client1@test.com", 2, "k1")
    
    b1 = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client 1", "client1@test.com")
    engine.cancel_booking(b1['booking_id'], "client1@test.com")
    
    recon = engine.get_system_reconciliation()
    assert recon['is_balanced'] is True
