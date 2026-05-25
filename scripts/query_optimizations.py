# ============================================================
# Django ORM PostgreSQL 查询优化示例
# 可直接复制到项目 views.py 或 services.py 中使用
# 依赖: Django >= 3.2, django.contrib.postgres
# ============================================================

from django.db import models
from django.db.models import Subquery, OuterRef, Prefetch, Count, Avg, Max
from django.contrib.postgres.search import TrigramSimilarity
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from cmdb.models import Server, ServerMetric, TerminalLog, HighRiskAudit
from ai_ops.models import ChatMessage, ChatSession
from script_manager.models import TaskLog, TaskExecution
from k8s_manager.models import ConfigMapHistory
from monitoring.models import AlertEvent, AlertRule, HealthScore, LogEntry


# ------------------------------------------------------------
# 1. optimized_dashboard()
# 优化仪表盘查询：使用 select_related + only() + Subquery
# 减少 N+1 查询和字段传输，提升仪表盘加载速度
# ------------------------------------------------------------
def optimized_dashboard(request):
    """
    优化后的仪表盘数据查询。

    优化点:
      - select_related('server'): 避免 ServerMetric -> Server 的 N+1 查询
      - only(): 仅加载需要的字段，减少网络传输和内存占用
      - Subquery: 用单条 SQL 子查询获取最新指标，避免多次往返数据库
      - 整体将仪表盘查询从 O(N) 次查询降至常数级
    """
    # 子查询：获取每台服务器的最新 metric ID
    latest_metric_subquery = (
        ServerMetric.objects
        .filter(server=OuterRef('pk'))
        .order_by('-created_at')
        .values('id')[:1]
    )

    # 主查询：获取服务器列表，并附带最新性能指标
    servers = (
        Server.objects
        .select_related('group')
        .only('id', 'hostname', 'ip_address', 'status', 'group__name')
        .annotate(
            latest_metric_id=Subquery(latest_metric_subquery),
        )
        .order_by('hostname')
    )

    # 批量获取最新指标详情（二次查询，但仅 1 次）
    latest_metric_ids = [s.latest_metric_id for s in servers if s.latest_metric_id]
    metrics_map = {
        m.id: m
        for m in ServerMetric.objects
        .filter(id__in=latest_metric_ids)
        .only('id', 'cpu_usage', 'mem_usage', 'disk_usage', 'load_1min', 'created_at')
    }

    # 组装仪表盘数据
    dashboard_data = []
    for server in servers:
        metric = metrics_map.get(server.latest_metric_id)
        dashboard_data.append({
            'server_id': server.id,
            'hostname': server.hostname,
            'ip': server.ip_address,
            'status': server.status,
            'group': server.group.name if server.group else None,
            'latest_metric': {
                'cpu': metric.cpu_usage if metric else None,
                'mem': metric.mem_usage if metric else None,
                'disk': metric.disk_usage if metric else None,
                'load': metric.load_1min if metric else None,
                'collected_at': metric.created_at.isoformat() if metric else None,
            },
        })

    return JsonResponse({
        'count': len(dashboard_data),
        'servers': dashboard_data,
    })


# ------------------------------------------------------------
# 2. cached_server_list()
# 使用 @cache_page 缓存服务器列表
# 适合读多写少的场景，如资产列表页、下拉选择框数据源
# ------------------------------------------------------------
@cache_page(60 * 5)  # 缓存 5 分钟
def cached_server_list(request):
    """
    带缓存的服务器列表接口。

    优化点:
      - @cache_page(300): 将完整响应缓存 5 分钟，避免重复查询
      - only(): 仅返回列表需要的字段
      - 适合资产列表页、监控目标选择器等低频变更场景

    注意:
      - 服务器状态变更后缓存会有延迟，可通过 Django Admin 操作或信号清除缓存
      - 如需更细粒度控制，可改用 django-redis + 手动 cache.set/get
    """
    servers = (
        Server.objects
        .only('id', 'hostname', 'ip_address', 'status', 'provider')
        .order_by('hostname')
    )

    data = [
        {
            'id': s.id,
            'hostname': s.hostname,
            'ip': s.ip_address,
            'status': s.status,
            'provider': s.provider,
        }
        for s in servers
    ]

    return JsonResponse({
        'cached': True,
        'count': len(data),
        'servers': data,
    })


