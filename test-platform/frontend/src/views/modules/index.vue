<template>
  <div class="page-container">
    <div class="app-button-group" v-if="isAdmin">
      <el-button type="primary" @click="openCreateDialog">
        <el-icon><Plus /></el-icon>
        创建模块
      </el-button>
      <el-button :loading="scanning" @click="scanTools">
        <el-icon><Refresh /></el-icon>
        扫描注册测试工具
      </el-button>
    </div>
    
    <el-row :gutter="20">
      <el-col
        v-for="module in modules"
        :key="module.id"
        :xs="24"
        :sm="12"
        :md="8"
        :lg="6"
      >
        <el-card class="app-card module-card" shadow="hover">
          <div class="module-header">
            <div class="module-icon">
              <el-icon size="32"><Grid /></el-icon>
            </div>
            <div class="module-actions" v-if="isAdmin">
              <el-button text circle @click="editModule(module)">
                <el-icon><Edit /></el-icon>
              </el-button>
              <el-button text circle type="danger" @click="deleteModule(module)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </div>
          
          <div class="module-body">
            <div class="module-name">{{ module.name }}</div>
            <div class="module-category">{{ module.category || '未分类' }}</div>
            <div class="module-desc">{{ module.description || '暂无描述' }}</div>
            <div class="module-stats">
              <el-tag size="small">{{ module.item_count || 0 }} 个测试项</el-tag>
            </div>
          </div>
          
          <div class="module-footer">
            <el-button text type="primary" @click="viewItems(module)">
              查看测试项
              <el-icon><ArrowRight /></el-icon>
            </el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
    
    <el-empty v-if="modules.length === 0" description="暂无测试模块" />
    
    <!-- 创建/编辑模块对话框 -->
    <el-dialog
      v-model="showCreateDialog"
      :title="editingModule ? '编辑模块' : '创建模块'"
      width="500px"
    >
      <el-form :model="form" label-width="80px">
        <el-form-item label="模块名称" required>
          <el-input v-model="form.name" placeholder="请输入模块名称" />
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="form.category" placeholder="请输入分类" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            rows="3"
            placeholder="请输入描述"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveModule">
          保存
        </el-button>
      </template>
    </el-dialog>
    
    <!-- 测试项管理抽屉 -->
    <el-drawer
      v-model="showItemsDrawer"
      :title="currentModule?.name + ' - 测试项管理'"
      size="700px"
      @closed="onItemsDrawerClosed"
    >
      <div class="drawer-content">
        <div class="drawer-actions" v-if="isAdmin">
          <el-button type="primary" @click="openItemDialog">
            <el-icon><Plus /></el-icon>
            添加测试项
          </el-button>
        </div>
        
        <el-empty v-if="moduleItems.length === 0" description="暂无测试项" />
        
        <el-timeline v-else>
          <el-timeline-item
            v-for="item in moduleItems"
            :key="item.id"
            :type="item.enabled ? 'primary' : 'info'"
          >
            <div class="timeline-content">
              <div class="item-header">
                <span class="item-name">{{ item.name }}</span>
                <div class="item-tags">
                  <el-tag size="small" :type="getExecTypeType(item.exec_type)">
                    {{ getExecTypeText(item.exec_type) }}
                  </el-tag>
                  <el-tag size="small" :type="getJudgeTypeType(item.judgement_type)" style="margin-left: 8px">
                    {{ getJudgeTypeText(item.judgement_type) }}
                  </el-tag>
                </div>
              </div>
              <div class="item-desc">{{ item.description || '暂无描述' }}</div>
              <div class="item-meta">
                <span>命令：{{ item.exec_command || '-' }}</span>
                <span v-if="item.timeout">超时：{{ item.timeout }}s</span>
              </div>
              <div class="item-actions" v-if="isAdmin">
                <el-button text type="primary" @click="editItem(item)">编辑</el-button>
                <el-button text type="danger" @click="deleteItem(item)">删除</el-button>
              </div>
            </div>
          </el-timeline-item>
        </el-timeline>
      </div>
    </el-drawer>
    
    <!-- 添加/编辑测试项对话框 -->
    <el-dialog
      v-model="showItemDialog"
      :title="editingItem ? '编辑测试项' : '添加测试项'"
      width="650px"
      @closed="onItemDialogClosed"
    >
      <el-form :model="itemForm" label-width="100px">
        <el-form-item label="测试项名称" required>
          <el-input v-model="itemForm.name" placeholder="请输入测试项名称" />
        </el-form-item>
        
        <el-form-item label="描述">
          <el-input
            v-model="itemForm.description"
            type="textarea"
            rows="2"
            placeholder="请输入描述"
          />
        </el-form-item>

        <el-form-item>
          <template #label>
            <span>测试目的</span>
            <el-tooltip content="说明本测试项要验证什么，例如：验证 EMMC 顺序读带宽是否达到标称值。" placement="top">
              <el-icon class="label-tip"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input
            v-model="itemForm.objective"
            type="textarea"
            rows="2"
            placeholder="请输入测试目的"
          />
        </el-form-item>

        <el-form-item>
          <template #label>
            <span>前置条件</span>
            <el-tooltip content="执行本测试项前必须满足的条件，例如：设备已 root、已连接 WIFI、存储剩余空间 > 1GB。" placement="top">
              <el-icon class="label-tip"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input
            v-model="itemForm.precondition"
            type="textarea"
            rows="2"
            placeholder="请输入前置条件"
          />
        </el-form-item>

        <el-form-item>
          <template #label>
            <span>测试步骤</span>
            <el-tooltip content="详细的操作步骤，支持多行。例如：1. 推送 fio 到设备 2. 执行 randread 命令 3. 收集 BW 数据。" placement="top">
              <el-icon class="label-tip"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input
            v-model="itemForm.steps"
            type="textarea"
            rows="4"
            placeholder="请输入测试步骤"
          />
        </el-form-item>

        <el-form-item>
          <template #label>
            <span>预期结果</span>
            <el-tooltip content="测试通过时应满足的标准，例如：顺序读带宽 ≥ 100 MB/s，无明显掉速。" placement="top">
              <el-icon class="label-tip"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input
            v-model="itemForm.expected_result"
            type="textarea"
            rows="3"
            placeholder="请输入预期结果"
          />
        </el-form-item>

        <el-form-item label="执行方式" required>
          <el-select v-model="itemForm.exec_type" placeholder="请选择执行方式" style="width: 100%">
            <el-option label="ADB Shell" value="adb_shell" />
            <el-option label="推送并执行" value="push_exec" />
            <el-option label="本地执行" value="host_exec" />
          </el-select>
        </el-form-item>
        
        <el-form-item required>
          <template #label>
            <span>执行命令</span>
            <el-tooltip content="可用占位符：{serial} 设备序列号、{tool} 工具路径，以及 device 字段如 {model} {android_version}。示例：adb -s {serial} shell fio --name=test" placement="top">
              <el-icon class="label-tip"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input
            v-model="itemForm.exec_command"
            type="textarea"
            rows="3"
            placeholder="请输入执行命令或脚本路径"
          />
        </el-form-item>
        
        <el-form-item label="关联工具">
          <el-select
            v-model="itemForm.tool_id"
            placeholder="请选择关联工具（可选）"
            clearable
            style="width: 100%"
          >
            <el-option
              v-for="tool in toolOptions"
              :key="tool.id"
              :label="tool.name"
              :value="tool.id"
            />
          </el-select>
        </el-form-item>
        
        <el-form-item label="推送目标" v-if="itemForm.exec_type === 'push_exec'">
          <el-input v-model="itemForm.push_target" placeholder="设备上的目标路径" />
        </el-form-item>
        
        <el-form-item required>
          <template #label>
            <span>判定方式</span>
            <el-tooltip placement="top">
              <template #content>
                <div style="max-width: 300px; line-height: 1.6">
                  <b>断言规则</b>：按 source/operator/target 匹配，例如 bw_mbps >= 100。<br>
                  <b>评分规则</b>：按阈值区间评分，例如 0-50 分 fail，50-80 分 warning，80-100 分 pass。<br>
                  <b>AI 兜底</b>：前两种未命中时调用大模型判定；需配置 LLM_API_KEY，否则降级为通过。
                </div>
              </template>
              <el-icon class="label-tip"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-select v-model="itemForm.judgement_type" placeholder="请选择判定方式" style="width: 100%">
            <el-option label="断言规则" value="assertion" />
            <el-option label="评分规则" value="rubric" />
            <el-option label="AI 兜底" value="ai_fallback" />
          </el-select>
        </el-form-item>
        
        <el-form-item label="超时时间">
          <el-input-number v-model="itemForm.timeout" :min="10" :max="7200" style="width: 150px" />
          <span class="unit-text">秒</span>
        </el-form-item>
        
        <el-form-item label="失败处理">
          <el-radio-group v-model="itemForm.on_failure">
            <el-radio label="continue">继续</el-radio>
            <el-radio label="stop">停止</el-radio>
          </el-radio-group>
        </el-form-item>
        
        <el-form-item label="重试次数">
          <el-input-number v-model="itemForm.retry_count" :min="0" :max="5" style="width: 150px" />
        </el-form-item>
        
        <el-form-item>
          <template #label>
            <span>参数(JSON)</span>
            <el-tooltip content='执行时使用的默认参数。示例：{"size": "256M", "runtime": "30s"}' placement="top">
              <el-icon class="label-tip"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input
            v-model="itemForm.parametersText"
            type="textarea"
            rows="3"
            placeholder='{"key": "value"}'
          />
        </el-form-item>

        <el-form-item>
          <template #label>
            <span>结果解析(JSON)</span>
            <el-tooltip placement="top">
              <template #content>
                <div style="max-width: 320px; line-height: 1.6">
                  配置如何从命令输出中提取指标。示例：<br>
                  {"regex": "BW=(\\d+)MB/s", "group_index": 1, "key": "bw_mbps"}<br>
                  支持多字段提取，提取后的值会进入判定规则。
                </div>
              </template>
              <el-icon class="label-tip"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input
            v-model="itemForm.resultParseText"
            type="textarea"
            rows="3"
            placeholder='{"regex": "BW=(\\d+)MB/s", "key": "bw_mbps"}'
          />
        </el-form-item>

        <el-form-item v-if="itemForm.judgement_type === 'assertion'">
          <template #label>
            <span>断言规则(JSON)</span>
            <el-tooltip placement="top">
              <template #content>
                <div style="max-width: 320px; line-height: 1.6">
                  示例：<br>
                  {"source": "bw_mbps", "operator": ">=", "target": 100}<br>
                  source 为结果解析后的 key；operator 支持 ==、!=、&gt;、&lt;、&gt;=、&lt;=、contains、regex。
                </div>
              </template>
              <el-icon class="label-tip"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input
            v-model="itemForm.conditionalRulesText"
            type="textarea"
            rows="3"
            placeholder='{"source": "bw_mbps", "operator": ">=", "target": 100}'
          />
        </el-form-item>

        <el-form-item v-if="itemForm.judgement_type === 'rubric'">
          <template #label>
            <span>评分规则(JSON)</span>
            <el-tooltip placement="top">
              <template #content>
                <div style="max-width: 320px; line-height: 1.6">
                  示例：<br>
                  {"metric": "bw_mbps", "criteria": [{"max": 50, "score": 0}, {"min": 50, "max": 100, "score": 60}, {"min": 100, "score": 100}]}<br>
                  score 决定 verdict：0 fail，&lt;80 warning，&ge;80 pass。
                </div>
              </template>
              <el-icon class="label-tip"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input
            v-model="itemForm.rubricCriteriaText"
            type="textarea"
            rows="3"
            placeholder='{"metric": "bw_mbps", "criteria": [...]}'
          />
        </el-form-item>

        <el-form-item>
          <template #label>
            <span>兼容性(JSON)</span>
            <el-tooltip placement="top">
              <template #content>
                <div style="max-width: 320px; line-height: 1.6">
                  支持字段：<br>
                  min_android_version / max_android_version<br>
                  supported_archs: ["arm64-v8a", "armeabi-v7a"]<br>
                  required_features: ["wifi", "bluetooth", "ethernet"]<br>
                  board_patterns / hardware_patterns: 正则列表
                </div>
              </template>
              <el-icon class="label-tip"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input
            v-model="itemForm.compatibilityText"
            type="textarea"
            rows="3"
            placeholder='{"supported_archs": ["arm64-v8a"], "required_features": ["wifi"]}'
          />
        </el-form-item>
        
        <el-form-item label="标签">
          <el-select
            v-model="itemForm.tags"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="输入标签后回车"
            style="width: 100%"
          />
        </el-form-item>
        
        <el-form-item label="启用">
          <el-switch v-model="itemForm.enabled" />
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="showItemDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingItem" @click="saveItem">
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Grid, Edit, Delete, ArrowRight, QuestionFilled, Refresh } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import {
  getModules,
  createModule,
  updateModule,
  deleteModule as deleteModuleApi,
  getModuleItems,
  createItem,
  updateItem,
  deleteItem as deleteItemApi
} from '@/api/module'
import { getTools, scanToolModules } from '@/api/tool'

