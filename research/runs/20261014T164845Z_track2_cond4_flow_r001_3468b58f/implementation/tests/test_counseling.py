import pytest
import os
from counseling import CounselingService

@pytest.fixture
def service():
    # Use an in-memory database for tests
    return CounselingService(db_path=":memory:")

def test_add_and_query_slots(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    
    service.add_available_slot(counselor_id, start_time)
    
    # Query all available
    slots = service.query_available_slots()
    assert len(slots) == 1
    assert slots[0]['counselor_id'] == counselor_id
    assert slots[0]['start_time'] == start_time
    
    # Query by counselor
    slots_c = service.query_available_slots(counselor_id=counselor_id)
    assert len(slots_c) == 1
    
    # Query by date
    slots_d = service.query_available_slots(date="2026-10-20")
    assert len(slots_d) == 1
    
    # Query by wrong date
    slots_wrong_d = service.query_available_slots(date="2026-10-21")
    assert len(slots_wrong_d) == 0

def test_create_booking_success(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    booking_id = service.create_booking(
        counselor_id=counselor_id,
        start_time=start_time,
        client_name="John Doe",
        client_email="john@example.com"
    )
    
    assert booking_id is not None
    assert len(booking_id) > 0
    
    # Verify slot is no longer available
    slots = service.query_available_slots()
    assert len(slots) == 0

def test_create_booking_duplicate_rejection(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    service.create_booking(counselor_id, start_time, "Client 1", "client1@example.com")
    
    with pytest.raises(ValueError, match="Slot unavailable"):
        service.create_booking(counselor_id, start_time, "Client 2", "client2@example.com")

def test_lookup_booking(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    email = "john@example.com"
    booking_id = service.create_booking(counselor_id, start_time, "John Doe", email)
    
    # Successful lookup
    booking = service.lookup_booking(booking_id, email)
    assert booking['client_name'] == "John Doe"
    assert booking['client_email'] == email
    
    # Unauthorized lookup (wrong email)
    with pytest.raises(ValueError, match="Unauthorized"):
        service.lookup_booking(booking_id, "wrong@example.com")
        
    # Non-existent booking
    with pytest.raises(ValueError, match="Booking not found"):
        service.lookup_booking("non-existent-id", email)

def test_cancel_booking_flow(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    email = "john@example.com"
    booking_id = service.create_booking(counselor_id, start_time, "John Doe", email)
    
    # Verify it's booked
    assert len(service.query_available_slots()) == 0
    
    # Cancel booking
    service.cancel_booking(booking_id, email)
    
    # Verify slot is available again
    slots = service.query_available_slots()
    assert len(slots) == 1
    assert slots[0]['counselor_id'] == counselor_id
    
    # Verify booking status is CANCELLED
    # We can't use lookup_booking because it might only return CONFIRMED? 
    # Actually, the design says lookup_booking returns booking details.
    # Let's check if lookup_booking still works for cancelled bookings.
    booking = service.lookup_booking(booking_id, email)
    assert booking['status'] == 'CANCELLED'

def test_cancel_booking_unauthorized(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    email = "john@example.com"
    booking_id = service.create_booking(counselor_id, start_time, "John Doe", email)
    
    with pytest.raises(ValueError, match="Unauthorized"):
        service.cancel_booking(booking_id, "wrong@example.com")

def test_cancel_non_existent_booking(service):
    with pytest.raises(ValueError, match="Booking not found"):
        service.cancel_booking("non-existent-id", "any@example.com")

def test_invalid_iso_format(service):
    with pytest.raises(ValueError, match="Invalid ISO 8601 format"):
        service.add_available_slot("c1", "not-a-date")
