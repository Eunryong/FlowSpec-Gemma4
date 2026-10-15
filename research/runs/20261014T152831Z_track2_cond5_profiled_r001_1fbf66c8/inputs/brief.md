# 1:1 Counseling Booking, Rescheduling, Session Pass & Waitlist Engine ("여백 상담실 V2" Large Brief)

## 1. Overview
Build a standalone Python module (`counseling_engine.py`) and SQLite-backed transactional booking engine (`CounselingBookingEngine`) for a 1:1 counseling reservation platform ("여백 상담실 V2") that coordinates four coupled domain subsystems:
1. **Counselor Schedule & Slot Lifecycle Subsystem** (`AVAILABLE`, `BOOKED`, `BLOCKED` slot states and counselor blackout rules)
2. **Client Session Pass & Idempotent Quota Ledger Subsystem** (session pass issuance/top-up with idempotency keys, session deduction on booking, and session restoration on cancellation)
3. **Booking Lifecycle & Atomic Rescheduling Saga Subsystem** (booking creation, email-authenticated lookup, atomic slot rescheduling with rollback if target slot is unavailable, and cancellation)
4. **Waitlist Auto-Promotion, Audit Log & System Reconciliation Subsystem** (FIFO waitlist registration on booked slots, automatic promotion of the first eligible waitlisted client upon booking cancellation, chronological booking audit logs, and global quota/slot accounting reconciliation)

All logic must be self-contained within this workspace using Python's standard library (`sqlite3`, `uuid`, `dataclasses`, `datetime`, etc.) and verified with an automated `pytest` suite in `tests/`.

---

## 2. Core Functional & Architectural Requirements

### 2.1 Subsystem A: Counselor Schedule & Slot Lifecycle
- **Register Counselor (`register_counselor`)**:
  - Inputs: `counselor_id: str`, `name: str`, `specialty: str`.
  - Validation: `counselor_id` and `name` must be non-empty; duplicate `counselor_id` must raise `ValueError`.
- **Add Available Slot (`add_slot`)**:
  - Inputs: `counselor_id: str`, `start_time: str` (ISO 8601 format, e.g. `"2026-10-20T14:00:00+09:00"`).
  - Validation: Counselor must exist; duplicate `(counselor_id, start_time)` must raise `ValueError`.
  - Initializes slot with unique `slot_id: str` (or integer/string ID), `status = "AVAILABLE"`, and returns the slot dictionary (`slot_id`, `counselor_id`, `start_time`, `status`).
- **Block / Unblock Counselor Slot (`block_slot`)**:
  - Inputs: `counselor_id: str`, `start_time: str`.
  - Behavior: Allowed **only** when the slot currently has `status == "AVAILABLE"` (raises `ValueError` if slot does not exist or is currently `"BOOKED"` or already `"BLOCKED"`). Transitions slot `status` to `"BLOCKED"`.
- **Query Available Slots (`query_available_slots`)**:
  - Inputs: `counselor_id: str | None = None`, `date_prefix: str | None = None` (e.g., `"2026-10-20"`).
  - Returns list of dictionaries for all slots currently in `status == "AVAILABLE"` matching the optional filters, ordered by `start_time` ascending.

### 2.2 Subsystem B: Client Session Pass & Idempotent Quota Ledger
- **Create / Top-up Client Pass (`issue_session_pass`)**:
  - Inputs: `client_email: str`, `sessions_to_add: int`, `idempotency_key: str`.
  - Validation: `client_email` must be non-empty, `sessions_to_add > 0` (raise `ValueError` otherwise).
  - **Idempotency Requirement**: Every session change (`"ISSUE"`, `"USE"`, `"RESTORE"`) must be recorded in a `pass_ledger` table (`entry_id`, `client_email`, `booking_id` nullable, `entry_type`, `delta_sessions`, `idempotency_key` unique). If `issue_session_pass` is called with an `idempotency_key` that already exists in `pass_ledger`, it must NOT add sessions a second time; it must safely return the current pass status.
  - Initializes or updates the client's `session_passes` record (`client_email`, `remaining_sessions`, `used_sessions`).
- **Get Client Pass (`get_session_pass`)**:
  - Input: `client_email: str`.
  - Returns dictionary with `client_email`, `remaining_sessions: int`, and `used_sessions: int` (if client has no pass record yet, returns `remaining_sessions = 0, used_sessions = 0` or raises `ValueError`).
