import pytest
from counseling_engine import CounselingBookingEngine

def test_counselor_and_slot_lifecycle():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    
    slots = engine.query_available_slots("C1")
    assert len(slots) == 1
    
    engine.block_slot("C1", "2026-10-20T14:00:00+09:00")
    assert len(engine.query_available_slots("C1")) == 0
    
    with pytest.raises(ValueError):
        engine.block_slot("C1", "2026-10-20T14:00:00+09:00")

def test_session_pass_and_idempotency():
    engine = CounselingBookingEngine()
    engine.issue_session_pass("client@test.com", 5, "key1")
    pass_info = engine.get_session_pass("client@test.com")
    assert pass_info['remaining_sessions'] == 5
    
    engine.issue_session_pass("client@test.com", 5, "key1")
    pass_info = engine.get_session_pass("client@test.com")
    assert pass_info['remaining_sessions'] == 5

def test_booking_creation_and_double_booking():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client A", "client@test.com")
    assert booking['status'] == 'CONFIRMED'
    assert engine.get_session_pass("client@test.com")['remaining_sessions'] == 0
    
    with pytest.raises(ValueError):
        engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client B", "client2@test.com")

def test_booking_failure_rollback():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    
    with pytest.raises(ValueError):
        engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client A", "client@test.com")
    
    assert len(engine.query_available_slots("C1")) == 1

def test_atomic_rescheduling_saga():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("C1", "2026-10-20T15:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client A", "client@test.com")
    booking_id = booking['booking_id']
    
    engine.reschedule_booking(booking_id, "client@test.com", "C1", "2026-10-20T15:00:00+09:00")
    
    assert len(engine.query_available_slots("C1")) == 1 # 14:00 should be available
    assert engine.get_session_pass("client@test.com")['remaining_sessions'] == 0

def test_cancellation_and_session_restoration():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client A", "client@test.com")
    engine.cancel_booking(booking['booking_id'], "client@test.com")
    
    assert engine.get_session_pass("client@test.com")['remaining_sessions'] == 1
    assert len(engine.query_available_slots("C1")) == 1

def test_waitlist_auto_promotion():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client1@test.com", 1, "key1")
    engine.issue_session_pass("client2@test.com", 1, "key2")
    
    booking1 = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client 1", "client1@test.com")
    engine.join_waitlist("C1", "2026-10-20T14:00:00+09:00", "Client 2", "client2@test.com")
    
    engine.cancel_booking(booking1['booking_id'], "client1@test.com")
    
    # Client 2 should be promoted
    assert engine.get_session_pass("client2@test.com")['remaining_sessions'] == 0
    assert len(engine.query_available_slots("C1")) == 0
    
    # Verify booking exists for client 2
    bookings = engine.conn.execute("SELECT * FROM bookings WHERE client_email='client2@test.com' AND status='CONFIRMED'").fetchone()
    assert bookings is not None

def test_global_reconciliation_and_audit_log():
    engine = CounselingBookingEngine()
    engine.register_counselor("C1", "Alice", "Psychology")
    engine.add_slot("C1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("C1", "2026-10-20T15:00:00+09:00")
    engine.issue_session_pass("client1@test.com", 2, "key1")
    
    booking1 = engine.create_booking("C1", "2026-10-20T14:00:00+09:00", "Client 1", "client1@test.com")
    engine.reschedule_booking(booking1['booking_id'], "client1@test.com", "C1", "2026-10-20T15:00:00+09:00")
    
    recon = engine.get_system_reconciliation()
    assert recon['is_balanced'] == True
    assert recon['active_confirmed_bookings'] == 1
    assert recon['booked_slots_count'] == 1
    
    logs = engine.get_booking_audit_log(booking1['booking_id'])
    assert len(logs) >= 2 # Created and Rescheduled
