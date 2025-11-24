from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, user_logged_in, update_session_auth_hash
from django.contrib.auth.views import LoginView
from django.views.generic import CreateView, TemplateView, FormView
from django.urls import reverse_lazy
from django.db import connection
from django.http import HttpResponseRedirect, JsonResponse
from django.views.decorators.http import require_http_methods
from django.dispatch import receiver
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.core.exceptions import ObjectDoesNotExist
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
import logging
import uuid
import hashlib
import time
from .models import User, UserProfile
from .forms import CustomUserCreationForm, UserProfileForm, CustomPasswordChangeForm, CustomAuthenticationForm
from services.integrations.facilitamovel_gateway import FacilitaMovelGateway
from services.utils.phone_utils import PhoneDevice

logger = logging.getLogger(__name__)

# Create your views here.
class CustomLoginView(LoginView):
    """Custom login view that handles device fingerprinting"""
    template_name = 'metronic/auth/login.html'
    form_class = CustomAuthenticationForm
    redirect_authenticated_user = True

    def get_device_fingerprint(self, request):
        """
        Generate a device fingerprint based on request headers and client info
        """
        # Get various client information
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        accept_language = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
        accept_encoding = request.META.get('HTTP_ACCEPT_ENCODING', '')
        remote_addr = request.META.get('REMOTE_ADDR', '')
        
        # Check if device fingerprint is provided via POST (from JavaScript)
        device_fingerprint_data = request.POST.get('device_fingerprint', '')
        
        if device_fingerprint_data:
            # Use the client-side generated fingerprint
            fingerprint_string = device_fingerprint_data
        else:
            # Fallback to server-side fingerprint generation
            fingerprint_string = f"{user_agent}|{accept_language}|{accept_encoding}|{remote_addr}"
        
        # Create a hash of the fingerprint data
        fingerprint_hash = hashlib.sha256(fingerprint_string.encode()).hexdigest()
        
        # Convert to UUID format for consistency
        try:
            return uuid.UUID(fingerprint_hash[:32])
        except ValueError:
            # If conversion fails, generate a new UUID
            return uuid.uuid4()

    def form_valid(self, form):
        """Handle successful login and update device fingerprint"""
        response = super().form_valid(form)
        
        # Get the logged-in user
        user = form.get_user()
        
        # Generate device fingerprint
        device_fingerprint = self.get_device_fingerprint(self.request)
        
        # Add device fingerprint to user's history
        user.add_device_fingerprint(device_fingerprint)
        
        # Add login IP
        ip_address = self.request.META.get('REMOTE_ADDR')
        if ip_address:
            user.add_login_ip(ip_address)
        
        logger.info(f"User {user.email} logged in with device fingerprint: {device_fingerprint}")
        
        return response

class ProfileView(LoginRequiredMixin, TemplateView):
    """View for user profile pages"""
    login_url = '/accounts/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        return context

class ProfileOverviewView(ProfileView):
    template_name = 'metronic/accounts/profile/overview.html'

