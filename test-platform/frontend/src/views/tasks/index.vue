<template>
  <div class="page-container">
    <div class="search-bar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索任务"
        clearable
        style="width: 300px"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      
      <el-select v-model="filterStatus" placeholder="状态筛选" clearable>
        <el-option label="等待中" value="pending" />
        <el-option label="执行中" value="running" />
        <el-option label="已完成" value="completed" />
        <el-option label="失败" value="failed" />
        <el-option label="已取消" value="cancelled" />
      </el-select>
      
      <el-button type="primary" @click="$router.push('/tasks/create')">
        <el-icon><Plus /></el-icon>
        新建任务
      </el-button>
    </div>
    
    <el-card class="app-card">
      <el-table :data="tasks" class="app-table" v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="任务名称" min-width="200">
          <template #default="{ row }">
            <el-link type="primary" @click="viewTask(row)">{{ row.name }}</el-link>
          </template>
        </el-table-column>
        <el-table-column prop="device_serial" label="设备" min-width="150">
          <template #default="{ row }">
            <el-tag size="small">{{ row.device_serial }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="180">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" effect="dark">
              {{ getStatusText(row.status) }}
            </el-tag>
            <el-tag
              v-if="row.status === 'completed' && row.result"
              :type="row.result === 'passed' ? 'success' : 'danger'"
              size="small"
              style="margin-left: 5px"
            >
              {{ row.result === 'passed' ? '全部通过' : '有失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="调度" min-width="150">
          <template #default="{ row }">
            <el-tag v-if="row.schedule_type === 'daily'" size="small" type="warning">
              每日 {{ row.scheduled_time }}
            </el-tag>
            <el-tag v-else-if="row.schedule_type === 'once' && row.next_run_at" size="small" type="warning">
              将于 {{ formatTime(row.next_run_at) }} 触发
            </el-tag>
            <span v-else-if="row.schedule_type === 'once'">定时一次（已触发）</span>
            <span v-else>立即执行</span>
          </template>
        </el-table-column>
        <el-table-column prop="progress_percent" label="进度" width="180">
          <template #default="{ row }">
            <el-progress
              :percentage="row.progress_percent"
              :status="getProgressStatus(row.status)"
            />
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'running'"
              text
              type="primary"
              @click="monitorTask(row)"
            >
              监控
            </el-button>
            <el-button
              v-if="row.status === 'completed' || row.status === 'failed'"
              text
              type="success"
              @click="viewReport(row)"
            >
              报告
            </el-button>
            <el-button
              v-if="(row.status === 'completed' || row.status === 'failed') && row.result === 'failed'"
              text
              type="warning"
              @click="rerunFailed(row)"
            >
              重跑失败项
            </el-button>
            <el-button
              v-if="row.status === 'pending' || row.status === 'running'"
              text
              type="danger"
              @click="cancelTask(row)"
            >
              取消
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @change="fetchTasks()"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Plus } from '@element-plus/icons-vue'
import { getTasks, cancelTask as cancelTaskApi, rerunFailedTasks } from '@/api/task'
import { formatDateTime } from '@/utils/datetime'
import { isSuccessResponse } from '@/api/client'

const router = useRouter()
const tasks = ref([])
const loading = ref(false)
const searchKeyword = ref('')
const filterStatus = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

// 有运行中/排队中任务时的轮询间隔（毫秒）
const POLL_INTERVAL = 10000
let pollTimer = null

const hasActiveTasks = computed(() =>
  tasks.value.some(task => task.status === 'running' || task.status === 'pending')
)

// 状态筛选变化：回到第一页重新按服务端条件查询
watch(filterStatus, () => {
  page.value = 1
  fetchTasks()
})

// 搜索输入防抖，避免每个字符都发请求
let searchTimer = null
watch(searchKeyword, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    fetchTasks()
  }, 300)
})

const fetchTasks = async (silent = false) => {
  if (!silent) loading.value = true
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value
    }
    // 状态与搜索均交给服务端过滤（分页前生效）
    if (filterStatus.value) params.status = filterStatus.value
    if (searchKeyword.value.trim()) params.search = searchKeyword.value.trim()

    const res = await getTasks(params)
    if (isSuccessResponse(res)) {
      tasks.value = res.data.items || []
      total.value = res.data.total || 0
    }
  } catch (error) {
    console.error('获取任务失败:', error)
  } finally {
    if (!silent) loading.value = false
  }
}

// 有运行中任务时每 10 秒静默刷新一次；页面隐藏时停止，可见时恢复并立即刷新
const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const startPolling = () => {
  stopPolling()
  pollTimer = setInterval(() => {
    if (hasActiveTasks.value) fetchTasks(true)
  }, POLL_INTERVAL)
}

const handleVisibilityChange = () => {
  if (document.hidden) {
    stopPolling()
  } else {
    if (hasActiveTasks.value) fetchTasks(true)
    startPolling()
  }
}

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
  if (status === 'failed') return 'exception'
  return ''
}

const formatTime = (time) => {
  return formatDateTime(time, 'YYYY-MM-DD HH:mm')
}

const viewTask = (task) => {
  if (task.status === 'running') {
    monitorTask(task)
  } else {
    viewReport(task)
  }
}

const monitorTask = (task) => {
  router.push(`/tasks/monitor/${task.id}`)
}

const viewReport = (task) => {
  router.push(`/reports?task_id=${task.id}`)
}

const rerunFailed = async (task) => {
  try {
    const res = await rerunFailedTasks(task.id)
    if (isSuccessResponse(res)) {
      ElMessage.success('已创建重跑任务')
      monitorTask(res.data)
    } else {
      ElMessage.error(res.message || '重跑失败')
    }
  } catch (error) {
    console.error('重跑失败项失败:', error)
    ElMessage.error(error.message || '重跑失败')
  }
}

const cancelTask = async (task) => {
  try {
    await ElMessageBox.confirm('确定取消该任务吗？', '提示', {
      type: 'warning'
    })
    const res = await cancelTaskApi(task.id)
    if (isSuccessResponse(res)) {
      ElMessage.success('任务已取消')
      fetchTasks()
    } else {
      ElMessage.error(res.message || '取消失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('取消任务失败:', error)
      ElMessage.error(error.message || '取消失败')
    }
  }
}

onMounted(() => {
  fetchTasks()
  startPolling()
  document.addEventListener('visibilitychange', handleVisibilityChange)
})

onUnmounted(() => {
  stopPolling()
  clearTimeout(searchTimer)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})
</script>

<style scoped lang="scss">
.app-table {
  margin-top: 20px;
}

.pagination-container {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid var(--tp-border-light);
}
</style>
