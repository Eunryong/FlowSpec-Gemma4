import pytest
import os
from counseling_service import CounselingService

@pytest.fixture
def service():
    # Use an in-memory database for tests
    return CounselingService(db_path=":memory:")

def test_add_and_query_slots(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    
    service.add_available_slot(counselor_id, start_time)
    
    slots = service.query_available_slots()
    assert len(slots) == 1
    assert slots[0]['counselor_id'] == counselor_id
    assert slots[0]['start_time'] == start_time

def test_query_slots_filters(service):
    service.add_available_slot("c1", "2026-10-20T10:00:00+09:00")
    service.add_available_slot("c1", "2026-10-20T11:00:00+09:00")
    service.add_available_slot("c2", "2026-10-20T10:00:00+09:00")
    service.add_available_slot("c2", "2026-10-21T10:00:00+09:00")
    
    # Filter by counselor
    c1_slots = service.query_available_slots(counselor_id="c1")
    assert len(c1_slots) == 2
    
    # Filter by date
    date_slots = service.query_available_slots(date="2026-10-20")
    assert len(date_slots) == 3
    
    # Filter by both
    both_slots = service.query_available_slots(counselor_id="c1", date="2026-10-20")
    assert len(both_slots) == 2

def test_create_booking_success(service):
    counselor_id = "c1"
    start_time = "2026-10-20T10:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    booking_id = service.create_booking(counselor_id, start_time, "John Doe", "john@example.com")
    
    assert booking_id is not None
    assert len(booking_id) > 0
    
    # Verify slot is no longer available
    slots = service.query_available_slots()
    assert len(slots) == 0

def test_create_booking_duplicate_rejection(service):
    counselor_id = "c1"
    start_time = "2026-10-20T10:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    service.create_booking(counselor_id, start_time, "John Doe", "john@example.com")
    
    with pytest.raises(ValueError, match="Slot is not available or does not exist."):
        service.create_booking(counselor_id, start_time, "Jane Doe", "jane@example.com")

def test_lookup_booking(service):
    counselor_id = "c1"
    start_time = "2026-10-20T10:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    booking_id = service.create_booking(counselor_id, start_time, "John Doe", "john@example.com")
    
    # Successful lookup
    booking = service.lookup_booking(booking_id, "john@example.com")
    assert booking['booking_id'] == booking_id
    assert booking['client_name'] == "John Doe"
    
    # Email mismatch
    with pytest.raises(ValueError, match="Email mismatch"):
        service.lookup_booking(booking_id, "wrong@example.com")
    
    # Non-existent booking
    with pytest.raises(ValueError, match="Booking not found"):
        service.lookup_booking("non-existent-id", "john@example.com")

def test_cancel_booking_flow(service):
    counselor_id = "c1"
    start_time = "2026-10-20T10:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    booking_id = service.create_booking(counselor_id, start_time, "John Doe", "john@example.com")
    
    # Verify it's booked
    assert len(service.query_available_slots()) == 0
    
    # Cancel booking
    service.cancel_booking(booking_id, "john@example.com")
    
    # Verify slot is reopened
    slots = service.query_available_slots()
    assert len(slots) == 1
    assert slots[0]['start_time'] == start_time
    
    # Verify booking status is CANCELLED
    # We need to check the DB or use lookup if lookup allows cancelled bookings
    # The current lookup_booking implementation doesn't filter by status, so it should work.
    booking = service.lookup_booking(booking_id, "john@example.com")
    assert booking['status'] == "CANCELLED"

def test_cancel_booking_unauthorized(service):
    counselor_id = "c1"
    start_time = "2026-10-20T10:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    booking_id = service.create_booking(counselor_id, start_time, "John Doe", "john@example.com")
    
    with pytest.raises(ValueError, match="Email mismatch"):
        service.cancel_booking(booking_id, "wrong@example.com")
    
    # Verify slot is still booked
    assert len(service.query_available_slots()) == 0

def test_invalid_time_format(service):
    with pytest.raises(ValueError, match="Invalid start_time format"):
        service.add_available_slot("c1", "invalid-date")
