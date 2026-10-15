import pytest
from counseling_service.service import CounselingService
from counseling_service.exceptions import (
    SlotNotFoundError,
    SlotAlreadyBookedError,
    BookingNotFoundError,
    UnauthorizedBookingError,
    InvalidTimeFormatError
)

@pytest.fixture
def service():
    # Use in-memory database for tests
    return CounselingService(db_path=":memory:")

def test_add_and_query_slots(service):
    service.add_available_slot("counselor-1", "2026-10-20T14:00:00+09:00")
    service.add_available_slot("counselor-1", "2026-10-20T14:30:00+09:00")
    service.add_available_slot("counselor-2", "2026-10-21T10:00:00+09:00")

    # All available
    slots = service.query_available_slots()
    assert len(slots) == 3

    # Filter by counselor
    slots_c1 = service.query_available_slots(counselor_id="counselor-1")
    assert len(slots_c1) == 2

    # Filter by date
    slots_date = service.query_available_slots(date="2026-10-20")
    assert len(slots_date) == 2

    # Filter by both
    slots_both = service.query_available_slots(counselor_id="counselor-1", date="2026-10-20")
    assert len(slots_both) == 2

def test_booking_creation_success(service):
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
    slots = service.query_available_slots(counselor_id=counselor_id, date="2026-10-20")
    assert len(slots) == 0

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
    assert booking['client_name'] == "John Doe"
    assert booking['status'] == "CONFIRMED"
    
    # Unauthorized lookup
    with pytest.raises(UnauthorizedBookingError):
        service.lookup_booking(booking_id, "wrong@example.com")
    
    # Non-existent booking
    with pytest.raises(BookingNotFoundError):
        service.lookup_booking("non-existent-id", "john@example.com")

def test_booking_cancellation_flow(service):
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
    
    # Verify booking status
    booking = service.lookup_booking(booking_id, "john@example.com")
    assert booking['status'] == "CANCELLED"
    
    # Verify slot is available again
    slots = service.query_available_slots(counselor_id=counselor_id, date="2026-10-20")
    assert len(slots) == 1
    assert slots[0]['start_time'] == start_time

def test_cancel_unauthorized(service):
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

def test_cancel_already_cancelled(service):
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
    
    with pytest.raises(ValueError, match="Booking is already cancelled"):
        service.cancel_booking(booking_id, "john@example.com")

def test_invalid_time_format(service):
    with pytest.raises(InvalidTimeFormatError):
        service.add_available_slot("counselor-1", "not-a-date")

def test_slot_not_found(service):
    with pytest.raises(SlotNotFoundError):
        service.create_booking("counselor-1", "2026-10-20T14:00:00+09:00", "John", "john@example.com")