class ProfileSettingsView(ProfileView):
    template_name = 'metronic/accounts/profile/settings.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Get or create user profile
        profile, created = UserProfile.objects.get_or_create(user=user)

        # Initialize profile form with user and profile data
        if self.request.method == 'POST' and 'submit_button' in self.request.POST and self.request.POST['submit_button'] == 'profile_details':
            form = UserProfileForm(self.request.POST, self.request.FILES, instance=profile, user=user)
            logger.debug("POST request - profile form initialized with POST data and FILES")
        else:
            form = UserProfileForm(instance=profile, user=user)
            logger.debug("GET request - profile form initialized with instance data")

        # Initialize password change form
        if self.request.method == 'POST' and 'submit_button' in self.request.POST and self.request.POST['submit_button'] == 'password_change':
            password_form = CustomPasswordChangeForm(user=user, data=self.request.POST)
            logger.debug("POST request - password form initialized with POST data")
        else:
            password_form = CustomPasswordChangeForm(user=user)
            logger.debug("GET request - password form initialized")

        context['form'] = form
        context['password_form'] = password_form
        return context

    def post(self, request, *args, **kwargs):
        logger.debug("==== ProfileSettingsView.post ====")
        logger.debug("POST data: %s", request.POST)
        logger.debug("FILES data: %s", request.FILES)
        logger.debug("Is AJAX request: %s", request.headers.get('X-Requested-With') == 'XMLHttpRequest')

        # Get the context data which includes the forms
        context = self.get_context_data(**kwargs)
        form = context['form']
        password_form = context['password_form']

        # Check which submit button was clicked
        submit_button = request.POST.get('submit_button', 'unknown')
        logger.debug("Submit button: %s", submit_button)

        # Add debug information to context
        import json
        debug_info = {
            'post_data': dict(request.POST.items()),
            'files_data': dict((k, v.name) for k, v in request.FILES.items()) if request.FILES else {},
            'submit_button': submit_button,
        }
        context['debug_info'] = json.dumps(debug_info)

        # Handle password change form submission
        if submit_button == 'password_change':
            logger.debug("Processing password change form")
            logger.debug("Password form bound: %s", password_form.is_bound)
            logger.debug("Is AJAX request: %s", request.headers.get('X-Requested-With') == 'XMLHttpRequest')

            if password_form.is_valid():
                logger.debug("Password form is valid")
                try:
                    # Save the new password
                    password_form.save()

                    # Update the session to prevent the user from being logged out
                    update_session_auth_hash(request, request.user)

                    # Add success message
                    messages.success(request, 'Your password was successfully updated!')
                    context['password_success'] = True

                    # Only show the popup for non-AJAX requests
                    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
                        context['show_password_popup'] = True

                    # Update debug info
                    debug_info['status'] = 'success'
                    debug_info['message'] = 'Password updated successfully'
                    context['debug_info'] = json.dumps(debug_info)

                    # If it's an AJAX request, return JSON response
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'status': 'success',
                            'message': 'Your password was successfully updated!'
                        })

                    # Redirect to avoid form resubmission
                    return redirect('accounts:profile_settings')
                except Exception as e:
                    logger.error("Error changing password: %s", e)
                    import traceback
                    logger.error("Traceback: %s", traceback.format_exc())

                    # Add error information to context
                    context['password_error'] = str(e)

                    # Only show the popup for non-AJAX requests
                    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
                        context['show_password_popup'] = True

                    messages.error(request, f'Error changing password: {str(e)}')

                    # Update debug info
                    debug_info['status'] = 'error'
                    debug_info['message'] = f'Error changing password: {str(e)}'
                    debug_info['traceback'] = traceback.format_exc()
                    context['debug_info'] = json.dumps(debug_info)

                    # If it's an AJAX request, return JSON response
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'status': 'error',
                            'message': str(e)
                        })
            else:
                logger.debug("Password form is invalid")
                logger.debug("Password form errors: %s", password_form.errors)

                # Add error information to context
                context['password_form_errors'] = password_form.errors

                # Only show the popup for non-AJAX requests
                if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
                    context['show_password_popup'] = True

                # Update debug info
                debug_info['status'] = 'invalid'
                debug_info['message'] = 'Password form validation failed'
                debug_info['password_form_errors'] = dict((k, list(v)) for k, v in password_form.errors.items())
                context['debug_info'] = json.dumps(debug_info)

                # If it's an AJAX request, return JSON response
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'status': 'invalid',
                        'message': 'Password form validation failed',
                        'errors': dict((k, list(v)) for k, v in password_form.errors.items())
                    })

        # Handle profile form submission
        elif submit_button == 'profile_details':
            logger.debug("Processing profile form")
            logger.debug("Form instance: %s", form.instance)
            logger.debug("Form initial: %s", form.initial)
            logger.debug("Form bound: %s", form.is_bound)
            logger.debug("Form data: %s", form.data)

            # Add more detailed logging
            logger.debug("Form data keys: %s", form.data.keys())
            logger.debug("Form files: %s", request.FILES)
            logger.debug("Form prefix: %s", form.prefix)
            logger.debug("Form fields: %s", form.fields.keys())

            if form.is_valid():
                logger.debug("Form is valid")
                logger.debug("Form cleaned_data: %s", form.cleaned_data)

                try:
                    # Save the form data
                    profile = form.save(user=request.user)
                    logger.debug("Profile saved successfully: %s", profile)

                    # Add success message to context
                    context['success'] = True
                    messages.success(request, 'Profile updated successfully!')

                    # Update debug info
                    debug_info['status'] = 'success'
                    debug_info['message'] = 'Profile saved successfully'
                    context['debug_info'] = json.dumps(debug_info)

                    # If it's an AJAX request, return JSON response
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'status': 'success',
                            'message': 'Your profile has been updated successfully!'
                        })

                    # Otherwise, redirect to the same page to avoid form resubmission
                    return redirect('accounts:profile_settings')
                except Exception as e:
                    logger.error("Error saving form: %s", e)
                    import traceback
                    logger.error("Traceback: %s", traceback.format_exc())

                    # Add error information to context
                    context['error'] = str(e)
                    messages.error(request, f'Error updating profile: {str(e)}')

                    # Update debug info
                    debug_info['status'] = 'error'
                    debug_info['message'] = f'Error saving form: {str(e)}'
                    debug_info['traceback'] = traceback.format_exc()
                    context['debug_info'] = json.dumps(debug_info)

                    # If it's an AJAX request, return JSON response
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'status': 'error',
                            'message': f'Error updating profile: {str(e)}'
                        })
            else:
                logger.debug("Form is invalid")
                logger.debug("Form errors: %s", form.errors)
                logger.debug("Form non_field_errors: %s", form.non_field_errors())

                # Add error information to context
                context['form_errors'] = form.errors

                # Update debug info
                debug_info['status'] = 'invalid'
                debug_info['message'] = 'Form validation failed'
                debug_info['form_errors'] = dict((k, list(v)) for k, v in form.errors.items())
                debug_info['non_field_errors'] = list(form.non_field_errors())
                context['debug_info'] = json.dumps(debug_info)

                # If it's an AJAX request, return JSON response
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'status': 'invalid',
                        'message': 'Form validation failed',
                        'errors': dict((k, list(v)) for k, v in form.errors.items())
                    })

        # Return the response
        return self.render_to_response(context)

