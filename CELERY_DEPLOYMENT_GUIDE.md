# Celery Integration - Deployment Guide

## Overview

This Django application uses **Celery** for asynchronous task processing with **Redis** as the message broker. The primary use case is automated event lifecycle management, specifically marking events as COMPLETED when their `end_date` has passed.

## Architecture

### Redis Database Allocation

To prevent conflicts between Django Channels and Celery, Redis is partitioned as follows:

- **DB 0**: Django Channels (WebSockets)
- **DB 1**: Celery Broker (task queue)
- **DB 2**: Celery Results (optional, currently using Django DB)

### Key Components

1. **Celery App** (`core/celery.py`): Main Celery configuration
2. **Tasks** (`apps/events/tasks.py`): Asynchronous task definitions
3. **Beat Scheduler** (`django-celery-beat`): Database-backed periodic task scheduler
4. **Management Command** (`apps/events/management/commands/setup_event_lifecycle_tasks.py`): Setup automation

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

New packages installed:
- `celery==5.4.0`
- `django-celery-beat==2.7.0`
- `django-celery-results==2.5.1`
- `kombu==5.4.2` (Celery messaging library)

### 2. Run Database Migrations

```bash
python manage.py migrate
```

This creates tables for:
- `django_celery_beat_*`: Periodic task scheduling
- `django_celery_results_*`: Task result storage

### 3. Setup Periodic Tasks

```bash
python manage.py setup_event_lifecycle_tasks
```

This creates the periodic task: **"Mark Ended Events as Completed"**
- Runs every 5 minutes
- Task: `events.mark_ended_events_as_completed`

## Running Celery

### Development

You need **three separate terminal/process windows**:

#### Terminal 1: Django Server
```bash
cd django/awsdocker
python manage.py runserver
```

#### Terminal 2: Celery Worker
```bash
cd django/awsdocker
celery -A core worker -l info
```

#### Terminal 3: Celery Beat Scheduler
```bash
cd django/awsdocker
celery -A core beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

### Production (Systemd Example)

Create three systemd service files:

#### `/etc/systemd/system/django.service`
```ini
[Unit]
Description=Django ASGI Application (Daphne)
After=network.target redis.service postgresql.service

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/path/to/django/awsdocker
Environment="DJANGO_SETTINGS_MODULE=core.settings"
ExecStart=/path/to/venv/bin/daphne -b 0.0.0.0 -p 8000 core.asgi:application
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

#### `/etc/systemd/system/celery-worker.service`
```ini
[Unit]
Description=Celery Worker for Event Management
After=network.target redis.service postgresql.service

[Service]
Type=forking
User=www-data
Group=www-data
WorkingDirectory=/path/to/django/awsdocker
Environment="DJANGO_SETTINGS_MODULE=core.settings"
ExecStart=/path/to/venv/bin/celery -A core worker \
    --loglevel=info \
    --logfile=/var/log/celery/worker.log \
    --pidfile=/var/run/celery/worker.pid \
    --detach
ExecStop=/path/to/venv/bin/celery -A core control shutdown
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
```

#### `/etc/systemd/system/celery-beat.service`
```ini
[Unit]
Description=Celery Beat Scheduler for Event Management
After=network.target redis.service postgresql.service celery-worker.service
Requires=celery-worker.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/path/to/django/awsdocker
Environment="DJANGO_SETTINGS_MODULE=core.settings"
ExecStart=/path/to/venv/bin/celery -A core beat \
    --loglevel=info \
    --logfile=/var/log/celery/beat.log \
    --pidfile=/var/run/celery/beat.pid \
    --scheduler django_celery_beat.schedulers:DatabaseScheduler
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
```

#### Enable and Start Services
```bash
sudo systemctl daemon-reload
sudo systemctl enable django celery-worker celery-beat
sudo systemctl start django celery-worker celery-beat
```

#### Check Status
```bash
sudo systemctl status celery-worker
sudo systemctl status celery-beat
```

### Production (Docker Compose Example)

Add to your `docker-compose.yaml`:

```yaml
services:
  # Existing services (django, redis, postgres, etc.)
  
  celery-worker:
    build: .
    command: celery -A core worker -l info
    volumes:
      - .:/app
    environment:
      - DJANGO_SETTINGS_MODULE=core.settings
    depends_on:
      - redis
      - postgres
    restart: unless-stopped

  celery-beat:
    build: .
    command: celery -A core beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
    volumes:
      - .:/app
    environment:
      - DJANGO_SETTINGS_MODULE=core.settings
    depends_on:
      - redis
      - postgres
      - celery-worker
    restart: unless-stopped
```

## Task Details

### `mark_ended_events_as_completed`

**Purpose**: Automatically marks events as COMPLETED when their `end_date` has passed.