# ------------------------------------------------------------
# 3. efficient_log_search()
# 使用 trigram_similar 进行全文/模糊搜索
# 依赖: pg_trgm 扩展 + 已创建的 GIN 索引 (idx_highriskaudit_command_gin)
# ------------------------------------------------------------
def efficient_log_search(request):
    """
    基于 trigram 相似度的高效日志模糊搜索。

    优化点:
      - TrigramSimilarity: 利用 PostgreSQL pg_trgm 扩展计算文本相似度
      - filter(similarity__gt=0.3): 只返回相似度足够高的结果，减少无效数据
      - 依赖 GIN 索引 idx_highriskaudit_command_gin 加速 WHERE 过滤
      - 比 LIKE '%keyword%' 快 10~100 倍，尤其在大数据量下

    请求参数:
      - q: 搜索关键词 (如 "rm -rf", "drop table")
      - limit: 最大返回条数 (默认 50)
    """
    query = request.GET.get('q', '').strip()
    limit = int(request.GET.get('limit', 50))

    if not query:
        return JsonResponse({'error': '缺少搜索参数 q'}, status=400)

    # 使用 TrigramSimilarity 进行模糊匹配，依赖 pg_trgm 和 GIN 索引
    results = (
        HighRiskAudit.objects
        .annotate(similarity=TrigramSimilarity('command', query))
        .filter(similarity__gt=0.3)
        .select_related('user', 'server')
        .only(
            'id', 'command', 'risk_level', 'action', 'created_at',
            'user__username', 'server__hostname', 'similarity'
        )
        .order_by('-similarity', '-created_at')
        [:limit]
    )

    data = [
        {
            'id': r.id,
            'command': r.command,
            'risk_level': r.risk_level,
            'action': r.action,
            'operator': r.user.username if r.user else None,
            'server': r.server.hostname if r.server else None,
            'similarity': round(r.similarity, 3),
            'created_at': r.created_at.isoformat() if r.created_at else None,
        }
        for r in results
    ]

    return JsonResponse({
        'query': query,
        'count': len(data),
        'results': data,
    })


# ------------------------------------------------------------
# 4. 额外优化示例: 批量聚合查询（监控告警统计）
# 使用 ORM 聚合函数一次性获取统计指标，避免循环查询
# ------------------------------------------------------------
def optimized_alert_statistics(request):
    """
    优化后的告警统计查询。

    优化点:
      - aggregate(): 单条 SQL 完成 COUNT / AVG / MAX 计算
      - values('severity').annotate(): 分组统计，避免 Python 端循环
      - 将多次查询合并为 2 次，适合仪表盘顶部统计卡片
    """
    # 整体聚合指标
    overall = AlertEvent.objects.aggregate(
        total_count=Count('id'),
        avg_duration=Avg(
            models.ExpressionWrapper(
                models.F('resolved_at') - models.F('fired_at'),
                output_field=models.DurationField()
            )
        ),
        latest_fired=Max('fired_at'),
    )

    # 按严重级别分组统计
    severity_stats = (
        AlertEvent.objects
        .values('severity')
        .annotate(
            count=Count('id'),
            unresolved=Count('id', filter=models.Q(status='firing')),
        )
        .order_by('-count')
    )

    return JsonResponse({
        'overall': {
            'total_count': overall['total_count'],
            'avg_resolution_seconds': (
                overall['avg_duration'].total_seconds()
                if overall['avg_duration'] else None
            ),
            'latest_fired': (
                overall['latest_fired'].isoformat()
                if overall['latest_fired'] else None
            ),
        },
        'by_severity': list(severity_stats),
    })


# ------------------------------------------------------------
# 5. 额外优化示例: 分页 + 延迟关联查询（审计日志列表）
# 使用 iterator() + 手动关联减少大分页内存占用
# ------------------------------------------------------------
def optimized_audit_log_list(request):
    """
    优化后的审计日志列表查询。

    优化点:
      - select_related('user', 'server'): 预加载外键，避免 N+1
      - defer('log_file'): 排除大字段（录像文件路径），减少传输
      - 适合审计日志这种字段多、数据量大的列表页
    """
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    offset = (page - 1) * page_size

    queryset = (
        TerminalLog.objects
        .select_related('user', 'server')
        .defer('log_file')  # 排除大字段/不常用字段
        .order_by('-start_time')
    )

    total = queryset.count()
    logs = queryset[offset:offset + page_size]

    data = [
        {
            'id': log.id,
            'operator': log.user.username if log.user else None,
            'server': log.server.hostname if log.server else None,
            'channel': log.channel_name,
            'start_time': log.start_time.isoformat() if log.start_time else None,
            'end_time': log.end_time.isoformat() if log.end_time else None,
        }
        for log in logs
    ]

    return JsonResponse({
        'page': page,
        'page_size': page_size,
        'total': total,
        'logs': data,
    })


