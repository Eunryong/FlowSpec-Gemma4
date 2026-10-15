class CounselingError(Exception):
    """Base exception for counseling service."""
    pass

class SlotNotFoundError(CounselingError):
    """Raised when a requested slot is not found."""
    pass

class SlotAlreadyBookedError(CounselingError):
    """Raised when a requested slot is already booked."""
    pass

class BookingNotFoundError(CounselingError):
    """Raised when a booking is not found."""
    pass

class BookingVerificationError(CounselingError):
    """Raised when booking verification (e.g., email mismatch) fails."""
    pass
