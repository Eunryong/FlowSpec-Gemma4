import pytest
from counseling_engine import CounselingBookingEngine

def test_counselor_slot_lifecycle():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "General")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    
    # Block slot
    engine.block_slot("c1", "2026-10-20T14:00:00+09:00")
    assert len(engine.query_available_slots("c1")) == 0
    
    # Try to block already blocked
    with pytest.raises(ValueError):
        engine.block_slot("c1", "2026-10-20T14:00:00+09:00")

def test_session_pass_idempotency():
    engine = CounselingBookingEngine()
    engine.issue_session_pass("client@test.com", 5, "key1")
    pass1 = engine.get_session_pass("client@test.com")
    assert pass1['remaining_sessions'] == 5
    
    # Duplicate key
    engine.issue_session_pass("client@test.com", 5, "key1")
    pass2 = engine.get_session_pass("client@test.com")
    assert pass2['remaining_sessions'] == 5

def test_booking_creation_and_double_booking():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "General")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client", "client@test.com")
    assert booking['status'] == "CONFIRMED"
    assert engine.get_session_pass("client@test.com")['remaining_sessions'] == 0
    
    # Double booking
    with pytest.raises(ValueError):
        engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Other", "other@test.com")

def test_booking_failure_insufficient_pass():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "General")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    
    with pytest.raises(ValueError):
        engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client", "client@test.com")
    
    assert len(engine.query_available_slots("c1")) == 1

def test_atomic_rescheduling():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "General")
    engine.register_counselor("c2", "Bob", "General")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("c2", "2026-10-20T15:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client", "client@test.com")
    b_id = booking['booking_id']
    
    engine.reschedule_booking(b_id, "client@test.com", "c2", "2026-10-20T15:00:00+09:00")
    
    # Check old slot is available, new slot is booked
    assert len(engine.query_available_slots("c1")) == 1
    assert len(engine.query_available_slots("c2")) == 0
    assert engine.get_session_pass("client@test.com")['remaining_sessions'] == 0

def test_cancellation_and_restoration():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "General")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Client", "client@test.com")
    engine.cancel_booking(booking['booking_id'], "client@test.com")
    
    assert engine.get_session_pass("client@test.com")['remaining_sessions'] == 1
    assert len(engine.query_available_slots("c1")) == 1

def test_waitlist_auto_promotion():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "General")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    
    engine.issue_session_pass("c1_client@test.com", 1, "k1")
    engine.issue_session_pass("c2_client@test.com", 1, "k2")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "C1", "c1_client@test.com")
    engine.join_waitlist("c1", "2026-10-20T14:00:00+09:00", "C2", "c2_client@test.com")
    
    engine.cancel_booking(booking['booking_id'], "c1_client@test.com")
    
    # C2 should be promoted
    assert engine.get_session_pass("c2_client@test.com")['remaining_sessions'] == 0
    assert len(engine.query_available_slots("c1")) == 0
    
    # Check if a new booking exists for C2
    bookings = engine.conn.execute("SELECT * FROM bookings WHERE client_email='c2_client@test.com'").fetchall()
    assert len(bookings) == 1
    assert bookings[0]['status'] == "CONFIRMED"

def test_global_reconciliation():
    engine = CounselingBookingEngine()
    engine.register_counselor("c1", "Alice", "General")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("c1", "2026-10-20T15:00:00+09:00")
    
    engine.issue_session_pass("client@test.com", 2, "k1")
    
    b1 = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "C", "client@test.com")
    engine.cancel_booking(b1['booking_id'], "client@test.com")
    
    b2 = engine.create_booking("c1", "2026-10-20T15:00:00+09:00", "C", "client@test.com")
    
    recon = engine.get_system_reconciliation()
    assert recon['is_balanced'] is True
    assert recon['active_confirmed_bookings'] == 1
    assert recon['booked_slots_count'] == 1