const userStore = useUserStore()
const isAdmin = computed(() => userStore.isAdmin)

const modules = ref([])
const moduleItems = ref([])
const toolOptions = ref([])
const showCreateDialog = ref(false)
const showItemsDrawer = ref(false)
const showItemDialog = ref(false)
const editingModule = ref(null)
const editingItem = ref(null)
const currentModule = ref(null)
const saving = ref(false)
const savingItem = ref(false)
const scanning = ref(false)

// 扫描 test-tools 下 manifest.yaml，幂等注册测试模块/测试项
const scanTools = async () => {
  scanning.value = true
  try {
    const res = await scanToolModules()
    const data = res.data || {}
    const modules = data.modules || []
    const errors = data.errors || []
    if (modules.length === 0 && errors.length === 0) {
      ElMessage.info('未发现任何 manifest.yaml')
    } else {
      const summary = modules
        .map(m => `${m.name}：新建 ${m.created_items}，更新 ${m.updated_items}`)
        .join('；')
      if (errors.length > 0) {
        ElMessage.warning(`扫描完成（${errors.length} 个错误）：${summary || '无成功模块'}`)
        console.error('扫描注册错误:', errors)
      } else {
        ElMessage.success(`扫描注册完成：${summary}`)
      }
    }
    fetchModules()
  } catch (error) {
    console.error('扫描注册失败:', error)
  } finally {
    scanning.value = false
  }
}

