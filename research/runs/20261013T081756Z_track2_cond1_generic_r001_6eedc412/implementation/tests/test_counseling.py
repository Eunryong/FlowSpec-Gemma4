import pytest
from counseling import CounselingService

@pytest.fixture
def service():
    # Use in-memory database for tests
    return CounselingService(db_path=":memory:")

def test_add_and_query_slots(service):
    service.add_available_slot("counselor-1", "2026-10-20T14:00:00+09:00")
    service.add_available_slot("counselor-1", "2026-10-20T14:30:00+09:00")
    service.add_available_slot("counselor-2", "2026-10-20T15:00:00+09:00")
    service.add_available_slot("counselor-1", "2026-10-21T10:00:00+09:00")

    # All available
    all_slots = service.query_available_slots()
    assert len(all_slots) == 4

    # Filter by counselor
    c1_slots = service.query_available_slots(counselor_id="counselor-1")
    assert len(c1_slots) == 3

    # Filter by date
    date_slots = service.query_available_slots(date="2026-10-20")
    assert len(date_slots) == 3

    # Filter by both
    both_slots = service.query_available_slots(counselor_id="counselor-1", date="2026-10-20")
    assert len(both_slots) == 2

def test_booking_lifecycle(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    client_name = "John Doe"
    client_email = "john@example.com"

    service.add_available_slot(counselor_id, start_time)

    # Create booking
    booking_id = service.create_booking(counselor_id, start_time, client_name, client_email)
    assert booking_id is not None
    
    # Verify slot is no longer available
    available = service.query_available_slots(counselor_id=counselor_id, date="2026-10-20")
    assert len(available) == 0

    # Lookup booking
    booking = service.lookup_booking(booking_id, client_email)
    assert booking is not None
    assert booking['client_name'] == client_name
    assert booking['status'] == "CONFIRMED"

    # Cancel booking
    service.cancel_booking(booking_id, client_email)
    
    # Verify slot is available again
    available = service.query_available_slots(counselor_id=counselor_id, date="2026-10-20")
    assert len(available) == 1

    # Verify booking status is CANCELLED
    booking = service.lookup_booking(booking_id, client_email)
    assert booking['status'] == "CANCELLED"

def test_duplicate_booking_rejection(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)

    service.create_booking(counselor_id, start_time, "Client 1", "client1@example.com")
    
    with pytest.raises(ValueError, match="Slot is not available or does not exist"):
        service.create_booking(counselor_id, start_time, "Client 2", "client2@example.com")

def test_email_verification(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    client_email = "client@example.com"
    service.add_available_slot(counselor_id, start_time)
    booking_id = service.create_booking(counselor_id, start_time, "Client", client_email)

    # Lookup with wrong email
    with pytest.raises(ValueError, match="Email verification failed"):
        service.lookup_booking(booking_id, "wrong@example.com")

    # Cancel with wrong email
    with pytest.raises(ValueError, match="Email verification failed"):
        service.cancel_booking(booking_id, "wrong@example.com")

def test_invalid_slot_booking(service):
    with pytest.raises(ValueError, match="Slot is not available or does not exist"):
        service.create_booking("non-existent", "2026-10-20T14:00:00+09:00", "Client", "email@example.com")

def test_invalid_time_format(service):
    with pytest.raises(ValueError, match="Invalid ISO 8601 start_time format"):
        service.add_available_slot("counselor-1", "2026-10-20 14:00")

def test_cancel_already_cancelled(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    client_email = "client@example.com"
    service.add_available_slot(counselor_id, start_time)
    booking_id = service.create_booking(counselor_id, start_time, "Client", client_email)

    service.cancel_booking(booking_id, client_email)
    with pytest.raises(ValueError, match="Booking is already cancelled"):
        service.cancel_booking(booking_id, client_email)
