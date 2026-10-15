from dataclasses import dataclass
from typing import Optional

class CounselingError(Exception):
    """Base exception for counseling service."""
    pass

class SlotNotFoundError(CounselingError):
    """Raised when a requested slot does not exist."""
    pass

class SlotAlreadyBookedError(CounselingError):
    """Raised when a requested slot is already booked."""
    pass

class BookingNotFoundError(CounselingError):
    """Raised when a booking ID is not found."""
    pass

class BookingVerificationError(CounselingError):
    """Raised when the provided email does not match the booking record."""
    pass
