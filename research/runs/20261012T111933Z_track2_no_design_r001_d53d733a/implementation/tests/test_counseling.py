import pytest
from counseling import CounselingService
from counseling.exceptions import (
    SlotNotFoundError,
    SlotAlreadyBookedError,
    BookingNotFoundError,
    BookingVerificationError
)

@pytest.fixture
def service():
    # Use in-memory database for tests
    return CounselingService(db_path=":memory:")

def test_add_and_query_slots(service):
    service.add_available_slot("counselor-1", "2026-10-20T14:00:00+09:00")
    service.add_available_slot("counselor-1", "2026-10-20T15:00:00+09:00")
    service.add_available_slot("counselor-2", "2026-10-21T10:00:00+09:00")

    # All available
    all_slots = service.query_available_slots()
    assert len(all_slots) == 3

    # Filter by counselor
    c1_slots = service.query_available_slots(counselor_id="counselor-1")
    assert len(c1_slots) == 2

    # Filter by date
    date_slots = service.query_available_slots(date="2026-10-20")
    assert len(date_slots) == 2

    # Combined filter
    combined_slots = service.query_available_slots(counselor_id="counselor-1", date="2026-10-20")
    assert len(combined_slots) == 2

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
    available = service.query_available_slots(counselor_id=counselor_id, date="2026-10-20")
    assert len(available) == 0

def test_create_booking_duplicate_rejection(service):
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
            client_name="Jane Smith",
            client_email="jane@example.com"
        )

def test_create_booking_invalid_slot(service):
    with pytest.raises(SlotNotFoundError):
        service.create_booking(
            counselor_id="non-existent",
            start_time="2026-10-20T14:00:00+09:00",
            client_name="John Doe",
            client_email="john@example.com"
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
    assert booking['counselor_id'] == counselor_id

def test_lookup_booking_verification_failure(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    booking_id = service.create_booking(
        counselor_id=counselor_id,
        start_time=start_time,
        client_name="John Doe",
        client_email="john@example.com"
    )

    with pytest.raises(BookingVerificationError):
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
    available = service.query_available_slots(counselor_id=counselor_id, date="2026-10-20")
    assert len(available) == 1
    
    # Verify booking status is CANCELLED
    # We need to check the DB directly or add a method to get booking status.
    # Since lookup_booking returns the booking, we can use it.
    # However, lookup_booking currently returns the booking regardless of status.
    # Let's check if it's cancelled.
    booking = service.lookup_booking(booking_id, "john@example.com")
    assert booking['status'] == "CANCELLED"

def test_cancel_booking_verification_failure(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    booking_id = service.create_booking(
        counselor_id=counselor_id,
        start_time=start_time,
        client_name="John Doe",
        client_email="john@example.com"
    )

    with pytest.raises(BookingVerificationError):
        service.cancel_booking(booking_id, "wrong@example.com")

def test_cancel_booking_not_found(service):
    with pytest.raises(BookingNotFoundError):
        service.cancel_booking("non-existent-id", "any@example.com")
