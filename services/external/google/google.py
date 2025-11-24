"""
Google Address Validation API Service with comprehensive validation.

This module provides a robust, production-ready service for integrating with Google's
Address Validation API, offering advanced address validation, geocoding, and
standardization capabilities with comprehensive error handling.
"""

import json
from typing import Dict, Any, Optional, List, Tuple, Union
import time

import requests
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError

from services.base import BaseAPIService, APIConstants


# Google Address Validation API specific constants
class GoogleAddressConstants:
    """
    Constants specific to Google Address Validation API service.
    
    These constants centralize all Google API-specific configuration,
    making it easy to maintain and update service behavior.
    """
    # API Configuration
    BASE_URL = "https://addressvalidation.googleapis.com/v1:validateAddress"
    API_VERSION = "v1"
    
    # Cache Configuration
    DEFAULT_CACHE_EXPIRY_DAYS = 30
    MAX_CACHE_EXPIRY_DAYS = 365
    MIN_CACHE_EXPIRY_DAYS = 1
    
    # Address Input Requirements
    REQUIRED_INPUT_FIELDS = ['regionCode', 'addressLines']
    OPTIONAL_INPUT_FIELDS = ['locality', 'administrativeArea', 'postalCode', 'languageCode']
    
    # Supported Region Codes (focus on Brazil but support others)
    SUPPORTED_REGIONS = ['BR', 'US', 'CA', 'GB', 'AU', 'DE', 'FR', 'IT', 'ES', 'MX', 'AR']
    DEFAULT_REGION_CODE = 'BR'
    
    # Response Structure Keys
    RESPONSE_RESULT_KEY = 'result'
    RESPONSE_ADDRESS_KEY = 'address'
    RESPONSE_VERDICT_KEY = 'verdict'
    RESPONSE_GEOCODE_KEY = 'geocode'
    
    # Verdict Granularity Levels
    GRANULARITY_LEVELS = {
        'GRANULARITY_UNSPECIFIED': 0,
        'SUB_PREMISE': 1,
        'PREMISE': 2,
        'PREMISE_PROXIMITY': 3,
        'BLOCK': 4,
        'ROUTE': 5,
        'OTHER': 6
    }
    
    # Address Quality Thresholds
    HIGH_CONFIDENCE_THRESHOLD = 0.8
    MEDIUM_CONFIDENCE_THRESHOLD = 0.6
    LOW_CONFIDENCE_THRESHOLD = 0.3
    
    # Error messages for better user experience
    ERROR_MESSAGES = {
        'invalid_input': 'Address input must contain regionCode and addressLines',
        'api_key_missing': 'Google API key not found in settings',
        'api_quota_exceeded': 'Google API quota exceeded',
        'invalid_region': 'Unsupported region code',
        'network_error': 'Network connection failed',
        'timeout_error': 'Request timed out',
        'api_error': 'Google Address Validation API error',
        'cache_error': 'Cache operation failed',
        'parsing_error': 'Failed to parse API response',
    }


class GoogleAddressError(Exception):
    """
    Custom exception for Google Address Validation API errors.
    
    This exception provides structured error information for better
    error handling and debugging in applications using the Google Address service.
    
    Attributes:
        message (str): Human-readable error message
        error_code (str): Machine-readable error code
        address_input (dict): The address input that caused the error (if applicable)
        api_response (dict): The raw API response (if available)
        original_error (Exception): The original exception that caused this error
    
    Usage:
        ```python
        try:
            result = service.validate_address(address_data)
        except GoogleAddressError as e:
            print(f"Error: {e.message}")
            print(f"Code: {e.error_code}")
            if e.address_input:
                print(f"Input: {e.address_input}")
        ```
    """
    
    def __init__(self, 
                 message: str, 
                 error_code: str = "unknown", 
                 address_input: Dict[str, Any] = None, 
                 api_response: Dict[str, Any] = None,
                 original_error: Exception = None):
        """
        Initialize Google Address error.
        
        Args:
            message: Human-readable error description
            error_code: Machine-readable error code for programmatic handling
            address_input: The address input that caused the error (optional)
            api_response: The raw API response if available (optional)
            original_error: The underlying exception that caused this error (optional)
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.address_input = address_input
        self.api_response = api_response
        self.original_error = original_error
    
    def __str__(self) -> str:
        """Return formatted error message."""
        parts = [self.message]
        if self.error_code != "unknown":
            parts.append(f"Code: {self.error_code}")
        if self.address_input and 'addressLines' in self.address_input:
            address_preview = ', '.join(self.address_input['addressLines'][:2])
            parts.append(f"Address: {address_preview}")
        return " | ".join(parts)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert error to dictionary for JSON serialization.
        
        Returns:
            Dictionary representation of the error
        """
        return {
            'error': True,
            'message': self.message,
            'error_code': self.error_code,
            'address_input': self.address_input,
            'timestamp': timezone.now().isoformat(),
            'service': 'GoogleAddressValidation'
        }


