<template>
  <div class="page-container">
    <el-tabs v-model="activeTab" type="border-card" class="memory-tabs">
      <!-- 设备维度 -->
      <el-tab-pane label="设备维度" name="devices">
        <div class="search-bar">
          <el-input
            v-model="deviceSearch"
            placeholder="搜索设备型号"
            clearable
            style="width: 320px"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
          <el-button @click="fetchAll">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>

        <el-empty v-if="filteredDeviceModels.length === 0" description="暂无设备画像数据" />

        <el-row v-else :gutter="20">
          <el-col
            v-for="model in filteredDeviceModels"
            :key="model"
            :xs="24"
            :sm="12"
            :lg="8"
            style="margin-bottom: 20px"
          >
            <el-card class="app-card device-card" shadow="hover">
              <template #header>
                <div class="card-header">
                  <span class="device-title">{{ model }}</span>
                  <el-tag size="small" type="info">{{ deviceModelMap[model]?.length || 0 }} 台设备</el-tag>
                </div>
              </template>

              <div class="device-profile">
                <div class="profile-item">
                  <span class="profile-label">Android 版本</span>
                  <span class="profile-value">{{ getDeviceField(model, 'android_version') || '-' }}</span>
                </div>
                <div class="profile-item">
                  <span class="profile-label">CPU 架构</span>
                  <span class="profile-value">{{ getDeviceField(model, 'cpu_abi') || '-' }}</span>
                </div>
                <div class="profile-item">
                  <span class="profile-label">主板平台</span>
                  <span class="profile-value">{{ getDeviceField(model, 'board') || '-' }}</span>
                </div>
                <div class="profile-item">
                  <span class="profile-label">DDR</span>
                  <span class="profile-value">{{ getDdrSummary(model) }}</span>
                </div>
                <div class="profile-item">
                  <span class="profile-label">EMMC</span>
                  <span class="profile-value">{{ getEmmcSummary(model) }}</span>
                </div>
                <div class="profile-item">
                  <span class="profile-label">通信模组</span>
                  <span class="profile-value">{{ getCommSummary(model) }}</span>
                </div>
                <div class="profile-item">
                  <span class="profile-label">能力特征</span>
                  <span class="profile-value">
                    <el-tag
                      v-for="feature in getDeviceFeatures(model)"
                      :key="feature"
                      size="small"
                      style="margin-right: 4px; margin-bottom: 4px"
                    >
                      {{ feature }}
                    </el-tag>
                    <span v-if="!getDeviceFeatures(model).length">-</span>
                  </span>
                </div>
              </div>

              <el-divider />

              <div class="model-metrics">
                <div class="metrics-title">已采集指标</div>
                <el-tag
                  v-for="metric in getModelMetrics(model)"
                  :key="metric"
                  size="small"
                  type="success"
                  style="margin-right: 6px; margin-bottom: 6px"
                >
                  {{ metric }}
                </el-tag>
                <span v-if="!getModelMetrics(model).length" class="empty-tip">暂无基线指标</span>
              </div>
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- 指标维度 -->
      <el-tab-pane label="指标维度" name="metrics">
        <div class="search-bar">
          <el-input
            v-model="metricSearch"
            placeholder="搜索设备型号 / 指标名"
            clearable
            style="width: 320px"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
          <el-button type="primary" v-if="isAdmin" @click="openBaselineDialog()">
            <el-icon><Plus /></el-icon>
            添加基线
          </el-button>
          <el-button @click="fetchBaselines">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>

        <el-table :data="filteredBaselines" size="small" class="app-table" v-loading="loadingBaselines">
          <el-table-column prop="device_model" label="设备型号" width="150" />
          <el-table-column prop="item_id" label="测试项 ID" width="100" />
          <el-table-column prop="metric_name" label="指标名" width="140" />
          <el-table-column prop="avg_value" label="平均值" width="120" />
          <el-table-column prop="min_value" label="最小值" width="120" />
          <el-table-column prop="max_value" label="最大值" width="120" />
          <el-table-column prop="sample_count" label="样本数" width="100" />
          <el-table-column prop="updated_at" label="更新时间" min-width="160">
            <template #default="{ row }">
              {{ formatTime(row.updated_at) }}
            </template>
          </el-table-column>
          <el-table-column v-if="isAdmin" label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button text type="primary" size="small" @click="openBaselineDialog(row)">
                <el-icon><Edit /></el-icon>
              </el-button>
              <el-button text type="danger" size="small" @click="handleDeleteBaseline(row)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 失败模式库 -->
      <el-tab-pane label="失败模式库" name="failures">
        <div class="search-bar">
          <el-select v-model="failureCategory" placeholder="类别筛选" clearable style="width: 160px">
            <el-option label="ADB" value="adb" />
            <el-option label="兼容性" value="compat" />
            <el-option label="超时" value="timeout" />
            <el-option label="权限" value="permission" />
          </el-select>
          <el-button type="primary" v-if="isAdmin" @click="openFailureDialog()">
            <el-icon><Plus /></el-icon>
            添加模式
          </el-button>
          <el-button @click="fetchFailurePatterns">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>

        <el-table :data="filteredFailures" size="small" class="app-table" v-loading="loadingFailures">
          <el-table-column prop="name" label="模式名称" width="160" />
          <el-table-column prop="category" label="类别" width="100" />
          <el-table-column prop="pattern" label="匹配正则" min-width="200">
            <template #default="{ row }">
              <code class="pattern-code">{{ row.pattern }}</code>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="描述" min-width="200" />
          <el-table-column prop="suggested_fix" label="建议修复" min-width="220" />
          <el-table-column prop="occurrence_count" label="命中次数" width="100" />
          <el-table-column v-if="isAdmin" label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button text type="primary" size="small" @click="openFailureDialog(row)">
                <el-icon><Edit /></el-icon>
              </el-button>
              <el-button text type="danger" size="small" @click="handleDeleteFailure(row)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 黄金案例 -->
      <el-tab-pane label="黄金案例" name="golden">
        <div class="search-bar">
          <el-input
            v-model="goldenSearch"
            placeholder="搜索设备型号"
            clearable
            style="width: 320px"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
          <el-button type="primary" v-if="isAdmin" @click="openGoldenDialog()">
            <el-icon><Plus /></el-icon>
            添加案例
          </el-button>
          <el-button @click="fetchGoldenCases">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>

        <el-empty v-if="!filteredGoldenCases.length" description="暂无黄金案例" />

        <el-row v-else :gutter="20">
          <el-col
            v-for="item in filteredGoldenCases"
            :key="item.id"
            :xs="24"
            :sm="12"
            :lg="8"
            style="margin-bottom: 20px"
          >
            <el-card class="app-card golden-card" shadow="hover">
              <div class="golden-header">
                <span class="golden-model">{{ item.device_model }}</span>
                <div class="golden-actions" v-if="isAdmin">
                  <el-button text type="primary" size="small" @click="openGoldenDialog(item)">
                    <el-icon><Edit /></el-icon>
                  </el-button>
                  <el-button text type="danger" size="small" @click="handleDeleteGolden(item)">
                    <el-icon><Delete /></el-icon>
                  </el-button>
                </div>
              </div>
              <div class="golden-item">测试项 ID: {{ item.item_id }}</div>
              <div class="golden-item">预期状态: {{ item.expected_status }}</div>
              <div class="golden-output">
                <div class="output-label">样本输出</div>
                <pre>{{ item.sample_output || '-' }}</pre>
              </div>
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>
    </el-tabs>

    <!-- 失败模式对话框 -->
    <el-dialog
      v-model="failureDialogVisible"
      :title="editingFailure ? '编辑失败模式' : '添加失败模式'"
      width="550px"
    >
      <el-form :model="failureForm" label-width="90px">
        <el-form-item label="模式名称" required>
          <el-input v-model="failureForm.name" placeholder="例如：ADB 设备离线" />
        </el-form-item>
        <el-form-item label="类别" required>
          <el-select v-model="failureForm.category" placeholder="请选择类别" style="width: 100%">
            <el-option label="ADB" value="adb" />
            <el-option label="兼容性" value="compat" />
            <el-option label="超时" value="timeout" />
            <el-option label="权限" value="permission" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="匹配正则" required>
          <el-input v-model="failureForm.pattern" placeholder="用于匹配失败输出的正则表达式" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="failureForm.description" type="textarea" rows="3" placeholder="失败原因描述" />
        </el-form-item>
        <el-form-item label="建议修复">
          <el-input v-model="failureForm.suggested_fix" type="textarea" rows="3" placeholder="修复建议" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="failureDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveFailure">保存</el-button>
      </template>
    </el-dialog>

    <!-- 基线对话框 -->
    <el-dialog
      v-model="baselineDialogVisible"
      :title="editingBaseline ? '编辑基线' : '添加基线'"
      width="550px"
    >
      <el-form :model="baselineForm" label-width="100px">
        <el-form-item label="设备型号" required>
          <el-input v-model="baselineForm.device_model" placeholder="例如：rk3568" />
        </el-form-item>
        <el-form-item label="测试项 ID" required>
          <el-input-number v-model="baselineForm.item_id" :min="1" style="width: 150px" />
        </el-form-item>
        <el-form-item label="指标名" required>
          <el-input v-model="baselineForm.metric_name" placeholder="例如：bw_mbps" />
        </el-form-item>
        <el-form-item label="平均值" required>
          <el-input v-model="baselineForm.avg_value" placeholder="例如：150.0" />
        </el-form-item>
        <el-form-item label="最小值" required>
          <el-input v-model="baselineForm.min_value" placeholder="例如：100.0" />
        </el-form-item>
        <el-form-item label="最大值" required>
          <el-input v-model="baselineForm.max_value" placeholder="例如：200.0" />
        </el-form-item>
        <el-form-item label="样本数">
          <el-input-number v-model="baselineForm.sample_count" :min="1" style="width: 150px" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="baselineDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveBaseline">保存</el-button>
      </template>
    </el-dialog>

    <!-- 黄金案例对话框 -->
    <el-dialog
      v-model="goldenDialogVisible"
      :title="editingGolden ? '编辑黄金案例' : '添加黄金案例'"
      width="550px"
    >
      <el-form :model="goldenForm" label-width="120px">
        <el-form-item label="测试项 ID" required>
          <el-input-number v-model="goldenForm.item_id" :min="1" style="width: 150px" />
        </el-form-item>
        <el-form-item label="设备型号" required>
          <el-input v-model="goldenForm.device_model" placeholder="例如：rk3568" />
        </el-form-item>
        <el-form-item label="预期状态">
          <el-input v-model="goldenForm.expected_status" placeholder="例如：pass" />
        </el-form-item>
        <el-form-item label="输出正则">
          <el-input v-model="goldenForm.expected_output_pattern" placeholder="可选，用于校验输出" />
        </el-form-item>
        <el-form-item label="样本输出">
          <el-input v-model="goldenForm.sample_output" type="textarea" rows="4" placeholder="通过的样本输出" />
        </el-form-item>
        <el-form-item label="是否有效">
          <el-switch v-model="goldenForm.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="goldenDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveGolden">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Refresh, Plus, Edit, Delete } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import {
  getFailurePatterns,
  createFailurePattern,
  updateFailurePattern,
  deleteFailurePattern,
  getBaselines,
  createBaseline,
  updateBaseline,
  deleteBaseline,
  getGoldenCases,
  createGoldenCase,
  updateGoldenCase,
  deleteGoldenCase
} from '@/api/memory'
import { getDevices } from '@/api/device'
import { formatDateTime } from '@/utils/datetime'

