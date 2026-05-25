from django.db import migrations


def create_log_trace_retention_policies(apps, schema_editor):
    DataRetentionPolicy = apps.get_model('monitoring', 'DataRetentionPolicy')
    DataRetentionPolicy.objects.get_or_create(
        name='logentry-7d',
        defaults={
            'metric_type': 'log',
            'retention_days': 7,
            'aggregation_interval': '1h',
            'is_active': True,
        },
    )
    DataRetentionPolicy.objects.get_or_create(
        name='tracespan-14d',
        defaults={
            'metric_type': 'trace',
            'retention_days': 14,
            'aggregation_interval': '1h',
            'is_active': True,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0003_default_data_retention_policies'),
    ]

    operations = [
        migrations.RunPython(create_log_trace_retention_policies, migrations.RunPython.noop),
    ]
