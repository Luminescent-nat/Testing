<template>
  <div class="page-container">
    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stat-row">
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card primary">
          <div class="stat-icon"><el-icon :size="28"><Cellphone /></el-icon></div>
          <div class="stat-content">
            <div class="stat-label">在线设备</div>
            <div class="stat-value">{{ stats.onlineDevices }}</div>
          </div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card success">
          <div class="stat-icon"><el-icon :size="28"><List /></el-icon></div>
          <div class="stat-content">
            <div class="stat-label">今日任务</div>
            <div class="stat-value">{{ stats.todayTasks }}</div>
          </div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card warning">
          <div class="stat-icon"><el-icon :size="28"><TrendCharts /></el-icon></div>
          <div class="stat-content">
            <div class="stat-label">通过率</div>
            <div class="stat-value">{{ stats.passRate }}%</div>
          </div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card danger">
          <div class="stat-icon"><el-icon :size="28"><Warning /></el-icon></div>
          <div class="stat-content">
            <div class="stat-label">失败任务</div>
            <div class="stat-value">{{ stats.failedTasks }}</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 统计图表 -->
    <el-row :gutter="20" class="chart-row">
      <el-col :xs="24" :lg="14">
        <el-card class="app-card chart-card">
          <template #header>
            <div class="card-header">
              <span><el-icon><TrendCharts /></el-icon> 最近 30 天任务趋势</span>
            </div>
          </template>
          <v-chart class="chart" :option="trendChartOption" autoresize />
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="10">
        <el-card class="app-card chart-card">
          <template #header>
            <div class="card-header">
              <span><el-icon><Histogram /></el-icon> 模块通过率</span>
            </div>
          </template>
          <div v-if="moduleStats.length === 0" class="empty-text">
            暂无统计数据
          </div>
          <v-chart v-else class="chart" :option="moduleChartOption" autoresize />
        </el-card>
      </el-col>
    </el-row>

    <!-- 快捷操作 -->
    <el-card class="app-card" style="margin-bottom: 20px;">
      <template #header>
        <div class="card-header">
          <span>快捷操作</span>
        </div>
      </template>
      <div class="quick-actions">
        <el-button type="primary" size="large" @click="$router.push('/tasks/create')">
          <el-icon><Plus /></el-icon>
          开始新测试
        </el-button>
        <el-button size="large" @click="$router.push('/devices')">
          <el-icon><Cellphone /></el-icon>
          查看设备
        </el-button>
        <el-button size="large" @click="$router.push('/tasks')">
          <el-icon><List /></el-icon>
          历史记录
        </el-button>
        <el-button size="large" @click="$router.push('/ai-test')">
          <el-icon><MagicStick /></el-icon>
          AI 测试
        </el-button>
      </div>
    </el-card>
    
    <!-- 设备列表和最近任务 -->
    <el-row :gutter="20">
      <el-col :xs="24" :lg="12">
        <el-card class="app-card">
          <template #header>
            <div class="card-header">
              <span><el-icon><Cellphone /></el-icon> 在线设备</span>
              <el-button text @click="refreshDevices">
                <el-icon><Refresh /></el-icon>
              </el-button>
            </div>
          </template>
          
          <div v-if="devices.length === 0" class="empty-text">
            暂无在线设备
          </div>
          
          <div v-else class="device-list">
            <div
              v-for="device in devices"
              :key="device.serial_number"
              class="device-item"
              @click="$router.push(`/devices?serial=${device.serial_number}`)"
            >
              <div class="device-info">
                <div class="device-name">{{ device.model || device.serial_number }}</div>
                <div class="device-meta">
                  <el-tag size="small" :type="device.status === 'online' ? 'success' : 'info'">
                    {{ device.status === 'online' ? '在线' : '离线' }}
                  </el-tag>
                  <span>Android {{ device.android_version }}</span>
                </div>
              </div>
              <el-icon><ArrowRight /></el-icon>
            </div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :xs="24" :lg="12">
        <el-card class="app-card">
          <template #header>
            <div class="card-header">
              <span><el-icon><List /></el-icon> 最近测试</span>
              <el-button text @click="$router.push('/tasks')">
                查看更多
              </el-button>
            </div>
          </template>
          
          <div v-if="recentTasks.length === 0" class="empty-text">
            暂无测试记录
          </div>
          
          <div v-else class="task-list">
            <div
              v-for="task in recentTasks"
              :key="task.id"
              class="task-item"
              @click="$router.push(`/tasks/monitor/${task.id}`)"
            >
              <div class="task-info">
                <div class="task-name">{{ task.name }}</div>
                <div class="task-meta">
                  <el-tag
                    size="small"
                    :type="getTaskStatusType(task.status)"
                  >
                    {{ getTaskStatusText(task.status) }}
                  </el-tag>
                  <span>{{ formatTime(task.created_at) }}</span>
                </div>
              </div>
              <el-icon><ArrowRight /></el-icon>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Plus, Cellphone, List, Refresh, ArrowRight, MagicStick, TrendCharts, Warning, Histogram } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { getDevices, getTasks, refreshDevices as refreshDevicesApi } from '@/api'
