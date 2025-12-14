"""
Management command to set up Celery Beat periodic tasks for event lifecycle management.

This command creates or updates the periodic task that automatically marks
ended events as COMPLETED.

Usage:
    python manage.py setup_event_lifecycle_tasks

This command is idempotent and can be run multiple times safely.
"""

from django.core.management.base import BaseCommand
from django_celery_beat.models import PeriodicTask, IntervalSchedule
import json


class Command(BaseCommand):
    help = 'Set up Celery Beat periodic tasks for event lifecycle management'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('Setting up event lifecycle tasks...'))

        # Create or get the interval schedule (every 5 minutes)
        schedule, created = IntervalSchedule.objects.get_or_create(
            every=5,
            period=IntervalSchedule.MINUTES,
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    '✓ Created interval schedule: Every 5 minutes'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    '• Interval schedule already exists: Every 5 minutes'
                )
            )

        # Create or update the periodic task
        task_name = 'Mark Ended Events as Completed'
        task, created = PeriodicTask.objects.get_or_create(
            name=task_name,
            defaults={
                'task': 'events.mark_ended_events_as_completed',
                'interval': schedule,
                'enabled': True,
                'description': (
                    'Automatically marks events as COMPLETED when their end_date has passed. '
                    'This task runs every 5 minutes and performs bulk updates.'
                ),
            }
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Created periodic task: {task_name}'
                )
            )
        else:
            # Update existing task to ensure it has the correct settings
            task.task = 'events.mark_ended_events_as_completed'
            task.interval = schedule
            task.enabled = True
            task.description = (
                'Automatically marks events as COMPLETED when their end_date has passed. '
                'This task runs every 5 minutes and performs bulk updates.'
            )
            task.save()
            self.stdout.write(
                self.style.WARNING(
                    f'• Updated existing periodic task: {task_name}'
                )
            )

        self.stdout.write(
            self.style.MIGRATE_LABEL('\nTask Configuration:')
        )
        self.stdout.write(f'  Task Name: {task.name}')
        self.stdout.write(f'  Task Function: {task.task}')
        self.stdout.write(f'  Schedule: Every {schedule.every} {schedule.period}')
        self.stdout.write(f'  Enabled: {task.enabled}')
        self.stdout.write(f'  Last Run: {task.last_run_at or "Never"}')

        self.stdout.write(
            self.style.MIGRATE_HEADING('\n✓ Event lifecycle tasks setup complete!')
        )

        self.stdout.write(
            self.style.WARNING('\nIMPORTANT:')
        )
        self.stdout.write(
            'Make sure Celery worker and beat scheduler are running:\n'
            '  1. Start worker: celery -A core worker -l info\n'
            '  2. Start beat: celery -A core beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler\n'
        )
