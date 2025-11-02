"""
Custom middleware for WebSocket JWT authentication using HTTPOnly cookies.
"""

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from urllib.parse import parse_qs
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


@database_sync_to_async
def get_user_from_token(token_string):
    """
    Get user from JWT access token.
    """
    try:
        # Validate and decode the token
        access_token = AccessToken(token_string)
        
        # Get user ID from token
        user_id = access_token.get('user_id')
        
        if not user_id:
            logger.warning("No user_id found in token")
            return AnonymousUser()
        
        # Get user from database
        user = User.objects.get(id=user_id)
        logger.info(f"✅ WebSocket auth successful for user: {user.username} (ID: {user_id})")
        return user
        
    except (InvalidToken, TokenError) as e:
        logger.warning(f"Invalid token: {str(e)}")
        return AnonymousUser()
    except User.DoesNotExist:
        logger.warning(f"User with ID {user_id} not found")
        return AnonymousUser()
    except Exception as e:
        logger.error(f"Error authenticating WebSocket user: {str(e)}")
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """
    Custom middleware that authenticates WebSocket connections using JWT tokens
    from HTTPOnly cookies.
    
    This middleware:
    1. Extracts the access_token from cookies
    2. Validates the JWT token
    3. Attaches the authenticated user to the scope
    """

    async def __call__(self, scope, receive, send):
        # Get cookies from headers
        headers = dict(scope.get('headers', []))
        cookie_header = headers.get(b'cookie', b'').decode('utf-8')
        
        # Parse cookies
        cookies = {}
        if cookie_header:
            for cookie in cookie_header.split('; '):
                if '=' in cookie:
                    key, value = cookie.split('=', 1)
                    cookies[key] = value
        
        # Get access token from cookies
        access_token = cookies.get('access_token')
        
        if access_token:
            logger.info(f"🔍 WebSocket auth attempt - Token found in cookies")
            logger.debug(f"Token preview: {access_token[:20]}...{access_token[-20:] if len(access_token) > 40 else ''}")
            # Authenticate user with token
            scope['user'] = await get_user_from_token(access_token)
        else:
            logger.warning("⚠️ WebSocket auth - No access_token cookie found")
            logger.warning(f"Cookie header: {cookie_header[:100] if cookie_header else 'EMPTY'}")
            logger.warning(f"Available cookies: {list(cookies.keys())}")
            scope['user'] = AnonymousUser()
        
        return await super().__call__(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    """
    Convenience function to wrap URLRouter with JWT authentication middleware.
    Usage in asgi.py:
        from core.middleware import JWTAuthMiddlewareStack
        
        application = ProtocolTypeRouter({
            "websocket": AllowedHostsOriginValidator(
                JWTAuthMiddlewareStack(
                    URLRouter(websocket_urlpatterns)
                )
            ),
        })
    """
    return JWTAuthMiddleware(inner)