import { getStatsTrend, getStatsByModule } from '@/api/report'
import { formatDateTime } from '@/utils/datetime'

use([LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const stats = ref({
  onlineDevices: 0,
  todayTasks: 0,
  passRate: 0,
  failedTasks: 0
})

const devices = ref([])
const recentTasks = ref([])

const trendData = ref([])
const moduleStats = ref([])

// 任务趋势图：通过/失败堆叠柱状 + 通过率折线（右轴）
const trendChartOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: ['通过', '失败', '通过率'] },
  grid: { left: 45, right: 50, top: 40, bottom: 30 },
  xAxis: {
    type: 'category',
    data: trendData.value.map(i => i.date.slice(5))
  },
  yAxis: [
    { type: 'value', name: '任务数', minInterval: 1 },
    { type: 'value', name: '通过率', max: 100, axisLabel: { formatter: '{value}%' } }
  ],
  series: [
    {
      name: '通过',
      type: 'bar',
      stack: 'task',
      data: trendData.value.map(i => i.passed),
      itemStyle: { color: '#67c23a' }
    },
    {
      name: '失败',
      type: 'bar',
      stack: 'task',
      data: trendData.value.map(i => i.failed),
      itemStyle: { color: '#f56c6c' }
    },
    {
      name: '通过率',
      type: 'line',
      yAxisIndex: 1,
      smooth: true,
      data: trendData.value.map(i => i.pass_rate),
      itemStyle: { color: '#409eff' }
    }
  ]
}))

// 模块通过率横向柱状图
const moduleChartOption = computed(() => ({
  tooltip: {
    trigger: 'axis',
    formatter: (params) => {
      const item = moduleStats.value[params[0].dataIndex]
      return `${item.module_name}<br/>通过率：${item.pass_rate}%（${item.passed}/${item.total}）`
    }
  },
  grid: { left: 10, right: 45, top: 20, bottom: 10, containLabel: true },
  xAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' } },
  yAxis: { type: 'category', data: moduleStats.value.map(i => i.module_name) },
  series: [
    {
      name: '通过率',
      type: 'bar',
      data: moduleStats.value.map(i => i.pass_rate),
      itemStyle: { color: '#409eff' },
      label: { show: true, position: 'right', formatter: '{c}%' }
    }
  ]
}))

const fetchTrend = async () => {
  try {
    const res = await getStatsTrend(30)
    if (res.code === 200) {
      trendData.value = res.data.series || []
    }
  } catch (error) {
    console.error('获取任务趋势失败:', error)
  }
}

const fetchModuleStats = async () => {
  try {
    const res = await getStatsByModule()
    if (res.code === 200) {
      moduleStats.value = res.data.items || []
    }
  } catch (error) {
    console.error('获取模块统计失败:', error)
  }
}