const userStore = useUserStore()
const isAdmin = computed(() => userStore.isAdmin)

const activeTab = ref('devices')
const devices = ref([])
const baselines = ref([])
const failures = ref([])
const goldenCases = ref([])
const loadingBaselines = ref(false)
const loadingFailures = ref(false)
const loadingGolden = ref(false)

const deviceSearch = ref('')
const metricSearch = ref('')
const failureCategory = ref('')
const goldenSearch = ref('')

const saving = ref(false)

// 失败模式对话框
const failureDialogVisible = ref(false)
const editingFailure = ref(null)
const failureForm = ref({
  name: '',
  category: '',
  pattern: '',
  description: '',
  suggested_fix: ''
})

// 基线对话框
const baselineDialogVisible = ref(false)
const editingBaseline = ref(null)
const baselineForm = ref({
  device_model: '',
  item_id: 1,
  metric_name: '',
  avg_value: '',
  min_value: '',
  max_value: '',
  sample_count: 1
})

// 黄金案例对话框
const goldenDialogVisible = ref(false)
const editingGolden = ref(null)
const goldenForm = ref({
  item_id: 1,
  device_model: '',
  expected_status: 'pass',
  expected_output_pattern: '',
  sample_output: '',
  is_active: true
})

const deviceModelMap = computed(() => {
  const map = {}
  devices.value.forEach(device => {
    const model = device.model || 'Unknown'
    if (!map[model]) map[model] = []
    map[model].push(device)
  })
  return map
})

