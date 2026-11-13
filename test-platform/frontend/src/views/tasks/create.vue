<template>
  <div class="page-container">
    <el-alert
      :title="prefillDeviceSerial ? '已为当前设备预选测试任务' : '选择测试项开始测试'"
      :description="prefillDeviceSerial ? `已预选择设备 ${getDeviceName(prefillDeviceSerial)}，请选择测试项后点击开始测试` : '请选择要执行的测试模块和测试项，然后选择目标设备开始测试'"
      type="info"
      show-icon
      style="margin-bottom: 20px"
    />
    
    <el-row :gutter="20">
      <!-- 左侧：测试项选择 -->
      <el-col :span="14">
        <el-card class="app-card">
          <template #header>
            <span>选择测试项</span>
          </template>
          
          <div v-for="module in modules" :key="module.id" class="module-section">
            <div class="module-header">
              <el-checkbox
                v-model="module.selected"
                :indeterminate="isIndeterminate(module)"
                @change="handleModuleChange(module)"
              >
                <span class="module-name">{{ module.name }}</span>
              </el-checkbox>
              <span class="module-count">{{ getSelectedCount(module) }}/{{ module.items?.length || 0 }}</span>
            </div>
            
            <div class="items-list">
              <el-checkbox-group v-model="selectedItems">
                <el-checkbox
                  v-for="item in module.items"
                  :key="item.id"
                  :label="item.id"
                  class="test-item"
                >
                  <div class="item-info">
                    <span class="item-name">{{ item.name }}</span>
                    <div class="item-tags">
                      <el-tag size="small" :type="getExecTypeType(item.exec_type)">
                        {{ getExecTypeText(item.exec_type) }}
                      </el-tag>
                      <el-tooltip
                        v-if="getItemCompatibility(item).status === 'incompatible'"
                        :content="getItemCompatibility(item).tips.join('；')"
                        placement="top"
                      >
                        <el-tag size="small" type="danger" style="margin-left: 6px">
                          不兼容
                        </el-tag>
                      </el-tooltip>
                      <el-tooltip
                        v-else-if="selectedDeviceInfo && getItemCompatibility(item).status === 'ok' && item.compatibility"
                        :content="'当前设备兼容该测试项'"
                        placement="top"
                      >
                        <el-tag size="small" type="success" style="margin-left: 6px">
                          兼容
                        </el-tag>
                      </el-tooltip>
                    </div>
                  </div>
                  <div class="item-desc">{{ item.description }}</div>
                </el-checkbox>
              </el-checkbox-group>
            </div>
          </div>
        </el-card>
      </el-col>
      
      <!-- 右侧：设备选择和确认 -->
      <el-col :span="10">
        <el-card class="app-card">
          <template #header>
            <span>选择设备</span>
          </template>
          
          <div v-if="devices.length === 0" class="empty-text">
            暂无可用设备，请先连接设备
          </div>
          
          <div v-else class="device-list">
            <el-radio-group v-model="selectedDevice">
              <el-radio
                v-for="device in devices"
                :key="device.serial_number"
                :label="device.serial_number"
                class="device-option"
                :disabled="device.status !== 'online'"
              >
                <div class="device-info">
                  <div class="device-name">{{ device.model || device.serial_number }}</div>
                  <div class="device-meta">
                    <el-tag size="small" :type="device.status === 'online' ? 'success' : 'info'">
                      {{ device.status === 'online' ? '在线' : '离线' }}
                    </el-tag>
                    <span>{{ device.android_version }}</span>
                  </div>
                </div>
              </el-radio>
            </el-radio-group>
          </div>
        </el-card>
        
        <el-card class="app-card" style="margin-top: 20px;">
          <template #header>
            <span>任务确认</span>
          </template>
          
          <div class="summary">
            <div class="summary-item">
              <span class="label">已选测试项：</span>
              <span class="value">{{ selectedItems.length }} 项</span>
            </div>
            <div class="summary-item">
              <span class="label">目标设备：</span>
              <span class="value">{{ selectedDevice ? getDeviceName(selectedDevice) : '未选择' }}</span>
            </div>
            <div class="summary-item" style="align-items: flex-start;">
              <span class="label">执行方式：</span>
              <el-radio-group v-model="scheduleType">
                <el-radio label="immediate">立即执行</el-radio>
                <el-radio
                  label="once"
                  disabled
                >
                  定时一次（后续版本）
                </el-radio>
                <el-radio
                  label="daily"
                  disabled
                >
                  每日定时（后续版本）
                </el-radio>
              </el-radio-group>
            </div>

            <div v-if="scheduleType === 'once'" class="summary-item">
              <span class="label">执行时间：</span>
              <el-date-picker
                v-model="scheduledTime"
                type="datetime"
                format="YYYY-MM-DD HH:mm"
                value-format="YYYY-MM-DD HH:mm"
                placeholder="选择执行时间"
                style="flex: 1"
              />
            </div>
            <div v-if="scheduleType === 'daily'" class="summary-item">
              <span class="label">每日时间：</span>
              <el-time-picker
                v-model="scheduledTime"
                format="HH:mm"
                value-format="HH:mm"
                placeholder="选择每日执行时间"
                style="flex: 1"
              />
            </div>
          </div>

          <el-button
            type="primary"
            size="large"
            :disabled="!canStart"
            :loading="starting"
            @click="startTask"
            style="width: 100%; margin-top: 20px"
          >
            {{ scheduleType === 'immediate' ? '开始测试' : '创建定时任务' }}
          </el-button>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getModules, getModuleDetail } from '@/api/module'
