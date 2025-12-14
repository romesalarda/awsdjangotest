"""
Celery Configuration for Core Project

This module configures Celery for asynchronous task processing.
Redis is used as both broker and result backend, with separate database
indices to avoid conflicts with Django Channels.

Redis Database Allocation:
- DB 0: Django Channels (default)
- DB 1: Celery broker
- DB 2: Celery results (optional)

Workers must be run as separate processes:
    celery -A core worker -l info
    celery -A core beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
"""

import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

app = Celery('core')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """
    Debug task for testing Celery configuration.
    Usage: from core.celery import debug_task; debug_task.delay()
    """
    print(f'Request: {self.request!r}')
