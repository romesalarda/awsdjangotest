"""
Custom JWT Authentication class that reads tokens from HTTPOnly cookies
instead of the Authorization header.
"""

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed


class JWTCookieAuthentication(JWTAuthentication):
    """
    Custom JWT authentication that reads the access token from HTTPOnly cookies.
    This provides better security against XSS attacks compared to localStorage or
    regular cookies that JavaScript can access.
    
    CORS-Safe Design:
    - Returns None when no token present (allows anonymous access)
    - Does not add WWW-Authenticate header (handled by exception handler)
    """

    def authenticate(self, request):
        """
        Authenticate the request using JWT from HTTPOnly cookie.
        
        Returns:
            None: No token present, user is anonymous (CORS-safe)
            tuple: (user, token) if authentication succeeds
        
        Raises:
            AuthenticationFailed: If token is invalid
        """
        # Get access token from HTTPOnly cookie
        raw_token = request.COOKIES.get('access_token')
        
        if raw_token is None:
            # No token present - user is anonymous
            # Return None to allow public endpoints
            return None

        # Validate the token
        try:
            validated_token = self.get_validated_token(raw_token)
        except (InvalidToken, AuthenticationFailed) as e:
            # Token is present but invalid
            # Re-raise to trigger 401 response
            raise AuthenticationFailed('Invalid or expired token')
        
        # Get the user from the token
        user = self.get_user(validated_token)
        
        return user, validated_token

    def authenticate_header(self, request):
        """
        Override to return None instead of 'Bearer'.
        This prevents DRF from adding WWW-Authenticate header on 401 responses,
        which would break CORS.
        
        Returns:
            None: Don't add WWW-Authenticate header
        """
        return None
