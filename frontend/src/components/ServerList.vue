<template>
  <div class="server-list">
    <h5 class="mb-3"><i class="fas fa-server mr-2"></i>服务器状态</h5>
    <div class="server-grid">
      <div v-for="server in servers" :key="server.id" class="server-card">
        <div class="server-header">
          <span class="server-name">{{ server.hostname }}</span>
          <span class="badge" :class="server.status === 'Running' ? 'badge-success' : 'badge-danger'">
            {{ server.status === 'Running' ? '运行中' : '已停止' }}
          </span>
        </div>
        <div class="server-metrics">
          <div class="metric-item">
            <span class="metric-label">CPU</span>
            <div class="progress">
              <div class="progress-bar" :class="getMetricClass(server.cpu_usage)" 
                   :style="{ width: (server.cpu_usage || 0) + '%' }">
                {{ server.cpu_usage || 0 }}%
              </div>
            </div>
          </div>
          <div class="metric-item">
            <span class="metric-label">内存</span>
            <div class="progress">
              <div class="progress-bar" :class="getMetricClass(server.mem_usage)" 
                   :style="{ width: (server.mem_usage || 0) + '%' }">
                {{ server.mem_usage || 0 }}%
              </div>
            </div>
          </div>
          <div class="metric-item">
            <span class="metric-label">磁盘</span>
            <div class="progress">
              <div class="progress-bar" :class="getMetricClass(server.disk_usage)" 
                   :style="{ width: (server.disk_usage || 0) + '%' }">
                {{ server.disk_usage || 0 }}%
              </div>
            </div>
          </div>
        </div>
        <div class="server-footer">
          <span class="server-ip"><i class="fas fa-network-wired mr-1"></i>{{ server.ip_address }}</span>
          <span class="server-os">{{ server.os_type }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  servers: {
    type: Array,
    default: () => []
  }
})

const getMetricClass = (value) => {
  if (value >= 90) return 'bg-danger'
  if (value >= 70) return 'bg-warning'
  return 'bg-success'
}
</script>

<style scoped>
.server-list {
  background: white;
  border-radius: 8px;
  padding: 15px;
  height: 100%;
}

.server-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 15px;
  max-height: 400px;
  overflow-y: auto;
}

.server-card {
  border: 1px solid #e9ecef;
  border-radius: 8px;
  padding: 15px;
  background: #fafafa;
}

.server-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.server-name {
  font-weight: 600;
  font-size: 15px;
}

.server-metrics {
  margin-bottom: 10px;
}

.metric-item {
  margin-bottom: 8px;
}

.metric-label {
  font-size: 12px;
  color: #6c757d;
  display: block;
  margin-bottom: 3px;
}

.progress {
  height: 16px;
  background: #e9ecef;
}

.progress-bar {
  font-size: 11px;
  line-height: 16px;
}

.server-footer {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #6c757d;
  padding-top: 8px;
  border-top: 1px solid #e9ecef;
}
</style>