class ProfileSecurityView(ProfileView):
    template_name = 'metronic/accounts/profile/security.html'

class ProfileActivityView(ProfileView):
    template_name = 'metronic/accounts/profile/activity.html'

class ProfileBillingView(ProfileView):
    template_name = 'metronic/accounts/profile/billing.html'

class ProfileStatementsView(ProfileView):
    template_name = 'metronic/accounts/profile/statements.html'

class ProfileReferralsView(ProfileView):
    template_name = 'metronic/accounts/profile/referrals.html'

class ProfileApiKeysView(ProfileView):
    template_name = 'metronic/accounts/profile/api-keys.html'

class ProfileLogsView(ProfileView):
    template_name = 'metronic/accounts/profile/logs.html'

class ProfilePropertiesView(ProfileView):
    template_name = 'metronic/accounts/profile/properties.html'

class RegisterView(CreateView):
    template_name = 'metronic/auth/sign-up.html'
    form_class = CustomUserCreationForm
    success_url = reverse_lazy('apps.portal:dashboard')

    def get_device_fingerprint(self, request):
        """
        Generate a device fingerprint based on request headers and client info
        """
        # Get various client information
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        accept_language = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
        accept_encoding = request.META.get('HTTP_ACCEPT_ENCODING', '')
        remote_addr = request.META.get('REMOTE_ADDR', '')
        
        # Check if device fingerprint is provided via POST (from JavaScript)
        device_fingerprint_data = request.POST.get('device_fingerprint', '')
        
        if device_fingerprint_data:
            # Use the client-side generated fingerprint
            fingerprint_string = device_fingerprint_data
        else:
            # Fallback to server-side fingerprint generation
            fingerprint_string = f"{user_agent}|{accept_language}|{accept_encoding}|{remote_addr}"
        
        # Create a hash of the fingerprint data
        fingerprint_hash = hashlib.sha256(fingerprint_string.encode()).hexdigest()
        
        # Convert to UUID format for consistency
        try:
            return uuid.UUID(fingerprint_hash[:32])
        except ValueError:
            # If conversion fails, generate a new UUID
            return uuid.uuid4()

    def form_valid(self, form):
        # Don't save the form yet, we need to set the role first
        user = form.save(commit=False)
        # Get the account type from the form data
        account_type = self.request.POST.get('account_type', 'unit')

        # Set the appropriate role based on account_type
        if account_type == 'manager':
            user.role = User.Role.BUILDING_ADMIN  # Building manager is the building_admin
        else:
            user.role = User.Role.UNIT_USER

        # Set username to email to avoid any database constraints
        user.username = user.email
        
        # Now save the user - Django ORM will automatically generate UUID
        user.save()

        # Get the user object (already saved above)
        # user is already the correct User object
        
        # Generate and add device fingerprint
        device_fingerprint = self.get_device_fingerprint(self.request)
        user.add_device_fingerprint(device_fingerprint)
        
        # Add login IP
        ip_address = self.request.META.get('REMOTE_ADDR')
        if ip_address:
            user.add_login_ip(ip_address)
        
        logger.info(f"User {user.email} registered with device fingerprint: {device_fingerprint}")
        
        login(self.request, user)

        return redirect(self.success_url)