class GoogleAddressService(BaseAPIService):
    """
    Service for integrating with Google Address Validation API.
    Provides caching functionality with PostgreSQL storage.
    """
    
    BASE_URL = "https://addressvalidation.googleapis.com/v1:validateAddress"
    CACHE_EXPIRY_DAYS = 30
    
    def __init__(self, service_name: Optional[str] = None, timeout: int = 30):
        """
        Initialize Google Address Validation service.
        
        Args:
            service_name: Optional service name for logging
            timeout: Request timeout in seconds
            
        Raises:
            GoogleAddressError: If Google API key is not configured
        """
        api_key = getattr(settings, 'ADD_VAL', None) or getattr(settings, 'GOOGLE_API_KEY', None)
        if not api_key:
            raise GoogleAddressError("Google API key not found in settings. Please set ADD_VAL or GOOGLE_API_KEY.")
        
        super().__init__(api_key=api_key, service_name=service_name or "GoogleAddress", timeout=timeout)
        
        # Try to import Google client library
        self._client = None
        try:
            from google.maps.addressvalidation_v1 import AddressValidationClient
            from google.oauth2 import service_account
            # Note: For production, you'd typically use service account credentials
            # For now, we'll use the API key approach with raw requests
            self._use_client = False
        except ImportError:
            self._use_client = False
            self.log_info("Google Maps client library not available, using raw requests")
    
    def validate_response(self, response: Any) -> bool:
        """
        Validate Google Address Validation API response structure and content.
        
        Args:
            response: Response object from requests or client
            
        Returns:
            True if response is valid, False otherwise
        """
        try:
            if hasattr(response, 'status_code'):
                # Raw requests response
                if response.status_code != 200:
                    return False
                data = response.json()
            else:
                # Assume it's already parsed data
                data = response
            
            # Check for required structure
            if not isinstance(data, dict):
                return False
            
            # Google Address Validation API returns a 'result' key
            if 'result' not in data:
                return False
            
            result = data['result']
            
            # Check for required subkeys in result
            required_keys = ['address', 'verdict']
            if not all(key in result for key in required_keys):
                return False
            
            return True
            
        except (ValueError, json.JSONDecodeError, AttributeError, KeyError):
            return False
    
    def validate_address(self, address_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate address using Google Address Validation API (no caching).
        
        Args:
            address_dict: Dictionary with address information.
                         Must contain 'regionCode': 'BR' and 'addressLines': list of strings
            
        Returns:
            Dictionary with standardized validation results
            
        Raises:
            GoogleAddressError: If address validation fails or API request fails
        """
        # Validate input format
        if not self._validate_input_address(address_dict):
            raise GoogleAddressError("Invalid address format. Must contain 'regionCode' and 'addressLines'.")
        
        # Make API request (cache disabled)
        try:
            if self._use_client and self._client:
                response_data = self._make_client_request(address_dict)
            else:
                response_data = self._make_raw_request(address_dict)
            
            if not self.validate_response(response_data):
                raise GoogleAddressError("Invalid response from Google Address Validation API")
            
            # Increment request count for actual API calls
            self.increment_request_count()
            
            # Parse and standardize response
            standardized_data = self._standardize_response(response_data)
            
            self.log_info("Successfully validated address (no cache).")
            return standardized_data
            
        except requests.RequestException as e:
            error_msg = f"Failed to validate address: {str(e)}"
            self.handle_api_error(GoogleAddressError(error_msg), self.BASE_URL)
            raise GoogleAddressError(error_msg) from e
        except Exception as e:
            error_msg = f"Unexpected error validating address: {str(e)}"
            self.handle_api_error(GoogleAddressError(error_msg), self.BASE_URL)
            raise GoogleAddressError(error_msg) from e
    
    def _make_raw_request(self, address_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make HTTP POST request to Google Address Validation API using raw requests.
        
        Args:
            address_dict: Address dictionary to validate
            
        Returns:
            Response data as dictionary
        """
        url = f"{self.BASE_URL}?key={self.api_key}"
        
        # Prepare request body according to Google API specification
        request_body = {
            "address": {
                "regionCode": address_dict.get("regionCode", "BR"),
                "addressLines": address_dict.get("addressLines", [])
            }
        }
        
        # Add optional fields if present
        if "locality" in address_dict:
            request_body["address"]["locality"] = address_dict["locality"]
        if "administrativeArea" in address_dict:
            request_body["address"]["administrativeArea"] = address_dict["administrativeArea"]
        if "postalCode" in address_dict:
            request_body["address"]["postalCode"] = address_dict["postalCode"]
        
        headers = {
            'Content-Type': 'application/json',
        }
        
        try:
            return self._request(
                "POST",
                url,
                headers=headers,
                json=request_body,
                timeout=self.timeout,
                parse_json=True,
            )
        except requests.RequestException as e:
            self.log_warning(f"Request failed for URL {url}: {str(e)}")
            raise
    
    def _make_client_request(self, address_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make request using Google Maps client library (if available).
        
        Args:
            address_dict: Address dictionary to validate
            
        Returns:
            Response data as dictionary
        """
        # This would be implemented if using the official client library
        # For now, fallback to raw requests
        return self._make_raw_request(address_dict)
    
    def _validate_input_address(self, address_dict: Dict[str, Any]) -> bool:
        """
        Validate input address dictionary format.
        
        Args:
            address_dict: Address dictionary to validate
            
        Returns:
            True if valid format, False otherwise
        """
        if not isinstance(address_dict, dict):
            return False
        
        # Check required fields
        if "regionCode" not in address_dict:
            return False
        
        if "addressLines" not in address_dict:
            return False
        
        if not isinstance(address_dict["addressLines"], list):
            return False
        
        if not address_dict["addressLines"]:
            return False
        
        return True
    
    
    def _standardize_response(self, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert Google API response to standardized format.
        
        Args:
            response_data: Raw response from Google API
            
        Returns:
            Standardized validation result dictionary
        """
        result = response_data.get('result', {})
        address = result.get('address', {})
        verdict = result.get('verdict', {})
        geocode = result.get('geocode', {})
        
        # Extract formatted address
        formatted_address = address.get('formattedAddress', '')
        
        # Extract place ID if available
        place_id = address.get('addressComponents', [{}])[0].get('placeId', '') if address.get('addressComponents') else ''
        
        # Extract coordinates
        location = geocode.get('location', {})
        latitude = location.get('latitude', None)
        longitude = location.get('longitude', None)
        
        # Extract verdict information
        input_granularity = verdict.get('inputGranularity', '')
        validation_granularity = verdict.get('validationGranularity', '')
        geocode_granularity = verdict.get('geocodeGranularity', '')
        address_complete = verdict.get('addressComplete', False)
        has_unconfirmed_components = verdict.get('hasUnconfirmedComponents', False)
        has_inferred_components = verdict.get('hasInferredComponents', False)
        has_replaced_components = verdict.get('hasReplacedComponents', False)
        
        return {
            'formatted_address': formatted_address,
            'place_id': place_id,
            'latitude': latitude,
            'longitude': longitude,
            'verdict': {
                'input_granularity': input_granularity,
                'validation_granularity': validation_granularity,
                'geocode_granularity': geocode_granularity,
                'address_complete': address_complete,
                'has_unconfirmed_components': has_unconfirmed_components,
                'has_inferred_components': has_inferred_components,
                'has_replaced_components': has_replaced_components,
            },
            'raw_response': response_data  # Keep original response for reference
        }
    
    def _get_cached_validation(self, address_hash: str) -> Optional[Dict[str, Any]]:
        """
        Cache disabled for Google API: always return None.
        """
        return None
    
    def _cache_validation(self, address_hash: str, validation_data: Dict[str, Any]) -> None:
        """
        Cache disabled for Google API: no operation.
        """
        return None

# ------------------
# Lightweight mapping helpers for Condo enrichment
# ------------------
from dataclasses import dataclass
from typing import Optional, Dict, Any

from services.utils.geo import geohash_from_latlng


@dataclass
class GooglePlaceData:
    formatted_address: Optional[str] = None
    place_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address_components: Optional[Dict[str, Any]] = None
    place_types: Optional[Any] = None
    location_type: Optional[str] = None
    viewport: Optional[Dict[str, Any]] = None
    plus_code: Optional[str] = None
    url: Optional[str] = None
    confidence: Optional[int] = None  # 0..100
    timezone: Optional[str] = None


def geocode_address(street: str, number: str, city: str, state: str, country: str, postal_code: str) -> GooglePlaceData:
    """Geocode using Google Address Validation service as proxy.

    This constructs a BR addressLines payload and parses the standardized response.
    """
    service = GoogleAddressService()
    address_lines = []
    line1 = ", ".join([p for p in [street or "", number or ""] if p])
    if line1:
        address_lines.append(line1)
    locality_line = ", ".join([p for p in [city or "", state or ""] if p])
    if locality_line:
        address_lines.append(locality_line)
    payload = {
        "regionCode": (country or "BR") or "BR",
        "addressLines": address_lines or [street or ""],
    }
    if postal_code:
        payload["postalCode"] = postal_code
    result = service.validate_address(payload)
    gp = GooglePlaceData(
        formatted_address=result.get('formatted_address'),
        place_id=result.get('place_id'),
        latitude=result.get('latitude'),
        longitude=result.get('longitude'),
        address_components=result.get('raw_response', {}).get('result', {}).get('address', {}).get('addressComponents'),
        # No direct place types/location type in Address Validation; leave None
    )
    return gp


def fetch_by_place_id(place_id: str) -> GooglePlaceData:
    """Fetch by place_id. Not supported via Address Validation; placeholder.

    In a full implementation, use Places Details API. Here we return a minimal structure.
    """
    # Placeholder to satisfy interface; a real implementation would call Places API.
    return GooglePlaceData(place_id=place_id)


def map_google_to_condo(condo, data: GooglePlaceData) -> None:
    """Map GooglePlaceData to Condo instance (in-place, no save)."""
    if data.formatted_address:
        condo.gmaps_formatted_address = data.formatted_address
    if data.place_id:
        condo.google_place_id = data.place_id
    if data.latitude is not None:
        condo.lat = data.latitude
    if data.longitude is not None:
        condo.lng = data.longitude
    if data.address_components is not None:
        condo.gmaps_address_components = data.address_components
    if data.place_types is not None:
        condo.gmaps_place_types = data.place_types
    if data.location_type is not None:
        condo.gmaps_location_type = data.location_type
    if data.viewport is not None:
        condo.gmaps_viewport = data.viewport
    if data.plus_code is not None:
        condo.gmaps_plus_code = data.plus_code
    if data.url is not None:
        condo.gmaps_url = data.url
    if data.confidence is not None:
        condo.geocode_confidence = int(data.confidence)
    if data.timezone is not None:
        condo.timezone = data.timezone
    # If lat/lng were set, compute geohash if missing
    if condo.lat is not None and condo.lng is not None and not condo.geohash:
        try:
            condo.geohash = geohash_from_latlng(float(condo.lat), float(condo.lng), precision=10)
        except Exception:
            pass
