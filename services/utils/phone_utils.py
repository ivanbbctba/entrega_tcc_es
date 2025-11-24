"""
Utility classes and functions for phone number handling and SMS integration.
"""
from phonenumbers import PhoneNumber


class PhoneDevice:
    """
    A device-like object that works with FacilitaMovel SMS gateway.
    This consolidates the TempDevice classes used in SignupView and PhoneVerifyView.
    """
    
    def __init__(self, phone_number):
        """
        Initialize with a phone number (can be PhoneNumber object or string).
        """
        self.number = phone_number
        
    @property
    def as_e164(self):
        """
        Return phone number in E.164 format for SMS gateway compatibility.
        """
        if hasattr(self.number, 'as_e164'):
            return self.number.as_e164
        else:
            # If it's a string, assume it's already in proper format
            return str(self.number)