class SignupView(FormView):
    """
    Phone-based registration view with OTP verification
    """
    template_name = 'metronic/auth/sign-up.html'
    form_class = CustomUserCreationForm
    success_url = reverse_lazy('accounts:phone_verify')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from services.business.phone_verification_service import PhoneVerificationService
        self.phone_service = PhoneVerificationService()

    def form_valid(self, form):
        # Create user but set as inactive until phone verification
        user = form.save(commit=False)
        user.is_active = False
        user.username = str(form.cleaned_data['phone_number'])  # Set username to phone number
        user.save()

        # Use phone verification service to handle OTP workflow
        phone_number = str(form.cleaned_data['phone_number'])
        result = self.phone_service.initiate_phone_verification(user, phone_number)
        
        if result['success']:
            # Store secure session data for verification
            session_data = result['session_data']
            self.request.session['verification_token'] = session_data['verification_token']
            self.request.session['signup_user_id'] = session_data['user_id']
            self.request.session['signup_device_id'] = session_data['device_id']
            self.request.session['phone_number'] = session_data['phone_number']
            
            messages.success(self.request, result['message'])
            logger.info(f"Phone verification initiated for user {user.id}")
            
        else:
            # Service handles cleanup internally
            user.delete()  # Remove the user since verification failed
            messages.error(self.request, result['error'])
            logger.error(f"Phone verification initiation failed for user {user.id}")
            return self.form_invalid(form)

        return super().form_valid(form)


