from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('cmdb', '0002_initial'),
        ('monitoring', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='CloudResource',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('provider', models.CharField(choices=[('aliyun', '阿里云'), ('tencent', '腾讯云'), ('huawei', '华为云'), ('aws', 'AWS')], max_length=20, verbose_name='云厂商')),
                ('resource_type', models.CharField(choices=[('ecs', '云服务器'), ('rds', '云数据库'), ('slb', '负载均衡'), ('oss', '对象存储'), ('redis_cloud', '云缓存'), ('cdn', 'CDN')], max_length=20, verbose_name='资源类型')),
                ('instance_id', models.CharField(max_length=100, verbose_name='实例ID')),
                ('instance_name', models.CharField(default='', max_length=200, verbose_name='实例名称')),
                ('region', models.CharField(default='', max_length=50, verbose_name='区域')),
                ('extra_config', models.JSONField(default=dict, verbose_name='扩展配置')),
                ('last_sync_at', models.DateTimeField(blank=True, null=True, verbose_name='最后同步时间')),
                ('is_active', models.BooleanField(default=True, verbose_name='是否启用')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('cloud_account', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cloud_resources', to='cmdb.cloudaccount', verbose_name='云账号')),
                ('local_server', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cloud_resource', to='cmdb.server', verbose_name='关联本地服务器')),
            ],
            options={
                'verbose_name': '云资源',
                'verbose_name_plural': '云资源',
                'unique_together': {('cloud_account', 'instance_id')},
            },
        ),
        migrations.AddIndex(
            model_name='cloudresource',
            index=models.Index(fields=['provider', 'resource_type'], name='idx_cloud_prov_type'),
        ),
        migrations.AddIndex(
            model_name='cloudresource',
            index=models.Index(fields=['is_active'], name='idx_cloud_active'),
        ),
        migrations.CreateModel(
            name='DataRetentionPolicy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='策略名称')),
                ('metric_type', models.CharField(default='raw', help_text='raw=原始明细, aggregated=聚合数据', max_length=50, verbose_name='指标类型')),
                ('retention_days', models.PositiveIntegerField(default=30, verbose_name='保留天数')),
                ('aggregation_interval', models.CharField(choices=[('5m', '5分钟'), ('1h', '1小时'), ('1d', '1天')], default='1h', max_length=20, verbose_name='聚合间隔')),
                ('is_active', models.BooleanField(default=True, verbose_name='是否启用')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': '数据保留策略',
                'verbose_name_plural': '数据保留策略',
            },
        ),
        migrations.CreateModel(
            name='MetricAggregation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('metric_type', models.CharField(help_text='cpu_usage/mem_usage/disk_usage等', max_length=50, verbose_name='指标类型')),
                ('aggregation_interval', models.CharField(choices=[('5m', '5分钟'), ('1h', '1小时'), ('1d', '1天')], default='1h', max_length=20, verbose_name='聚合间隔')),
                ('avg_value', models.FloatField(default=0.0, verbose_name='平均值')),
                ('max_value', models.FloatField(default=0.0, verbose_name='最大值')),
                ('min_value', models.FloatField(default=0.0, verbose_name='最小值')),
                ('sample_count', models.PositiveIntegerField(default=0, verbose_name='样本数')),
                ('timestamp', models.DateTimeField(db_index=True, verbose_name='时间戳')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('cloud_resource', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='metric_aggregations', to='monitoring.cloudresource', verbose_name='云资源')),
                ('server', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='metric_aggregations', to='cmdb.server', verbose_name='服务器')),
            ],
            options={
                'verbose_name': '指标聚合',
                'verbose_name_plural': '指标聚合',
                'ordering': ['-timestamp'],
            },
        ),
        migrations.AddIndex(
            model_name='metricaggregation',
            index=models.Index(fields=['server', 'metric_type', '-timestamp'], name='idx_agg_srv_metric_ts'),
        ),
        migrations.AddIndex(
            model_name='metricaggregation',
            index=models.Index(fields=['cloud_resource', 'metric_type', '-timestamp'], name='idx_agg_cr_metric_ts'),
        ),
    ]
