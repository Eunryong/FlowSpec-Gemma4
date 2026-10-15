import pytest
from counseling.service import (
    CounselingService, 
    SlotNotFoundError, 
    SlotAlreadyBookedError, 
    BookingNotFoundError, 
    AuthenticationError,
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

def test_query_filters(service):
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
    
    booking_id = service.create_booking(
        counselor_id=counselor_id,
        start_time=start_time,
        client_name="John Doe",
        client_email="john@example.com"
    )
    
    assert booking_id is not None
    assert len(booking_id) > 0
    
    # Slot should no longer be available
    slots = service.query_available_slots(counselor_id=counselor_id)
    assert len(slots) == 0

def test_double_booking_rejection(service):
    counselor_id = "c1"
    start_time = "2026-10-20T10:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    service.create_booking(counselor_id, start_time, "Client 1", "c1@example.com")
    
    with pytest.raises(SlotAlreadyBookedError):
        service.create_booking(counselor_id, start_time, "Client 2", "c2@example.com")

def test_booking_nonexistent_slot(service):
    with pytest.raises(SlotNotFoundError):
        service.create_booking("c1", "2026-10-20T10:00:00+09:00", "Client 1", "c1@example.com")

def test_lookup_booking_success(service):
    counselor_id = "c1"
    start_time = "2026-10-20T10:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    email = "john@example.com"
    booking_id = service.create_booking(counselor_id, start_time, "John Doe", email)
    
    booking = service.lookup_booking(booking_id, email)
    assert booking['booking_id'] == booking_id
    assert booking['client_email'] == email
    assert booking['status'] == "CONFIRMED"

def test_lookup_booking_auth_failure(service):
    counselor_id = "c1"
    start_time = "2026-10-20T10:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    booking_id = service.create_booking(counselor_id, start_time, "John Doe", "john@example.com")
    
    with pytest.raises(AuthenticationError):
        service.lookup_booking(booking_id, "wrong@example.com")

def test_cancel_booking_success(service):
    counselor_id = "c1"
    start_time = "2026-10-20T10:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    email = "john@example.com"
    booking_id = service.create_booking(counselor_id, start_time, "John Doe", email)
    
    service.cancel_booking(booking_id, email)
    
    # Verify booking status
    booking = service.lookup_booking(booking_id, email)
    assert booking['status'] == "CANCELLED"
    
    # Verify slot is reopened
    slots = service.query_available_slots(counselor_id=counselor_id)
    assert len(slots) == 1
    assert slots[0]['start_time'] == start_time

def test_cancel_booking_auth_failure(service):
    counselor_id = "c1"
    start_time = "2026-10-20T10:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    booking_id = service.create_booking(counselor_id, start_time, "John Doe", "john@example.com")
    
    with pytest.raises(AuthenticationError):
        service.cancel_booking(booking_id, "wrong@example.com")

def test_cancel_already_cancelled_booking(service):
    counselor_id = "c1"
    start_time = "2026-10-20T10:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    email = "john@example.com"
    booking_id = service.create_booking(counselor_id, start_time, "John Doe", email)
    
    service.cancel_booking(booking_id, email)
    # Second cancellation should be idempotent
    service.cancel_booking(booking_id, email)
    
    booking = service.lookup_booking(booking_id, email)
    assert booking['status'] == "CANCELLED"

def test_invalid_iso_format(service):
    with pytest.raises(ValueError):
        service.add_available_slot("c1", "not-a-date")

def test_duplicate_slot_creation(service):
    counselor_id = "c1"
    start_time = "2026-10-20T10:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    with pytest.raises(CounselingError):
        service.add_available_slot(counselor_id, start_time)