# ------------------------------------------------------------
# 6. 额外优化示例: 基于 Prefetch 的会话消息批量加载
# 避免 ChatSession -> ChatMessage 的 N+1 查询
# ------------------------------------------------------------
def optimized_chat_session_list(request):
    """
    优化后的会话列表查询，附带最近一条消息预览。

    优化点:
      - Prefetch('messages'): 批量预加载关联消息
      - queryset=...[:1]: 仅预加载最近一条消息，控制数据量
      - 将会话列表查询从 N+1 降至 2 次查询
    """
    sessions = (
        ChatSession.objects
        .select_related('ai_model')
        .prefetch_related(
            Prefetch(
                'messages',
                queryset=ChatMessage.objects.order_by('-created_at')[:1],
                to_attr='latest_message_list'
            )
        )
        .order_by('-updated_at')
        [:50]
    )

    data = []
    for session in sessions:
        latest = session.latest_message_list[0] if session.latest_message_list else None
        data.append({
            'id': session.id,
            'title': session.title,
            'model': session.ai_model.name if session.ai_model else None,
            'updated_at': session.updated_at.isoformat(),
            'latest_message_preview': (
                latest.content[:100] if latest else None
            ),
            'latest_message_role': latest.role if latest else None,
        })

    return JsonResponse({
        'count': len(data),
        'sessions': data,
    })


# ------------------------------------------------------------
# 7. 额外优化示例: 时间范围过滤 + 部分索引利用
# 利用 ServerMetric 的部分索引 (idx_servermetric_recent_7d) 加速查询
# ------------------------------------------------------------
def optimized_recent_metrics(request, server_id):
    """
    查询某台服务器最近7天的性能指标。

    优化点:
      - filter(created_at__gte=...): 时间范围过滤
      - 自动利用部分索引 idx_servermetric_recent_7d
      - values(): 仅返回需要的字段，减少序列化开销
      - 适合仪表盘趋势图数据接口
    """
    from django.utils import timezone
    from datetime import timedelta

    seven_days_ago = timezone.now() - timedelta(days=7)

    metrics = (
        ServerMetric.objects
        .filter(server_id=server_id, created_at__gte=seven_days_ago)
        .order_by('created_at')
        .values('created_at', 'cpu_usage', 'mem_usage', 'disk_usage', 'load_1min')
    )

    data = [
        {
            'ts': m['created_at'].isoformat(),
            'cpu': m['cpu_usage'],
            'mem': m['mem_usage'],
            'disk': m['disk_usage'],
            'load': m['load_1min'],
        }
        for m in metrics
    ]

    return JsonResponse({
        'server_id': server_id,
        'days': 7,
        'count': len(data),
        'metrics': data,
    })


# ------------------------------------------------------------
# 8. 额外优化示例: 基于 GIN 索引的日志模式搜索
# 利用 LogEntry 已有的索引结构，结合 trigram 做异常日志检索
# ------------------------------------------------------------
def optimized_anomaly_log_search(request):
    """
    在异常日志中搜索包含特定关键词的记录。

    优化点:
      - filter(is_anomaly=True): 先过滤异常标记，缩小数据集
      - message__icontains: 如已添加 GIN 索引可替换为 TrigramSimilarity
      - 结合 is_anomaly 的 db_index 快速定位异常日志子集
    """
    keyword = request.GET.get('keyword', '').strip()
    limit = int(request.GET.get('limit', 50))

    queryset = (
        LogEntry.objects
        .filter(is_anomaly=True)
        .select_related('server')
        .only('id', 'timestamp', 'level', 'message', 'server__hostname')
        .order_by('-timestamp')
    )

    if keyword:
        # 如有大量日志搜索需求，建议为 message 字段也创建 GIN 索引
        queryset = queryset.filter(message__icontains=keyword)

    logs = queryset[:limit]

    data = [
        {
            'id': log.id,
            'timestamp': log.timestamp.isoformat(),
            'level': log.level,
            'message': log.message[:200],
            'server': log.server.hostname if log.server else None,
        }
        for log in logs
    ]

    return JsonResponse({
        'keyword': keyword or None,
        'count': len(data),
        'logs': data,
    })
