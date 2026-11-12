<template>
  <div class="page-container">
    <div class="task-header">
      <div class="task-title">
        <h2>{{ task?.name || '任务监控' }}</h2>
        <el-tag :type="getStatusType(task?.status)" size="large" effect="dark">
          {{ getStatusText(task?.status) }}
        </el-tag>
        <el-tag
          v-if="task?.status === 'completed' && task?.result"
          :type="task.result === 'passed' ? 'success' : 'danger'"
          size="large"
        >
          {{ task.result === 'passed' ? '全部通过' : '有失败' }}
        </el-tag>
      </div>
      <div class="task-actions">
        <el-button v-if="task?.status === 'running'" type="danger" @click="handleCancelTask">
          取消任务
        </el-button>
        <el-button @click="$router.back()">返回</el-button>
      </div>
    </div>

    <!-- 总体进度 -->
    <el-card class="app-card" style="margin-bottom: 20px;">
      <div class="progress-section">
        <div class="progress-info">
          <div class="progress-text">
            <span class="label">总体进度</span>
            <span class="value">{{ task?.progress_percent || 0 }}%</span>
          </div>
          <div class="progress-stats">
            <span>已完成: {{ completedCount }}/{{ totalCount }} 项</span>
            <span v-if="elapsedTime">已耗时: {{ elapsedTime }}</span>
          </div>
        </div>
        <el-progress
          :percentage="task?.progress_percent || 0"
          :status="getProgressStatus(task?.status)"
          :stroke-width="20"
          striped
          :striped-flow="task?.status === 'running'"
        />
      </div>
    </el-card>

    <!-- 设备占用与 AI 规划 -->
    <el-row :gutter="20" style="margin-bottom: 20px;">
      <el-col :span="12">
        <el-card class="app-card">
          <template #header>
            <span>设备占用状态</span>
          </template>
          <div v-if="task?.device" class="device-info">
            <div class="info-row">
              <span class="label">设备型号</span>
              <span class="value">{{ task.device.model || task.device.serial_number }}</span>
            </div>
            <div class="info-row">
              <span class="label">序列号</span>
              <span class="value">{{ task.device.serial_number }}</span>
            </div>
            <div class="info-row">
              <span class="label">Android / CPU</span>
              <span class="value">{{ task.device.android_version || '-' }} / {{ task.device.cpu_abi || '-' }}</span>
            </div>
            <div class="info-row">
              <span class="label">当前占用者</span>
              <span class="value">{{ task.executor?.username || '当前用户' }}</span>
            </div>
            <div class="info-row">
              <span class="label">预计剩余时间</span>
              <span class="value">{{ estimatedRemainingTime || '-' }}</span>
            </div>
          </div>
          <el-empty v-else description="暂无设备信息" />
        </el-card>
      </el-col>

      <el-col :span="12" v-if="task?.plan">
        <el-card class="app-card">
          <template #header>
            <span>AI 规划结果</span>
          </template>
          <div class="plan-info">
            <div class="info-row">
              <span class="label">识别到的设备</span>
              <span class="value">{{ task.plan.device_serial }}</span>
            </div>
            <div class="info-row">
              <span class="label">测试意图</span>
              <span class="value">{{ task.plan.intent }}</span>
            </div>
            <div class="info-row">
              <span class="label">识别模块</span>
              <span class="value">
                <el-tag
                  v-for="m in task.plan.selected_modules"
                  :key="m"
                  size="small"
                  style="margin-right: 5px"
                >
                  {{ m }}
                </el-tag>
              </span>
            </div>
            <div class="info-row">
              <span class="label">测试类型</span>
              <span class="value">{{ task.plan.test_type }}</span>
            </div>
            <div class="info-row">
              <span class="label">选中测试项</span>
              <span class="value">{{ task.plan.item_ids?.length || 0 }} 项</span>
            </div>
            <el-alert
              v-if="!task.plan.llm_available"
              title="当前使用规则匹配完成规划"
              description="可在后端 .env 配置 LLM_API_KEY 启用 AI 增强理解"
              type="info"
              :closable="false"
              style="margin-top: 12px"
            />
            <el-alert
              v-else-if="task.plan.llm_used"
              title="已使用 AI 增强理解"
              type="success"
              :closable="false"
              style="margin-top: 12px"
            />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 执行流程时间线 -->
    <el-card class="app-card" style="margin-bottom: 20px;">
      <template #header>
        <span>执行流程</span>
      </template>
      <div v-if="testItems.length === 0" class="empty-text">
        暂无执行记录
      </div>
      <el-timeline v-else class="execution-timeline">
        <el-timeline-item
          v-for="(item, index) in testItems"
          :key="item.id"
          :type="getRecordStatusType(item.status)"
          :hollow="item.status === 'pending'"
          :timestamp="item.execution_time ? `${item.execution_time}s` : ''"
          placement="top"
        >
          <div
            class="timeline-node"
            :class="{ clickable: item.status !== 'pending' && item.status !== 'running' }"
            @click="(item.status !== 'pending' && item.status !== 'running') && viewItemLog(item)"
          >
            <div class="node-index">{{ index + 1 }}</div>
            <div class="node-content">
              <div class="node-name">{{ item.name }}</div>
              <div class="node-meta">{{ item.module_name }}</div>
            </div>
            <div class="node-status">
              <el-tag :type="getRecordStatusType(item.status)" size="small" effect="dark">
                {{ getRecordStatusText(item.status) }}
              </el-tag>
            </div>
          </div>
        </el-timeline-item>
      </el-timeline>
    </el-card>

    <!-- 测试项列表 -->
    <el-card class="app-card">
      <template #header>
        <span>执行详情</span>
      </template>

      <div v-if="testItems.length === 0" class="empty-text">
        暂无执行记录
      </div>

      <div v-else class="test-items">
        <div
          v-for="(item, index) in testItems"
          :key="item.id"
          class="test-item"
          :class="{ active: currentItem?.id === item.id }"
        >
          <div class="item-header">
            <div class="item-index">{{ index + 1 }}</div>
            <div class="item-info">
              <div class="item-name">{{ item.name }}</div>
              <div class="item-module">{{ item.module_name }}</div>
            </div>
            <div class="item-status">
              <el-icon v-if="item.status === 'running'" class="rotating">
                <Loading />
              </el-icon>
              <el-icon v-else-if="item.status === 'pass'" color="#67c23a">
                <CircleCheckFilled />
              </el-icon>
              <el-icon v-else-if="item.status === 'fail'" color="#f56c6c">
                <CircleCloseFilled />
              </el-icon>
              <el-icon v-else-if="item.status === 'error'" color="#f56c6c">
                <CircleCloseFilled />
              </el-icon>
              <el-icon v-else-if="item.status === 'timeout'" color="#f56c6c">
                <CircleCloseFilled />
              </el-icon>
              <el-icon v-else-if="item.status === 'skip'" color="#909399">
                <WarningFilled />
              </el-icon>
              <el-icon v-else color="#e6a23c">
                <Timer />
              </el-icon>
            </div>
          </div>

          <div v-if="item.status === 'running' || item.status === 'fail' || item.status === 'error' || item.status === 'timeout'" class="item-detail">
            <div v-if="item.status === 'running'" class="running-info">
              <pre class="log-preview live-log">{{ getLiveLog(item) || '执行中，等待输出...' }}</pre>
            </div>
            <div v-if="item.status === 'fail' || item.status === 'error' || item.status === 'timeout'" class="fail-info">
              <el-alert
                :title="item.fail_reason || '执行失败'"
                type="error"
                :closable="false"
              />
            </div>
          </div>

          <div class="item-footer">
            <span v-if="item.execution_time" class="execution-time">
              耗时: {{ item.execution_time }}秒
            </span>
            <span v-if="item.extracted_data" class="extracted-data">
              结果: {{ JSON.stringify(item.extracted_data) }}
            </span>
            <el-button
              v-if="item.status && item.status !== 'pending'"
              text
              type="primary"
              size="small"
              @click="handleDownloadLog(item)"
            >
              下载完整日志
            </el-button>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 实时日志 -->
    <el-card class="app-card" style="margin-top: 20px;">
      <template #header>
        <div class="log-header">
          <span>实时日志</span>
          <el-button text @click="clearLog">
            <el-icon><Delete /></el-icon>
            清空
          </el-button>
        </div>
      </template>

      <div v-if="logTruncated" class="log-truncated-tip">
        日志过长，仅显示最近 {{ MAX_LOG_LINES }} 行，可点击测试项的“下载完整日志”获取全部内容
      </div>
      <div class="log-container" ref="logContainer">
        <pre class="log-content">{{ logContent || '等待执行...' }}</pre>
      </div>
    </el-card>

    <!-- 测试项日志弹窗 -->
    <el-dialog
      v-model="showLogDialog"
      title="测试项日志"
      width="800px"
    >
      <div v-loading="logLoading" class="log-detail">
        <el-descriptions :column="1" border v-if="currentLog">
          <el-descriptions-item label="测试项">{{ currentLog.item_name }}</el-descriptions-item>
          <el-descriptions-item label="模块">{{ currentLog.module_name }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="getRecordStatusType(currentLog.status)" size="small">
              {{ getRecordStatusText(currentLog.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="失败原因">{{ currentLog.fail_reason || '-' }}</el-descriptions-item>
        </el-descriptions>
        <pre v-if="currentLog?.output" class="log-output">{{ currentLog.output }}</pre>
        <el-empty v-else description="无日志输出" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Loading, CircleCheckFilled, CircleCloseFilled,
  WarningFilled, Timer, Delete
} from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import { getTaskDetail, getTaskRecords, cancelTask, downloadRecordLog } from '@/api/task'
import { getItemLog } from '@/api/report'
import { isSuccessResponse } from '@/api/client'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const taskId = route.params.id

// 日志面板最多渲染的行数，防止长压测把页面拖垮
const MAX_LOG_LINES = 2000

const task = ref(null)
const testItems = ref([])
// 全局日志面板按行存储，超出 MAX_LOG_LINES 时丢弃最早的行
const logLines = ref([])
const logTruncated = ref(false)
// record_id -> 实时日志行（原始行含换行符），执行中的测试项用于展示实时输出
const liveLogs = reactive({})
const logContent = computed(() => logLines.value.join('\n'))
const currentItem = ref(null)
const ws = ref(null)
const logContainer = ref(null)
const showLogDialog = ref(false)
const logLoading = ref(false)
const currentLog = ref(null)
const selectedItemId = ref(null)

const completedCount = computed(() => {
  return testItems.value.filter(item => ['pass', 'fail', 'skip', 'error', 'timeout'].includes(item.status)).length
})

const totalCount = computed(() => testItems.value.length)

const elapsedTime = computed(() => {
  if (!task.value?.started_at) return ''
  const start = new Date(task.value.started_at)
  const end = task.value.completed_at ? new Date(task.value.completed_at) : new Date()
  const diff = Math.floor((end - start) / 1000)
  const minutes = Math.floor(diff / 60)
  const seconds = diff % 60
  return `${minutes}分${seconds}秒`
})

const getStatusType = (status) => {
  const types = {
    'completed': 'success',
    'running': 'warning',
    'failed': 'danger',
    'pending': 'info',
    'cancelled': 'info'
  }
  return types[status] || 'info'
}

const getStatusText = (status) => {
  const texts = {
    'completed': '已完成',
    'running': '执行中',
    'failed': '失败',
    'pending': '等待中',
    'cancelled': '已取消'
  }
  return texts[status] || status
}

const getProgressStatus = (status) => {
  if (status === 'completed') return 'success'
  if (status === 'failed' || status === 'cancelled') return 'exception'
  return ''
}

const getRecordStatusType = (status) => {
  const types = {
    'pass': 'success',
    'fail': 'danger',
    'skip': 'info',
    'error': 'warning',
    'timeout': 'danger',
    'running': 'warning',
    'pending': 'info'
  }
  return types[status] || 'info'
}

const getRecordStatusText = (status) => {
  const texts = {
    'pass': '通过',
    'fail': '失败',
    'skip': '跳过',
    'error': '错误',
    'timeout': '超时',
    'running': '执行中',
    'pending': '等待中'
  }
  return texts[status] || status
}

const estimatedRemainingTime = computed(() => {
  if (!task.value?.started_at || !['running', 'pending'].includes(task.value?.status)) return ''
  const completed = completedCount.value
  const total = totalCount.value
  if (!completed || !total || completed >= total) return ''

  const start = new Date(task.value.started_at)
  const now = new Date()
  const elapsedSec = Math.floor((now - start) / 1000)
  const avgPerItem = elapsedSec / completed
  const remainingSec = Math.ceil(avgPerItem * (total - completed))
  const minutes = Math.floor(remainingSec / 60)
  const seconds = remainingSec % 60
  return minutes > 0 ? `约 ${minutes}分${seconds}秒` : `约 ${seconds}秒`
})

const viewItemLog = async (item) => {
  selectedItemId.value = item.id
  logLoading.value = true
  showLogDialog.value = true
  currentLog.value = null
  try {
    const res = await getItemLog(taskId, item.item_id)
    if (isSuccessResponse(res)) {
      currentLog.value = {
        ...res.data,
        item_name: item.name,
        module_name: item.module_name
      }
    }
  } catch (error) {
    console.error('获取日志失败:', error)
    ElMessage.error('获取日志失败')
    showLogDialog.value = false
  } finally {
    logLoading.value = false
  }
}

const appendToLogPanel = (text) => {
  if (!text) return
  const lines = String(text).split('\n')
  if (lines.length && lines[lines.length - 1] === '') lines.pop()
  logLines.value.push(...lines)
  if (logLines.value.length > MAX_LOG_LINES) {
    logLines.value.splice(0, logLines.value.length - MAX_LOG_LINES)
    logTruncated.value = true
  }
  nextTick(() => {
    if (logContainer.value) {
      logContainer.value.scrollTop = logContainer.value.scrollHeight
    }
  })
}

const appendLog = (text) => {
  if (!text) return
  const time = new Date().toLocaleTimeString()
  appendToLogPanel(`[${time}] ${text}`)
}

// 测试项对应的记录ID：records 接口返回的 id 即记录ID，WS 进度消息带 record_id
const recordIdOf = (item) => item.record_id || item.id

const getLiveLog = (item) => {
  const lines = liveLogs[recordIdOf(item)]
  return lines ? lines.join('') : ''
}

const handleDownloadLog = async (item) => {
  const recordId = recordIdOf(item)
  try {
    const blob = await downloadRecordLog(recordId)
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `record_${recordId}.log`
    link.click()
    window.URL.revokeObjectURL(url)
  } catch (error) {
    // 404 等错误已由 request 拦截器提示
    console.error('下载日志失败:', error)
  }
}

const fetchTaskData = async () => {
  try {
    const [taskRes, recordsRes] = await Promise.all([
      getTaskDetail(taskId),
      getTaskRecords(taskId)
    ])

    if (isSuccessResponse(taskRes)) {
      task.value = taskRes.data
    }

    if (isSuccessResponse(recordsRes)) {
      const items = recordsRes.data.items || []
      testItems.value = items
      currentItem.value = items.find(item => item.status === 'running') || null

      // 更新日志内容（按行存储并限制总行数）
      const logs = items
        .filter(item => item.output)
        .map(item => `=== ${item.module_name} / ${item.name} ===\n${item.output}`)
      logLines.value = logs.length ? logs.join('\n\n').split('\n') : []
      if (logLines.value.length > MAX_LOG_LINES) {
        logLines.value = logLines.value.slice(-MAX_LOG_LINES)
        logTruncated.value = true
      }
    }
  } catch (error) {
    console.error('获取任务数据失败:', error)
  }
}

const connectWebSocket = () => {
  if (!userStore.token) return

  // 按当前页面地址推导同源 WS 地址：开发环境经 vite 代理 /ws 转发到后端，
  // 生产环境前后端同源部署；token 不再放 URL，改为连接建立后首条消息认证
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${window.location.host}/ws/tasks/${taskId}`

  ws.value = new WebSocket(wsUrl)

  ws.value.onopen = () => {
    // 首条消息发送 token 完成认证
    ws.value.send(JSON.stringify({ token: userStore.token }))
    appendLog('WebSocket 已连接')
  }

  ws.value.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data)
      handleWebSocketMessage(message)
    } catch (error) {
      appendLog(`收到非 JSON 消息: ${event.data}`)
    }
  }

  ws.value.onerror = (error) => {
    console.error('WebSocket 错误:', error)
    appendLog('WebSocket 连接错误')
  }

  ws.value.onclose = () => {
    appendLog('WebSocket 已断开')
    // 如果任务还在运行，尝试重连
    if (task.value?.status === 'running') {
      setTimeout(connectWebSocket, 3000)
    }
  }
}

const handleWebSocketMessage = (message) => {
  if (message.type === 'pong') return

  // 实时日志行：追加到对应记录的日志流和全局日志面板
  if (message.type === 'log') {
    const recordId = message.record_id
    const line = message.line ?? ''
    if (recordId != null) {
      if (!liveLogs[recordId]) liveLogs[recordId] = []
      liveLogs[recordId].push(line)
      if (liveLogs[recordId].length > MAX_LOG_LINES) {
        liveLogs[recordId].splice(0, liveLogs[recordId].length - MAX_LOG_LINES)
      }
    }
    appendToLogPanel(line)
    return
  }

  if (message.type !== 'test_progress') return

  const data = message.data || {}
  if (data.task_status) {
    task.value = { ...task.value, status: data.task_status, progress_percent: data.progress_percent }
  }

  if (data.completed_results) {
    testItems.value = [...data.completed_results]
  }
  if (data.current_item) {
    currentItem.value = data.current_item
    // 避免 current_item 和 completed_results 重复
    const exists = testItems.value.find(item => item.id === data.current_item.id)
    if (!exists) {
      testItems.value.push(data.current_item)
    }
  }

  appendLog(`进度更新: ${data.completed_items || 0}/${data.total_items || 0} (${data.progress_percent || 0}%)`)

  // 任务结束后刷新完整数据
  if (['completed', 'failed', 'cancelled'].includes(data.task_status)) {
    fetchTaskData()
  }
}

const handleCancelTask = async () => {
  try {
    await ElMessageBox.confirm('确定取消该任务吗？', '提示', {
      type: 'warning'
    })
    await cancelTask(taskId)
    ElMessage.success('任务已取消')
  } catch {
    // 取消操作
  }
}

const clearLog = () => {
  logLines.value = []
  logTruncated.value = false
}

onMounted(() => {
  fetchTaskData()
  connectWebSocket()
})

onUnmounted(() => {
  if (ws.value) {
    ws.value.close()
    ws.value = null
  }
})
</script>

<style scoped lang="scss">
.task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;

  .task-title {
    display: flex;
    align-items: center;
    gap: 15px;

    h2 {
      margin: 0;
      color: var(--tp-text);
    }
  }
}

.device-info,
.plan-info {
  .info-row {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: 8px 0;
    border-bottom: 1px solid var(--tp-border-light);

    &:last-child {
      border-bottom: none;
    }
  }

  .label {
    font-size: 13px;
    color: var(--tp-text-secondary);
  }

  .value {
    font-size: 13px;
    color: var(--tp-text);
    text-align: right;
    max-width: 60%;
  }
}

.execution-timeline {
  padding-left: 10px;

  .timeline-node {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px;
    border-radius: 8px;
    transition: background-color 0.3s;

    &.clickable {
      cursor: pointer;

      &:hover {
        background-color: var(--tp-bg-page);
      }
    }
  }

  .node-index {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background-color: var(--el-color-primary-light-9);
    color: var(--el-color-primary);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
    font-weight: 600;
  }

  .node-content {
    flex: 1;

    .node-name {
      font-weight: 500;
      font-size: 14px;
    }

    .node-meta {
      font-size: 12px;
      color: var(--tp-text-secondary);
      margin-top: 2px;
    }
  }
}

.log-detail {
  .log-output {
    background-color: var(--tp-bg-page);
    border: 1px solid var(--tp-border-light);
    border-radius: 6px;
    padding: 15px;
    margin-top: 15px;
    font-family: monospace;
    font-size: 12px;
    color: var(--tp-text);
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 500px;
    overflow-y: auto;
  }
}

.progress-section {
  .progress-info {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 15px;

    .progress-text {
      .label {
        font-size: 14px;
        color: var(--tp-text-secondary);
        margin-right: 10px;
      }

      .value {
        font-size: 24px;
        font-weight: bold;
        color: var(--tp-text);
      }
    }

    .progress-stats {
      display: flex;
      gap: 20px;
      color: var(--tp-text-secondary);
      font-size: 14px;
    }
  }
}

.test-items {
  .test-item {
    padding: 15px;
    border-bottom: 1px solid var(--tp-border-light);
    transition: background-color 0.3s;

    &:hover {
      background-color: var(--tp-bg-page);
    }

    &.active {
      background-color: var(--el-color-primary-light-9);
      border-left: 3px solid var(--el-color-primary);
    }

    &:last-child {
      border-bottom: none;
    }

    .item-header {
      display: flex;
      align-items: center;
      gap: 15px;

      .item-index {
        width: 28px;
        height: 28px;
        border-radius: 50%;
        background-color: var(--tp-bg-page);
        color: var(--tp-text-secondary);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 13px;
      }

      .item-info {
        flex: 1;

        .item-name {
          font-weight: 500;
          color: var(--tp-text);
          margin-bottom: 3px;
        }

        .item-module {
          font-size: 12px;
          color: var(--tp-text-tertiary);
        }
      }

      .item-status {
        .el-icon {
          font-size: 24px;

          &.rotating {
            animation: rotate 1s linear infinite;
          }
        }
      }
    }

    .item-detail {
      margin-top: 10px;
      padding-left: 43px;

      .running-info {
        .log-preview {
          margin-top: 8px;
          padding: 8px;
          background-color: var(--tp-bg-page);
          border-radius: 4px;
          font-family: monospace;
          font-size: 12px;
          color: var(--tp-text-secondary);

          &.live-log {
            max-height: 200px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-break: break-all;
          }
        }
      }
    }

    .item-footer {
      margin-top: 10px;
      padding-left: 43px;
      display: flex;
      gap: 15px;
      font-size: 12px;
      color: var(--tp-text-tertiary);
    }
  }
}

.log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.log-truncated-tip {
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--el-color-warning);
}

.log-container {
  height: 300px;
  overflow-y: auto;
  background-color: var(--tp-bg-page);
  border-radius: 4px;
  padding: 15px;

  .log-content {
    margin: 0;
    font-family: 'Courier New', monospace;
    font-size: 13px;
    line-height: 1.6;
    color: var(--tp-text-secondary);
    white-space: pre-wrap;
    word-break: break-all;
  }
}

.empty-text {
  text-align: center;
  padding: 40px;
  color: var(--tp-text-tertiary);
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(180deg); }
}
</style>
