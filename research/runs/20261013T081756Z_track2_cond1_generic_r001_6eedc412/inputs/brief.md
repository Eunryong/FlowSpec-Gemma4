# 1:1 Counseling Booking Service (V1 Brief)

## 1. Overview
Build a standalone Python library and SQLite-backed service for a 1:1 counseling booking system ("여백 상담실").
All logic must be self-contained within this workspace, with clean module organization and automated unit tests.

## 2. Core Functional Requirements

### 2.1 Counselor Slot Management
- **Add Available Slot**: Counselors can open a 30-minute counseling time slot by specifying:
  - `counselor_id`: string identifier (e.g. `"counselor-1"`)
  - `start_time`: ISO 8601 formatted string with Asia/Seoul timezone or offset (e.g. `"2026-10-20T14:00:00+09:00"`)
- **Query Available Slots**: Clients can query open (unbooked) slots, optionally filtering by `counselor_id` and/or `date` (`"YYYY-MM-DD"`).

### 2.2 Booking Lifecycle
- **Create Booking**:
  - Inputs: `counselor_id`, `start_time`, `client_name`, `client_email`.
  - Behavior:
    - Generates a unique `booking_id` (UUID format).
    - Checks that the requested slot exists and is currently unbooked.
    - Atomically marks the slot as booked and records the booking with initial status `"CONFIRMED"`.
    - If the slot is already booked or invalid, rejects the request with an appropriate exception (e.g. `ValueError` or custom domain exception).
- **Lookup Booking**:
  - Clients can look up their booking by providing `booking_id` and `client_email` for verification.
- **Cancel Booking**:
  - Inputs: `booking_id` and `client_email`.
  - Behavior:
    - Verifies the email matches the booking record.
    - Transitions booking status to `"CANCELLED"`.
    - Automatically reopens the corresponding counseling slot so other clients can book it.

### 2.3 Storage & Persistence
- Implement SQLite persistence using Python's standard `sqlite3` module.
- The service class (e.g., `CounselingService`) must accept a `db_path` parameter (defaulting to `"counseling.sqlite3"` or `":memory:"` for test environments).
- Tables and schema should be initialized automatically if they do not exist.

### 2.4 Test Suite Requirement
- Write comprehensive unit and integration tests using `pytest` in `tests/` (e.g. `tests/test_counseling.py`).
- Tests must verify:
  1. Adding slots and querying available slots.
  2. Successful booking creation and UUID issuance.
  3. Rejection of duplicate bookings for the same slot.
  4. Cancellation flow and subsequent reopening of the slot.
  5. Authentication/email mismatch rejection on cancellation or lookup.
- Ensure all tests pass when running `pytest` via the `run_tests` tool.