import { getDevices } from '@/api/device'
import { createTask } from '@/api/task'
import { isSuccessResponse } from '@/api/client'

const router = useRouter()
const route = useRoute()
const modules = ref([])
const devices = ref([])
const selectedItems = ref([])
const selectedDevice = ref('')
const starting = ref(false)
const prefillDeviceSerial = ref(route.query.device || '')
const scheduleType = ref('immediate')
const scheduledTime = ref('')

// 切换执行方式时清空已选时间（once/daily 时间格式不同）
watch(scheduleType, () => {
  scheduledTime.value = ''
})

const canStart = computed(() => {
  const base = selectedItems.value.length > 0 && selectedDevice.value
  if (scheduleType.value === 'immediate') return base
  return base && !!scheduledTime.value
})

const getSelectedCount = (module) => {
  return module.items?.filter(item => selectedItems.value.includes(item.id)).length || 0
}

const isIndeterminate = (module) => {
  const selected = getSelectedCount(module)
  return selected > 0 && selected < (module.items?.length || 0)
}

const handleModuleChange = (module) => {
  const itemIds = module.items?.map(item => item.id) || []
  if (module.selected) {
    selectedItems.value = [...new Set([...selectedItems.value, ...itemIds])]
  } else {
    selectedItems.value = selectedItems.value.filter(id => !itemIds.includes(id))
  }
}

const getExecTypeType = (type) => {
  const types = {
    'adb_shell': 'primary',
    'push_exec': 'success',
    'host_exec': 'warning'
  }
  return types[type] || 'info'
}

const getExecTypeText = (type) => {
  const texts = {
    'adb_shell': 'ADB',
    'push_exec': '推送',
    'host_exec': '本地'
  }
  return texts[type] || type
}

const selectedDeviceInfo = computed(() => {
  return devices.value.find(d => d.serial_number === selectedDevice.value)
})

const getDeviceName = (serial) => {
  const device = devices.value.find(d => d.serial_number === serial)
  return device?.model || serial
}

const getItemCompatibility = (item) => {
  const device = selectedDeviceInfo.value
  if (!device || !item.compatibility) return { status: 'unknown', tips: [] }

  const compat = item.compatibility
  const tips = []
  let incompatible = false

  if (compat.supported_archs?.length) {
    const match = compat.supported_archs.some(arch =>
      device.cpu_abi?.toLowerCase().includes(arch.toLowerCase())
    )
    if (!match) {
      incompatible = true
      tips.push(`仅支持 ${compat.supported_archs.join('/')}`)
    }
  }

  if (compat.min_android_version && device.android_version) {
    if (String(device.android_version) < String(compat.min_android_version)) {
      incompatible = true
      tips.push(`Android 版本需 ≥ ${compat.min_android_version}`)
    }
  }

  if (compat.max_android_version && device.android_version) {
    if (String(device.android_version) > String(compat.max_android_version)) {
      incompatible = true
      tips.push(`Android 版本需 ≤ ${compat.max_android_version}`)
    }
  }

  if (compat.required_features?.length) {
    const deviceFeatures = device.features || []
    const missing = compat.required_features.filter(f => !deviceFeatures.includes(f))
    if (missing.length) {
      incompatible = true
      tips.push(`需设备能力: ${missing.join(', ')}`)
    }
  }

  return {
    status: incompatible ? 'incompatible' : 'ok',
    tips
  }
}

