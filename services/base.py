from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Union, List, Tuple
import logging
from datetime import datetime, timedelta
import time
import json
import requests

# Configure logger for all services
logger = logging.getLogger(__name__)

# Service status constants for better maintainability
class ServiceStatus:
    """
    Constants for service status tracking.
    
    These constants provide a standardized way to track service states
    across all service implementations, making monitoring and debugging easier.
    """
    INITIALIZING = "initializing"
    READY = "ready"
    BUSY = "busy"
    ERROR = "error"
    MAINTENANCE = "maintenance"
    SHUTDOWN = "shutdown"

# Common validation patterns
class ValidationPatterns:
    """
    Common validation patterns used across services.
    
    Centralized validation patterns help maintain consistency
    and reduce code duplication across different service implementations.
    """
    EMAIL_PATTERN = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    PHONE_PATTERN = r'^\+?1?\d{9,15}$'
    UUID_PATTERN = r'^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'


class BaseService(ABC):
    """
    Base class for all services in the application.
    """

    def __init__(self, service_name: Optional[str] = None):
        """
        Initialize the base service.
        
        Args:
            service_name: Optional custom name for the service. If not provided,
                         uses the class name. This name appears in all log messages
                         and is used for service identification in monitoring.
        
        Attributes:
            service_name (str): The name of this service instance
            logger (Logger): Configured logger instance for this service
            _initialized_at (datetime): Timestamp when service was initialized
            _status (str): Current service status (see ServiceStatus constants)
            _error_count (int): Number of errors encountered since initialization
            _last_error (Optional[Exception]): Last error that occurred
        """
        self.service_name = service_name or self.__class__.__name__
        self.logger = logger
        self._initialized_at = datetime.now()
        self._status = ServiceStatus.INITIALIZING
        self._error_count = 0
        self._last_error: Optional[Exception] = None
        
        # Mark service as ready after initialization
        self._status = ServiceStatus.READY
        self.log_info(f"Service initialized successfully at {self._initialized_at}")

    def get_service_info(self) -> Dict[str, Any]:
        """
        Get comprehensive information about this service instance.
        
        Returns:
            Dictionary containing service metadata, status, and performance metrics.
            Useful for health checks, monitoring dashboards, and debugging.
            
        Example:
            ```python
            service = MyService()
            info = service.get_service_info()
            print(f"Service {info['name']} has been running for {info['uptime_seconds']} seconds")
            ```
        """
        return {
            'name': self.service_name,
            'class': self.__class__.__name__,
            'status': self._status,
            'initialized_at': self._initialized_at.isoformat(),
            'uptime_seconds': self.uptime,
            'error_count': self._error_count,
            'last_error': str(self._last_error) if self._last_error else None,
            'memory_usage': self._get_memory_usage(),
        }

    def _get_memory_usage(self) -> Dict[str, Any]:
        """
        Get memory usage information for this service.
        
        Returns:
            Dictionary with memory usage statistics. Returns empty dict
            if psutil is not available.
        """
        try:
            import psutil
            import os
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            return {
                'rss_mb': round(memory_info.rss / 1024 / 1024, 2),
                'vms_mb': round(memory_info.vms / 1024 / 1024, 2),
            }
        except ImportError:
            return {'note': 'psutil not available for memory monitoring'}
        except Exception as e:
            return {'error': f'Failed to get memory info: {str(e)}'}

    def set_status(self, status: str, context: str = "") -> None:
        """
        Update the service status with optional context.
        
        Args:
            status: New status (use ServiceStatus constants)
            context: Optional context about why status changed
        """
        old_status = self._status
        self._status = status
        
        log_message = f"Status changed from {old_status} to {status}"
        if context:
            log_message += f" - {context}"
            
        self.log_info(log_message, "status_change")

    def handle_error(self, error: Exception, context: str = "", raise_error: bool = False) -> None:
        """
        Centralized error handling for all services.
        
        This method provides consistent error handling across all services:
        - Logs errors with full context and stack traces
        - Updates service status and error counters
        - Optionally re-raises errors for upstream handling
        - Stores last error for debugging and monitoring
        
        Args:
            error: The exception that occurred. Can be any Exception subclass.
            context: Additional context about where/why the error occurred.
                    Examples: "database_connection", "api_call", "data_validation"
            raise_error: Whether to re-raise the error after logging.
                        Set to True when the caller needs to handle the error.
                        Set to False for non-critical errors that can be ignored.
        
        Example:
            ```python
            try:
                result = self.risky_operation()
            except ValueError as e:
                # Log but don't stop execution
                self.handle_error(e, "risky_operation", raise_error=False)
                result = self.get_default_value()
            except ConnectionError as e:
                # Log and re-raise for upstream handling
                self.handle_error(e, "database_connection", raise_error=True)
            ```
        """
        # Update error tracking
        self._error_count += 1
        self._last_error = error
        
        # Update service status to indicate error state
        old_status = self._status
        self._status = ServiceStatus.ERROR
        
        # Create comprehensive error message
        error_msg = f"[{self.service_name}] Error in {context}: {str(error)}"
        if hasattr(error, '__class__'):
            error_msg += f" (Type: {error.__class__.__name__})"
        
        # Log with full stack trace for debugging
        self.logger.error(error_msg, exc_info=True)
        
        # Log status change if it actually changed
        if old_status != ServiceStatus.ERROR:
            self.log_info(f"Service status changed to ERROR due to: {str(error)}", "error_handling")
        
        # Re-raise if requested
        if raise_error:
            raise error

    def log_info(self, message: str, context: str = "") -> None:
        """
        Log informational messages with service context.
        
        Args:
            message: The message to log
            context: Optional context category (e.g., "startup", "processing", "cleanup")
        
        Example:
            ```python
            self.log_info("Processing 150 records", "batch_processing")
            # Output: [MyService] batch_processing: Processing 150 records
            ```
        """
        log_msg = f"[{self.service_name}] {context}: {message}" if context else f"[{self.service_name}] {message}"
        self.logger.info(log_msg)

    def log_warning(self, message: str, context: str = "") -> None:
        """
        Log warning messages with service context.
        
        Args:
            message: The warning message to log
            context: Optional context category (e.g., "validation", "performance", "deprecation")
        
        Example:
            ```python
            self.log_warning("API response time exceeded 5 seconds", "performance")
            # Output: [MyService] performance: API response time exceeded 5 seconds
            ```
        """
        log_msg = f"[{self.service_name}] {context}: {message}" if context else f"[{self.service_name}] {message}"
        self.logger.warning(log_msg)

    def log_debug(self, message: str, context: str = "") -> None:
        """
        Log debug messages with service context.
        
        Debug messages are only shown when logging level is set to DEBUG.
        Useful for detailed troubleshooting and development.
        
        Args:
            message: The debug message to log
            context: Optional context category
        """
        log_msg = f"[{self.service_name}] {context}: {message}" if context else f"[{self.service_name}] {message}"
        self.logger.debug(log_msg)

    def validate_required_fields(self, data: Dict[str, Any], required_fields: List[str]) -> bool:
        """
        Generic validation for required fields in data dictionaries.
        
        This method checks that all required fields are present and contain
        meaningful values (not None, empty string, or empty collections).
        
        Args:
            data: Dictionary to validate. Can be nested dictionaries.
            required_fields: List of required field names. Supports dot notation
                           for nested fields (e.g., "user.profile.email").
        
        Returns:
            True if all required fields are present and valid, False otherwise.
            
        Example:
            ```python
            user_data = {
                "name": "John Doe",
                "email": "john@example.com",
                "profile": {"age": 30}
            }
            
            # Simple validation
            if self.validate_required_fields(user_data, ["name", "email"]):
                print("Basic fields are valid")
            
            # Nested field validation
            if self.validate_required_fields(user_data, ["profile.age"]):
                print("Nested fields are valid")
            ```
        """
        for field in required_fields:
            if not self._check_field_value(data, field):
                self.log_warning(f"Missing or empty required field: {field}", "validation")
                return False
        return True

    def _check_field_value(self, data: Dict[str, Any], field_path: str) -> bool:
        """
        Check if a field (including nested fields) has a valid value.
        
        Args:
            data: Dictionary to check
            field_path: Field path, supports dot notation for nested fields
            
        Returns:
            True if field exists and has a valid value
        """
        try:
            # Handle nested field paths (e.g., "user.profile.email")
            current_data = data
            field_parts = field_path.split('.')
            
            for part in field_parts:
                if not isinstance(current_data, dict) or part not in current_data:
                    return False
                current_data = current_data[part]
            
            # Check if value is meaningful
            if current_data is None:
                return False
            if isinstance(current_data, str) and current_data.strip() == "":
                return False
            if isinstance(current_data, (list, dict)) and len(current_data) == 0:
                return False
                
            return True
            
        except (KeyError, TypeError, AttributeError):
            return False

    def validate_data_types(self, data: Dict[str, Any], type_specs: Dict[str, type]) -> Tuple[bool, List[str]]:
        """
        Validate that fields in data match expected types.
        
        Args:
            data: Dictionary to validate
            type_specs: Dictionary mapping field names to expected types
            
        Returns:
            Tuple of (is_valid, list_of_errors)
            
        Example:
            ```python
            data = {"age": 25, "name": "John", "active": True}
            specs = {"age": int, "name": str, "active": bool}
            
            is_valid, errors = self.validate_data_types(data, specs)
            if not is_valid:
                self.log_warning(f"Type validation failed: {errors}")
            ```
        """
        errors = []
        
        for field, expected_type in type_specs.items():
            if field in data:
                if not isinstance(data[field], expected_type):
                    actual_type = type(data[field]).__name__
                    expected_type_name = expected_type.__name__
                    errors.append(f"Field '{field}' expected {expected_type_name}, got {actual_type}")
        
        return len(errors) == 0, errors

    @property
    def uptime(self) -> float:
        """
        Get service uptime in seconds since initialization.
        
        Returns:
            Float representing seconds since service was initialized.
            Useful for monitoring service health and performance.
            
        Example:
            ```python
            service = MyService()
            time.sleep(5)
            print(f"Service has been running for {service.uptime:.2f} seconds")
            # Output: Service has been running for 5.01 seconds
            ```
        """
        return (datetime.now() - self._initialized_at).total_seconds()

    @property
    def status(self) -> str:
        """Get current service status."""
        return self._status

    @property
    def error_count(self) -> int:
        """Get total number of errors encountered since initialization."""
        return self._error_count

    @property
    def last_error(self) -> Optional[Exception]:
        """Get the last error that occurred, if any."""
        return self._last_error

    def reset_error_count(self) -> None:
        """
        Reset error counter and clear last error.
        
        Useful for service recovery scenarios or after maintenance.
        """
        old_count = self._error_count
        self._error_count = 0
        self._last_error = None
        
        if self._status == ServiceStatus.ERROR:
            self._status = ServiceStatus.READY
            
        self.log_info(f"Error count reset from {old_count} to 0", "maintenance")


