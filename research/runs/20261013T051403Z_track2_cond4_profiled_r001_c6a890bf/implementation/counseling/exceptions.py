class CounselingError(Exception):

    """Base exception for counseling service"""
    pass

class SlotUnavailableError(CounselingError):
    """Raised when a slot is already booked or does not exist"""
    pass

class BookingNotFoundError(CounselingError):
    """Raised when a booking cannot be found"""
    pass

class UnauthorizedBookingError(CounselingError):
    """Raised when the email does not match the booking record"""
    pass