const form = ref({
  name: '',
  category: '',
  description: ''
})

const getDefaultItemForm = () => ({
  name: '',
  description: '',
  objective: '',
  precondition: '',
  steps: '',
  expected_result: '',
  exec_type: 'adb_shell',
  exec_command: '',
  tool_id: null,
  push_target: '',
  judgement_type: 'assertion',
  timeout: 300,
  on_failure: 'continue',
  retry_count: 0,
  parametersText: '{}',
  resultParseText: '{}',
  conditionalRulesText: '{}',
  rubricCriteriaText: '{}',
  compatibilityText: '{}',
  tags: [],
  enabled: true
})

const itemForm = ref(getDefaultItemForm())

const fetchModules = async () => {
  try {
    const res = await getModules()
    if (res.code === 200) {
      modules.value = res.data.items || []
    }
  } catch (error) {
    console.error('获取模块失败:', error)
    ElMessage.error('获取模块失败')
  }
}

const openCreateDialog = () => {
  editingModule.value = null
  form.value = { name: '', category: '', description: '' }
  showCreateDialog.value = true
}

const editModule = (module) => {
  editingModule.value = module
  form.value = {
    name: module.name,
    category: module.category,
    description: module.description
  }
  showCreateDialog.value = true
}

const deleteModule = async (module) => {
  try {
    await ElMessageBox.confirm(`确定删除模块 "${module.name}" 吗？`, '提示', {
      type: 'warning'
    })
    await deleteModuleApi(module.id)
    ElMessage.success('删除成功')
    fetchModules()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除失败:', error)
      ElMessage.error('删除失败')
    }
  }
}

