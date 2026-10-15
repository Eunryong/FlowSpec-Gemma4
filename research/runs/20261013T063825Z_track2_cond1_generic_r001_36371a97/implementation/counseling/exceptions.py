from datetime import datetime

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
    """Raised when a booking ID is not found."""
    pass

class AuthenticationError(CounselingError):
    """Raised when the provided email does not match the booking."""
    pass

class InvalidTimeFormatError(CounselingError):
    """Raised when the provided time string is not valid ISO 8601."""
    pass

class DatabaseError(CounselingError):
    """Raised when a database operation fails."""
    pass
