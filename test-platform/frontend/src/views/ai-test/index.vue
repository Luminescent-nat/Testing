<template>
  <div class="page-container">
    <el-card class="app-card">
      <template #header>
        <div class="card-header">
          <span>AI 智能测试</span>
          <el-tag type="info">自然语言创建测试任务</el-tag>
        </div>
      </template>

      <el-alert
        title="用自然语言描述测试需求"
        description="例如：对 rk3568 设备做 DDR 稳定性测试；测试 A133P 所有功能"
        type="info"
        show-icon
        :closable="false"
        style="margin-bottom: 20px"
      />

      <el-input
        v-model="inputText"
        type="textarea"
        :rows="4"
        placeholder="请输入测试指令..."
        maxlength="500"
        show-word-limit
      />

      <div class="actions">
        <el-button
          type="primary"
          size="large"
          :loading="parsing"
          :disabled="!inputText.trim()"
          @click="handleSubmit"
        >
          <el-icon><MagicStick /></el-icon>
          创建并执行测试
        </el-button>
      </div>

      <!-- 解析结果预览（产品决策：保留面板；数据来自任务详情 plan 快照） -->
      <div
        v-if="planResult"
        class="plan-preview"
      >
        <h4>解析结果</h4>
        <el-descriptions
          v-if="planResult.hasPlan"
          :column="2"
          border
        >
          <el-descriptions-item label="目标设备">
            {{ planResult.device_serial }}
          </el-descriptions-item>
          <el-descriptions-item label="测试意图">
            {{ planResult.plan.intent }}
          </el-descriptions-item>
          <el-descriptions-item label="测试模块">
            <el-tag
              v-for="module in planResult.plan.selected_modules"
              :key="module"
              size="small"
              style="margin-right: 5px"
            >
              {{ module }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="测试类型">
            {{ planResult.plan.test_type }}
          </el-descriptions-item>
          <el-descriptions-item label="选中测试项">
            {{ planResult.plan.item_ids.length }} 项
          </el-descriptions-item>
        </el-descriptions>
        <el-alert
          v-else
          :title="noPlanText"
          type="info"
          :closable="false"
          show-icon
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { createNaturalTask } from '@/api/ai'
import { getTaskDetail } from '@/api/task'
import { isSuccessResponse } from '@/api/client'
import { NO_PLAN_TEXT, buildPlanPreview, extractCreatedTaskId } from '@/utils/aiTask'

const router = useRouter()
const inputText = ref('')
const parsing = ref(false)
const planResult = ref(null)
const noPlanText = NO_PLAN_TEXT

const handleSubmit = async () => {
  const text = inputText.value.trim()
  if (!text) return

  parsing.value = true
  planResult.value = null

  try {
    const res = await createNaturalTask(text)
    if (!isSuccessResponse(res)) return

    // 契约 v1.1：创建响应 data 为 Task 对象，任务 ID 为正整数 id（legacy task_id 已废弃）
    const taskId = extractCreatedTaskId(res.data)
    if (taskId === null) {
      ElMessage.error('任务创建成功但返回的任务 ID 非法，已取消跳转')
      planResult.value = buildPlanPreview(res.data)
      return
    }

    ElMessage.success('AI 任务已创建')

    // 预览面板（产品决策保留）：创建成功后经 getTaskDetail 拉取详情渲染 plan 快照；
    // plan 为 null/缺失时显示「该任务无规划快照」；详情拉取失败时保留创建响应兜底，不阻塞跳转。
    planResult.value = buildPlanPreview(res.data)
    try {
      const detailRes = await getTaskDetail(taskId)
      if (isSuccessResponse(detailRes)) {
        planResult.value = buildPlanPreview(detailRes.data)
      }
    } catch (detailError) {
      console.error('获取任务详情失败:', detailError)
    }

    setTimeout(() => {
      router.push(`/tasks/monitor/${taskId}`)
    }, 1500)
  } catch (error) {
    console.error('创建 AI 任务失败:', error)
  } finally {
    parsing.value = false
  }
}
</script>

<style scoped lang="scss">
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.actions {
  margin-top: 20px;
  text-align: right;
}

.plan-preview {
  margin-top: 30px;

  h4 {
    margin-bottom: 15px;
    color: var(--tp-text);
  }
}
</style>
