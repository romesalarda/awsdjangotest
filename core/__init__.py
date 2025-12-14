"""
Core Django application initialization.

This ensures Celery is loaded when Django starts,
enabling Celery to auto-discover tasks in all installed apps.
"""

# This will make sure the Celery app is always imported when
# Django starts so that shared_task will use this app.
from .celery import app as celery_app

__all__ = ('celery_app',)
