from typing import NoReturn

class CounselingError(Exception):
    """Base exception for counseling service."""
    pass

class SlotNotFoundError(CounselingError):
    """Raised when a requested slot does not exist."""
    pass

class SlotAlreadyBookedError(CounselingError):
    """Raised when a slot is already booked."""
    pass

class BookingNotFoundError(CounselingError):
    """Raised when a booking cannot be found with the provided ID and email."""
    pass

class BookingAlreadyCancelledError(CounselingError):
    """Raised when attempting to cancel an already cancelled booking."""
    pass

class InvalidTimeFormatError(CounselingError):
    """Raised when the provided time string is not in valid ISO 8601 format."""
    pass
