"""
Improved SMS gateway service with proper error handling and OOP design.
"""
import logging
from typing import Dict, Any, Optional
from django.conf import settings
from services.base import BaseIntegrationService
from services.external.facilitamovel.facilitamovel import FacilitaMovelClient, load_config_from_env, FacilitaMovelConfig


logger = logging.getLogger(__name__)


class SMSServiceError(Exception):
    """Custom exception for SMS service errors."""
    pass


class FacilitaMovelGateway(BaseIntegrationService):
    """
    SMS gateway service for FacilitaMovel integration with proper error handling.
    """
    
    def __init__(self):
        super().__init__(service_name="facilitamovel_sms")
        self._client = None
        self._config = None
        self.message_template = getattr(settings, 'SMS_OTP_MESSAGE_TEMPLATE', 
                                      'Seu codigo da recobr.ai: {token}')
    
    @property
    def client(self) -> FacilitaMovelClient:
        """Lazy initialization of SMS client with connection validation."""
        if self._client is None:
            try:
                self._config = load_config_from_env()
                self._validate_config(self._config)
                self._client = FacilitaMovelClient(self._config)
                self.set_status('active')
                self.log_info("SMS client initialized successfully")
            except Exception as e:
                self.set_status('error')
                self.handle_error(e, context="client_initialization", raise_error=True)
        
        return self._client
    
    def send_sms(self, device, token: str) -> Dict[str, Any]:
        """
        Send SMS with improved error handling and logging.
        
        Args:
            device: Phone device object or phone number string
            token (str): OTP token to send
            
        Returns:
            Dict containing send results
            
        Raises:
            SMSServiceError: If SMS sending fails
        """
        try:
            phone_number = self._extract_phone_number(device)
            message = self.message_template.format(token=token)
            
            self.log_info(f"Sending SMS to {phone_number[:6]}****", 
                         context="sms_send")
            
            result = self.client.send_sms(to=phone_number, message=message)
            
            if result.get('success'):
                self.log_info("SMS sent successfully", context="sms_send")
                self.increment_request_count()
                return {
                    'success': True,
                    'message_id': result.get('message_id'),
                    'status': 'sent'
                }
            else:
                error_msg = f"SMS send failed: {result.get('error', 'Unknown error')}"
                self.log_warning(error_msg, context="sms_send")
                raise SMSServiceError(error_msg)
                
        except SMSServiceError:
            raise
        except Exception as e:
            self.handle_error(e, context="sms_send")
            raise SMSServiceError(f"SMS service error: {str(e)}")

    def send_text_sms(self, to: str, message: str) -> Dict[str, Any]:
        """
        Send a raw text SMS to a phone number in E.164 or local format.

        Args:
            to: Phone number string
            message: Message text to send

        Returns:
            Dict with keys: success (bool), message_id (str|None), status (str)
        """
        try:
            phone_number = str(to)
            self.log_info(f"Sending raw SMS to {phone_number[:6]}****", context="sms_send_text")

            result = self.client.send_sms(to=phone_number, message=message)

            if result.get('success'):
                self.log_info("Raw SMS sent successfully", context="sms_send_text")
                self.increment_request_count()
                return {
                    'success': True,
                    'message_id': result.get('message_id'),
                    'status': 'sent'
                }
            else:
                error_msg = f"Raw SMS send failed: {result.get('error', 'Unknown error') }"
                self.log_warning(error_msg, context="sms_send_text")
                raise SMSServiceError(error_msg)
        except SMSServiceError:
            raise
        except Exception as e:
            self.handle_error(e, context="sms_send_text")
            raise SMSServiceError(f"SMS service error: {str(e)}")
    
    def check_connection(self) -> Dict[str, Any]:
        """
        Check SMS gateway connection and service health.
        
        Returns:
            Dict containing connection status
        """
        try:
            # Test connection with the SMS gateway
            if self._client is None:
                # Initialize client to test connection
                _ = self.client
            
            return {
                'status': 'connected',
                'service': 'FacilitaMovel',
                'last_check': self._get_current_timestamp()
            }
            
        except Exception as e:
            self.handle_error(e, context="connection_check")
            return {
                'status': 'disconnected',
                'error': str(e),
                'last_check': self._get_current_timestamp()
            }
    
    def _extract_phone_number(self, device) -> str:
        """
        Extract phone number from various device types.
        
        Args:
            device: Phone device object or string
            
        Returns:
            str: Phone number in E.164 format
        """
        try:
            # Handle PhoneDevice utility objects
            if hasattr(device, 'as_e164'):
                return device.as_e164
            
            # Handle django-otp device objects
            elif hasattr(device, 'number') and hasattr(device.number, 'as_e164'):
                return device.number.as_e164
            
            # Handle phone number objects with as_e164 method
            elif hasattr(device, 'number'):
                return str(device.number)
            
            # Handle string phone numbers
            else:
                return str(device)
                
        except Exception as e:
            raise SMSServiceError(f"Invalid phone number format: {str(e)}")
    
    def _validate_config(self, config: FacilitaMovelConfig) -> None:
        """
        Validate SMS gateway configuration.
        
        Args:
            config (FacilitaMovelConfig): Configuration dataclass instance
            
        Raises:
            SMSServiceError: If configuration is invalid
        """
        required_fields = ['user', 'password', 'hash_seguranca', 'base_url']
        
        for field in required_fields:
            if not getattr(config, field, None):
                raise SMSServiceError(f"Missing required SMS configuration: {field}")
        
        self.log_info("SMS gateway configuration validated successfully")
    
    def _get_current_timestamp(self) -> float:
        """Get current timestamp."""
        import time
        return time.time()