@method_decorator(never_cache, name='dispatch')
class PhoneVerifyView(FormView):
    """
    Phone verification view that handles OTP verification and auto-login
    """
    template_name = 'metronic/auth/phone-verify.html'
    success_url = reverse_lazy('apps.portal:dashboard')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from services.business.phone_verification_service import PhoneVerificationService
        self.phone_service = PhoneVerificationService()
    
    def dispatch(self, request, *args, **kwargs):
        # Check if we have the required session data
        if not all([
            request.session.get('signup_user_id'),
            request.session.get('signup_device_id'),
            request.session.get('phone_number'),
            request.session.get('verification_token')
        ]):
            messages.error(request, 'Sessão expirada. Por favor, registre-se novamente.')
            return redirect('accounts:signup')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['phone_number'] = self.request.session.get('phone_number')
        context['can_resend'] = self._can_resend_otp()
        return context
    
    def get_form(self, form_class=None):
        """Return an instance of the form to be used in this view."""
        from django import forms
        
        class OTPForm(forms.Form):
            otp = forms.CharField(
                max_length=6,
                min_length=6,
                widget=forms.TextInput(attrs={
                    'class': 'form-control form-control-lg',
                    'placeholder': 'Digite o código de 6 dígitos',
                    'autocomplete': 'one-time-code',
                    'inputmode': 'numeric',
                    'pattern': '[0-9]{6}'
                }),
                label='Código de Verificação'
            )
        
        return OTPForm(**self.get_form_kwargs())
    
    def form_valid(self, form):
        otp_code = form.cleaned_data['otp']
        
        # Get session data
        user_id = self.request.session.get('signup_user_id')
        device_id = self.request.session.get('signup_device_id')
        
        # Use phone verification service for OTP verification
        result = self.phone_service.verify_otp_token(user_id, device_id, otp_code)
        
        if result['success']:
            # Auto-login the verified user
            user = result['user']
            login(self.request, user)
            
            # Clear session data
            self._clear_session_data()
            
            messages.success(self.request, result['message'])
            logger.info(f"Phone verification completed for user {user.id}")
            
            return redirect(self.success_url)
        else:
            # Handle verification failure
            if 'Sessão expirada' in result['error']:
                messages.error(self.request, result['error'])
                return redirect('accounts:signup')
            else:
                form.add_error('otp', result['error'])
                return self.form_invalid(form)
    
    def _can_resend_otp(self):
        """Check if user can resend OTP (rate limiting)"""
        resend_count = self.request.session.get('otp_resend_count', 0)
        last_resend_time = self.request.session.get('last_otp_resend_time', 0)
        return resend_count < 3 and (time.time() - last_resend_time >= 60)
    
    def post(self, request, *args, **kwargs):
        # Handle resend OTP request
        if 'resend_otp' in request.POST:
            return self._resend_otp()
        
        # Handle normal form submission
        return super().post(request, *args, **kwargs)
    
    def _resend_otp(self):
        """Resend OTP using phone verification service"""
        # Get session data for rate limiting
        current_attempts = self.request.session.get('otp_resend_count', 0)
        last_attempt_time = self.request.session.get('last_otp_resend_time', 0)
        
        user_id = self.request.session.get('signup_user_id')
        device_id = self.request.session.get('signup_device_id')
        phone_number = self.request.session.get('phone_number')
        
        # Use phone verification service for resending
        result = self.phone_service.resend_otp_token(
            user_id, device_id, phone_number, current_attempts, last_attempt_time
        )
        
        if result['success']:
            # Update session rate limiting data
            self.request.session['otp_resend_count'] = current_attempts + 1
            self.request.session['last_otp_resend_time'] = time.time()
            messages.success(self.request, result['message'])
            logger.info(f"OTP resent for user {user_id}")
        else:
            messages.error(self.request, result['error'])
            logger.warning(f"OTP resend failed for user {user_id}")
        
        return redirect('accounts:phone_verify')
    
    def _clear_session_data(self):
        """Clear all phone verification session data"""
        session_keys = [
            'signup_user_id', 'signup_device_id', 'phone_number',
            'verification_token', 'otp_resend_count', 'last_otp_resend_time'
        ]
        for key in session_keys:
            self.request.session.pop(key, None)


@require_http_methods(["GET"])
def custom_logout(request):
    """
    Custom logout view that ensures proper session termination.
    """
    # Explicitly log out the user
    logout(request)

    # Clear session data
    request.session.flush()

    # Create response for redirect
    response = HttpResponseRedirect('/')

    # Delete session cookie
    response.delete_cookie('sessionid')

    # Delete any other cookies that might be causing issues
    response.delete_cookie('csrftoken')

    return response


@receiver(user_logged_in)
def user_logged_in_handler(sender, request, user, **kwargs):
    """
    Signal handler to capture the IP address when a user logs in
    and add it to their login history.
    """
    # Get the IP address from the request
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')

    # Add the IP to the user's login history
    user.add_login_ip(ip)
