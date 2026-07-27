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

      <!-- 解析结果预览 -->
      <div v-if="planResult" class="plan-preview">
        <h4>解析结果</h4>
        <el-descriptions :column="2" border>
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

const router = useRouter()
const inputText = ref('')
const parsing = ref(false)
const planResult = ref(null)

const handleSubmit = async () => {
  const text = inputText.value.trim()
  if (!text) return

  parsing.value = true
  planResult.value = null

  try {
    const res = await createNaturalTask(text)
    if (res.code === 200) {
      ElMessage.success('AI 任务已创建')
      planResult.value = res.data
      setTimeout(() => {
        router.push(`/tasks/monitor/${res.data.task_id}`)
      }, 1500)
    }
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