**Behavior**:
- Runs every 5 minutes
- Only processes events with status: `CONFIRMED` or `ONGOING`
- Ignores events without an `end_date`
- Uses timezone-aware datetime comparison (Europe/London)
- Performs bulk updates (efficient, single query)
- Idempotent (safe to run multiple times)
- Retries up to 3 times on failure

**Query Logic**:
```python
events_to_complete = Event.objects.filter(
    end_date__lt=now,  # End date is in the past
    status__in=[Event.EventStatus.CONFIRMED, Event.EventStatus.ONGOING]
).exclude(end_date__isnull=True)
```

**Impact on Views**:
- **List/Discovery**: COMPLETED events are excluded from public listing
- **Direct Access**: COMPLETED events remain accessible via direct URL
- **My Events**: Users can still see their COMPLETED events (optional filter)

### Future Tasks (Placeholders)

- `archive_old_completed_events`: Archive events after 90 days
- `send_event_reminder_emails`: Send reminders to participants

## Monitoring

### Admin Interface

Access Django admin to manage periodic tasks:
```
http://your-domain/admin/django_celery_beat/periodictask/
```

You can:
- Enable/disable tasks
- Change schedules
- View last run times
- Check task arguments

### Celery Flower (Optional Monitoring Tool)

Install Flower:
```bash
pip install flower
```

Run Flower:
```bash
celery -A core flower --port=5555
```

Access dashboard:
```
http://localhost:5555
```

### Logs

Development:
- Worker logs appear in Terminal 2
- Beat logs appear in Terminal 3

Production:
- Worker: `/var/log/celery/worker.log`
- Beat: `/var/log/celery/beat.log`

### Testing Tasks Manually

From Django shell:
```python
python manage.py shell

from apps.events.tasks import mark_ended_events_as_completed

# Run synchronously (for testing)
result = mark_ended_events_as_completed()
print(f"Marked {result} events as completed")

# Run asynchronously (production mode)
task = mark_ended_events_as_completed.delay()
print(f"Task ID: {task.id}")
```

## Troubleshooting

### Worker Not Processing Tasks

1. Check Redis connection:
   ```bash
   redis-cli -n 1 ping
   ```

2. Check worker logs:
   ```bash
   sudo systemctl status celery-worker
   sudo journalctl -u celery-worker -f
   ```

3. Verify task registration:
   ```bash
   celery -A core inspect registered
   ```

### Beat Not Scheduling Tasks

1. Check beat is running:
   ```bash
   sudo systemctl status celery-beat
   ```

2. Verify periodic tasks in database:
   ```python
   python manage.py shell
   from django_celery_beat.models import PeriodicTask
   print(PeriodicTask.objects.filter(enabled=True).values('name', 'task', 'enabled', 'last_run_at'))
   ```

3. Check beat logs for errors:
   ```bash
   sudo journalctl -u celery-beat -f
   ```

### Tasks Failing

1. Check task logs in Django admin:
   ```
   http://your-domain/admin/django_celery_results/taskresult/
   ```

2. Verify task can run manually:
   ```python
   python manage.py shell
   from apps.events.tasks import mark_ended_events_as_completed
   mark_ended_events_as_completed()
   ```

3. Check for database connection issues or timezone problems

## Configuration Reference

### Key Settings (settings.py)

```python
# Celery Broker (Redis DB 1)
CELERY_BROKER_URL = 'redis://127.0.0.1:6379/1'

# Result Backend (Django DB)
CELERY_RESULT_BACKEND = 'django-db'

# Timezone
CELERY_TIMEZONE = 'Europe/London'
CELERY_ENABLE_UTC = True

# Task Settings
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_TASK_ACKS_LATE = True

# Scheduler
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
```

## Security Considerations

1. **Task Serialization**: Only JSON is accepted (no pickle)
2. **Redis Access**: Ensure Redis is not exposed to the public internet
3. **Task Isolation**: Each task runs in its own transaction
4. **Error Handling**: Tasks retry on failure with exponential backoff
5. **Logging**: All task executions are logged for audit trail

## Performance Notes

- Tasks use bulk updates, not per-row loops
- Result backend uses Django DB to avoid Redis memory pressure
- Tasks acknowledge late (CELERY_TASK_ACKS_LATE) for reliability
- Worker prefetch is limited to 1 for long-running tasks

## Backup Considerations

When backing up the database, include:
- `django_celery_beat_*` tables (periodic task schedules)
- `django_celery_results_*` tables (task execution history)

## Scaling

To handle more load:
1. Increase worker concurrency:
   ```bash
   celery -A core worker -l info --concurrency=4
   ```

2. Run multiple workers:
   ```bash
   celery -A core worker -l info -n worker1@%h
   celery -A core worker -l info -n worker2@%h
   ```

3. Use Redis Sentinel for high availability

## Support

For issues or questions, check:
- Celery logs
- Django admin periodic tasks
- Redis connectivity
- Event model status transitions
