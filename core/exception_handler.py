"""
Custom DRF Exception Handler to ensure CORS headers are preserved on authentication failures.

The Problem:
When DRF authentication fails (no JWT cookie), the default exception handler adds a
'WWW-Authenticate: Bearer realm="api"' header to 401 responses. This header breaks CORS
in browsers, causing them to reject the response BEFORE CORS headers can be processed.

The Solution:
Remove the WWW-Authenticate header from 401 responses, allowing CORS headers to be
visible to the browser. This is safe because:
1. The client already knows the API requires authentication (documented)
2. The 401 status code itself indicates authentication is required
3. CORS security is preserved
4. The API remains RESTful
"""

from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    """
    Custom exception handler that ensures CORS works with authentication failures.
    
    This handler:
    1. Calls DRF's default exception handler
    2. Removes WWW-Authenticate header from 401 responses
    3. Preserves all other response data and headers
    
    Args:
        exc: The exception that was raised
        context: Dictionary with 'view' and 'request' keys
    
    Returns:
        Response object with proper CORS-compatible headers
    """
    # Get the standard error response
    response = exception_handler(exc, context)
    
    if response is not None:
        # Remove WWW-Authenticate header from 401 responses
        # This header breaks CORS and is not essential for our JWT cookie auth
        if response.status_code == 401:
            response.pop('WWW-Authenticate', None)
    
    return response
