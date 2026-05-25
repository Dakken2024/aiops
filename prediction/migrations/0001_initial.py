from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('cmdb', '0002_initial'),
        ('monitoring', '0007_webhookendpoint'),
    ]

    operations = [
        migrations.CreateModel(
            name='CapacityForecast',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('metric_type', models.CharField(choices=[('cpu', 'CPU使用率'), ('memory', '内存使用率'), ('disk', '磁盘使用率')], max_length=20, verbose_name='指标类型')),
                ('forecast_data', models.JSONField(default=list, verbose_name='预测值数组')),
                ('forecast_date', models.DateField(db_index=True, verbose_name='预测日期')),
                ('confidence', models.FloatField(default=0.0, verbose_name='置信度')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('server', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='capacity_forecasts', to='cmdb.server', verbose_name='服务器')),
            ],
            options={
                'verbose_name': '容量预测结果',
                'verbose_name_plural': '容量预测结果',
                'unique_together': {('server', 'metric_type', 'forecast_date')},
            },
        ),
        migrations.CreateModel(
            name='AlertForecast',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('predicted_count', models.IntegerField(default=0, verbose_name='预测触发次数')),
                ('predicted_time', models.DateTimeField(db_index=True, verbose_name='预测时间')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('rule', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='alert_forecasts', to='monitoring.alertrule', verbose_name='告警规则')),
            ],
            options={
                'verbose_name': '告警预测',
                'verbose_name_plural': '告警预测',
            },
        ),
        migrations.CreateModel(
            name='AnomalyDetection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('detected_at', models.DateTimeField(db_index=True, verbose_name='检测时间')),
                ('score', models.FloatField(verbose_name='异常分数')),
                ('features', models.JSONField(default=dict, verbose_name='参与计算的特征')),
                ('metric_name', models.CharField(default='', max_length=50, verbose_name='指标名')),
                ('severity', models.CharField(choices=[('high', '高度异常'), ('medium', '中度异常'), ('low', '轻度异常')], default='medium', max_length=10, verbose_name='异常程度')),
                ('method_used', models.CharField(default='', max_length=50, verbose_name='使用方法')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('server', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='anomaly_detections', to='cmdb.server', verbose_name='服务器')),
            ],
            options={
                'verbose_name': '异常检测结果',
                'verbose_name_plural': '异常检测结果',
                'ordering': ['-detected_at'],
            },
        ),
        migrations.CreateModel(
            name='BaselineModel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('metric_type', models.CharField(choices=[('cpu_usage', 'CPU使用率'), ('mem_usage', '内存使用率'), ('disk_usage', '磁盘使用率'), ('load_1min', '1分钟负载'), ('net_in', '入站流量'), ('net_out', '出站流量')], max_length=50, verbose_name='指标类型')),
                ('baseline_data', models.JSONField(default=dict, verbose_name='基线数据')),
                ('learned_periods', models.JSONField(default=dict, verbose_name='学习到的周期')),
                ('last_learned_at', models.DateTimeField(blank=True, null=True, verbose_name='最后学习时间')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('server', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='baseline_models', to='cmdb.server', verbose_name='服务器')),
            ],
            options={
                'verbose_name': '智能基线',
                'verbose_name_plural': '智能基线',
                'unique_together': {('server', 'metric_type')},
            },
        ),
        migrations.AddIndex(
            model_name='capacityforecast',
            index=models.Index(fields=['server', 'metric_type', '-forecast_date'], name='predictio_server_m_e13573_idx'),
        ),
        migrations.AddIndex(
            model_name='alertforecast',
            index=models.Index(fields=['rule', '-predicted_time'], name='predictio_rule_pr_715308_idx'),
        ),
        migrations.AddIndex(
            model_name='anomalydetection',
            index=models.Index(fields=['server', '-detected_at'], name='predictio_server_d_5632a2_idx'),
        ),
        migrations.AddIndex(
            model_name='anomalydetection',
            index=models.Index(fields=['severity'], name='predictio_severit_c49319_idx'),
        ),
        migrations.AddIndex(
            model_name='baselinemodel',
            index=models.Index(fields=['server', 'metric_type'], name='predictio_server_m_382266_idx'),
        ),
    ]