const filteredDeviceModels = computed(() => {
  const models = Object.keys(deviceModelMap.value)
  if (!deviceSearch.value) return models
  return models.filter(m => m.toLowerCase().includes(deviceSearch.value.toLowerCase()))
})

const filteredBaselines = computed(() => {
  const keyword = metricSearch.value.toLowerCase()
  if (!keyword) return baselines.value
  return baselines.value.filter(b =>
    (b.device_model || '').toLowerCase().includes(keyword) ||
    (b.metric_name || '').toLowerCase().includes(keyword)
  )
})

const filteredFailures = computed(() => {
  if (!failureCategory.value) return failures.value
  return failures.value.filter(f => f.category === failureCategory.value)
})

const filteredGoldenCases = computed(() => {
  const keyword = goldenSearch.value.toLowerCase()
  if (!keyword) return goldenCases.value
  return goldenCases.value.filter(g =>
    (g.device_model || '').toLowerCase().includes(keyword)
  )
})

const getDeviceField = (model, field) => {
  const list = deviceModelMap.value[model] || []
  const device = list.find(d => d[field])
  return device ? device[field] : null
}

const getDdrSummary = (model) => {
  const total = deviceModelMap.value[model]?.find(d => d.ddr_info?.total_mb)
  return total ? `${total.ddr_info.total_mb} MB` : '-'
}