const startTask = async () => {
  if (!canStart.value) return
  
  starting.value = true
  try {
    const payload = {
      device_serial: selectedDevice.value,
      item_ids: selectedItems.value,
      name: `测试任务_${new Date().toLocaleString()}`,
      schedule_type: scheduleType.value
    }
    if (scheduleType.value !== 'immediate') {
      payload.scheduled_time = scheduledTime.value
    }

    const res = await createTask(payload)

    if (isSuccessResponse(res)) {
      if (scheduleType.value === 'immediate') {
        ElMessage.success('任务创建成功')
        router.push(`/tasks/monitor/${res.data.id}`)
      } else {
        ElMessage.success('定时任务创建成功，将由调度器到期触发')
        router.push('/tasks')
      }
    }
  } catch (error) {
    console.error('创建任务失败:', error)
  } finally {
    starting.value = false
  }
}

const fetchData = async () => {
  try {
    const [modulesRes, devicesRes] = await Promise.all([
      getModules(),
      getDevices({ status: 'online' })
    ])

    if (isSuccessResponse(modulesRes)) {
      const moduleList = modulesRes.data.items || []
      // 并行获取每个模块的测试项
      const modulesWithItems = await Promise.all(
        moduleList.map(async (m) => {
          try {
            const detailRes = await getModuleDetail(m.id, true)
            return {
              ...m,
              items: isSuccessResponse(detailRes) ? (detailRes.data.items || []) : [],
              selected: false
            }
          } catch (error) {
            console.error(`获取模块 ${m.name} 测试项失败:`, error)
            return { ...m, items: [], selected: false }
          }
        })
      )
      modules.value = modulesWithItems
    }

    if (isSuccessResponse(devicesRes)) {
      devices.value = devicesRes.data.items
      // 如果从设备页跳转过来，预选择设备
      if (prefillDeviceSerial.value) {
        const exists = devices.value.some(d => d.serial_number === prefillDeviceSerial.value)
        if (exists) {
          selectedDevice.value = prefillDeviceSerial.value
        } else {
          ElMessage.warning(`预选择设备 ${prefillDeviceSerial.value} 不在线或不存在`)
        }
      }
    }
  } catch (error) {
    console.error('获取数据失败:', error)
  }
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped lang="scss">
.module-section {
  margin-bottom: 20px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--tp-border-light);
  
  &:last-child {
    border-bottom: none;
    margin-bottom: 0;
    padding-bottom: 0;
  }
  
  .module-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
    
    .module-name {
      font-weight: 600;
      font-size: 15px;
    }
    
    .module-count {
      font-size: 13px;
      color: var(--tp-text-tertiary);
    }
  }
  
  .items-list {
    padding-left: 25px;
    
    .test-item {
      display: flex;
      flex-direction: column;
      margin-bottom: 10px;
      
      :deep(.el-checkbox__label) {
        flex: 1;
      }
      
      .item-info {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 4px;
        
        .item-name {
          font-weight: 500;
        }
        
        .item-tags {
          display: flex;
          align-items: center;
        }
      }
      
      .item-desc {
        font-size: 12px;
        color: var(--tp-text-tertiary);
      }
    }
  }
}

.device-list {
  .device-option {
    display: flex;
    margin-bottom: 15px;
    width: 100%;
    
    :deep(.el-radio__label) {
      flex: 1;
    }
    
    .device-info {
      .device-name {
        font-weight: 500;
        margin-bottom: 5px;
      }
      
      .device-meta {
        display: flex;
        gap: 10px;
        align-items: center;
        font-size: 13px;
        color: var(--tp-text-secondary);
      }
    }
  }
}

.summary {
  .summary-item {
    display: flex;
    justify-content: space-between;
    margin-bottom: 10px;
    
    .label {
      color: var(--tp-text-secondary);
    }
    
    .value {
      font-weight: 500;
    }
  }
}

.empty-text {
  text-align: center;
  padding: 40px;
  color: var(--tp-text-tertiary);
}
</style>
