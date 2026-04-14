import logging
from collections import deque, defaultdict

from monitoring.models import ServiceTopology, AlertEvent

logger = logging.getLogger(__name__)


class TopologyTracker:

    @staticmethod
    def get_full_graph():
        nodes = list(ServiceTopology.objects.select_related('server').prefetch_related('depends_on'))
        node_map = {n.id: n for n in nodes}

        graph = {'nodes': [], 'links': [], 'node_map': {}}
        type_colors = {
            'application': '#1890ff', 'database': '#722ed1',
            'cache': '#fa8c16', 'queue': '#13c2c2',
            'lb': '#52c41a', 'storage': '#eb2f96', 'external': '#999',
        }

        for node in nodes:
            health = TopologyTracker._node_health(node)
            graph['nodes'].append({
                'id': node.id,
                'name': node.name,
                'type': node.service_type,
                'color': type_colors.get(node.service_type, '#1890ff'),
                'health': health,
                'server_hostname': node.server.hostname if node.server else '',
            })
            graph['node_map'][node.id] = len(graph['nodes']) - 1

        for node in nodes:
            source_idx = graph['node_map'].get(node.id)
            for dep in node.depends_on.all():
                target_idx = graph['node_map'].get(dep.id)
                if source_idx is not None and target_idx is not None:
                    graph['links'].append({
                        'source': source_idx,
                        'target': target_idx,
                    })

        return graph

    @staticmethod
    def _node_health(node):
        if not node.server:
            return 'unknown'
        firing = AlertEvent.objects.filter(
            server=node.server, status='firing'
        ).count()
        if firing == 0:
            return 'healthy'
        has_critical = AlertEvent.objects.filter(
            server=node.server, status='firing', severity__in=['P0', 'P1']
        ).exists()
        return 'critical' if has_critical else 'warning'

    @staticmethod
    def get_impact_analysis(node_id):
        try:
            node = ServiceTopology.objects.get(id=node_id)
        except ServiceTopology.DoesNotExist:
            return None

        affected_upstream = set()
        queue = deque([node_id])
        visited = {node_id}

        while queue:
            current_id = queue.popleft()
            dependents = ServiceTopology.objects.filter(
                depends_on__id=current_id
            )
            for dep in dependents:
                if dep.id not in visited:
                    visited.add(dep.id)
                    affected_upstream.add(dep.id)
                    queue.append(dep.id)

        affected_nodes = ServiceTopology.objects.filter(id__in=affected_upstream).select_related('server')
        return {
            'source_node': {'id': node.id, 'name': node.name},
            'affected_count': len(affected_upstream),
            'affected_services': [{
                'id': a.id, 'name': a.name,
                'type': a.service_type,
                'server': a.server.hostname if a.server else '',
            } for a in affected_nodes],
        }

    @staticmethod
    def get_dependency_chain(node_id):
        try:
            root = ServiceTopology.objects.get(id=node_id)
        except ServiceTopology.DoesNotExist:
            return []

        chain = []
        visited = set()

        def dfs(current, depth):
            if current.id in visited or depth > 10:
                return
            visited.add(current.id)
            chain.append({'id': current.id, 'name': current.name, 'depth': depth})
            for dep in current.depends_on.all():
                dfs(dep, depth + 1)

        dfs(root, 0)
        return chain