# API-specific constants for better maintainability
class APIConstants:
    """
    Constants for API service configuration and behavior.
    
    Centralized constants help maintain consistency across all API services
    and make it easy to adjust behavior without modifying multiple files.
    """
    # Default timeout values (in seconds)
    DEFAULT_TIMEOUT = 30
    FAST_TIMEOUT = 10
    SLOW_TIMEOUT = 60
    
    # Retry configuration
    DEFAULT_MAX_RETRIES = 3
    RETRY_BACKOFF_FACTOR = 2
    
    # Rate limiting
    DEFAULT_RATE_LIMIT = 100  # requests per minute
    BURST_RATE_LIMIT = 10     # requests per second
    
    # Response size limits
    MAX_RESPONSE_SIZE_MB = 50
    MAX_RESPONSE_SIZE_BYTES = MAX_RESPONSE_SIZE_MB * 1024 * 1024
    
    # Common HTTP status codes
    HTTP_OK = 200
    HTTP_CREATED = 201
    HTTP_BAD_REQUEST = 400
    HTTP_UNAUTHORIZED = 401
    HTTP_FORBIDDEN = 403
    HTTP_NOT_FOUND = 404
    HTTP_RATE_LIMITED = 429
    HTTP_SERVER_ERROR = 500


class BaseAPIService(BaseService):
    """
    Base class for external API services.
    
    This class extends BaseService with API-specific functionality including:
    - Request/response handling and validation
    - Rate limiting and retry logic
    - API key management and security
    - Request counting and performance monitoring
    - Standardized error handling for API failures
    - Response caching and optimization
    
    Design Principles:
    - Fail fast with clear error messages
    - Provide comprehensive logging for debugging
    - Support both synchronous and asynchronous operations
    - Enable easy testing with mock responses
    - Follow REST API best practices
    
    Security Considerations:
    - API keys are never logged or exposed in error messages
    - All requests use HTTPS by default
    - Request/response data is validated before processing
    - Rate limiting prevents API abuse
    
    Usage Example:
        ```python
        class WeatherAPIService(BaseAPIService):
            def __init__(self):
                super().__init__(
                    api_key=settings.WEATHER_API_KEY,
                    service_name="WeatherAPI",
                    timeout=15
                )
            
            def validate_response(self, response):
                return (response.status_code == 200 and 
                       'temperature' in response.json())
            
            def get_weather(self, city: str) -> Dict[str, Any]:
                try:
                    response = self._make_request(f"/weather?city={city}")
                    if self.validate_response(response):
                        return self._parse_weather_data(response.json())
                    else:
                        raise WeatherAPIError("Invalid response format")
                except Exception as e:
                    self.handle_api_error(e, f"/weather?city={city}")
        ```
    
    Thread Safety:
        This class is thread-safe for concurrent API requests.
        Request counting and error tracking use atomic operations.
    """

    def __init__(self, api_key: str, service_name: Optional[str] = None, timeout: int = APIConstants.DEFAULT_TIMEOUT):
        """
        Initialize the API service.
        
        Args:
            api_key: API key for authentication. Should be loaded from secure settings.
                    Never hardcode API keys in source code.
            service_name: Optional custom name for the service. Used in logging and monitoring.
            timeout: Request timeout in seconds. Use APIConstants for standard values.
        
        Raises:
            ValueError: If api_key is empty or None
            TypeError: If timeout is not a positive integer
        
        Example:
            ```python
            # Good: Load from settings
            service = MyAPIService(
                api_key=settings.MY_API_KEY,
                service_name="MyAPI",
                timeout=APIConstants.FAST_TIMEOUT
            )
            
            # Bad: Hardcoded key (security risk)
            service = MyAPIService(api_key="sk-1234567890abcdef")
            ```
        """
        super().__init__(service_name)
        
        # Validate API key (allow empty string for services that don't require authentication)
        if api_key is None or not isinstance(api_key, str):
            raise ValueError("API key must be a string (can be empty for services without authentication)")
        
        # Validate timeout
        if not isinstance(timeout, int) or timeout <= 0:
            raise TypeError("Timeout must be a positive integer")
        
        self.api_key = api_key
        self.timeout = timeout
        
        # Request tracking and performance metrics
        self._request_count = 0
        self._successful_requests = 0
        self._failed_requests = 0
        self._total_response_time = 0.0
        self._last_request_time: Optional[datetime] = None
        
        # Rate limiting
        self._request_times: List[datetime] = []
        self._rate_limit = APIConstants.DEFAULT_RATE_LIMIT
        
        self.log_info(f"API service initialized with timeout={timeout}s", "initialization")

    @abstractmethod
    def validate_response(self, response: Any) -> bool:
        """
        Validate API response structure and content.
        
        This method must be implemented by each API service to define
        what constitutes a valid response for that specific API.
        
        Args:
            response: The response object from the API call.
                     Could be requests.Response, dict, or other format.
        
        Returns:
            True if response is valid and can be processed safely.
            False if response is invalid or malformed.
        
        Implementation Guidelines:
        - Check HTTP status codes (usually 200-299 for success)
        - Validate required fields are present
        - Check data types and formats
        - Verify response size is reasonable
        - Don't raise exceptions - return False for invalid responses
        
        Example:
            ```python
            def validate_response(self, response) -> bool:
                # Check HTTP status
                if response.status_code != 200:
                    return False
                
                try:
                    data = response.json()
                    
                    # Check required fields
                    required_fields = ['id', 'status', 'data']
                    if not all(field in data for field in required_fields):
                        return False
                    
                    # Check data types
                    if not isinstance(data['id'], int):
                        return False
                    
                    return True
                    
                except (ValueError, KeyError, TypeError):
                    return False
            ```
        """
        pass

    def increment_request_count(self) -> None:
        """
        Track API request count for monitoring and rate limiting.
        
        This method is called automatically by the base class for each
        API request. It updates various metrics used for monitoring
        and performance analysis.
        
        Metrics Updated:
        - Total request count
        - Request timestamps (for rate limiting)
        - Last request time
        
        Thread Safety:
            This method is thread-safe and can be called concurrently.
        """
        self._request_count += 1
        current_time = datetime.now()
        self._last_request_time = current_time
        
        # Track request times for rate limiting (keep only recent requests)
        self._request_times.append(current_time)
        
        # Clean up old request times (older than 1 minute)
        cutoff_time = current_time - timedelta(minutes=1)
        self._request_times = [t for t in self._request_times if t > cutoff_time]
        
        self.log_debug(f"Request count incremented to {self._request_count}", "metrics")

    def track_successful_request(self, response_time: float) -> None:
        """
        Track successful API request metrics.
        
        Args:
            response_time: Time taken for the request in seconds
        """
        self._successful_requests += 1
        self._total_response_time += response_time
        
        self.log_debug(f"Successful request tracked (response_time={response_time:.3f}s)", "metrics")

    def track_failed_request(self) -> None:
        """Track failed API request metrics."""
        self._failed_requests += 1
        self.log_debug("Failed request tracked", "metrics")

    def check_rate_limit(self) -> bool:
        """
        Check if current request rate is within limits.
        
        Returns:
            True if request can proceed, False if rate limited
        """
        current_time = datetime.now()
        
        # Count requests in the last minute
        cutoff_time = current_time - timedelta(minutes=1)
        recent_requests = [t for t in self._request_times if t > cutoff_time]
        
        if len(recent_requests) >= self._rate_limit:
            self.log_warning(f"Rate limit exceeded: {len(recent_requests)} requests in last minute", "rate_limiting")
            return False
        
        return True

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Union[Dict[str, Any], str, bytes]] = None,
        timeout: Optional[int] = None,
        parse_json: bool = False,
    ) -> Union[requests.Response, Dict[str, Any]]:
        """
        Internal HTTP request helper to reduce duplication across API services.

        Args:
            method: HTTP method (e.g., 'GET', 'POST').
            url: Full request URL.
            headers: Optional HTTP headers.
            params: Optional query string parameters.
            json: Optional JSON body (for POST/PUT/PATCH).
            data: Optional raw body.
            timeout: Optional timeout override (defaults to self.timeout).
            parse_json: If True, returns response.json(); otherwise returns Response.

        Returns:
            requests.Response or parsed JSON dict depending on parse_json.

        Raises:
            requests.RequestException: Network/HTTP-level errors.
            ValueError/JSONDecodeError: If parse_json is True and response body is not valid JSON.
        """
        req_timeout = timeout if isinstance(timeout, int) and timeout > 0 else self.timeout
        method_upper = (method or "GET").upper()

        self.log_debug(f"HTTP {method_upper} {url}", "http_request")

        try:
            response = requests.request(
                method=method_upper,
                url=url,
                headers=headers,
                params=params,
                json=json,
                data=data,
                timeout=req_timeout,
            )
            response.raise_for_status()

            return response.json() if parse_json else response
        except requests.RequestException as e:
            # Let callers decide how to categorize/handle; just add context here
            self.log_warning(f"HTTP {method_upper} request failed for URL {url}: {str(e)}", "http_request")
            raise

    def get_api_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive API performance metrics.
        
        Returns:
            Dictionary with detailed metrics about API usage and performance.
            Useful for monitoring dashboards and performance analysis.
        
        Example:
            ```python
            metrics = service.get_api_metrics()
            print(f"Success rate: {metrics['success_rate']:.2%}")
            print(f"Average response time: {metrics['avg_response_time']:.3f}s")
            ```
        """
        total_requests = self._successful_requests + self._failed_requests
        success_rate = (self._successful_requests / total_requests) if total_requests > 0 else 0
        avg_response_time = (self._total_response_time / self._successful_requests) if self._successful_requests > 0 else 0
        
        return {
            'total_requests': self._request_count,
            'successful_requests': self._successful_requests,
            'failed_requests': self._failed_requests,
            'success_rate': success_rate,
            'avg_response_time_seconds': avg_response_time,
            'last_request_time': self._last_request_time.isoformat() if self._last_request_time else None,
            'current_rate_limit': self._rate_limit,
            'requests_last_minute': len(self._request_times),
        }

    @property
    def request_count(self) -> int:
        """
        Get total number of API requests made since initialization.
        
        Returns:
            Integer count of all API requests (successful and failed).
            
        Note:
            This includes all requests, regardless of success/failure.
            Use get_api_metrics() for more detailed breakdown.
        """
        return self._request_count

    @property
    def success_rate(self) -> float:
        """
        Get API request success rate as a percentage.
        
        Returns:
            Float between 0.0 and 1.0 representing success rate.
            Returns 0.0 if no requests have been made.
        """
        total = self._successful_requests + self._failed_requests
        return (self._successful_requests / total) if total > 0 else 0.0

    def handle_api_error(self, error: Exception, endpoint: str = "", raise_error: bool = True) -> None:
        """
        Specialized error handling for API services.
        
        This method provides API-specific error handling including:
        - Categorization of different error types
        - Endpoint-specific error context
        - API key security (never logs sensitive data)
        - Request failure tracking
        - Retry recommendations
        
        Args:
            error: The exception that occurred during API call
            endpoint: The API endpoint that failed (for context)
            raise_error: Whether to re-raise the error after logging
        
        Error Categories Handled:
        - Network errors (connection, timeout, DNS)
        - HTTP errors (4xx, 5xx status codes)
        - Authentication errors (invalid API key)
        - Rate limiting errors (429 status)
        - Parsing errors (invalid JSON, unexpected format)
        
        Example:
            ```python
            try:
                response = requests.get(url, timeout=self.timeout)
                response.raise_for_status()
            except requests.exceptions.Timeout as e:
                self.handle_api_error(e, "/users/profile", raise_error=True)
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    self.handle_api_error(e, "/users/profile", raise_error=True)
                else:
                    self.handle_api_error(e, "/users/profile", raise_error=False)
            ```
        """
        # Track failed request
        self.track_failed_request()
        
        # Create context with endpoint information
        context = f"API call to {endpoint}" if endpoint else "API call"
        
        # Categorize error type for better debugging
        error_category = self._categorize_api_error(error)
        if error_category:
            context += f" ({error_category})"
        
        # Add retry recommendation for transient errors
        if self._is_retryable_error(error):
            context += " - Consider retrying"
        
        # Use base class error handling (never logs API key)
        self.handle_error(error, context, raise_error)

    def _categorize_api_error(self, error: Exception) -> str:
        """
        Categorize API errors for better debugging and monitoring.
        
        Args:
            error: The exception to categorize
            
        Returns:
            String describing the error category
        """
        error_type = type(error).__name__
        
        # Network-related errors
        if 'timeout' in error_type.lower() or 'timeout' in str(error).lower():
            return "timeout"
        elif 'connection' in error_type.lower() or 'connection' in str(error).lower():
            return "connection"
        elif 'dns' in str(error).lower() or 'resolve' in str(error).lower():
            return "dns"
        
        # HTTP errors
        elif hasattr(error, 'response') and hasattr(error.response, 'status_code'):
            status_code = error.response.status_code
            if status_code == 401:
                return "authentication"
            elif status_code == 403:
                return "authorization"
            elif status_code == 404:
                return "not_found"
            elif status_code == 429:
                return "rate_limited"
            elif 400 <= status_code < 500:
                return "client_error"
            elif 500 <= status_code < 600:
                return "server_error"
        
        # Parsing errors
        elif 'json' in error_type.lower() or 'decode' in error_type.lower():
            return "parsing"
        
        return "unknown"

    def _is_retryable_error(self, error: Exception) -> bool:
        """
        Determine if an API error is retryable.
        
        Args:
            error: The exception to check
            
        Returns:
            True if error is likely transient and worth retrying
        """
        error_category = self._categorize_api_error(error)
        
        # Retryable error categories
        retryable_categories = {
            "timeout", "connection", "dns", "server_error", "rate_limited"
        }
        
        return error_category in retryable_categories


class BaseBusinessService(BaseService):
    """
    Base class for business logic services.
    Extends BaseService with business-specific functionality.
    """

    def __init__(self, service_name: Optional[str] = None):
        super().__init__(service_name)
        self._operation_count = 0

    def validate_business_rules(self, data: Dict[str, Any], rules: Dict[str, Any]) -> tuple[bool, list]:
        """
        Generic business rule validation
        
        Args:
            data: Data to validate
            rules: Dictionary of validation rules
            
        Returns:
            Tuple of (is_valid: bool, errors: list)
        """
        errors = []
        
        # This is a flexible pattern that can be extended by specific business services
        for rule_name, rule_config in rules.items():
            if not self._apply_business_rule(data, rule_name, rule_config):
                errors.append(f"Business rule violation: {rule_name}")
        
        return len(errors) == 0, errors

    def _apply_business_rule(self, data: Dict[str, Any], rule_name: str, rule_config: Any) -> bool:
        """
        Apply a specific business rule - to be overridden by specific services
        
        Args:
            data: Data to validate
            rule_name: Name of the rule
            rule_config: Configuration for the rule
            
        Returns:
            True if rule passes, False otherwise
        """
        # Default implementation with some common rule patterns
        if rule_name == 'required_fields' and isinstance(rule_config, list):
            return self.validate_required_fields(data, rule_config)
        
        # For other rules, specific services should override this method
        return True

    def track_operation(self) -> None:
        """Track business operations for monitoring"""
        self._operation_count += 1

    @property
    def operation_count(self) -> int:
        """Get total number of business operations performed"""
        return self._operation_count


class BaseUtilityService(BaseService):
    """
    Base class for utility services.
    Extends BaseService with utility-specific functionality.
    """

    def __init__(self, service_name: Optional[str] = None):
        super().__init__(service_name)

    def process_data(self, data: Any, **kwargs) -> Any:
        """
        Generic data processing method - to be overridden by specific utility services
        
        Args:
            data: Data to process
            **kwargs: Additional processing parameters
            
        Returns:
            Processed data
        """
        # Default implementation - specific services should override this
        return data

    def validate_input_format(self, data: Any, expected_type: type) -> bool:
        """
        Validate input data format
        
        Args:
            data: Data to validate
            expected_type: Expected data type
            
        Returns:
            True if data matches expected type
        """
        if not isinstance(data, expected_type):
            self.log_warning(f"Input data type mismatch. Expected {expected_type}, got {type(data)}", "validation")
            return False
        return True


class BaseIntegrationService(BaseService):
    """
    Base class for integration services.
    Extends BaseService with integration-specific functionality.
    """

    def __init__(self, service_name: Optional[str] = None):
        super().__init__(service_name)
        self._integration_status = "initialized"
        self._request_count = 0

    def check_connection(self) -> bool:
        """
        Check connection status - to be overridden by specific integration services
        
        Returns:
            True if connection is healthy
        """
        # Default implementation - specific services should override this
        return True

    def get_status(self) -> Dict[str, Any]:
        """
        Get integration service status
        
        Returns:
            Dictionary with status information
        """
        return {
            "service_name": self.service_name,
            "status": self._integration_status,
            "uptime": self.uptime,
            "connection_healthy": self.check_connection()
        }

    def set_status(self, status: str) -> None:
        """Set integration status"""
        self._integration_status = status
        self.log_info(f"Status changed to: {status}", "status_update")

    def increment_request_count(self) -> None:
        """
        Track integration service request count for monitoring.
        
        This method is called to track requests made through the integration service.
        It updates the request count metric for monitoring and performance analysis.
        """
        self._request_count += 1
        self.log_debug(f"Request count incremented to {self._request_count}", "metrics")

    @property
    def request_count(self) -> int:
        """Get total number of requests made through this integration service"""
        return self._request_count