const getEmmcSummary = (model) => {
  const info = deviceModelMap.value[model]?.find(d => d.emmc_info?.size_gb)
  return info ? `${info.emmc_info.size_gb} GB / ${info.emmc_info.model || '-'}` : '-'
}

const getCommSummary = (model) => {
  const device = deviceModelMap.value[model]?.[0]
  if (!device) return '-'
  const parts = []
  if (device.wifi_chip) parts.push(`WIFI: ${device.wifi_chip}`)
  if (device.bt_chip) parts.push(`BT: ${device.bt_chip}`)
  if (device.eth_interfaces?.length) parts.push(`ETH: ${device.eth_interfaces.join(', ')}`)
  return parts.length ? parts.join(' / ') : '-'
}

const getDeviceFeatures = (model) => {
  const device = deviceModelMap.value[model]?.[0]
  return device?.features || []
}

const getModelMetrics = (model) => {
  const set = new Set()
  baselines.value
    .filter(b => b.device_model === model)
    .forEach(b => set.add(b.metric_name))
  return Array.from(set)
}

const formatTime = (time) => {
  return formatDateTime(time, 'YYYY-MM-DD HH:mm')
}

const fetchDevices = async () => {
  try {
    const res = await getDevices()
    if (res.code === 200) {
      devices.value = res.data.items || []
    }
  } catch (error) {
    console.error('获取设备失败:', error)
    ElMessage.error('获取设备失败')
  }
}

