import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 10000
})

// 请求拦截器 - 添加JWT token
api.interceptors.request.use(
  config => {
    const token = localStorage.getItem('jwt_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  error => Promise.reject(error)
)

// 响应拦截器
api.interceptors.response.use(
  response => response.data,
  error => Promise.reject(error)
)

export default {
  // 获取仪表盘概览
  getDashboardOverview() {
    return api.get('/monitoring/dashboard/overview')
  },
  
  // 获取告警列表
  getAlerts(params) {
    return api.get('/monitoring/alerts', { params })
  },
  
  // 获取本地服务器列表
  getLocalServers(params) {
    return api.get('/cmdb/servers', { params })
  },
  
  // 获取云资源列表
  getCloudResources(params) {
    return api.get('/monitoring/cloud-resources', { params })
  },
  
  // 获取指标趋势数据
  getMetricTrend(params) {
    return api.get('/monitoring/metric-trend', { params })
  }
}