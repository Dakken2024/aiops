<template>
  <div class="dashboard-container">
    <!-- 顶部统计卡片 -->
    <div class="row mb-4">
      <div class="col-lg-3 col-md-6 mb-3">
        <div class="stat-card card-success">
          <div class="stat-icon">
            <i class="fas fa-server"></i>
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ overview.servers?.total || 0 }}</div>
            <div class="stat-label">服务器总数</div>
          </div>
        </div>
      </div>
      <div class="col-lg-3 col-md-6 mb-3">
        <div class="stat-card card-primary">
          <div class="stat-icon">
            <i class="fas fa-play-circle"></i>
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ overview.servers?.up || 0 }}</div>
            <div class="stat-label">运行中</div>
          </div>
        </div>
      </div>
      <div class="col-lg-3 col-md-6 mb-3">
        <div class="stat-card card-danger">
          <div class="stat-icon">
            <i class="fas fa-exclamation-triangle"></i>
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ overview.alerts?.firing || 0 }}</div>
            <div class="stat-label">活跃告警</div>
          </div>
        </div>
      </div>
      <div class="col-lg-3 col-md-6 mb-3">
        <div class="stat-card card-info">
          <div class="stat-icon">
            <i class="fas fa-shield-alt"></i>
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ overview.alerts?.sla_24h || 100 }}%</div>
            <div class="stat-label">24h SLA</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 图表区域 -->
    <div class="row mb-4">
      <div class="col-lg-8">
        <div class="card">
          <div class="card-header">
            <h5 class="mb-0"><i class="fas fa-chart-line mr-2"></i>告警趋势 (7天)</h5>
          </div>
          <div class="card-body">
            <MetricChart :option="alertTrendOption" height="300px" />
          </div>
        </div>
      </div>
      <div class="col-lg-4">
        <AlertList :alerts="alerts" />
      </div>
    </div>

    <!-- 服务器列表 -->
    <div class="row">
      <div class="col-12">
        <ServerList :servers="servers" />
      </div>
    </div>

    <!-- 自动刷新指示器 -->
    <div class="refresh-indicator">
      <i :class="isRefreshing ? 'fas fa-sync fa-spin' : 'fas fa-sync'"></i>
      自动刷新 ({{ refreshInterval }}s)
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import MetricChart from './MetricChart.vue'
import AlertList from './AlertList.vue'
import ServerList from './ServerList.vue'
import api from '../api'

const overview = ref({})
const alerts = ref([])
const servers = ref([])
const isRefreshing = ref(false)
const refreshInterval = ref(5)
let refreshTimer = null

const alertTrendOption = computed(() => {
  const trend = overview.value.trend?.alerts_7d || []
  const dates = []
  const now = new Date()
  for (let i = 6; i >= 0; i--) {
    const d = new Date(now)
    d.setDate(d.getDate() - i)
    dates.push(`${d.getMonth() + 1}/${d.getDate()}`)
  }
  
  return {
    tooltip: {
      trigger: 'axis'
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false
    },
    yAxis: {
      type: 'value'
    },
    series: [
      {
        name: '告警数',
        type: 'line',
        smooth: true,
        data: trend.length ? trend : [0, 0, 0, 0, 0, 0, 0],
        areaStyle: {
          color: 'rgba(220, 53, 69, 0.1)'
        },
        lineStyle: {
          color: '#dc3545',
          width: 2
        },
        itemStyle: {
          color: '#dc3545'
        }
      }
    ]
  }
})

const loadDashboardData = async () => {
  isRefreshing.value = true
  try {
    // 加载概览数据
    try {
      const overviewData = await api.getDashboardOverview()
      if (overviewData.code === 0) {
        overview.value = overviewData.data
      }
    } catch (e) {
      console.warn('获取概览数据失败:', e)
    }

    // 加载告警数据
    try {
      const alertsData = await api.getAlerts({ status: 'firing', page_size: 10 })
      if (alertsData.code === 0) {
        alerts.value = alertsData.data?.items || []
      }
    } catch (e) {
      console.warn('获取告警数据失败:', e)
    }

    // 加载服务器数据
    try {
      const serversData = await api.getLocalServers({ page_size: 20 })
      if (serversData.code === 0) {
        servers.value = serversData.data?.items || []
      }
    } catch (e) {
      console.warn('获取服务器数据失败:', e)
    }
  } catch (error) {
    console.error('加载仪表盘数据失败:', error)
  } finally {
    isRefreshing.value = false
  }
}

onMounted(() => {
  loadDashboardData()
  // 自动刷新
  refreshTimer = setInterval(loadDashboardData, refreshInterval.value * 1000)
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }
})
</script>

<style scoped>
.dashboard-container {
  padding: 20px;
  background: #f5f7fa;
  min-height: 100vh;
}

.stat-card {
  display: flex;
  align-items: center;
  padding: 20px;
  border-radius: 8px;
  color: white;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.stat-card.card-success {
  background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
}

.stat-card.card-primary {
  background: linear-gradient(135deg, #007bff 0%, #6610f2 100%);
}

.stat-card.card-danger {
  background: linear-gradient(135deg, #dc3545 0%, #e83e8c 100%);
}

.stat-card.card-info {
  background: linear-gradient(135deg, #17a2b8 0%, #6f42c1 100%);
}

.stat-icon {
  font-size: 48px;
  opacity: 0.8;
  margin-right: 20px;
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: 36px;
  font-weight: 700;
  line-height: 1.2;
}

.stat-label {
  font-size: 14px;
  opacity: 0.9;
}

.card {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  height: 100%;
}

.card-header {
  background: #f8f9fa;
  border-bottom: 1px solid #e9ecef;
  padding: 15px 20px;
  border-radius: 8px 8px 0 0;
}

.card-body {
  padding: 20px;
}

.refresh-indicator {
  position: fixed;
  bottom: 20px;
  right: 20px;
  background: white;
  padding: 10px 20px;
  border-radius: 30px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  font-size: 14px;
  color: #495057;
}

.refresh-indicator i {
  margin-right: 8px;
}
</style>