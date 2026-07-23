<template>
  <div class="page-container">
    <div class="search-bar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索任务名称 / 设备型号"
        clearable
        style="width: 320px"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      
      <el-select v-model="filterStatus" placeholder="状态筛选" clearable style="width: 140px">
        <el-option label="通过率高 ≥80%" value="good" />
        <el-option label="通过率一般 50-80%" value="warning" />
        <el-option label="通过率低 <50%" value="danger" />
      </el-select>
      
      <el-button type="primary" :disabled="!selectedTaskIds.length" @click="exportSelected">
        <el-icon><Download /></el-icon>
        导出选中
      </el-button>
      <el-button @click="fetchReports">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </div>
    
    <el-row :gutter="20">
      <el-col
        v-for="report in filteredReports"
        :key="report.task_id"
        :xs="24"
        :sm="12"
        :lg="8"
      >
        <el-card class="app-card report-card" shadow="hover">
          <div class="report-header">
            <div class="report-id">#{{ report.task_id }}</div>
            <el-tag :type="getStatusType(report.summary)" size="small" effect="dark">
              {{ getPassRate(report.summary) }}% 通过
            </el-tag>
          </div>
          
          <div class="report-body">
            <div class="report-name">{{ report.task_name || '未命名任务' }}</div>
            <div class="report-meta">
              <div class="meta-item">
                <el-icon><Cellphone /></el-icon>
                <span>{{ report.device?.model || report.device?.serial_number || '-' }}</span>
              </div>
              <div class="meta-item">
                <el-icon><Clock /></el-icon>
                <span>{{ formatTime(report.created_at) }}</span>
              </div>
              <div class="meta-item">
                <el-icon><Timer /></el-icon>
                <span>{{ report.total_duration || '-' }}</span>
              </div>
            </div>
            
            <div class="report-stats">
              <div class="stat-item pass">
                <div class="stat-value">{{ report.summary?.passed || 0 }}</div>
                <div class="stat-label">通过</div>
              </div>
              <div class="stat-item fail">
                <div class="stat-value">{{ report.summary?.failed || 0 }}</div>
                <div class="stat-label">失败</div>
              </div>
              <div class="stat-item skip">
                <div class="stat-value">{{ report.summary?.skipped || 0 }}</div>
                <div class="stat-label">跳过</div>
              </div>
              <div class="stat-item error">
                <div class="stat-value">{{ report.summary?.error || 0 }}</div>
                <div class="stat-label">错误</div>
              </div>
            </div>
          </div>
          
          <div class="report-footer">
            <el-checkbox v-model="report.selected" @change="updateSelection">
              选中导出
            </el-checkbox>
            <div class="footer-actions">
              <el-button text type="primary" @click="viewReport(report)">
                查看详情
              </el-button>
              <el-button text @click="exportSingle(report)">
                <el-icon><Download /></el-icon>
              </el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
    
    <el-empty v-if="!loading && filteredReports.length === 0" description="暂无报告" />
    
    <!-- 报告详情对话框 -->
    <el-dialog
      v-model="showDetailDialog"
      title="测试报告详情"
      width="900px"
    >
      <div v-if="currentReport" v-loading="detailLoading" class="report-detail">
        <div class="detail-header">
          <div>
            <h3>{{ currentReport.task_name || '未命名任务' }}</h3>
            <div class="detail-meta">
              <el-tag :type="getStatusType(currentReport.summary)" size="small" effect="dark">
                {{ getPassRate(currentReport.summary) }}%
              </el-tag>
              <span>报告ID: {{ currentReport.report_id }}</span>
              <span>设备: {{ currentReport.device?.model || currentReport.device?.serial_number || '-' }}</span>
              <span>执行时间: {{ formatTime(currentReport.created_at) }}</span>
            </div>
          </div>
          <el-button type="primary" size="small" @click="exportCurrentReport">
            <el-icon><Download /></el-icon>
            导出报告
          </el-button>
        </div>

        <el-divider />

        <div class="detail-stats">
          <div class="stat-box">
            <div class="stat-title">总项数</div>
            <div class="stat-number">{{ currentReport.summary?.total_items || 0 }}</div>
          </div>
          <div class="stat-box pass">
            <div class="stat-title">通过</div>
            <div class="stat-number">{{ currentReport.summary?.passed || 0 }}</div>
          </div>
          <div class="stat-box fail">
            <div class="stat-title">失败</div>
            <div class="stat-number">{{ currentReport.summary?.failed || 0 }}</div>
          </div>
          <div class="stat-box skip">
            <div class="stat-title">跳过</div>
            <div class="stat-number">{{ currentReport.summary?.skipped || 0 }}</div>
          </div>
          <div class="stat-box error">
            <div class="stat-title">错误</div>
            <div class="stat-number">{{ currentReport.summary?.error || 0 }}</div>
          </div>
        </div>

        <el-divider />

        <div class="detail-results">
          <h4>测试结果</h4>
          <el-table :data="currentReport.results" size="small" class="app-table">
            <el-table-column type="expand" width="40">
              <template #default="{ row }">
                <div class="result-detail">
                  <div class="detail-section" v-if="row.objective">
                    <div class="section-label">测试目的</div>
                    <div class="text-content">{{ row.objective }}</div>
                  </div>

                  <div class="detail-section" v-if="row.precondition">
                    <div class="section-label">前置条件</div>
                    <div class="text-content">{{ row.precondition }}</div>
                  </div>

                  <div class="detail-section" v-if="row.steps">
                    <div class="section-label">测试步骤</div>
                    <pre class="text-block">{{ row.steps }}</pre>
                  </div>

                  <div class="detail-section" v-if="row.expected_result">
                    <div class="section-label">预期结果</div>
                    <div class="text-content">{{ row.expected_result }}</div>
                  </div>

                  <div class="detail-section" v-if="row.actual_result">
                    <div class="section-label">实际结果</div>
                    <pre v-if="typeof row.actual_result === 'object'" class="json-block">{{ JSON.stringify(row.actual_result, null, 2) }}</pre>
                    <div v-else class="text-content">{{ row.actual_result }}</div>
                  </div>

                  <div class="detail-section" v-if="row.verdict_basis">
                    <div class="section-label">判定依据</div>
                    <div class="text-content">{{ row.verdict_basis }}</div>
                  </div>

                  <div class="detail-section" v-if="row.judgement_type">
                    <div class="section-label">判定方式</div>
                    <el-tag size="small" :type="getJudgeTypeType(row.judgement_type)">
                      {{ getJudgeTypeText(row.judgement_type) }}
                    </el-tag>
                  </div>

                  <div class="detail-section" v-if="row.conditional_rules">
                    <div class="section-label">断言规则（期望值）</div>
                    <pre class="json-block">{{ JSON.stringify(row.conditional_rules, null, 2) }}</pre>
                  </div>

                  <div class="detail-section" v-if="row.rubric_criteria">
                    <div class="section-label">评分规则（期望值）</div>
                    <pre class="json-block">{{ JSON.stringify(row.rubric_criteria, null, 2) }}</pre>
                  </div>

                  <div class="detail-section" v-if="row.suggested_fix">
                    <div class="section-label">修复建议</div>
                    <div class="fix-suggestion">{{ row.suggested_fix }}</div>
                  </div>

                  <div class="detail-section" v-if="row.output_summary">
                    <div class="section-label">输出摘要</div>
                    <pre class="output-block">{{ row.output_summary }}</pre>
                  </div>

                  <div class="detail-actions">
                    <el-button size="small" type="primary" @click="viewItemLog(row)">
                      查看完整日志
                    </el-button>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="module_name" label="模块" width="120" />
            <el-table-column prop="item_name" label="测试项" min-width="180" />
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="getResultType(row.status)" size="small" effect="dark">
                  {{ getResultText(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="execution_time" label="耗时" width="100">
              <template #default="{ row }">
                {{ row.execution_time || 0 }}秒
              </template>
            </el-table-column>
            <el-table-column prop="fail_reason" label="失败原因" min-width="180">
              <template #default="{ row }">
                <span class="fail-reason">{{ row.fail_reason || '-' }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </el-dialog>

    <!-- 日志详情对话框 -->
    <el-dialog
      v-model="showLogDialog"
      title="测试项日志"
      width="800px"
    >
      <div v-loading="logLoading" class="log-detail">
        <el-descriptions :column="1" border v-if="currentLog">
          <el-descriptions-item label="测试项">{{ currentLog.item_name }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="getResultType(currentLog.status)" size="small">
              {{ getResultText(currentLog.status) }}
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
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Cellphone, Clock, Timer, Download, Refresh } from '@element-plus/icons-vue'
import { getReport, getSummaryReport, exportReport, exportBatchReport, getItemLog } from '@/api/report'
import dayjs from 'dayjs'
import { formatDateTime } from '@/utils/datetime'

const reports = ref([])
const loading = ref(false)
const searchKeyword = ref('')
const filterStatus = ref('')
const showDetailDialog = ref(false)
const currentReport = ref(null)
const detailLoading = ref(false)
const showLogDialog = ref(false)
const logLoading = ref(false)
const currentLog = ref(null)

const filteredReports = computed(() => {
  return reports.value.filter(report => {
    const keyword = searchKeyword.value.toLowerCase()
    const text = `${report.task_name || ''} ${report.device?.model || ''} ${report.device?.serial_number || ''}`.toLowerCase()
    const matchKeyword = !keyword || text.includes(keyword)

    const rate = getPassRate(report.summary)
    let matchStatus = true
    if (filterStatus.value === 'good') matchStatus = rate >= 80
    if (filterStatus.value === 'warning') matchStatus = rate >= 50 && rate < 80
    if (filterStatus.value === 'danger') matchStatus = rate < 50

    return matchKeyword && matchStatus
  })
})

const selectedTaskIds = computed(() => {
  return reports.value.filter(r => r.selected).map(r => r.task_id)
})

const fetchReports = async () => {
  loading.value = true
  try {
    const res = await getSummaryReport()
    if (res.code === 200) {
      const data = res.data
      reports.value = (data.tasks || []).map(task => {
        const taskReport = data.results.filter(r => r.task_id === task.task_id)
        return {
          task_id: task.task_id,
          task_name: task.task_name,
          device: { model: task.device_model, serial_number: task.device_serial },
          created_at: task.created_at,
          total_duration: '-',
          summary: {
            total_items: task.total_items,
            passed: taskReport.filter(r => r.status === 'pass').length,
            failed: taskReport.filter(r => r.status === 'fail').length,
            skipped: taskReport.filter(r => r.status === 'skip').length,
            error: taskReport.filter(r => r.status === 'error').length
          },
          results: taskReport,
          selected: false
        }
      })
    }
  } catch (error) {
    if (error?.response?.status === 404) {
      reports.value = []
    } else {
      console.error('获取报告失败:', error)
      ElMessage.error('获取报告失败')
    }
  } finally {
    loading.value = false
  }
}

const getStatusType = (summary) => {
  if (!summary || summary.total_items === 0) return 'info'
  const rate = summary.passed / summary.total_items
  if (rate === 1) return 'success'
  if (rate >= 0.8) return 'warning'
  return 'danger'
}

const getPassRate = (summary) => {
  if (!summary || summary.total_items === 0) return 0
  return Math.round((summary.passed / summary.total_items) * 100)
}

const getResultType = (status) => {
  const types = {
    'pass': 'success',
    'fail': 'danger',
    'skip': 'info',
    'error': 'warning',
    'running': 'warning',
    'pending': 'info'
  }
  return types[status] || 'info'
}

const getResultText = (status) => {
  const texts = {
    'pass': '通过',
    'fail': '失败',
    'skip': '跳过',
    'error': '错误',
    'running': '执行中',
    'pending': '等待中'
  }
  return texts[status] || status
}

const getJudgeTypeType = (type) => {
  const types = {
    'assertion': 'success',
    'rubric': 'warning',
    'ai_fallback': 'info'
  }
  return types[type] || 'info'
}

const getJudgeTypeText = (type) => {
  const texts = {
    'assertion': '断言',
    'rubric': '评分',
    'ai_fallback': 'AI'
  }
  return texts[type] || type
}

const exportCurrentReport = async () => {
  if (!currentReport.value) return
  try {
    const res = await exportReport(currentReport.value.task_id, 'html')
    downloadBlob(res, `report_${currentReport.value.task_id}.html`)
    ElMessage.success('报告导出成功')
  } catch (error) {
    console.error('导出报告失败:', error)
    ElMessage.error('导出报告失败')
  }
}

const viewItemLog = async (row) => {
  if (!currentReport.value) return
  logLoading.value = true
  showLogDialog.value = true
  currentLog.value = null
  try {
    const res = await getItemLog(currentReport.value.task_id, row.item_id)
    if (res.code === 200) {
      currentLog.value = {
        ...res.data,
        item_name: row.item_name
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

const formatTime = (time) => {
  return formatDateTime(time, 'YYYY-MM-DD HH:mm')
}

const viewReport = async (report) => {
  detailLoading.value = true
  showDetailDialog.value = true
  try {
    const res = await getReport(report.task_id)
    if (res.code === 200) {
      currentReport.value = res.data
    }
  } catch (error) {
    console.error('获取报告详情失败:', error)
    ElMessage.error('获取报告详情失败')
    showDetailDialog.value = false
  } finally {
    detailLoading.value = false
  }
}

const exportSingle = async (report) => {
  try {
    const res = await exportReport(report.task_id, 'html')
    downloadBlob(res, `report_${report.task_id}.html`)
    ElMessage.success('报告导出成功')
  } catch (error) {
    console.error('导出报告失败:', error)
    ElMessage.error('导出报告失败')
  }
}

const exportSelected = async () => {
  if (!selectedTaskIds.value.length) return
  try {
    const res = await exportBatchReport(selectedTaskIds.value, 'html')
    downloadBlob(res, `batch_report_${dayjs().format('YYYYMMDD_HHmmss')}.html`)
    ElMessage.success('批量导出成功')
  } catch (error) {
    console.error('批量导出失败:', error)
    ElMessage.error('批量导出失败')
  }
}

const downloadBlob = (blob, filename) => {
  const url = window.URL.createObjectURL(new Blob([blob]))
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', filename)
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

const updateSelection = () => {
  // 触发 computed 更新
}

onMounted(() => {
  fetchReports()
})
</script>

<style scoped lang="scss">
.report-card {
  margin-bottom: 20px;
  
  .report-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
    
    .report-id {
      font-family: monospace;
      font-size: 13px;
      color: var(--tp-text-tertiary);
    }
  }
  
  .report-body {
    .report-name {
      font-size: 16px;
      font-weight: 600;
      color: var(--tp-text);
      margin-bottom: 10px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    
    .report-meta {
      margin-bottom: 15px;
      
      .meta-item {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 6px;
        font-size: 13px;
        color: var(--tp-text-secondary);
        
        .el-icon {
          color: var(--tp-text-tertiary);
        }
      }
    }
    
    .report-stats {
      display: flex;
      justify-content: space-around;
      padding: 12px;
      background-color: var(--tp-bg-page);
      border-radius: 8px;
      
      .stat-item {
        text-align: center;
        
        &.pass .stat-value { color: #67c23a; }
        &.fail .stat-value { color: #f56c6c; }
        &.skip .stat-value { color: #909399; }
        &.error .stat-value { color: #e6a23c; }
        
        .stat-value {
          font-size: 22px;
          font-weight: bold;
          margin-bottom: 4px;
        }
        
        .stat-label {
          font-size: 12px;
          color: var(--tp-text-secondary);
        }
      }
    }
  }
  
  .report-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 15px;
    padding-top: 15px;
    border-top: 1px solid var(--tp-border-light);
    
    .footer-actions {
      display: flex;
      gap: 8px;
    }
  }
}

.report-detail {
  .detail-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    
    h3 {
      margin: 0 0 10px 0;
      color: var(--tp-text);
    }
    
    .detail-meta {
      display: flex;
      align-items: center;
      gap: 15px;
      font-size: 13px;
      color: var(--tp-text-secondary);
      flex-wrap: wrap;
    }
  }
  
  .detail-stats {
    display: flex;
    justify-content: space-around;
    padding: 20px 0;
    
    .stat-box {
      text-align: center;
      
      .stat-title {
        font-size: 12px;
        color: var(--tp-text-secondary);
        margin-bottom: 5px;
      }
      
      .stat-number {
        font-size: 28px;
        font-weight: bold;
        color: var(--tp-text);
      }
      
      &.pass .stat-number { color: #67c23a; }
      &.fail .stat-number { color: #f56c6c; }
      &.skip .stat-number { color: #909399; }
      &.error .stat-number { color: #e6a23c; }
    }
  }
  
  .detail-results {
    h4 {
      margin: 0 0 15px 0;
      color: var(--tp-text);
    }
    
    .fail-reason {
      color: #f56c6c;
      font-size: 13px;
    }
  }
}

.result-detail {
  padding: 15px 20px;
  background-color: var(--tp-bg-page);
  border-radius: 8px;
  margin: 5px 0;
  
  .detail-section {
    margin-bottom: 15px;
    
    &:last-child {
      margin-bottom: 0;
    }
  }
  
  .section-label {
    font-size: 13px;
    font-weight: 600;
    color: var(--tp-text-secondary);
    margin-bottom: 8px;
  }
  
  .text-content {
    font-size: 13px;
    color: var(--tp-text);
    line-height: 1.6;
  }

  .text-block,
  .json-block,
  .output-block {
    background-color: var(--tp-bg-card);
    border: 1px solid var(--tp-border-light);
    border-radius: 6px;
    padding: 12px;
    margin: 0;
    font-family: monospace;
    font-size: 12px;
    color: var(--tp-text);
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 200px;
    overflow-y: auto;
  }
  
  .fix-suggestion {
    color: #e6a23c;
    font-size: 13px;
    line-height: 1.6;
  }
  
  .detail-actions {
    margin-top: 15px;
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
</style>
