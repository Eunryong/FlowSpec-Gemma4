import pytest
from counseling_engine import CounselingBookingEngine

def test_counselor_and_slot_lifecycle():
    engine = CounselingBookingEngine(":memory:")
    engine.register_counselor("c1", "Alice", "Psychology")
    
    # Add slot
    slot = engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    assert slot["status"] == "AVAILABLE"
    
    # Duplicate slot
    with pytest.raises(ValueError):
        engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    
    # Block slot
    engine.block_slot("c1", "2026-10-20T14:00:00+09:00")
    available = engine.query_available_slots("c1")
    assert len(available) == 0
    
    # Block already blocked
    with pytest.raises(ValueError):
        engine.block_slot("c1", "2026-10-20T14:00:00+09:00")

def test_session_pass_and_idempotency():
    engine = CounselingBookingEngine(":memory:")
    # Issue pass
    pass_info = engine.issue_session_pass("client@test.com", 5, "key1")
    assert pass_info["remaining_sessions"] == 5
    
    # Idempotent call
    pass_info_2 = engine.issue_session_pass("client@test.com", 5, "key1")
    assert pass_info_2["remaining_sessions"] == 5
    
    # New issue
    pass_info_3 = engine.issue_session_pass("client@test.com", 2, "key2")
    assert pass_info_3["remaining_sessions"] == 7

def test_booking_creation_and_double_booking():
    engine = CounselingBookingEngine(":memory:")
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Bob", "client@test.com", "book1")
    assert booking["status"] == "CONFIRMED"
    
    # Check session deducted
    pass_info = engine.get_session_pass("client@test.com")
    assert pass_info["remaining_sessions"] == 0
    
    # Double booking
    with pytest.raises(ValueError):
        engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Charlie", "other@test.com")
    
    # Idempotency
    booking_2 = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Bob", "client@test.com", "book1")
    assert booking_2["booking_id"] == booking["booking_id"]

def test_booking_failure_rollback():
    engine = CounselingBookingEngine(":memory:")
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    
    # No pass issued
    with pytest.raises(ValueError):
        engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Bob", "client@test.com")
    
    # Slot should still be available
    available = engine.query_available_slots("c1")
    assert len(available) == 1

def test_atomic_rescheduling_saga():
    engine = CounselingBookingEngine(":memory:")
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.register_counselor("c2", "Dave", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("c2", "2026-10-20T15:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Bob", "client@test.com")
    
    # Reschedule
    updated = engine.reschedule_booking(booking["booking_id"], "client@test.com", "c2", "2026-10-20T15:00:00+09:00")
    assert updated["counselor_id"] == "c2"
    assert updated["start_time"] == "2026-10-20T15:00:00+09:00"
    
    # Old slot should be available
    available = engine.query_available_slots("c1")
    assert len(available) == 1
    
    # New slot should be booked
    available_c2 = engine.query_available_slots("c2")
    assert len(available_c2) == 0

def test_cancellation_and_session_restoration():
    engine = CounselingBookingEngine(":memory:")
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.issue_session_pass("client@test.com", 1, "key1")
    
    booking = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Bob", "client@test.com")
    engine.cancel_booking(booking["booking_id"], "client@test.com")
    
    pass_info = engine.get_session_pass("client@test.com")
    assert pass_info["remaining_sessions"] == 1
    
    available = engine.query_available_slots("c1")
    assert len(available) == 1

def test_waitlist_auto_promotion():
    engine = CounselingBookingEngine(":memory:")
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    
    engine.issue_session_pass("client1@test.com", 1, "k1")
    engine.issue_session_pass("client2@test.com", 1, "k2")
    
    booking1 = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Bob", "client1@test.com")
    
    # Join waitlist
    engine.join_waitlist("c1", "2026-10-20T14:00:00+09:00", "Charlie", "client2@test.com")
    
    # Cancel first booking
    engine.cancel_booking(booking1["booking_id"], "client1@test.com")
    
    # Check if client2 is promoted
    pass_info2 = engine.get_session_pass("client2@test.com")
    assert pass_info2["remaining_sessions"] == 0
    
    # Slot should still be booked
    available = engine.query_available_slots("c1")
    assert len(available) == 0
    
    # Verify booking exists for client2
    bookings = engine.conn.execute("SELECT * FROM bookings WHERE client_email = 'client2@test.com' AND status = 'CONFIRMED'").fetchall()
    assert len(bookings) == 1

def test_global_reconciliation_and_audit_log():
    engine = CounselingBookingEngine(":memory:")
    engine.register_counselor("c1", "Alice", "Psychology")
    engine.add_slot("c1", "2026-10-20T14:00:00+09:00")
    engine.add_slot("c1", "2026-10-20T15:00:00+09:00")
    
    engine.issue_session_pass("c1@test.com", 2, "k1")
    
    b1 = engine.create_booking("c1", "2026-10-20T14:00:00+09:00", "Bob", "c1@test.com")
    b2 = engine.create_booking("c1", "2026-10-20T15:00:00+09:00", "Bob", "c1@test.com")
    
    engine.cancel_booking(b1["booking_id"], "c1@test.com")
    
    recon = engine.get_system_reconciliation()
    assert recon["is_balanced"] is True
    
    logs = engine.get_booking_audit_log(b1["booking_id"])
    assert len(logs) >= 2 # Created and Cancelled
