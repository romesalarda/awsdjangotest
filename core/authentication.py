"""
Custom JWT Authentication class that reads tokens from HTTPOnly cookies
instead of the Authorization header.
"""

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed
from rest_framework.authentication import CSRFCheck
from rest_framework import exceptions


class JWTCookieAuthentication(JWTAuthentication):
    """
    Custom JWT authentication that reads the access token from HTTPOnly cookies.
    This provides better security against XSS attacks compared to localStorage or
    regular cookies that JavaScript can access.
    """

    def authenticate(self, request):
        # Get access token from HTTPOnly cookie
        raw_token = request.COOKIES.get('access_token')
        
        if raw_token is None:
            return None

        # Validate the token
        validated_token = self.get_validated_token(raw_token)
        
        # Enforce CSRF check for state-changing operations
        self.enforce_csrf(request)
        
        # Get the user from the token
        return self.get_user(validated_token), validated_token

    def enforce_csrf(self, request):
        """
        Enforce CSRF validation for unsafe HTTP methods.
        """
        # Only check CSRF for state-changing methods
        if request.method not in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):
            csrf_check = CSRFCheck(request)
            # CSRF check will raise an exception if the check fails
            reason = csrf_check.process_request(request)
            if reason:
                raise exceptions.PermissionDenied(f'CSRF Failed: {reason}')
