# Generated migration to convert TimeField + DateField to DateTimeField
from django.db import migrations, models
import django.utils.timezone
import pytz


def migrate_attendance_data(apps, schema_editor):
    """
    Migrate existing attendance data from separate day_date + time fields
    to combined datetime fields
    """
    EventDayAttendance = apps.get_model('events', 'EventDayAttendance')
    london_tz = pytz.timezone('Europe/London')
    
    for attendance in EventDayAttendance.objects.all():
        # Combine day_date + check_in_time into check_in_at datetime
        if hasattr(attendance, 'day_date') and hasattr(attendance, 'check_in_time'):
            if attendance.day_date and attendance.check_in_time:
                # Create timezone-aware datetime from date + time
                naive_dt = django.utils.timezone.datetime.combine(
                    attendance.day_date, 
                    attendance.check_in_time
                )
                attendance.check_in_at = london_tz.localize(naive_dt)
        
        # Combine day_date + check_out_time into check_out_at datetime
        if hasattr(attendance, 'day_date') and hasattr(attendance, 'check_out_time'):
            if attendance.day_date and attendance.check_out_time:
                naive_dt = django.utils.timezone.datetime.combine(
                    attendance.day_date,
                    attendance.check_out_time
                )
                attendance.check_out_at = london_tz.localize(naive_dt)
        
        attendance.save()


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0007_alter_eventdayattendance_check_in_time_and_more'),
    ]

    operations = [
        # Step 1: Add new DateTimeField columns with temporary names
        migrations.AddField(
            model_name='eventdayattendance',
            name='check_in_at',
            field=models.DateTimeField(verbose_name='check-in timestamp', null=True, blank=True),
        ),
        migrations.AddField(
            model_name='eventdayattendance',
            name='check_out_at',
            field=models.DateTimeField(verbose_name='check-out timestamp', null=True, blank=True),
        ),
        
        # Step 2: Migrate existing data (combine day_date + time into datetime)
        migrations.RunPython(migrate_attendance_data, reverse_code=migrations.RunPython.noop),
        
        # Step 3: Remove old fields
        migrations.RemoveField(
            model_name='eventdayattendance',
            name='day_date',
        ),
        migrations.RemoveField(
            model_name='eventdayattendance',
            name='day_id',
        ),
        migrations.RemoveField(
            model_name='eventdayattendance',
            name='check_in_time',
        ),
        migrations.RemoveField(
            model_name='eventdayattendance',
            name='check_out_time',
        ),
        
        # Step 4: Rename new fields to original names
        migrations.RenameField(
            model_name='eventdayattendance',
            old_name='check_in_at',
            new_name='check_in_time',
        ),
        migrations.RenameField(
            model_name='eventdayattendance',
            old_name='check_out_at',
            new_name='check_out_time',
        ),
        
        # Step 5: Make check_in_time non-nullable (as per model definition)
        migrations.AlterField(
            model_name='eventdayattendance',
            name='check_in_time',
            field=models.DateTimeField(verbose_name='check-in timestamp'),
        ),
    ]