- **Pass Conservation Invariant**:
  - A client's `remaining_sessions` must never drop below `0`.
  - When a booking is confirmed (either directly or via waitlist auto-promotion), `remaining_sessions` decreases by `1`, `used_sessions` increases by `1`, and a `"USE"` entry (`delta_sessions = -1`) is recorded in `pass_ledger`.
  - When a confirmed booking is cancelled, `remaining_sessions` increases by `1`, `used_sessions` decreases by `1`, and a `"RESTORE"` entry (`delta_sessions = +1`) is recorded in `pass_ledger`.

### 2.3 Subsystem C: Booking Lifecycle & Atomic Rescheduling Saga
- **Create Booking (`create_booking`)**:
  - Inputs: `counselor_id: str`, `start_time: str`, `client_name: str`, `client_email: str`, `idempotency_key: str | None = None`.
  - **Execution Flow**:
    1. If `idempotency_key` is provided and an active/existing booking was already created with that `idempotency_key`, return that existing booking dictionary without deducting another session pass or double-booking.
    2. Verify the slot `(counselor_id, start_time)` exists and its `status == "AVAILABLE"` (raise `ValueError` if missing, `"BOOKED"`, or `"BLOCKED"`).
    3. Verify the client (`client_email`) has `remaining_sessions >= 1` (raise `ValueError` if insufficient sessions; slot must remain `"AVAILABLE"`).
    4. Atomically in a single transaction:
       - Mark the slot `status = "BOOKED"`.
       - Deduct 1 session from `session_passes` (`remaining_sessions -= 1`, `used_sessions += 1`) and insert a `"USE"` entry into `pass_ledger`.
       - Insert booking record (`booking_id` UUID, `counselor_id`, `start_time`, `client_name`, `client_email`, `status = "CONFIRMED"`, `idempotency_key`).
       - Append audit log entry (`event_type = "BOOKING_CREATED"`, `from_status = None`, `to_status = "CONFIRMED"`).
    5. Return the booking dictionary.
- **Lookup Booking (`lookup_booking`)**:
  - Inputs: `booking_id: str`, `client_email: str`.
  - Verifies booking exists and `client_email` matches the booking's `client_email` (raises `PermissionError` or `ValueError` on email mismatch or missing booking). Returns the booking dictionary.
- **Atomic Reschedule Booking (`reschedule_booking`)**:
  - Inputs: `booking_id: str`, `client_email: str`, `new_counselor_id: str`, `new_start_time: str`.
  - **Execution Flow**:
    1. Verify `booking_id` exists, `client_email` matches (raise `PermissionError` or `ValueError` otherwise), and current booking `status == "CONFIRMED"` (cancelled bookings cannot be rescheduled).
    2. Verify the target slot `(new_counselor_id, new_start_time)` exists and has `status == "AVAILABLE"` (if target slot is `"BOOKED"`, `"BLOCKED"`, or nonexistent, raise `ValueError` and ensure the original booking and original slot remain `"CONFIRMED"` / `"BOOKED"` with zero state corruption).
    3. Atomically:
       - Release the old slot (`status = "AVAILABLE"`, or if the old slot has an eligible waitlist entry, promote the first waitlisted client—see 2.4).
       - Occupy the new slot (`status = "BOOKED"`).
       - Update the booking's `counselor_id` and `start_time` to `new_counselor_id` and `new_start_time` (status remains `"CONFIRMED"`, session pass count is unchanged since it is a 1:1 slot swap).
       - Append audit log entry (`event_type = "BOOKING_RESCHEDULED"`, `from_status = "CONFIRMED"`, `to_status = "CONFIRMED"`).
    4. Return the updated booking dictionary.

### 2.4 Subsystem D: Cancellation, Waitlist Auto-Promotion & Reconciliation
- **Join Waitlist (`join_waitlist`)**:
  - Inputs: `counselor_id: str`, `start_time: str`, `client_name: str`, `client_email: str`.
  - Behavior:
    - Allowed **only** when the slot `(counselor_id, start_time)` currently has `status == "BOOKED"` (raises `ValueError` if slot is `"AVAILABLE"`, `"BLOCKED"`, or nonexistent).
    - Client must have `remaining_sessions >= 1` at the time of joining (raises `ValueError` otherwise).
    - Inserts a waitlist record (`waitlist_id`, `counselor_id`, `start_time`, `client_name`, `client_email`, `status = "WAITING"`, ordered FIFO by insertion sequence).
