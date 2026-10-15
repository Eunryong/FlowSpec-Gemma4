import pytest
from counseling_service import CounselingService

@pytest.fixture
def service():
    # Use :memory: for tests to ensure isolation and speed
    return CounselingService(db_path=":memory:")

def test_add_and_query_slots(service):
    service.add_available_slot("counselor-1", "2026-10-20T14:00:00+09:00")
    service.add_available_slot("counselor-1", "2026-10-20T15:00:00+09:00")
    service.add_available_slot("counselor-2", "2026-10-20T14:00:00+09:00")
    service.add_available_slot("counselor-1", "2026-10-21T14:00:00+09:00")

    # Query all
    all_slots = service.query_available_slots()
    assert len(all_slots) == 4

    # Query by counselor
    c1_slots = service.query_available_slots(counselor_id="counselor-1")
    assert len(c1_slots) == 3

    # Query by date
    date_slots = service.query_available_slots(date="2026-10-20")
    assert len(date_slots) == 3

    # Query by both
    both_slots = service.query_available_slots(counselor_id="counselor-1", date="2026-10-20")
    assert len(both_slots) == 2

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
    available = service.query_available_slots(counselor_id=counselor_id)
    assert len(available) == 0

def test_duplicate_booking_rejection(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)

    # First booking
    service.create_booking(counselor_id, start_time, "Client 1", "client1@example.com")

    # Second booking for same slot should fail
    with pytest.raises(ValueError, match="Slot is not available or does not exist"):
        service.create_booking(counselor_id, start_time, "Client 2", "client2@example.com")

def test_booking_lookup_and_verification(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    email = "john@example.com"
    booking_id = service.create_booking(counselor_id, start_time, "John Doe", email)

    # Successful lookup
    booking = service.lookup_booking(booking_id, email)
    assert booking is not None
    assert booking['client_name'] == "John Doe"
    assert booking['status'] == "CONFIRMED"

    # Failed lookup due to email mismatch
    wrong_booking = service.lookup_booking(booking_id, "wrong@example.com")
    assert wrong_booking is None

def test_cancel_booking_flow(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    email = "john@example.com"
    booking_id = service.create_booking(counselor_id, start_time, "John Doe", email)

    # Verify it's booked
    assert len(service.query_available_slots(counselor_id=counselor_id)) == 0

    # Cancel booking
    service.cancel_booking(booking_id, email)

    # Verify slot is available again
    available = service.query_available_slots(counselor_id=counselor_id)
    assert len(available) == 1
    assert available[0]['start_time'] == start_time

    # Verify booking status is CANCELLED
    # Note: lookup_booking still works for cancelled bookings if email matches
    booking = service.lookup_booking(booking_id, email)
    assert booking['status'] == "CANCELLED"

def test_cancel_booking_auth_failure(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    email = "john@example.com"
    booking_id = service.create_booking(counselor_id, start_time, "John Doe", email)

    with pytest.raises(ValueError, match="Booking not found or email mismatch"):
        service.cancel_booking(booking_id, "wrong@example.com")

def test_duplicate_slot_addition(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    
    service.add_available_slot(counselor_id, start_time)
    service.add_available_slot(counselor_id, start_time) # Should be no-op

    available = service.query_available_slots(counselor_id=counselor_id)
    assert len(available) == 1

def test_book_non_existent_slot(service):
    with pytest.raises(ValueError, match="Slot is not available or does not exist"):
        service.create_booking("non-existent", "2026-10-20T14:00:00+09:00", "Client", "client@example.com")

def test_cancel_already_cancelled_booking(service):
    counselor_id = "counselor-1"
    start_time = "2026-10-20T14:00:00+09:00"
    service.add_available_slot(counselor_id, start_time)
    
    email = "john@example.com"
    booking_id = service.create_booking(counselor_id, start_time, "John Doe", email)

    # First cancellation
    service.cancel_booking(booking_id, email)
    assert len(service.query_available_slots(counselor_id=counselor_id)) == 1

    # Second cancellation (idempotency)
    service.cancel_booking(booking_id, email)
    assert len(service.query_available_slots(counselor_id=counselor_id)) == 1
