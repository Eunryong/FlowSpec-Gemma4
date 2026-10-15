import pytest
import os
from counseling_service import (
    CounselingService, 
    SlotNotFoundError, 
    SlotAlreadyBookedError, 
    BookingNotFoundError, 
    AuthenticationError,
    Slot,
    Booking
)

@pytest.fixture
def service():
    # Use an in-memory database for tests to ensure isolation
    return CounselingService(db_path=":memory:")

def test_add_and_query_slots(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    
    service.add_available_slot(counselor_id, start_time)
    
    # Query all
    slots = service.query_available_slots()
    assert len(slots) == 1
    assert slots[0].counselor_id == counselor_id
    assert slots[0].start_time == start_time
    
    # Query by counselor
    slots_c = service.query_available_slots(counselor_id=counselor_id)
    assert len(slots_c) == 1
    
    # Query by date
    slots_d = service.query_available_slots(date="2026-10-20")
    assert len(slots_d) == 1
    
    # Query by counselor and date
    slots_cd = service.query_available_slots(counselor_id=counselor_id, date="2026-10-20")
    assert len(slots_cd) == 1

def test_add_duplicate_slot(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    
    service.add_available_slot(counselor_id, start_time)
    with pytest.raises(ValueError, match="Slot already exists"):
        service.add_available_slot(counselor_id, start_time)

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
    # Slot should no longer be available
    slots = service.query_available_slots()
    assert len(slots) == 0

def test_create_booking_not_found(service):
    with pytest.raises(SlotNotFoundError):
        service.create_booking(
            counselor_id="none",
            start_time="2026-10-20T14:00:00+09:00",
            client_name="John Doe",
            client_email="john@example.com"
        )

def test_create_booking_already_booked(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    # First booking
    service.create_booking(counselor_id, start_time, "Client 1", "c1@example.com")
    
    # Second booking attempt
    with pytest.raises(SlotAlreadyBookedError):
        service.create_booking(counselor_id, start_time, "Client 2", "c2@example.com")

def test_lookup_booking_success(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    booking_id = service.create_booking(counselor_id, start_time, "John Doe", "john@example.com")
    
    booking = service.lookup_booking(booking_id, "john@example.com")
    assert booking.booking_id == booking_id
    assert booking.client_name == "John Doe"
    assert booking.status == "CONFIRMED"

def test_lookup_booking_not_found(service):
    with pytest.raises(BookingNotFoundError):
        service.lookup_booking("non-existent-id", "any@example.com")

def test_lookup_booking_auth_error(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    booking_id = service.create_booking(counselor_id, start_time, "John Doe", "john@example.com")
    
    with pytest.raises(AuthenticationError):
        service.lookup_booking(booking_id, "wrong@example.com")

def test_cancel_booking_success(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    booking_id = service.create_booking(counselor_id, start_time, "John Doe", "john@example.com")
    
    service.cancel_booking(booking_id, "john@example.com")
    
    # Verify booking status
    # Since lookup_booking checks email, we can use it to verify status if we have the email
    # But wait, lookup_booking returns the booking. Let's check if it's still there but CANCELLED.
    # Actually, the design says lookup_booking returns the booking.
    booking = service.lookup_booking(booking_id, "john@example.com")
    assert booking.status == "CANCELLED"
    
    # Verify slot is available again
    slots = service.query_available_slots()
    assert len(slots) == 1
    assert slots[0].start_time == start_time

def test_cancel_booking_auth_error(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    booking_id = service.create_booking(counselor_id, start_time, "John Doe", "john@example.com")
    
    with pytest.raises(AuthenticationError):
        service.cancel_booking(booking_id, "wrong@example.com")

def test_cancel_booking_not_found(service):
    with pytest.raises(BookingNotFoundError):
        service.cancel_booking("non-existent-id", "any@example.com")
