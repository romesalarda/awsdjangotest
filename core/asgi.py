"""
ASGI config for core project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import OriginValidator

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

from core.routing import websocket_urlpatterns
from core.middleware import JWTAuthMiddlewareStack
from django.conf import settings

# Create CORS-aware WebSocket origin validator
# Uses CORS_ALLOWED_ORIGINS instead of ALLOWED_HOSTS for WebSocket connections
class CORSOriginValidator(OriginValidator):
    """
    WebSocket origin validator that uses CORS_ALLOWED_ORIGINS.
    This fixes 403 errors when frontend and backend are on different domains.
    """
    def __init__(self, application):
        # Convert CORS_ALLOWED_ORIGINS to set of allowed origins
        cors_origins = getattr(settings, 'CORS_ALLOWED_ORIGINS', [])
        
        # Extract hostnames from CORS origins for WebSocket validation
        # e.g., 'https://example.com' -> 'example.com'
        allowed_origins = []
        for origin in cors_origins:
            # Remove protocol
            if '://' in origin:
                origin = origin.split('://', 1)[1]
            # Remove port if present
            if ':' in origin:
                origin = origin.split(':', 1)[0]
            allowed_origins.append(origin)
        
        # Also add ALLOWED_HOSTS
        allowed_hosts = getattr(settings, 'ALLOWED_HOSTS', [])
        allowed_origins.extend(allowed_hosts)
        
        # Remove duplicates and wildcards
        self.allowed = set(h for h in allowed_origins if h and h != '*')
        
        super().__init__(application, self.allowed)

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": CORSOriginValidator(
        JWTAuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    ),
})
