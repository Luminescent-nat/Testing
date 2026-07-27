<template>
  <div class="page-container">
    <div class="search-bar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索设备"
        clearable
        style="width: 300px"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      
      <el-select v-model="filterStatus" placeholder="状态筛选" clearable>
        <el-option label="在线" value="online" />
        <el-option label="离线" value="offline" />
        <el-option label="测试中" value="testing" />
      </el-select>
      
      <el-button type="primary" @click="refreshDevices">
        <el-icon><Refresh /></el-icon>
        刷新设备
      </el-button>
    </div>
    
    <el-row :gutter="20">
      <el-col
        v-for="device in filteredDevices"
        :key="device.serial_number"
        :xs="24"
        :sm="12"
        :md="8"
        :lg="6"
      >
        <el-card class="app-card device-card" shadow="hover">
          <div class="device-header">
            <div class="device-status" :class="device.status">
              <el-icon v-if="device.status === 'online'" class="status-icon"><CircleCheckFilled /></el-icon>
              <el-icon v-else-if="device.status === 'testing'" class="status-icon"><Loading /></el-icon>
              <el-icon v-else class="status-icon"><CircleCloseFilled /></el-icon>
            </div>
            <el-dropdown @command="handleCommand($event, device)">
              <el-icon class="more-icon"><MoreFilled /></el-icon>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="detail">查看详情</el-dropdown-item>
                  <el-dropdown-item command="test" :disabled="device.status !== 'online'">
                    开始测试
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
          
          <div class="device-body">
            <div class="device-model">{{ device.model || 'Unknown Device' }}</div>
            <div class="device-serial">{{ device.serial_number }}</div>
            
            <div class="device-info">
              <div class="info-item">
                <el-icon><Phone /></el-icon>
                <span>Android {{ device.android_version }}</span>
              </div>
              <div class="info-item">
                <el-icon><Cpu /></el-icon>
                <span>{{ device.cpu_abi }}</span>
              </div>
              <div class="info-item" v-if="device.battery_level">
                <el-icon><Lightning /></el-icon>
                <span>{{ device.battery_level }}%</span>
              </div>
            </div>
          </div>
          
          <div class="device-footer">
            <el-tag :type="getStatusType(device.status)" size="small">
              {{ getStatusText(device.status) }}
            </el-tag>
            <span class="last-seen">{{ formatTime(device.last_seen_at) }}</span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <div v-if="filteredDevices.length === 0" class="empty-container">
      <el-empty description="暂无设备" />
    </div>

    <!-- 设备详情抽屉 -->
    <el-drawer
      v-model="detailDrawerVisible"
      :title="currentDevice?.model || '设备详情'"
      size="500px"
    >
      <div v-if="currentDevice" v-loading="detailLoading" class="device-detail">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="序列号">{{ currentDevice.serial_number }}</el-descriptions-item>
          <el-descriptions-item label="型号">{{ currentDevice.model || '-' }}</el-descriptions-item>
          <el-descriptions-item label="品牌">{{ currentDevice.brand || '-' }}</el-descriptions-item>
          <el-descriptions-item label="Android 版本">{{ currentDevice.android_version || '-' }}</el-descriptions-item>
          <el-descriptions-item label="SDK 版本">{{ currentDevice.sdk_version || '-' }}</el-descriptions-item>
          <el-descriptions-item label="CPU 架构">{{ currentDevice.cpu_abi || '-' }}</el-descriptions-item>
          <el-descriptions-item label="分辨率">{{ currentDevice.resolution || '-' }}</el-descriptions-item>
          <el-descriptions-item label="主板平台">{{ currentDevice.board || '-' }}</el-descriptions-item>
          <el-descriptions-item label="硬件名称">{{ currentDevice.hardware || '-' }}</el-descriptions-item>
        </el-descriptions>

        <h4 class="section-title">DDR</h4>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="总容量">
            {{ currentDevice.ddr_info?.total_mb ? `${currentDevice.ddr_info.total_mb} MB` : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="可用容量">
            {{ currentDevice.ddr_info?.available_mb ? `${currentDevice.ddr_info.available_mb} MB` : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="频率">
            {{ currentDevice.ddr_info?.freq_mhz ? `${currentDevice.ddr_info.freq_mhz} MHz` : '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <h4 class="section-title">EMMC</h4>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="容量">
            {{ currentDevice.emmc_info?.size_gb ? `${currentDevice.emmc_info.size_gb} GB` : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="型号">{{ currentDevice.emmc_info?.model || '-' }}</el-descriptions-item>
          <el-descriptions-item label="健康状态">{{ currentDevice.emmc_info?.health || '-' }}</el-descriptions-item>
        </el-descriptions>

        <h4 class="section-title">通信模组</h4>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="WIFI 芯片">{{ currentDevice.wifi_chip || '-' }}</el-descriptions-item>
          <el-descriptions-item label="蓝牙芯片">{{ currentDevice.bt_chip || '-' }}</el-descriptions-item>
          <el-descriptions-item label="以太网接口">
            {{ currentDevice.eth_interfaces?.join(', ') || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="能力特征">
            <el-tag v-for="feature in (currentDevice.features || [])" :key="feature" size="small" style="margin-right: 5px">
              {{ feature }}
            </el-tag>
            <span v-if="!(currentDevice.features?.length)">-</span>
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Search, Refresh, CircleCheckFilled, CircleCloseFilled,
  Loading, MoreFilled, Phone, Cpu, Lightning
} from '@element-plus/icons-vue'
import { getDevices, getDeviceDetail, refreshDevices as refreshDevicesApi } from '@/api/device'
import { formatDateTime } from '@/utils/datetime'

const route = useRoute()
const router = useRouter()
const devices = ref([])
const searchKeyword = ref('')
const filterStatus = ref('')
const detailDrawerVisible = ref(false)
const currentDevice = ref(null)
const detailLoading = ref(false)

// 设备列表轮询间隔（毫秒）
const POLL_INTERVAL = 15000
let pollTimer = null

const filteredDevices = computed(() => {
  return devices.value.filter(device => {
    const matchKeyword = !searchKeyword.value || 
      device.model?.toLowerCase().includes(searchKeyword.value.toLowerCase()) ||
      device.serial_number.toLowerCase().includes(searchKeyword.value.toLowerCase())
    
    const matchStatus = !filterStatus.value || device.status === filterStatus.value
    
    return matchKeyword && matchStatus
  })
})

const refreshDevices = async () => {
  try {
    const res = await refreshDevicesApi()
    if (res.code === 200) {
      devices.value = res.data.items || []
      ElMessage.success('刷新成功')
    }
  } catch (error) {
    console.error('刷新设备失败:', error)
  }
}

// 静默拉取设备列表（轮询用，不触发 adb 全量发现、不弹提示）
const fetchDevices = async () => {
  try {
    const res = await getDevices()
    if (res.code === 200) {
      devices.value = res.data.items || []
    }
  } catch (error) {
    console.error('获取设备列表失败:', error)
  }
}

// 页面隐藏时停止轮询，重新可见时立即刷新一次并恢复轮询
const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const startPolling = () => {
  stopPolling()
  pollTimer = setInterval(fetchDevices, POLL_INTERVAL)
}

const handleVisibilityChange = () => {
  if (document.hidden) {
    stopPolling()
  } else {
    fetchDevices()
    startPolling()
  }
}

const getStatusType = (status) => {
  const types = {
    'online': 'success',
    'offline': 'info',
    'testing': 'warning'
  }
  return types[status] || 'info'
}

const getStatusText = (status) => {
  const texts = {
    'online': '在线',
    'offline': '离线',
    'testing': '测试中'
  }
  return texts[status] || status
}

const formatTime = (time) => {
  return formatDateTime(time, 'MM-DD HH:mm')
}

const handleCommand = async (command, device) => {
  switch (command) {
    case 'detail':
      // 先用列表数据打开抽屉，再拉取完整详情（DDR/EMMC 等画像字段）覆盖
      currentDevice.value = device
      detailDrawerVisible.value = true
      detailLoading.value = true
      try {
        const res = await getDeviceDetail(device.serial_number)
        if (res.code === 200) {
          currentDevice.value = res.data
        }
      } catch (error) {
        console.error('获取设备详情失败:', error)
      } finally {
        detailLoading.value = false
      }
      break
    case 'test':
      router.push({
        path: '/tasks/create',
        query: { device: device.serial_number }
      })
      break
  }
}

onMounted(() => {
  // 支持带 ?serial= 跳转（如仪表盘）时自动搜索定位目标设备
  const serial = route.query.serial
  if (serial) {
    searchKeyword.value = String(serial)
  }
  refreshDevices()
  startPolling()
  document.addEventListener('visibilitychange', handleVisibilityChange)
})

onUnmounted(() => {
  stopPolling()
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})
</script>

<style scoped lang="scss">
.device-card {
  margin-bottom: 20px;
  
  .device-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 15px;
    
    .device-status {
      width: 40px;
      height: 40px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      
      &.online {
        background-color: rgba(103, 194, 58, 0.1);
        color: #67c23a;
      }
      
      &.offline {
        background-color: rgba(144, 147, 153, 0.1);
        color: #909399;
      }
      
      &.testing {
        background-color: rgba(230, 162, 60, 0.1);
        color: #e6a23c;
      }
      
      .status-icon {
        font-size: 20px;
      }
    }
    
    .more-icon {
      cursor: pointer;
      color: var(--tp-text-tertiary);
      
      &:hover {
        color: var(--tp-text);
      }
    }
  }
  
  .device-body {
    margin-bottom: 15px;
    
    .device-model {
      font-size: 16px;
      font-weight: 600;
      color: var(--tp-text);
      margin-bottom: 5px;
    }
    
    .device-serial {
      font-size: 12px;
      color: var(--tp-text-tertiary);
      margin-bottom: 15px;
    }
    
    .device-info {
      .info-item {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 8px;
        font-size: 13px;
        color: var(--tp-text-secondary);
        
        .el-icon {
          color: var(--tp-text-tertiary);
        }
      }
    }
  }
  
  .device-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-top: 15px;
    border-top: 1px solid var(--tp-border-light);
    
    .last-seen {
      font-size: 12px;
      color: var(--tp-text-tertiary);
    }
  }
}

.empty-container {
  padding: 60px 0;
}

.device-detail {
  .section-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--tp-text);
    margin: 20px 0 12px;
  }
}
</style>