const refreshDevices = async () => {
  try {
    const res = await refreshDevicesApi()
    if (res.code === 200) {
      devices.value = res.data.items || []
      stats.value.onlineDevices = devices.value.filter(d => d.status === 'online').length
      ElMessage.success('刷新成功')
    }
  } catch (error) {
    console.error('刷新设备失败:', error)
  }
}

const fetchTasks = async () => {
  try {
    const res = await getTasks({ page_size: 5 })
    if (res.code === 200) {
      recentTasks.value = res.data.items || []
      stats.value.todayTasks = recentTasks.value.length
      const total = recentTasks.value.length
      const passed = recentTasks.value.filter(t => t.status === 'completed').length
      const failed = recentTasks.value.filter(t => t.status === 'failed').length
      stats.value.passRate = total ? Math.round((passed / total) * 100) : 0
      stats.value.failedTasks = failed
    }
  } catch (error) {
    console.error('获取任务失败:', error)
  }
}

const getTaskStatusType = (status) => {
  const types = {
    'completed': 'success',
    'running': 'warning',
    'failed': 'danger',
    'pending': 'info'
  }
  return types[status] || 'info'
}

const getTaskStatusText = (status) => {
  const texts = {
    'completed': '已完成',
    'running': '执行中',
    'failed': '失败',
    'pending': '等待中'
  }
  return texts[status] || status
}

const formatTime = (time) => {
  return formatDateTime(time, 'MM-DD HH:mm')
}

onMounted(() => {
  refreshDevices()
  fetchTasks()
  fetchTrend()
  fetchModuleStats()
})
</script>

<style scoped lang="scss">
.stat-row {
  margin-bottom: 20px;
}

.chart-row {
  margin-bottom: 20px;
}

.chart-card {
  margin-bottom: 20px;
}

.chart {
  height: 320px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  border-radius: 12px;
  color: white;
  margin-bottom: 20px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  
  &.primary { background: linear-gradient(135deg, #409eff 0%, #66b1ff 100%); }
  &.success { background: linear-gradient(135deg, #67c23a 0%, #85ce61 100%); }
  &.warning { background: linear-gradient(135deg, #e6a23c 0%, #ebb563 100%); }
  &.danger { background: linear-gradient(135deg, #f56c6c 0%, #f78989 100%); }
  
  .stat-icon {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.2);
    display: flex;
    align-items: center;
    justify-content: center;
  }
  
  .stat-content {
    flex: 1;
    
    .stat-label {
      font-size: 14px;
      opacity: 0.9;
      margin-bottom: 6px;
    }
    
    .stat-value {
      font-size: 28px;
      font-weight: 700;
    }
  }
}

.quick-actions {
  display: flex;
  gap: 15px;
  flex-wrap: wrap;
  
  .el-button {
    display: flex;
    align-items: center;
    gap: 5px;
  }
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  
  .el-icon {
    vertical-align: middle;
    margin-right: 4px;
  }
}

.device-list,
.task-list {
  .device-item,
  .task-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 15px;
    border-bottom: 1px solid var(--tp-border-light);
    cursor: pointer;
    transition: background-color 0.3s;
    border-radius: 8px;
    
    &:hover {
      background-color: var(--tp-bg-page);
    }
    
    &:last-child {
      border-bottom: none;
    }
    
    .device-info,
    .task-info {
      flex: 1;
      
      .device-name,
      .task-name {
        font-weight: 500;
        margin-bottom: 5px;
        color: var(--tp-text);
      }
      
      .device-meta,
      .task-meta {
        display: flex;
        align-items: center;
        gap: 10px;
        color: var(--tp-text-secondary);
        font-size: 13px;
      }
    }
  }
}

.empty-text {
  text-align: center;
  padding: 40px;
  color: var(--tp-text-tertiary);
}
</style>
