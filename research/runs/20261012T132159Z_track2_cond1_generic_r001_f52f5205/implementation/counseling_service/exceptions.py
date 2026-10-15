from datetime import datetime

class CounselingError(Exception):
    """Base exception for counseling service."""
    pass

class SlotNotFoundError(CounselingError):
    """Raised when a requested slot does not exist."""
    pass

class SlotAlreadyBookedError(CounselingError):
    """Raised when attempting to book an already booked slot."""
    pass

class BookingNotFoundError(CounselingError):
    """Raised when a booking ID is not found."""
    pass

class UnauthorizedBookingError(CounselingError):
    """Raised when the provided email does not match the booking record."""
    pass

class InvalidTimeFormatError(CounselingError):
    """Raised when the provided time string is not in valid ISO 8601 format."""
    pass
