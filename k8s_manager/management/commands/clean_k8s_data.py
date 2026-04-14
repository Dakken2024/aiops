from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from k8s_manager.models import NodeSnapshot


class Command(BaseCommand):
    help = '清理 K8s 监控历史数据 (默认保留 7 天)'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=7, help='保留天数')

    def handle(self, *args, **options):
        days = options['days']
        expire_date = timezone.now() - timedelta(days=days)

        # 执行删除
        count, _ = NodeSnapshot.objects.filter(updated_at__lt=expire_date).delete()

        self.stdout.write(self.style.SUCCESS(f'[{timezone.now()}] 清理完成: 删除了 {days} 天前的 {count} 条记录'))