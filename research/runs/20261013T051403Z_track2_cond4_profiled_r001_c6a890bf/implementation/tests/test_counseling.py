from counseling.service import CounselingService
from counseling.exceptions import SlotUnavailableError, BookingNotFoundError, UnauthorizedBookingError
import pytest
import os

@pytest.fixture
def service():
    # Use an in-memory database for each test to ensure isolation
    return CounselingService(db_path=":memory:")

def test_add_and_query_slots(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    
    service.add_available_slot(counselor_id, start_time)
    
    slots = service.query_available_slots(counselor_id=counselor_id)
    assert len(slots) == 1
    assert slots[0]['counselor_id'] == counselor_id
    assert slots[0]['start_time'] == start_time

def test_query_slots_filter_date(service):
    counselor_id = "counselor-1"
    service.add_available_slot(counselor_id, "2026-10-20T14:00:00+09:00")
    service.add_available_slot(counselor_id, "2026-10-21T14:00:00+09:00")
    
    slots_20 = service.query_available_slots(date="2026-10-20")
    assert len(slots_20) == 1
    assert slots_20[0]['start_time'].startswith("2026-10-20")

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
    slots = service.query_available_slots(counselor_id=counselor_id)
    assert len(slots) == 0

def test_create_booking_duplicate_rejection(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    # First booking
    service.create_booking(
        counselor_id=counselor_id,
        start_time=start_time,
        client_name="John Doe",
        client_email="john@example.com"
    )
    
    # Second booking attempt for same slot
    with pytest.raises(SlotUnavailableError):
        service.create_booking(
            counselor_id=counselor_id,
            start_time=start_time,
            client_name="Jane Doe",
            client_email="jane@example.com"
        )

def test_lookup_booking_success(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    booking_id = service.create_booking(
        counselor_id=counselor_id,
        start_time=start_time,
        client_name="John Doe",
        client_email="john@example.com"
    )
    
    booking = service.lookup_booking(booking_id, "john@example.com")
    assert booking['booking_id'] == booking_id
    assert booking['client_name'] == "John Doe"

def test_lookup_booking_unauthorized(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    booking_id = service.create_booking(
        counselor_id=counselor_id,
        start_time=start_time,
        client_name="John Doe",
        client_email="john@example.com"
    )
    
    with pytest.raises(UnauthorizedBookingError):
        service.lookup_booking(booking_id, "wrong@example.com")

def test_lookup_booking_not_found(service):
    with pytest.raises(BookingNotFoundError):
        service.lookup_booking("non-existent-id", "any@example.com")

def test_cancel_booking_success(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    booking_id = service.create_booking(
        counselor_id=counselor_id,
        start_time=start_time,
        client_name="John Doe",
        client_email="john@example.com"
    )
    
    service.cancel_booking(booking_id, "john@example.com")
    
    # Verify slot is available again
    slots = service.query_available_slots(counselor_id=counselor_id)
    assert len(slots) == 1
    assert slots[0]['start_time'] == start_time

def test_cancel_booking_unauthorized(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    booking_id = service.create_booking(
        counselor_id=counselor_id,
        start_time=start_time,
        client_name="John Doe",
        client_email="john@example.com"
    )
    
    with pytest.raises(UnauthorizedBookingError):
        service.cancel_booking(booking_id, "wrong@example.com")

def test_invalid_iso_format(service):
    with pytest.raises(ValueError, match="Invalid ISO 8601 format"):
        service.add_available_slot("counselor-1", "2026-10-20 14:00")

def test_duplicate_slot_creation(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    with pytest.raises(ValueError, match="Slot already exists"):
        service.add_available_slot(counselor_id, start_time)
