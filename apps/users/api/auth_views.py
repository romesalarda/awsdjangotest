"""
Secure Authentication Views with HTTPOnly Cookies
This module provides secure JWT authentication using HTTPOnly cookies
to prevent XSS attacks and includes CSRF protection.
"""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from django.contrib.auth import authenticate
from django.middleware.csrf import get_token
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from datetime import timedelta

from .serializers import CommunityUserSerializer


@method_decorator(csrf_exempt, name='dispatch')
class SecureTokenObtainView(APIView):
    """
    Secure login endpoint that sets JWT tokens in HTTPOnly cookies
    instead of returning them in the response body.
    CSRF exempt because no session exists yet at login time.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        if not username or not password:
            return Response({
                'detail': 'Username and password are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Authenticate user
        user = authenticate(username=username, password=password)
        
        if user is None:
            return Response({
                'detail': 'Invalid credentials'
            }, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_active:
            return Response({
                'detail': 'Account is disabled'
            }, status=status.HTTP_401_UNAUTHORIZED)

        # Generate tokens
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        # Serialize user data
        user_data = CommunityUserSerializer(user).data

        # Create response
        response = Response({
            'user': user_data,
            'message': 'Login successful'
        }, status=status.HTTP_200_OK)

        # Set secure HTTPOnly cookies
        # Access token (shorter lifetime)
        response.set_cookie(
            key='access_token',
            value=access_token,
            max_age=int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds()),
            httponly=True,  # Prevents JavaScript access (XSS protection)
            secure=not settings.DEBUG,  # HTTPS only in production
            samesite='None' if not settings.DEBUG else 'Lax',  # 'None' required for cross-origin with credentials
            path='/'
        )

        # Refresh token (longer lifetime)
        response.set_cookie(
            key='refresh_token',
            value=refresh_token,
            max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
            httponly=True,  # Prevents JavaScript access (XSS protection)
            secure=not settings.DEBUG,  # HTTPS only in production
            samesite='None' if not settings.DEBUG else 'Lax',  # 'None' required for cross-origin with credentials
            path='/'
        )

        # Set CSRF token cookie (readable by JS for CSRF header)
        csrf_token = get_token(request)
        response.set_cookie(
            key='csrftoken',
            value=csrf_token,
            max_age=31449600,  # 1 year
            httponly=False,  # Must be readable by JavaScript
            secure=not settings.DEBUG,
            samesite='None' if not settings.DEBUG else 'Lax',  # 'None' required for cross-origin with credentials
            path='/'
        )

        return response


@method_decorator(csrf_exempt, name='dispatch')
class SecureTokenRefreshView(APIView):
    """
    Secure token refresh endpoint that reads refresh token from HTTPOnly cookie
    and sets new access token in HTTPOnly cookie.
    CSRF exempt because refresh uses HTTPOnly cookie which cannot be stolen via XSS.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        # Get refresh token from HTTPOnly cookie
        refresh_token = request.COOKIES.get('refresh_token')

        if not refresh_token:
            return Response({
                'detail': 'Refresh token not found'
            }, status=status.HTTP_401_UNAUTHORIZED)

        try:
            # Validate and refresh token
            refresh = RefreshToken(refresh_token)
            access_token = str(refresh.access_token)

            # Create response
            response = Response({
                'message': 'Token refreshed successfully'
            }, status=status.HTTP_200_OK)

            # Set new access token in HTTPOnly cookie
            response.set_cookie(
                key='access_token',
                value=access_token,
                max_age=int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds()),
                httponly=True,
                secure=not settings.DEBUG,
                samesite='None' if not settings.DEBUG else 'Lax',  # 'None' required for cross-origin
                path='/'
            )

            # Optionally rotate refresh token (if ROTATE_REFRESH_TOKENS is True)
            if settings.SIMPLE_JWT.get('ROTATE_REFRESH_TOKENS', False):
                refresh.set_jti()
                refresh.set_exp()
                new_refresh_token = str(refresh)
                
                response.set_cookie(
                    key='refresh_token',
                    value=new_refresh_token,
                    max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
                    httponly=True,
                    secure=not settings.DEBUG,
                    samesite='None' if not settings.DEBUG else 'Lax',  # 'None' required for cross-origin
                    path='/'
                )

            return response

        except TokenError as e:
            return Response({
                'detail': 'Invalid or expired refresh token'
            }, status=status.HTTP_401_UNAUTHORIZED)


@method_decorator(csrf_exempt, name='dispatch')
class SecureLogoutView(APIView):
    """
    Secure logout endpoint that clears HTTPOnly cookies.
    CSRF exempt because:
    1. User might be logging out with expired CSRF token
    2. Logout action is idempotent and clearing cookies is not a state change that needs protection
    3. The endpoint only clears cookies, no other sensitive operations
    AllowAny because user might have expired access token but still needs to logout.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        # Optionally blacklist the refresh token
        refresh_token = request.COOKIES.get('refresh_token')
        
        if refresh_token and settings.SIMPLE_JWT.get('BLACKLIST_AFTER_ROTATION', False):
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass  # Token already invalid or blacklist not enabled

        # Create response
        response = Response({
            'message': 'Logout successful'
        }, status=status.HTTP_200_OK)

        # Clear all auth cookies - using set_cookie with max_age=0 for more reliable deletion
        # This is more reliable than delete_cookie() in some browsers
        samesite_value = 'None' if not settings.DEBUG else 'Lax'
        cookie_settings = {
            'value': '',
            'max_age': 0,
            'expires': 'Thu, 01 Jan 1970 00:00:00 GMT',
            'path': '/',
            'httponly': True,
            'secure': not settings.DEBUG,
            'samesite': samesite_value  # Must match original cookie settings
        }
        
        # Delete access token
        response.set_cookie('access_token', **cookie_settings)
        
        # Delete refresh token
        response.set_cookie('refresh_token', **cookie_settings)
        
        # Delete CSRF token (not httponly)
        csrf_settings = cookie_settings.copy()
        csrf_settings['httponly'] = False
        response.set_cookie('csrftoken', **csrf_settings)
        
        # Also clear any Django session cookie if it exists
        response.set_cookie('sessionid', **cookie_settings)

        return response

class CurrentUserView(APIView):
    """
    Get current authenticated user information.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = CommunityUserSerializer(request.user)
        return Response({
            'user': serializer.data
        }, status=status.HTTP_200_OK)


class CSRFTokenView(APIView):
    """
    Get CSRF token for making authenticated requests.
    This is useful for the client to get a CSRF token on initial load.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        csrf_token = get_token(request)
        
        response = Response({
            'message': 'CSRF token generated'
        }, status=status.HTTP_200_OK)
        
        response.set_cookie(
            key='csrftoken',
            value=csrf_token,
            max_age=31449600,  # 1 year
            httponly=False,  # Must be readable by JavaScript
            secure=not settings.DEBUG,
            samesite='None' if not settings.DEBUG else 'Lax',  # 'None' required for cross-origin
            path='/'
        )
        
        return response
