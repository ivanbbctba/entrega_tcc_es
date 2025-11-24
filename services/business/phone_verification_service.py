"""
Phone verification business service with proper OOP design and security.
"""
import secrets
import string
import logging
import hashlib
from typing import Dict, Any, Optional, Tuple
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django.conf import settings

from services.base import BaseBusinessService
from services.integrations.facilitamovel_gateway import FacilitaMovelGateway
from services.utils.phone_utils import PhoneDevice


User = get_user_model()
logger = logging.getLogger(__name__)


class PhoneVerificationService(BaseBusinessService):
    """
    Business service for phone number verification with OTP.
    Handles the complete phone verification workflow with proper security.
    """
    
    def __init__(self):
        super().__init__(service_name="phone_verification")
        self.sms_gateway = FacilitaMovelGateway()
        self.otp_length = getattr(settings, 'OTP_LENGTH', 6)
        self.max_resend_attempts = getattr(settings, 'MAX_OTP_RESEND_ATTEMPTS', 3)
        self.resend_cooldown = getattr(settings, 'OTP_RESEND_COOLDOWN_SECONDS', 60)
    
    def generate_secure_otp(self) -> str:
        """
        Generate a cryptographically secure OTP token.
        
        Returns:
            str: Secure random OTP token
        """
        try:
            # Use cryptographically secure random number generation
            alphabet = string.digits
            otp = ''.join(secrets.choice(alphabet) for _ in range(self.otp_length))
            
            self.log_info(f"Generated secure OTP token", context="otp_generation")
            return otp
            
        except Exception as e:
            self.handle_error(e, context="otp_generation", raise_error=True)
    
    def create_verification_token(self, phone_number: str) -> Dict[str, Any]:
        """
        Create a secure verification token for session management.
        
        Args:
            phone_number (str): Phone number to verify
            
        Returns:
            Dict containing encrypted token and metadata
        """
        try:
            # Create a secure token for session management
            token_data = f"{phone_number}:{secrets.token_urlsafe(32)}"
            token_hash = hashlib.sha256(token_data.encode()).hexdigest()
            
            return {
                'verification_token': token_hash[:32],  # Truncate for session use
                'phone_number': str(phone_number),
                'created_at': self._get_current_timestamp()
            }
            
        except Exception as e:
            self.handle_error(e, context="token_creation", raise_error=True)
    
    def initiate_phone_verification(self, user: User, phone_number: str) -> Dict[str, Any]:
        """
        Initiate phone verification process for a user.
        
        Args:
            user (User): User object to verify
            phone_number (str): Phone number to verify
            
        Returns:
            Dict containing verification results
        """
        try:
            self.log_info(f"Initiating phone verification for user {user.id}", 
                         context="verification_start")
            
            # Create OTP device
            device = StaticDevice.objects.create(
                user=user,
                name='phone_verification',
                confirmed=False
            )
            
            # Generate secure OTP
            otp_token = self.generate_secure_otp()
            StaticToken.objects.create(device=device, token=otp_token)
            
            # Send SMS
            self._send_verification_sms(phone_number, otp_token)
            
            # Create secure session token
            session_token = self.create_verification_token(phone_number)
            session_token['user_id'] = str(user.id)
            session_token['device_id'] = str(device.id)
            
            self.track_operation()
            self.log_info(f"Phone verification initiated successfully", 
                         context="verification_start")
            
            return {
                'success': True,
                'session_data': session_token,
                'message': f'Código de verificação enviado para {phone_number}'
            }
            
        except Exception as e:
            # Cleanup on failure
            if 'device' in locals():
                device.delete()
            
            self.handle_error(e, context="verification_initiation")
            return {
                'success': False,
                'error': 'Erro ao iniciar verificação. Tente novamente.'
            }
    
    def verify_otp_token(self, user_id: str, device_id: str, otp_code: str) -> Dict[str, Any]:
        """
        Verify OTP token and activate user if valid.
        
        Args:
            user_id (str): User ID from session
            device_id (str): Device ID from session
            otp_code (str): OTP code provided by user
            
        Returns:
            Dict containing verification results
        """
        try:
            self.log_info(f"Verifying OTP for user {user_id}", context="otp_verification")
            
            # Get user and device
            user = User.objects.get(id=user_id)
            device = StaticDevice.objects.get(id=device_id, user=user)
            
            # Verify OTP token
            token_obj = StaticToken.objects.filter(device=device, token=otp_code).first()
            if not token_obj:
                self.log_warning(f"Invalid OTP attempt for user {user_id}", 
                               context="otp_verification")
                return {
                    'success': False,
                    'error': 'Código de verificação inválido ou expirado.'
                }
            
            # Activate user and confirm device
            user.is_active = True
            user.save()
            
            device.confirmed = True
            device.save()
            
            # Delete used token (one-time use)
            token_obj.delete()
            
            self.track_operation()
            self.log_info(f"Phone verification completed successfully for user {user_id}", 
                         context="otp_verification")
            
            return {
                'success': True,
                'user': user,
                'message': 'Telefone verificado com sucesso!'
            }
            
        except (User.DoesNotExist, StaticDevice.DoesNotExist) as e:
            self.log_warning(f"Verification failed - invalid user/device: {user_id}/{device_id}", 
                           context="otp_verification")
            return {
                'success': False,
                'error': 'Sessão expirada. Por favor, registre-se novamente.'
            }
        except Exception as e:
            self.handle_error(e, context="otp_verification")
            return {
                'success': False,
                'error': 'Erro interno. Tente novamente.'
            }
    
    def resend_otp_token(self, user_id: str, device_id: str, phone_number: str,
                        current_attempts: int, last_attempt_time: float) -> Dict[str, Any]:
        """
        Resend OTP token with rate limiting.
        
        Args:
            user_id (str): User ID from session
            device_id (str): Device ID from session  
            phone_number (str): Phone number to send to
            current_attempts (int): Current resend attempt count
            last_attempt_time (float): Last attempt timestamp
            
        Returns:
            Dict containing resend results
        """
        try:
            # Check rate limiting
            if not self._can_resend_otp(current_attempts, last_attempt_time):
                return {
                    'success': False,
                    'error': 'Aguarde antes de solicitar um novo código.'
                }
            
            self.log_info(f"Resending OTP for user {user_id}", context="otp_resend")
            
            # Get user and device
            user = User.objects.get(id=user_id)
            device = StaticDevice.objects.get(id=device_id, user=user)
            
            # Clear existing tokens
            StaticToken.objects.filter(device=device).delete()
            
            # Generate new OTP
            otp_token = self.generate_secure_otp()
            StaticToken.objects.create(device=device, token=otp_token)
            
            # Send SMS
            self._send_verification_sms(phone_number, otp_token)
            
            self.track_operation()
            self.log_info(f"OTP resent successfully for user {user_id}", context="otp_resend")
            
            return {
                'success': True,
                'message': f'Novo código enviado para {phone_number}.'
            }
            
        except Exception as e:
            self.handle_error(e, context="otp_resend")
            return {
                'success': False,
                'error': 'Erro ao reenviar código. Tente novamente.'
            }
    
    def _send_verification_sms(self, phone_number: str, otp_token: str) -> None:
        """
        Send verification SMS using the configured gateway.
        
        Args:
            phone_number (str): Phone number to send to
            otp_token (str): OTP token to send
        """
        try:
            phone_device = PhoneDevice(phone_number)
            self.sms_gateway.send_sms(phone_device, otp_token)
            
            self.log_info("Verification SMS sent successfully", 
                         context="sms_sending")
            
        except Exception as e:
            self.handle_error(e, context="sms_sending", raise_error=True)
    
    def _can_resend_otp(self, current_attempts: int, last_attempt_time: float) -> bool:
        """
        Check if OTP can be resent based on rate limiting rules.
        
        Args:
            current_attempts (int): Current number of attempts
            last_attempt_time (float): Timestamp of last attempt
            
        Returns:
            bool: True if resend is allowed
        """
        import time
        
        if current_attempts >= self.max_resend_attempts:
            return False
        
        if time.time() - last_attempt_time < self.resend_cooldown:
            return False
            
        return True
    
    def _get_current_timestamp(self) -> float:
        """Get current timestamp for token creation."""
        import time
        return time.time()