const saveModule = async () => {
  if (!form.value.name) {
    ElMessage.warning('请输入模块名称')
    return
  }
  
  saving.value = true
  try {
    if (editingModule.value) {
      await updateModule(editingModule.value.id, form.value)
      ElMessage.success('更新成功')
    } else {
      await createModule(form.value)
      ElMessage.success('创建成功')
    }
    showCreateDialog.value = false
    fetchModules()
    form.value = { name: '', category: '', description: '' }
    editingModule.value = null
  } catch (error) {
    console.error('保存失败:', error)
    ElMessage.error(error.message || '保存失败')
  } finally {
    saving.value = false
  }
}

const fetchModuleItems = async (moduleId) => {
  try {
    const res = await getModuleItems(moduleId)
    if (res.code === 200) {
      moduleItems.value = res.data.items || []
    } else {
      moduleItems.value = []
    }
  } catch (error) {
    console.error('获取测试项失败:', error)
    moduleItems.value = []
    ElMessage.error('获取测试项失败')
  }
}

const viewItems = async (module) => {
  currentModule.value = module
  showItemsDrawer.value = true
  await fetchModuleItems(module.id)
}

const onItemsDrawerClosed = () => {
  currentModule.value = null
  moduleItems.value = []
}

const openItemDialog = () => {
  editingItem.value = null
  itemForm.value = getDefaultItemForm()
  showItemDialog.value = true
}

