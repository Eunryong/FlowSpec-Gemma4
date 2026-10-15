import pytest
from counseling.service import CounselingService
from counseling.exceptions import (
    SlotNotFoundError,
    SlotAlreadyBookedError,
    BookingNotFoundError,
    BookingVerificationError,
)

@pytest.fixture
def service():
    # Use in-memory database for test isolation
    return CounselingService(db_path=":memory:")

def test_add_and_query_slots(service):
    service.add_available_slot("counselor-1", "2026-10-20T14:00:00+09:00")
    service.add_available_slot("counselor-1", "2026-10-20T15:00:00+09:00")
    service.add_available_slot("counselor-2", "2026-10-21T10:00:00+09:00")
    
    # Query all
    slots = service.query_available_slots()
    assert len(slots) == 3
    
    # Query by counselor
    slots_c1 = service.query_available_slots(counselor_id="counselor-1")
    assert len(slots_c1) == 2
    
    # Query by date
    slots_date = service.query_available_slots(date="2026-10-20")
    assert len(slots_date) == 2

def test_create_booking_success(service):
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot("counselor-1", start_time)
    
    booking_id = service.create_booking(
        counselor_id="counselor-1",
        start_time=start_time,
        client_name="John Doe",
        client_email="john@example.com"
    )
    
    assert booking_id is not None
    assert len(booking_id) > 0
    
    # Verify slot is now booked
    slots = service.query_available_slots(counselor_id="counselor-1", date="2026-10-20")
    assert len(slots) == 0

def test_create_booking_duplicate_rejection(service):
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot("counselor-1", start_time)
    
    service.create_booking(
        counselor_id="counselor-1",
        start_time=start_time,
        client_name="John Doe",
        client_email="john@example.com"
    )
    
    with pytest.raises(SlotAlreadyBookedError):
        service.create_booking(
            counselor_id="counselor-1",
            start_time=start_time,
            client_name="Jane Doe",
            client_email="jane@example.com"
        )

def test_create_booking_nonexistent_slot(service):
    with pytest.raises(SlotNotFoundError):
        service.create_booking(
            counselor_id="counselor-1",
            start_time="2026-10-20T14:00:00+09:00",
            client_name="John Doe",
            client_email="john@example.com"
        )

def test_lookup_booking_success(service):
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot("counselor-1", start_time)
    booking_id = service.create_booking(
        counselor_id="counselor-1",
        start_time=start_time,
        client_name="John Doe",
        client_email="john@example.com"
    )
    
    booking = service.lookup_booking(booking_id, "john@example.com")
    assert booking.booking_id == booking_id
    assert booking.client_name == "John Doe"

def test_lookup_booking_email_mismatch(service):
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot("counselor-1", start_time)
    booking_id = service.create_booking(
        counselor_id="counselor-1",
        start_time=start_time,
        client_name="John Doe",
        client_email="john@example.com"
    )
    
    with pytest.raises(BookingVerificationError):
        service.lookup_booking(booking_id, "wrong@example.com")

def test_cancel_booking_success(service):
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot("counselor-1", start_time)
    booking_id = service.create_booking(
        counselor_id="counselor-1",
        start_time=start_time,
        client_name="John Doe",
        client_email="john@example.com"
    )
    
    service.cancel_booking(booking_id, "john@example.com")
    
    # Verify booking status is CANCELLED
    booking = service.lookup_booking(booking_id, "john@example.com")
    assert booking.status == "CANCELLED"
    
    # Verify slot is available again
    slots = service.query_available_slots(counselor_id="counselor-1", date="2026-10-20")
    assert len(slots) == 1
    assert slots[0].start_time == start_time

def test_cancel_booking_email_mismatch(service):
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot("counselor-1", start_time)
    booking_id = service.create_booking(
        counselor_id="counselor-1",
        start_time=start_time,
        client_name="John Doe",
        client_email="john@example.com"
    )
    
    with pytest.raises(BookingVerificationError):
        service.cancel_booking(booking_id, "wrong@example.com")

def test_cancel_booking_not_found(service):
    with pytest.raises(BookingNotFoundError):
        service.cancel_booking("non-existent-id", "john@example.com")

def test_invalid_iso_format(service):
    with pytest.raises(ValueError, match="start_time must be in ISO 8601 format"):
        service.add_available_slot("counselor-1", "2026-10-20 14:00")
