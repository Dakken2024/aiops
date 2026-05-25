import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0002_initial'),
        ('monitoring', '0005_add_log_trace_case_models'),
    ]

    operations = [
        migrations.CreateModel(
            name='MetricBaseline',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('metric_name', models.CharField(max_length=50, verbose_name='指标名')),
                ('hour_of_day', models.IntegerField(verbose_name='小时(0-23)')),
                ('weekday', models.IntegerField(blank=True, null=True, verbose_name='星期(0-6,0=周一)')),
                ('avg_value', models.FloatField(verbose_name='平均值')),
                ('std_dev', models.FloatField(default=0, verbose_name='标准差')),
                ('sample_count', models.IntegerField(default=0, verbose_name='样本数')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('server', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='metric_baselines', to='cmdb.server', verbose_name='服务器')),
            ],
            options={
                'verbose_name': '指标基线',
                'verbose_name_plural': '指标基线',
                'unique_together': {('server', 'metric_name', 'hour_of_day', 'weekday')},
            },
        ),
        migrations.AddIndex(
            model_name='metricbaseline',
            index=models.Index(fields=['server', 'metric_name', 'hour_of_day'], name='monitoring_m_server_id_metric_na_idx'),
        ),
    ]
