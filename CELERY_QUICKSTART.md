# Quick Start: Celery Setup

## Step 1: Install Dependencies

```bash
cd C:\Users\User\Documents\AWS\django\awsdocker
pip install celery==5.4.0 django-celery-beat==2.7.0 django-celery-results==2.5.1 kombu==5.4.2
```

## Step 2: Run Migrations

```bash
python manage.py migrate
```

Expected output:
```
Running migrations:
  Applying django_celery_beat.0001_initial... OK
  Applying django_celery_beat.0002_... OK
  ...
  Applying django_celery_results.0001_initial... OK
  ...
```

## Step 3: Setup Periodic Tasks

```bash
python manage.py setup_event_lifecycle_tasks
```

Expected output:
```
Setting up event lifecycle tasks...
✓ Created interval schedule: Every 5 minutes
✓ Created periodic task: Mark Ended Events as Completed
...
✓ Event lifecycle tasks setup complete!
```

## Step 4: Verify Redis is Running

```bash
redis-cli ping
```

Expected: `PONG`

If Redis is not running:
```bash
# Windows (if using WSL or Redis for Windows)
redis-server

# Or check if it's running as a service
```

## Step 5: Start Celery Worker

Open a new PowerShell terminal:

```powershell
cd C:\Users\User\Documents\AWS\django\awsdocker
celery -A core worker -l info
```

You should see:
```
[tasks]
  . events.archive_old_completed_events
  . events.mark_ended_events_as_completed
  . events.send_event_reminder_emails
```

## Step 6: Start Celery Beat Scheduler

Open another new PowerShell terminal:

```powershell
cd C:\Users\User\Documents\AWS\django\awsdocker
celery -A core beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

You should see:
```
celery beat v5.4.0 is starting.
__    -    ... [config:core.celery:app]
Scheduler: django_celery_beat.schedulers:DatabaseScheduler
```

## Step 7: Test the Setup

### Manual Test (Optional)

```powershell
python manage.py shell
```

Then in the Python shell:
```python
from apps.events.tasks import mark_ended_events_as_completed

# Test synchronously
result = mark_ended_events_as_completed()
print(f"Events marked as completed: {result}")

# Test asynchronously (with worker running)
task = mark_ended_events_as_completed.delay()
print(f"Task ID: {task.id}")
print(f"Task status: {task.status}")
```

### Verify Periodic Task is Scheduled

```python
from django_celery_beat.models import PeriodicTask
tasks = PeriodicTask.objects.filter(enabled=True)
for task in tasks:
    print(f"{task.name}: {task.task} - Runs {task.interval}")
```

## Running All Services Together

You'll need **3 terminal windows**:

### Terminal 1: Django Server
```powershell
cd C:\Users\User\Documents\AWS\django\awsdocker
python manage.py runserver
```

### Terminal 2: Celery Worker
```powershell
cd C:\Users\User\Documents\AWS\django\awsdocker
celery -A core worker -l info
```

### Terminal 3: Celery Beat
```powershell
cd C:\Users\User\Documents\AWS\django\awsdocker
celery -A core beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

## Monitoring

- **Django Admin**: http://localhost:8000/admin/django_celery_beat/periodictask/
- **Check Worker Status**: Look at Terminal 2 output
- **Check Beat Status**: Look at Terminal 3 output
- **Task Execution Logs**: Worker terminal will show task execution every 5 minutes

## What Happens Now?

Every 5 minutes, Celery Beat will trigger the `mark_ended_events_as_completed` task:

1. Task finds events where `end_date < now()`
2. Only updates events with status: `CONFIRMED` or `ONGOING`
3. Changes their status to `COMPLETED`
4. Logs the number of events updated

**Impact on Your App**:
- ✅ Completed events **still accessible** via direct URL
- ✅ Completed events **hidden from** public discovery/listing
- ✅ Users can still see their own completed events in "my-events"
- ✅ Event staff can still access completed events

## Troubleshooting

### "No module named 'celery'"
```bash
pip install -r requirements.txt
```

### "Connection refused" from Celery
Check Redis is running:
```bash
redis-cli ping
```

### Tasks not executing
1. Verify worker is running (Terminal 2)
2. Verify beat is running (Terminal 3)
3. Check periodic task is enabled in Django admin

### "Task has no registered task" error
Restart the Celery worker (Terminal 2):
- Press `Ctrl+C` to stop
- Run the command again

## Next Steps

1. ✅ All services running? You're done!
2. ⚙️ Want to adjust the schedule? Edit in Django admin
3. 📊 Need monitoring? Install Flower: `pip install flower && celery -A core flower`
4. 🚀 Production deployment? See `CELERY_DEPLOYMENT_GUIDE.md`
