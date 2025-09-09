from rest_framework import permissions

class IsEncoderPermission (permissions.BasePermission):
    """
    Custom permission to only allow users with 'encoder' role to access certain views.
    Assumes the User model has a 'role' attribute.
    """

    def has_permission(self, request, view):
        # Check if the user is authenticated and has the 'encoder' role
        return request.user and request.user.is_authenticated and getattr(request.user, 'is_encoder', False)