const editItem = (item) => {
  editingItem.value = item
  itemForm.value = {
    name: item.name,
    description: item.description || '',
    objective: item.objective || '',
    precondition: item.precondition || '',
    steps: item.steps || '',
    expected_result: item.expected_result || '',
    exec_type: item.exec_type,
    exec_command: item.exec_command || '',
    tool_id: item.tool_id || null,
    push_target: item.push_target || '',
    judgement_type: item.judgement_type,
    timeout: item.timeout,
    on_failure: item.on_failure,
    retry_count: item.retry_count,
    parametersText: JSON.stringify(item.parameters || {}, null, 2),
    resultParseText: JSON.stringify(item.result_parse || {}, null, 2),
    conditionalRulesText: JSON.stringify(item.conditional_rules || {}, null, 2),
    rubricCriteriaText: JSON.stringify(item.rubric_criteria || {}, null, 2),
    compatibilityText: JSON.stringify(item.compatibility || {}, null, 2),
    tags: item.tags || [],
    enabled: item.enabled !== false
  }
  showItemDialog.value = true
}

const deleteItem = async (item) => {
  if (!currentModule.value) return
  try {
    await ElMessageBox.confirm(`确定删除测试项 "${item.name}" 吗？`, '提示', {
      type: 'warning'
    })
    await deleteItemApi(currentModule.value.id, item.id)
    ElMessage.success('删除成功')
    fetchModuleItems(currentModule.value.id)
    fetchModules()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除测试项失败:', error)
      ElMessage.error('删除测试项失败')
    }
  }
}

const parseJsonText = (text, fieldName) => {
  if (!text || text.trim() === '') return {}
  try {
    return JSON.parse(text)
  } catch (error) {
    throw new Error(`${fieldName} 不是有效的 JSON`)
  }
}