const fetchBaselines = async () => {
  loadingBaselines.value = true
  try {
    const res = await getBaselines()
    if (res.code === 200) {
      baselines.value = res.data || []
    }
  } catch (error) {
    console.error('获取基线失败:', error)
    ElMessage.error('获取基线失败')
  } finally {
    loadingBaselines.value = false
  }
}

const fetchFailurePatterns = async () => {
  loadingFailures.value = true
  try {
    const res = await getFailurePatterns()
    if (res.code === 200) {
      failures.value = res.data || []
    }
  } catch (error) {
    console.error('获取失败模式失败:', error)
    ElMessage.error('获取失败模式失败')
  } finally {
    loadingFailures.value = false
  }
}

const fetchGoldenCases = async () => {
  loadingGolden.value = true
  try {
    const res = await getGoldenCases()
    if (res.code === 200) {
      goldenCases.value = res.data || []
    }
  } catch (error) {
    console.error('获取黄金案例失败:', error)
    ElMessage.error('获取黄金案例失败')
  } finally {
    loadingGolden.value = false
  }
}

const fetchAll = () => {
  fetchDevices()
  fetchBaselines()
  fetchFailurePatterns()
  fetchGoldenCases()
}

// 失败模式 CRUD
const openFailureDialog = (row = null) => {
  editingFailure.value = row
  if (row) {
    failureForm.value = { ...row }
  } else {
    failureForm.value = {
      name: '',
      category: '',
      pattern: '',
      description: '',
      suggested_fix: ''
    }
  }
  failureDialogVisible.value = true
}

const saveFailure = async () => {
  if (!failureForm.value.name || !failureForm.value.category || !failureForm.value.pattern) {
    ElMessage.warning('请填写必填项')
    return
  }
  saving.value = true
  try {
    if (editingFailure.value) {
      await updateFailurePattern(editingFailure.value.id, failureForm.value)
      ElMessage.success('更新成功')
    } else {
      await createFailurePattern(failureForm.value)
      ElMessage.success('创建成功')
    }
    failureDialogVisible.value = false
    fetchFailurePatterns()
  } catch (error) {
    console.error('保存失败模式失败:', error)
  } finally {
    saving.value = false
  }
}

const handleDeleteFailure = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除失败模式 "${row.name}" 吗？`, '提示', { type: 'warning' })
    await deleteFailurePattern(row.id)
    ElMessage.success('删除成功')
    fetchFailurePatterns()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除失败模式失败:', error)
    }
  }
}

// 基线 CRUD
const openBaselineDialog = (row = null) => {
  editingBaseline.value = row
  if (row) {
    baselineForm.value = { ...row }
  } else {
    baselineForm.value = {
      device_model: '',
      item_id: 1,
      metric_name: '',
      avg_value: '',
      min_value: '',
      max_value: '',
      sample_count: 1
    }
  }
  baselineDialogVisible.value = true
}

const saveBaseline = async () => {
  if (!baselineForm.value.device_model || !baselineForm.value.metric_name ||
      !baselineForm.value.avg_value || !baselineForm.value.min_value || !baselineForm.value.max_value) {
    ElMessage.warning('请填写必填项')
    return
  }
  saving.value = true
  try {
    const payload = {
      ...baselineForm.value,
      item_id: Number(baselineForm.value.item_id),
      sample_count: Number(baselineForm.value.sample_count)
    }
    if (editingBaseline.value) {
      await updateBaseline(editingBaseline.value.id, payload)
      ElMessage.success('更新成功')
    } else {
      await createBaseline(payload)
      ElMessage.success('创建成功')
    }
    baselineDialogVisible.value = false
    fetchBaselines()
  } catch (error) {
    console.error('保存基线失败:', error)
  } finally {
    saving.value = false
  }
}

const handleDeleteBaseline = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除基线 "${row.device_model} / ${row.metric_name}" 吗？`, '提示', { type: 'warning' })
    await deleteBaseline(row.id)
    ElMessage.success('删除成功')
    fetchBaselines()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除基线失败:', error)
    }
  }
}