- **Cancel Booking & Waitlist Auto-Promotion (`cancel_booking`)**:
  - Inputs: `booking_id: str`, `client_email: str`.
  - **Execution Flow**:
    1. Verify booking exists, `client_email` matches, and booking `status == "CONFIRMED"` (raises `ValueError` if already `"CANCELLED"` or email mismatch).
    2. Atomically:
       - Transition the cancelled booking to `status = "CANCELLED"`.
       - Restore 1 session to the cancelling client (`remaining_sessions += 1`, `used_sessions -= 1`) and record a `"RESTORE"` entry in `pass_ledger`.
       - Append audit log entry (`event_type = "BOOKING_CANCELLED"`, `from_status = "CONFIRMED"`, `to_status = "CANCELLED"`).
       - **Waitlist Auto-Promotion Check**: Query `WAITING` waitlist entries for `(counselor_id, start_time)` in FIFO order:
         - Find the first waitlisted client who currently has `remaining_sessions >= 1`.
         - **If such a waitlisted client exists**:
           - Mark their waitlist entry `status = "PROMOTED"`.
           - Deduct 1 session from that promoted client (`remaining_sessions -= 1`, `used_sessions += 1`) and record a `"USE"` entry in `pass_ledger`.
           - Create a new `"CONFIRMED"` booking for that promoted client on `(counselor_id, start_time)` and record `"WAITLIST_PROMOTED"` in `audit_logs`.
           - Keep the slot `status = "BOOKED"`.
         - **If no eligible waitlisted client exists**:
           - Transition the slot `status = "AVAILABLE"`.
    3. Return the cancelled booking dictionary.
- **Audit Log (`get_booking_audit_log`)**:
  - Input: `booking_id: str`.
  - Returns chronological list of audit events (`log_id`, `booking_id`, `event_type`, `from_status`, `to_status`, `timestamp`) for that booking.
- **System Reconciliation (`get_system_reconciliation`)**:
  - Returns a dictionary summarizing system-wide booking and session pass integrity:
    - `total_issued_sessions`: sum of `"ISSUE"` delta_sessions in `pass_ledger`.
    - `total_remaining_sessions`: sum of `remaining_sessions` across all clients in `session_passes`.
    - `total_used_sessions`: sum of `used_sessions` across all clients in `session_passes`.
    - `active_confirmed_bookings`: count of bookings currently with `status == "CONFIRMED"`.
    - `booked_slots_count`: count of slots currently with `status == "BOOKED"`.
    - `is_balanced`: boolean (`total_issued_sessions == total_remaining_sessions + total_used_sessions` AND `total_used_sessions == active_confirmed_bookings` AND `active_confirmed_bookings == booked_slots_count`).

---

## 3. Storage & Persistence Requirements
- Implement SQLite persistence using Python's `sqlite3` module in `counseling_engine.py`.
- `CounselingBookingEngine(db_path: str = ":memory:")` must maintain a persistent connection when `:memory:` is used so all tables persist across method calls.
- Tables must be initialized automatically on instantiation.

## 4. Test Suite Requirements (`tests/`)
Write a comprehensive `pytest` test suite (e.g., `tests/test_counseling_engine.py`) verifying at least the following 8 scenarios:
1. **Counselor & Slot Lifecycle**: Registering counselors, adding slots, blocking unbooked slots, and preventing blocking of already booked slots.
2. **Session Pass & Idempotency**: Issuing session passes, preventing duplicate additions on repeated `idempotency_key`, and verifying `pass_ledger`.
3. **Booking Creation & Double-Booking Guard**: Creating a booking deducts 1 session pass, transitions slot to `"BOOKED"`, prevents double booking, and guarantees checkout `idempotency_key` safety.
4. **Booking Failure Rollback (Insufficient Pass Quota)**: Attempting to book with `0` remaining sessions raises `ValueError` and leaves the slot `"AVAILABLE"`.
5. **Atomic Rescheduling Saga**: Rescheduling a confirmed booking moves it to the new slot and frees the old slot without extra session deduction; attempting to reschedule into an already `"BOOKED"` or `"BLOCKED"` slot raises `ValueError` and preserves the original booking intact.
6. **Cancellation & Session Restoration**: Cancelling a `"CONFIRMED"` booking with no waitlist restores 1 session pass to the client and reopens the slot to `"AVAILABLE"`.
7. **Waitlist Auto-Promotion on Cancellation**: Joining a waitlist for a `"BOOKED"` slot, and verifying that when the current holder cancels, the first waitlisted client is automatically promoted to a `"CONFIRMED"` booking (with 1 session deducted) and the slot remains `"BOOKED"`.
8. **Global Reconciliation & Audit Log**: After a mix of bookings, reschedules, cancellations, and waitlist promotions, `get_system_reconciliation()` reports `is_balanced == True` (`total_used_sessions == active_confirmed_bookings == booked_slots_count`).
