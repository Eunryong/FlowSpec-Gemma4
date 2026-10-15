import pytest
from counseling_service import (
    CounselingService, 
    SlotUnavailableError, 
    BookingNotFoundError, 
    BookingVerificationError, 
    CounselingError
)

@pytest.fixture
def service():
    # Use in-memory database for tests
    return CounselingService(":memory:")

def test_add_and_query_slots(service):
    service.add_available_slot("counselor-1", "2026-10-20T14:00:00+09:00")
    service.add_available_slot("counselor-1", "2026-10-20T14:30:00+09:00")
    service.add_available_slot("counselor-2", "2026-10-20T15:00:00+09:00")
    
    # Query all
    slots = service.query_available_slots()
    assert len(slots) == 3
    
    # Query by counselor
    slots_c1 = service.query_available_slots(counselor_id="counselor-1")
    assert len(slots_c1) == 2
    
    # Query by date
    slots_date = service.query_available_slots(date="2026-10-20")
    assert len(slots_date) == 3
    
    # Query by date and counselor
    slots_both = service.query_available_slots(counselor_id="counselor-2", date="2026-10-20")
    assert len(slots_both) == 1

def test_duplicate_slot_rejection(service):
    service.add_available_slot("counselor-1", "2026-10-20T14:00:00+09:00")
    with pytest.raises(CounselingError, match="already exists"):
        service.add_available_slot("counselor-1", "2026-10-20T14:00:00+09:00")

def test_booking_creation_success(service):
    c_id = "counselor-1"
    s_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(c_id, s_time)
    
    booking_id = service.create_booking(c_id, s_time, "Alice", "alice@example.com")
    assert booking_id is not None
    assert len(booking_id) > 0
    
    # Slot should no longer be available
    slots = service.query_available_slots(counselor_id=c_id)
    assert len(slots) == 0

def test_double_booking_rejection(service):
    c_id = "counselor-1"
    s_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(c_id, s_time)
    
    service.create_booking(c_id, s_time, "Alice", "alice@example.com")
    
    with pytest.raises(SlotUnavailableError):
        service.create_booking(c_id, s_time, "Bob", "bob@example.com")

def test_booking_nonexistent_slot(service):
    with pytest.raises(SlotUnavailableError):
        service.create_booking("none", "2026-10-20T14:00:00+09:00", "Alice", "alice@example.com")

def test_lookup_booking_success(service):
    c_id = "counselor-1"
    s_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(c_id, s_time)
    booking_id = service.create_booking(c_id, s_time, "Alice", "alice@example.com")
    
    details = service.lookup_booking(booking_id, "alice@example.com")
    assert details['booking_id'] == booking_id
    assert details['client_name'] == "Alice"
    assert details['status'] == "CONFIRMED"
    assert details['counselor_id'] == c_id
    assert details['start_time'] == s_time

def test_lookup_booking_email_mismatch(service):
    c_id = "counselor-1"
    s_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(c_id, s_time)
    booking_id = service.create_booking(c_id, s_time, "Alice", "alice@example.com")
    
    with pytest.raises(BookingVerificationError):
        service.lookup_booking(booking_id, "wrong@example.com")

def test_lookup_booking_not_found(service):
    with pytest.raises(BookingNotFoundError):
        service.lookup_booking("non-existent-id", "any@example.com")

def test_cancel_booking_success(service):
    c_id = "counselor-1"
    s_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(c_id, s_time)
    booking_id = service.create_booking(c_id, s_time, "Alice", "alice@example.com")
    
    service.cancel_booking(booking_id, "alice@example.com")
    
    # Verify status is CANCELLED
    details = service.lookup_booking(booking_id, "alice@example.com")
    assert details['status'] == "CANCELLED"
    
    # Verify slot is available again
    slots = service.query_available_slots(counselor_id=c_id)
    assert len(slots) == 1
    assert slots[0]['start_time'] == s_time

def test_cancel_booking_email_mismatch(service):
    c_id = "counselor-1"
    s_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(c_id, s_time)
    booking_id = service.create_booking(c_id, s_time, "Alice", "alice@example.com")
    
    with pytest.raises(BookingVerificationError):
        service.cancel_booking(booking_id, "wrong@example.com")
    
    # Slot should still be booked
    slots = service.query_available_slots(counselor_id=c_id)
    assert len(slots) == 0

def test_cancel_booking_idempotency(service):
    c_id = "counselor-1"
    s_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(c_id, s_time)
    booking_id = service.create_booking(c_id, s_time, "Alice", "alice@example.com")
    
    service.cancel_booking(booking_id, "alice@example.com")
    # Second cancellation should not raise error or double-open slot
    service.cancel_booking(booking_id, "alice@example.com")
    
    slots = service.query_available_slots(counselor_id=c_id)
    assert len(slots) == 1
