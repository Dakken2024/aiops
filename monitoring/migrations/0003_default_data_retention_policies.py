from django.db import migrations


def create_default_policies(apps, schema_editor):
    DataRetentionPolicy = apps.get_model('monitoring', 'DataRetentionPolicy')
    DataRetentionPolicy.objects.get_or_create(
        name='raw-30d-5m-agg',
        defaults={
            'metric_type': 'raw',
            'retention_days': 30,
            'aggregation_interval': '5m',
            'is_active': True,
        },
    )
    DataRetentionPolicy.objects.get_or_create(
        name='raw-7d-1h-agg',
        defaults={
            'metric_type': 'raw',
            'retention_days': 7,
            'aggregation_interval': '1h',
            'is_active': True,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0002_cloudresource_dataretentionpolicy_metricaggregation'),
    ]

    operations = [
        migrations.RunPython(create_default_policies, migrations.RunPython.noop),
    ]
