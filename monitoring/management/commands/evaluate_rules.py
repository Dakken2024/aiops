import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from django.core.management.base import BaseCommand
from django.conf import settings

from monitoring.engine.rule_evaluator import RuleEvaluator

logger = logging.getLogger(__name__)


def job_evaluate_all():
    logger.info("--- [RuleEngine] 开始周期性评估 ---")
    result = RuleEvaluator.evaluate_all()
    logger.info(
        f"[RuleEngine] 评估完成: 评估{result['evaluated']}条规则, "
        f"触发{result['fired']}次告警"
    )
    if result['errors']:
        for err in result['errors']:
            logger.error(f"[RuleEngine] 错误: {err}")


class Command(BaseCommand):
    help = '启动预警规则评估调度器 (基于APScheduler)'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('[RuleEngine] 预警规则评估器启动...'))

        scheduler = BlockingScheduler(timezone=settings.TIME_ZONE)

        scheduler.add_job(job_evaluate_all, 'interval', seconds=60,
                         id='evaluate_alert_rules', replace_existing=True, max_instances=1)

        try:
            job_evaluate_all()
            scheduler.start()
        except KeyboardInterrupt:
            self.stdout.write("[RuleEngine] 已停止.")
