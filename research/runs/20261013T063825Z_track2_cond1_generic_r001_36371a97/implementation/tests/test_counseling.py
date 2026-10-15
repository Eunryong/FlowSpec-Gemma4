from counseling.service import CounselingService
from counseling.exceptions import (
    SlotNotFoundError,
    SlotAlreadyBookedError,
    BookingNotFoundError,
    AuthenticationError,
    InvalidTimeFormatError
)
import pytest
import os

@pytest.fixture
def service():
    # Use in-memory database for tests
    return CounselingService(db_path=":memory:")

def test_add_and_query_slots(service):
    service.add_available_slot("counselor-1", "2026-10-20T14:00:00+09:00")
    service.add_available_slot("counselor-1", "2026-10-20T14:30:00+09:00")
    service.add_available_slot("counselor-2", "2026-10-21T10:00:00+09:00")

    # Query all
    all_slots = service.query_available_slots()
    assert len(all_slots) == 3

    # Query by counselor
    c1_slots = service.query_available_slots(counselor_id="counselor-1")
    assert len(c1_slots) == 2
    assert all(s['counselor_id'] == "counselor-1" for s in c1_slots)

    # Query by date
    date_slots = service.query_available_slots(date="2026-10-20")
    assert len(date_slots) == 2
    assert all("2026-10-20" in s['start_time'] for s in date_slots)

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
    # Verify slot is no longer available
    available_slots = service.query_available_slots(counselor_id=counselor_id)
    assert len(available_slots) == 0

def test_duplicate_booking_rejection(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    service.create_booking(
        counselor_id=counselor_id,
        start_time=start_time,
        client_name="John Doe",
        client_email="john@example.com"
    )
    
    with pytest.raises(SlotAlreadyBookedError):
        service.create_booking(
            counselor_id=counselor_id,
            start_time=start_time,
            client_name="Jane Doe",
            client_email="jane@example.com"
        )

def test_booking_lookup_and_auth(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    booking_id = service.create_booking(
        counselor_id=counselor_id,
        start_time=start_time,
        client_name="John Doe",
        client_email="john@example.com"
    )
    
    # Successful lookup
    booking = service.lookup_booking(booking_id, "john@example.com")
    assert booking['booking_id'] == booking_id
    assert booking['client_name'] == "John Doe"
    
    # Failed lookup (wrong email)
    with pytest.raises(AuthenticationError):
        service.lookup_booking(booking_id, "wrong@example.com")
    
    # Failed lookup (non-existent ID)
    with pytest.raises(BookingNotFoundError):
        service.lookup_booking("non-existent-id", "john@example.com")

def test_cancel_booking_flow(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    booking_id = service.create_booking(
        counselor_id=counselor_id,
        start_time=start_time,
        client_name="John Doe",
        client_email="john@example.com"
    )
    
    # Cancel booking
    service.cancel_booking(booking_id, "john@example.com")
    
    # Verify slot is available again
    available_slots = service.query_available_slots(counselor_id=counselor_id)
    assert len(available_slots) == 1
    assert available_slots[0]['start_time'] == start_time
    
    # Verify booking status is CANCELLED
    # We can't use lookup_booking because it doesn't filter by status, 
    # but we can check if it's still retrievable (it is, but status should be CANCELLED)
    booking = service.lookup_booking(booking_id, "john@example.com")
    assert booking['status'] == "CANCELLED"

def test_cancel_booking_auth_failure(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    booking_id = service.create_booking(
        counselor_id=counselor_id,
        start_time=start_time,
        client_name="John Doe",
        client_email="john@example.com"
    )
    
    with pytest.raises(AuthenticationError):
        service.cancel_booking(booking_id, "wrong@example.com")

def test_invalid_time_format(service):
    with pytest.raises(InvalidTimeFormatError):
        service.add_available_slot("counselor-1", "2026-10-20 14:00") # Not ISO 8601

def test_booking_non_existent_slot(service):
    with pytest.raises(SlotNotFoundError):
        service.create_booking("counselor-1", "2026-10-20T14:00:00+09:00", "John", "john@example.com")
