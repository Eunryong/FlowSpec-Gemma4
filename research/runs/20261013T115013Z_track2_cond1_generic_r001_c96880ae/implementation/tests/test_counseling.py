import pytest
from counseling.service import CounselingService
from counseling.exceptions import (
    SlotNotFoundError,
    SlotAlreadyBookedError,
    BookingNotFoundError,
    BookingVerificationError,
    CounselingError
)

@pytest.fixture
def service():
    # Use in-memory database for tests
    return CounselingService(db_path=":memory:")

def test_add_and_query_slots(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    
    service.add_available_slot(counselor_id, start_time)
    
    slots = service.query_available_slots()
    assert len(slots) == 1
    assert slots[0]['counselor_id'] == counselor_id
    assert slots[0]['start_time'] == start_time

def test_query_slots_filtering(service):
    service.add_available_slot("c1", "2026-10-20T14:00:00+09:00")
    service.add_available_slot("c1", "2026-10-20T15:00:00+09:00")
    service.add_available_slot("c2", "2026-10-20T14:00:00+09:00")
    service.add_available_slot("c2", "2026-10-21T14:00:00+09:00")
    
    # Filter by counselor
    c1_slots = service.query_available_slots(counselor_id="c1")
    assert len(c1_slots) == 2
    
    # Filter by date
    date_slots = service.query_available_slots(date="2026-10-20")
    assert len(date_slots) == 3
    
    # Filter by both
    c1_date_slots = service.query_available_slots(counselor_id="c1", date="2026-10-20")
    assert len(c1_date_slots) == 1

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
    
    # Slot should no longer be available
    slots = service.query_available_slots(counselor_id=counselor_id, date="2026-10-20")
    assert len(slots) == 0

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
            client_name="Jane Doe",
            client_email="jane@example.com"
        )

def test_create_booking_nonexistent_slot(service):
    with pytest.raises(SlotNotFoundError):
        service.create_booking(
            counselor_id="none",
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
    assert booking['status'] == "CONFIRMED"

def test_lookup_booking_email_mismatch(service):
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
    
    # Verify booking status
    booking = service.lookup_booking(booking_id, "john@example.com")
    assert booking['status'] == "CANCELLED"
    
    # Verify slot is available again
    slots = service.query_available_slots(counselor_id=counselor_id, date="2026-10-20")
    assert len(slots) == 1

def test_cancel_booking_email_mismatch(service):
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

def test_cancel_booking_already_cancelled(service):
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
    
    with pytest.raises(CounselingError):
        service.cancel_booking(booking_id, "john@example.com")

def test_invalid_iso_date(service):
    with pytest.raises(ValueError):
        service.add_available_slot("c1", "invalid-date")
