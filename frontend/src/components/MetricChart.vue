<template>
  <div ref="chartRef" class="metric-chart"></div>
</template>

<script setup>
import { ref, onMounted, watch, onUnmounted } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  option: {
    type: Object,
    required: true
  },
  height: {
    type: String,
    default: '300px'
  }
})

const chartRef = ref(null)
let chart = null

const initChart = () => {
  chart = echarts.init(chartRef.value)
  chart.setOption(props.option)
}

const handleResize = () => {
  if (chart) {
    chart.resize()
  }
}

watch(() => props.option, (newOption) => {
  if (chart) {
    chart.setOption(newOption)
  }
}, { deep: true })

onMounted(() => {
  initChart()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (chart) {
    chart.dispose()
  }
})
</script>

<style scoped>
.metric-chart {
  width: 100%;
  height: v-bind(height);
}
</style>