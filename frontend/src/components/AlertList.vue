<template>
  <div class="alert-list">
    <h5 class="mb-3"><i class="fas fa-bell mr-2"></i>实时告警</h5>
    <div class="alert-items">
      <div v-for="alert in alerts" :key="alert.id" class="alert-item" :class="`severity-${alert.severity.toLowerCase()}`">
        <div class="alert-header">
          <span class="alert-rule">{{ alert.rule_name }}</span>
          <span class="badge" :class="getSeverityBadge(alert.severity)">{{ alert.severity }}</span>
        </div>
        <div class="alert-info">
          <span class="alert-server"><i class="fas fa-server mr-1"></i>{{ alert.server_name }}</span>
          <span class="alert-time">{{ formatTime(alert.fired_at) }}</span>
        </div>
        <div class="alert-message">{{ alert.message }}</div>
      </div>
      <div v-if="alerts.length === 0" class="text-muted text-center py-4">
        暂无告警信息
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  alerts: {
    type: Array,
    default: () => []
  }
})

const getSeverityBadge = (severity) => {
  const badges = {
    'P0': 'badge-danger',
    'P1': 'badge-warning',
    'P2': 'badge-info',
    'P3': 'badge-secondary'
  }
  return badges[severity] || 'badge-secondary'
}

const formatTime = (timeStr) => {
  if (!timeStr) return ''
  const date = new Date(timeStr)
  return date.toLocaleString('zh-CN')
}
</script>

<style scoped>
.alert-list {
  background: white;
  border-radius: 8px;
  padding: 15px;
  height: 100%;
}

.alert-items {
  max-height: 350px;
  overflow-y: auto;
}

.alert-item {
  border-left: 4px solid;
  padding: 10px 15px;
  margin-bottom: 10px;
  background: #f8f9fa;
  border-radius: 4px;
}

.alert-item.severity-p0 {
  border-color: #dc3545;
}

.alert-item.severity-p1 {
  border-color: #ffc107;
}

.alert-item.severity-p2 {
  border-color: #17a2b8;
}

.alert-item.severity-p3 {
  border-color: #6c757d;
}

.alert-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 5px;
}

.alert-rule {
  font-weight: 600;
  font-size: 14px;
}

.alert-info {
  display: flex;
  gap: 15px;
  font-size: 12px;
  color: #6c757d;
  margin-bottom: 5px;
}

.alert-message {
  font-size: 13px;
  color: #495057;
}
</style>