// 黄金案例 CRUD
const openGoldenDialog = (row = null) => {
  editingGolden.value = row
  if (row) {
    goldenForm.value = { ...row }
  } else {
    goldenForm.value = {
      item_id: 1,
      device_model: '',
      expected_status: 'pass',
      expected_output_pattern: '',
      sample_output: '',
      is_active: true
    }
  }
  goldenDialogVisible.value = true
}

const saveGolden = async () => {
  if (!goldenForm.value.device_model || !goldenForm.value.item_id) {
    ElMessage.warning('请填写必填项')
    return
  }
  saving.value = true
  try {
    const payload = {
      ...goldenForm.value,
      item_id: Number(goldenForm.value.item_id)
    }
    if (editingGolden.value) {
      await updateGoldenCase(editingGolden.value.id, payload)
      ElMessage.success('更新成功')
    } else {
      await createGoldenCase(payload)
      ElMessage.success('创建成功')
    }
    goldenDialogVisible.value = false
    fetchGoldenCases()
  } catch (error) {
    console.error('保存黄金案例失败:', error)
  } finally {
    saving.value = false
  }
}

const handleDeleteGolden = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除黄金案例 "${row.device_model} / 测试项${row.item_id}" 吗？`, '提示', { type: 'warning' })
    await deleteGoldenCase(row.id)
    ElMessage.success('删除成功')
    fetchGoldenCases()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除黄金案例失败:', error)
    }
  }
}

onMounted(() => {
  fetchAll()
})
</script>

<style scoped lang="scss">
.memory-tabs {
  :deep(.el-tabs__header) {
    margin-bottom: 20px;
  }
}

.search-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.device-card {
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .device-title {
    font-weight: 600;
    font-size: 16px;
  }
}

.device-profile {
  .profile-item {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: 8px 0;
    border-bottom: 1px solid var(--tp-border-light);

    &:last-child {
      border-bottom: none;
    }
  }

  .profile-label {
    font-size: 13px;
    color: var(--tp-text-secondary);
    min-width: 80px;
  }

  .profile-value {
    font-size: 13px;
    color: var(--tp-text);
    text-align: right;
    flex: 1;
    margin-left: 10px;
  }
}

.model-metrics {
  .metrics-title {
    font-size: 13px;
    color: var(--tp-text-secondary);
    margin-bottom: 10px;
  }

  .empty-tip {
    font-size: 12px;
    color: var(--tp-text-tertiary);
  }
}

.pattern-code {
  background-color: var(--tp-bg-page);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: monospace;
  font-size: 12px;
}

.golden-card {
  .golden-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
  }

  .golden-model {
    font-weight: 600;
    font-size: 15px;
  }

  .golden-actions {
    display: flex;
    gap: 5px;
  }

  .golden-item {
    font-size: 13px;
    color: var(--tp-text-secondary);
    margin-bottom: 6px;
  }

  .golden-output {
    margin-top: 12px;

    .output-label {
      font-size: 12px;
      color: var(--tp-text-secondary);
      margin-bottom: 6px;
    }

    pre {
      background-color: var(--tp-bg-page);
      border: 1px solid var(--tp-border-light);
      border-radius: 6px;
      padding: 10px;
      margin: 0;
      font-size: 12px;
      max-height: 150px;
      overflow-y: auto;
      white-space: pre-wrap;
      word-break: break-all;
    }
  }
}
</style>