const saveItem = async () => {
  if (!itemForm.value.name) {
    ElMessage.warning('请输入测试项名称')
    return
  }
  if (!itemForm.value.exec_command) {
    ElMessage.warning('请输入执行命令')
    return
  }
  if (!currentModule.value) {
    ElMessage.error('未选择模块')
    return
  }
  
  let parameters
  let resultParse
  let conditionalRules
  let rubricCriteria
  let compatibility
  try {
    parameters = parseJsonText(itemForm.value.parametersText, '参数')
    resultParse = parseJsonText(itemForm.value.resultParseText, '结果解析')
    conditionalRules = parseJsonText(itemForm.value.conditionalRulesText, '断言规则')
    rubricCriteria = parseJsonText(itemForm.value.rubricCriteriaText, '评分规则')
    compatibility = parseJsonText(itemForm.value.compatibilityText, '兼容性')
  } catch (error) {
    ElMessage.warning(error.message)
    return
  }

  const payload = {
    module_id: currentModule.value.id,
    name: itemForm.value.name,
    description: itemForm.value.description,
    objective: itemForm.value.objective,
    precondition: itemForm.value.precondition,
    steps: itemForm.value.steps,
    expected_result: itemForm.value.expected_result,
    exec_type: itemForm.value.exec_type,
    exec_command: itemForm.value.exec_command,
    tool_id: itemForm.value.tool_id,
    push_target: itemForm.value.push_target,
    judgement_type: itemForm.value.judgement_type,
    timeout: itemForm.value.timeout,
    on_failure: itemForm.value.on_failure,
    retry_count: itemForm.value.retry_count,
    parameters,
    result_parse: resultParse,
    conditional_rules: conditionalRules,
    rubric_criteria: rubricCriteria,
    compatibility,
    tags: itemForm.value.tags,
    enabled: itemForm.value.enabled
  }
  
  savingItem.value = true
  try {
    if (editingItem.value) {
      await updateItem(currentModule.value.id, editingItem.value.id, payload)
      ElMessage.success('更新成功')
    } else {
      await createItem(currentModule.value.id, payload)
      ElMessage.success('创建成功')
    }
    showItemDialog.value = false
    await fetchModuleItems(currentModule.value.id)
    fetchModules()
  } catch (error) {
    console.error('保存测试项失败:', error)
    ElMessage.error(error.message || '保存测试项失败')
  } finally {
    savingItem.value = false
  }
}

const onItemDialogClosed = () => {
  editingItem.value = null
  itemForm.value = getDefaultItemForm()
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

const fetchTools = async () => {
  try {
    const res = await getTools()
    if (res.code === 200) {
      toolOptions.value = res.data.items || []
    }
  } catch (error) {
    console.error('获取工具列表失败:', error)
  }
}

onMounted(() => {
  fetchModules()
  fetchTools()
})
</script>

<style scoped lang="scss">
.module-card {
  margin-bottom: 20px;
  
  .module-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 15px;
    
    .module-icon {
      width: 48px;
      height: 48px;
      border-radius: 8px;
      background-color: var(--el-color-primary-light-9);
      color: var(--el-color-primary);
      display: flex;
      align-items: center;
      justify-content: center;
    }
    
    .module-actions {
      display: flex;
      gap: 5px;
    }
  }
  
  .module-body {
    margin-bottom: 15px;
    
    .module-name {
      font-size: 16px;
      font-weight: 600;
      color: var(--tp-text);
      margin-bottom: 5px;
    }
    
    .module-category {
      font-size: 13px;
      color: var(--tp-text-secondary);
      margin-bottom: 10px;
    }
    
    .module-desc {
      font-size: 13px;
      color: var(--tp-text-tertiary);
      margin-bottom: 10px;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
  }
  
  .module-footer {
    padding-top: 15px;
    border-top: 1px solid var(--tp-border-light);
  }
}

.drawer-content {
  padding: 20px;
  
  .drawer-actions {
    margin-bottom: 20px;
  }
  
  .timeline-content {
    .item-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
      
      .item-name {
        font-weight: 500;
      }
    }
    
    .item-desc {
      font-size: 13px;
      color: var(--tp-text-secondary);
      margin-bottom: 10px;
    }
    
    .item-meta {
      font-size: 12px;
      color: var(--tp-text-tertiary);
      margin-bottom: 10px;
      
      span {
        margin-right: 15px;
      }
    }
    
    .item-actions {
      display: flex;
      gap: 10px;
    }
  }
}

.unit-text {
  margin-left: 10px;
  color: var(--tp-text-secondary);
}

.label-tip {
  margin-left: 4px;
  color: var(--el-color-info);
  cursor: help;
  font-size: 14px;
  vertical-align: middle;
}
</style>
