import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0002_initial'),
        ('monitoring', '0004_log_trace_retention_policies'),
    ]

    operations = [
        migrations.AddField(
            model_name='anomalyhistory',
            name='confidence',
            field=models.FloatField(blank=True, default=0.0, null=True, verbose_name='AI\u7f6e\u4fe1\u5ea6'),
        ),
        migrations.AddField(
            model_name='remediationhistory',
            name='decision_mode',
            field=models.CharField(blank=True, default='auto_confirm', max_length=20, verbose_name='\u51b3\u7b56\u6a21\u5f0f'),
        ),
        migrations.CreateModel(
            name='LogEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timestamp', models.DateTimeField(db_index=True, verbose_name='\u65e5\u5fd7\u65f6\u95f4')),
                ('level', models.CharField(db_index=True, max_length=10, verbose_name='\u7ea7\u522b', choices=[('EMERG', 'EMERG'), ('ALERT', 'ALERT'), ('CRIT', 'CRIT'), ('ERROR', 'ERROR'), ('WARN', 'WARN'), ('NOTICE', 'NOTICE'), ('INFO', 'INFO'), ('DEBUG', 'DEBUG')])),
                ('source', models.CharField(default='syslog', max_length=50, verbose_name='\u6765\u6e90')),
                ('message', models.TextField(verbose_name='\u65e5\u5fd7\u5185\u5bb9')),
                ('message_vector', models.TextField(blank=True, null=True)),
                ('structured_data', models.JSONField(default=dict, verbose_name='\u7ed3\u6784\u5316\u6570\u636e')),
                ('is_anomaly', models.BooleanField(db_index=True, default=False, verbose_name='\u662f\u5426\u5f02\u5e38')),
                ('pattern_id', models.IntegerField(blank=True, db_index=True, null=True, verbose_name='\u6a21\u5f0fID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('server', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='log_entries', to='cmdb.server', verbose_name='\u670d\u52a1\u5668')),
            ],
            options={
                'verbose_name': '\u65e5\u5fd7\u6761\u76ee',
                'verbose_name_plural': '\u65e5\u5fd7\u6761\u76ee',
                'ordering': ['-timestamp'],
            },
        ),
        migrations.AddIndex(
            model_name='logentry',
            index=models.Index(fields=['server', '-timestamp'], name='idx_logentry_server_time'),
        ),
        migrations.AddIndex(
            model_name='logentry',
            index=models.Index(fields=['level', '-timestamp'], name='idx_logentry_level_time'),
        ),
        migrations.CreateModel(
            name='LogPattern',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pattern_template', models.TextField(verbose_name='\u6a21\u5f0f\u6a21\u677f')),
                ('pattern_vector', models.TextField(blank=True, null=True)),
                ('level', models.CharField(default='ERROR', max_length=10, verbose_name='\u7ea7\u522b')),
                ('source', models.CharField(default='syslog', max_length=50, verbose_name='\u6765\u6e90')),
                ('occurrence_count', models.PositiveIntegerField(default=1, verbose_name='\u51fa\u73b0\u6b21\u6570')),
                ('first_seen', models.DateTimeField(verbose_name='\u9996\u6b21\u51fa\u73b0')),
                ('last_seen', models.DateTimeField(verbose_name='\u6700\u540e\u51fa\u73b0')),
                ('is_anomaly_pattern', models.BooleanField(default=False, verbose_name='\u5f02\u5e38\u6a21\u5f0f')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('server', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='log_patterns', to='cmdb.server', verbose_name='\u670d\u52a1\u5668')),
            ],
            options={
                'verbose_name': '\u65e5\u5fd7\u6a21\u5f0f',
                'verbose_name_plural': '\u65e5\u5fd7\u6a21\u5f0f',
                'ordering': ['-occurrence_count'],
            },
        ),
        migrations.CreateModel(
            name='TraceSpan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('trace_id', models.CharField(db_index=True, max_length=32, verbose_name='TraceID')),
                ('span_id', models.CharField(max_length=16, verbose_name='SpanID')),
                ('parent_span_id', models.CharField(blank=True, max_length=16, null=True, verbose_name='ParentSpanID')),
                ('service_name', models.CharField(db_index=True, max_length=100, verbose_name='\u670d\u52a1\u540d')),
                ('operation', models.CharField(max_length=200, verbose_name='\u64cd\u4f5c')),
                ('start_time', models.DateTimeField(db_index=True, verbose_name='\u5f00\u59cb\u65f6\u95f4')),
                ('duration_ms', models.IntegerField(default=0, verbose_name='\u8017\u65f6(ms)')),
                ('status', models.CharField(choices=[('OK', 'OK'), ('ERROR', 'ERROR'), ('UNSET', 'UNSET')], db_index=True, default='UNSET', max_length=10, verbose_name='\u72b6\u6001')),
                ('error_message', models.TextField(blank=True, verbose_name='\u9519\u8bef\u4fe1\u606f')),
                ('attributes', models.JSONField(default=dict, verbose_name='\u5c5e\u6027')),
                ('span_vector', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('server', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='trace_spans', to='cmdb.server', verbose_name='\u670d\u52a1\u5668')),
            ],
            options={
                'verbose_name': '\u94fe\u8def\u8ffd\u8e2a',
                'verbose_name_plural': '\u94fe\u8def\u8ffd\u8e2a',
                'ordering': ['-start_time'],
            },
        ),
        migrations.AddIndex(
            model_name='tracespan',
            index=models.Index(fields=['service_name', '-start_time'], name='idx_tracespan_svc_time'),
        ),
        migrations.AddIndex(
            model_name='tracespan',
            index=models.Index(fields=['status', '-start_time'], name='idx_tracespan_status_time'),
        ),
        migrations.CreateModel(
            name='CaseVector',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200, verbose_name='\u6848\u4f8b\u6807\u9898')),
                ('symptoms', models.TextField(verbose_name='\u75c7\u72b6\u63cf\u8ff0')),
                ('root_cause', models.TextField(verbose_name='\u6839\u56e0\u5206\u6790')),
                ('remediation', models.TextField(verbose_name='\u4fee\u590d\u65b9\u5f0f')),
                ('confidence', models.FloatField(default=0.0, verbose_name='\u7f6e\u4fe1\u5ea6')),
                ('effectiveness_score', models.FloatField(default=0.0, verbose_name='\u6709\u6548\u6027\u8bc4\u5206')),
                ('usage_count', models.PositiveIntegerField(default=0, verbose_name='\u4f7f\u7528\u6b21\u6570')),
                ('symptom_vector', models.TextField(blank=True, null=True)),
                ('related_alert_rules', models.JSONField(default=list, verbose_name='\u5173\u8054\u544a\u8b66\u89c4\u5219')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('related_runbook', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='case_vectors', to='monitoring.runbookentry', verbose_name='\u5173\u8054Runbook')),
            ],
            options={
                'verbose_name': '\u5386\u53f2\u6848\u4f8b',
                'verbose_name_plural': '\u5386\u53f2\u6848\u4f8b',
                'ordering': ['-effectiveness_score'],
            },
        ),
    ]
