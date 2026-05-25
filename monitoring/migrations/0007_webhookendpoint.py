from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring', '0005_add_log_trace_case_models'),
    ]

    operations = [
        migrations.CreateModel(
            name='WebhookEndpoint',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('url', models.URLField()),
                ('secret', models.CharField(blank=True, default='', max_length=200)),
                ('events', models.JSONField(default=list, help_text="订阅的事件类型: ['alert.fired','alert.resolved','remediation.success','remediation.failed']")),
                ('is_active', models.BooleanField(default=True)),
                ('last_status', models.CharField(blank=True, default='', max_length=20)),
                ('last_sent_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Webhook端点',
                'verbose_name_plural': 'Webhook端点',
            },
        ),
    ]
