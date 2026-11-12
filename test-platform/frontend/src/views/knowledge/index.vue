<template>
  <div class="page-container">
    <!-- 搜索与上传栏 -->
    <div class="search-bar">
      <el-input
        v-model="searchForm.keyword"
        placeholder="搜索标题 / 分类 / 内容"
        clearable
        style="width: 260px"
        @keyup.enter="fetchEntries"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>

      <el-select
        v-model="searchForm.entry_type"
        placeholder="类型"
        clearable
        style="width: 140px"
        @change="fetchEntries"
      >
        <el-option
          v-for="item in entryTypeOptions"
          :key="item.value"
          :label="item.label"
          :value="item.value"
        />
      </el-select>

      <el-select
        v-model="searchForm.status"
        placeholder="状态"
        clearable
        style="width: 120px"
        @change="fetchEntries"
      >
        <el-option
          v-for="item in statusOptions"
          :key="item.value"
          :label="item.label"
          :value="item.value"
        />
      </el-select>

      <el-input
        v-model="searchForm.category"
        placeholder="分类"
        clearable
        style="width: 140px"
        @keyup.enter="fetchEntries"
      />

      <el-button type="primary" @click="fetchEntries">
        <el-icon><Search /></el-icon>
        查询
      </el-button>

      <el-button @click="resetSearch">
        <el-icon><RefreshRight /></el-icon>
        重置
      </el-button>

      <div class="search-actions">
        <el-button type="success" @click="openUploadDialog">
          <el-icon><Upload /></el-icon>
          上传资料
        </el-button>

        <el-button type="primary" v-if="isAdmin" @click="openEditDialog()">
          <el-icon><Plus /></el-icon>
          新增条目
        </el-button>
      </div>
    </div>

    <!-- 语义搜索栏 -->
    <div class="semantic-search-bar">
      <el-input
        v-model="semanticQuery"
        placeholder="语义搜索：输入测试意图，如 EMMC 稳定性测试规范"
        clearable
        style="width: 420px"
        @keyup.enter="handleSemanticSearch"
      >
        <template #prefix>
          <el-icon><MagicStick /></el-icon>
        </template>
      </el-input>

      <el-button type="primary" :loading="searching" @click="handleSemanticSearch">
        <el-icon><Search /></el-icon>
        语义搜索
      </el-button>

      <el-button v-if="isSemanticMode" @click="exitSemanticSearch">
        返回列表
      </el-button>

      <span class="semantic-tip">基于关键词 + 向量相似度的混合检索</span>
    </div>

    <!-- 标签筛选 -->
    <div class="tag-filter" v-if="allTags.length && !isSemanticMode">
      <span class="filter-label">标签：</span>
      <el-check-tag
        :checked="!searchForm.tag"
        @click="searchForm.tag = ''"
        class="filter-tag"
      >
        全部
      </el-check-tag>
      <el-check-tag
        v-for="tag in allTags"
        :key="tag"
        :checked="searchForm.tag === tag"
        @click="searchForm.tag = tag"
        class="filter-tag"
      >
        {{ tag }}
      </el-check-tag>
    </div>

    <!-- 语义搜索结果 -->
    <div v-if="isSemanticMode">
      <div class="search-summary" v-if="!searching">
        语义搜索 “<strong>{{ semanticQuery }}</strong>” 共找到 {{ searchResults.length }} 条结果
      </div>

      <el-empty v-if="!searching && searchResults.length === 0" description="未找到相关知识" />

      <el-row v-else :gutter="20">
        <el-col
          v-for="item in searchResults"
          :key="item.id"
          :xs="24"
          :sm="12"
          :lg="8"
          :xl="6"
          style="margin-bottom: 20px"
        >
          <el-card class="app-card knowledge-card search-result-card" shadow="hover">
            <div class="score-badge">相似度 {{ item.score }}</div>
            <div class="card-header">
              <div class="title-wrapper">
                <el-tag size="small" :type="entryTypeColor(item.entry_type)" effect="light">
                  {{ entryTypeLabel(item.entry_type) }}
                </el-tag>
                <span class="entry-title" :title="item.title">{{ item.title }}</span>
              </div>
            </div>

            <div class="card-meta">
              <span v-if="item.category" class="meta-item">
                <el-icon><Folder /></el-icon>
                {{ item.category }}
              </span>
              <span class="meta-item">
                <el-tag size="small" :type="statusColor(item.status)">
                  {{ statusLabel(item.status) }}
                </el-tag>
              </span>
            </div>

            <div class="card-tags" v-if="item.tags?.length">
              <el-tag
                v-for="tag in item.tags.slice(0, 4)"
                :key="tag"
                size="small"
                type="info"
                effect="plain"
                class="tag-item"
              >
                {{ tag }}
              </el-tag>
            </div>

            <div class="card-content-preview">
              {{ item.content ? item.content.slice(0, 120) : '暂无内容' }}
            </div>

            <div class="score-breakdown">
              关键词 {{ item.keyword_score }} · 语义 {{ item.semantic_score }}
            </div>

            <div class="card-actions">
              <el-button text type="primary" size="small" @click="openDetailById(item.id)">
                查看详情
              </el-button>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <!-- 列表 -->
    <el-empty v-if="!isSemanticMode && !loading && entries.length === 0" description="暂无知识库条目" />

    <el-row v-else-if="!isSemanticMode" :gutter="20">
      <el-col
        v-for="entry in entries"
        :key="entry.id"
        :xs="24"
        :sm="12"
        :lg="8"
        :xl="6"
        style="margin-bottom: 20px"
      >
        <el-card class="app-card knowledge-card" shadow="hover">
          <div class="card-header">
            <div class="title-wrapper">
              <el-tag size="small" :type="entryTypeColor(entry.entry_type)" effect="light">
                {{ entryTypeLabel(entry.entry_type) }}
              </el-tag>
              <span class="entry-title" :title="entry.title">{{ entry.title }}</span>
            </div>
            <el-dropdown v-if="isAdmin" @command="handleCommand($event, entry)">
              <el-button text circle size="small">
                <el-icon><MoreFilled /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="edit">
                    <el-icon><Edit /></el-icon>编辑
                  </el-dropdown-item>
                  <el-dropdown-item command="delete" divided>
                    <el-icon><Delete /></el-icon>删除
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>

          <div class="card-meta">
            <span v-if="entry.category" class="meta-item">
              <el-icon><Folder /></el-icon>
              {{ entry.category }}
            </span>
            <span class="meta-item">
              <el-tag size="small" :type="statusColor(entry.status)">
                {{ statusLabel(entry.status) }}
              </el-tag>
            </span>
          </div>

          <div class="card-tags" v-if="entry.tags?.length">
            <el-tag
              v-for="tag in entry.tags.slice(0, 4)"
              :key="tag"
              size="small"
              type="info"
              effect="plain"
              class="tag-item"
            >
              {{ tag }}
            </el-tag>
          </div>

          <div class="card-content-preview">
            {{ entry.content ? entry.content.slice(0, 120) : '暂无内容' }}
          </div>

          <div class="card-footer">
            <div class="stats">
              <el-tooltip content="命中次数">
                <span class="stat-item"><el-icon><View /></el-icon>{{ entry.hit_count || 0 }}</span>
              </el-tooltip>
              <el-tooltip content="通过次数">
                <span class="stat-item"><el-icon><CircleCheck /></el-icon>{{ entry.pass_count || 0 }}</span>
              </el-tooltip>
              <el-tooltip content="失败次数">
                <span class="stat-item"><el-icon><CircleClose /></el-icon>{{ entry.fail_count || 0 }}</span>
              </el-tooltip>
            </div>
            <div class="update-time">{{ formatTime(entry.updated_at) }}</div>
          </div>

          <div class="card-actions">
            <el-button text type="primary" size="small" @click="openDetail(entry)">
              查看详情
            </el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 分页 -->
    <div class="pagination-container" v-if="total > 0">
      <el-pagination
        v-model:current-page="searchForm.page"
        v-model:page-size="searchForm.page_size"
        :page-sizes="[12, 24, 48]"
        :total="total"
        layout="total, sizes, prev, pager, next"
        @change="fetchEntries"
      />
    </div>

    <!-- 详情弹窗 -->
    <el-dialog
      v-model="detailVisible"
      :title="currentEntry?.title || '知识详情'"
      width="700px"
      class="knowledge-detail-dialog"
    >
      <div class="detail-header">
        <el-tag :type="entryTypeColor(currentEntry?.entry_type)" effect="light">
          {{ entryTypeLabel(currentEntry?.entry_type) }}
        </el-tag>
        <el-tag v-if="currentEntry?.category" type="info" effect="plain" style="margin-left: 8px">
          {{ currentEntry.category }}
        </el-tag>
        <el-tag :type="statusColor(currentEntry?.status)" style="margin-left: 8px">
          {{ statusLabel(currentEntry?.status) }}
        </el-tag>
      </div>

      <div class="detail-tags" v-if="currentEntry?.tags?.length">
        <el-tag
          v-for="tag in currentEntry.tags"
          :key="tag"
          size="small"
          type="info"
          effect="plain"
          style="margin-right: 6px"
        >
          {{ tag }}
        </el-tag>
      </div>

      <div class="detail-content" v-if="currentEntry?.content">
        <pre>{{ currentEntry.content }}</pre>
      </div>
      <el-empty v-else description="暂无正文内容" />

      <!-- AI 提取的测试用例 -->
      <div class="detail-test-cases" v-if="currentEntry?.meta?.ai_extracted_test_cases?.test_cases?.length">
        <div class="meta-title">AI 提取的测试用例（{{ currentEntry.meta.ai_extracted_test_cases.test_cases.length }} 条）</div>
        <div class="test-case-list">
          <el-collapse>
            <el-collapse-item
              v-for="(tc, idx) in currentEntry.meta.ai_extracted_test_cases.test_cases"
              :key="idx"
              :title="`${tc.module_name || '未分类'} / ${tc.name}`"
            >
              <el-descriptions :column="1" size="small" border>
                <el-descriptions-item label="测试目的" v-if="tc.objective">{{ tc.objective }}</el-descriptions-item>
                <el-descriptions-item label="前置条件" v-if="tc.precondition">{{ tc.precondition }}</el-descriptions-item>
                <el-descriptions-item label="测试步骤" v-if="tc.steps">
                  <pre class="case-steps">{{ tc.steps }}</pre>
                </el-descriptions-item>
                <el-descriptions-item label="预期结果" v-if="tc.expected_result">{{ tc.expected_result }}</el-descriptions-item>
                <el-descriptions-item label="执行方式" v-if="tc.exec_type">{{ tc.exec_type }}</el-descriptions-item>
                <el-descriptions-item label="判定方式" v-if="tc.judgement_type">{{ tc.judgement_type }}</el-descriptions-item>
                <el-descriptions-item label="超时" v-if="tc.timeout">{{ tc.timeout }} 秒</el-descriptions-item>
              </el-descriptions>
            </el-collapse-item>
          </el-collapse>
        </div>
      </div>

      <div class="detail-meta" v-if="currentEntry?.meta && Object.keys(currentEntry.meta).length">
        <div class="meta-title">扩展信息</div>
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item
            v-for="(value, key) in currentEntry.meta"
            :key="key"
            :label="key"
          >
            {{ formatMetaValue(value) }}
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <div class="detail-stats">
        <span>命中 {{ currentEntry?.hit_count || 0 }}</span>
        <span>通过 {{ currentEntry?.pass_count || 0 }}</span>
        <span>失败 {{ currentEntry?.fail_count || 0 }}</span>
        <span>更新于 {{ formatTime(currentEntry?.updated_at) }}</span>
      </div>

      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button type="primary" :loading="embedding" @click="handleEmbed(currentEntry.id)">
          生成嵌入
        </el-button>
        <el-button type="success" :loading="extracting" @click="handleExtract(currentEntry.id)">
          AI 提取
        </el-button>
        <el-button type="warning" v-if="isAdmin" @click="openConvertDialog(currentEntry)">
          转为测试资产
        </el-button>
      </template>
    </el-dialog>

    <!-- 编辑弹窗 -->
    <el-dialog
      v-model="editVisible"
      :title="editingEntry ? '编辑知识条目' : '新增知识条目'"
      width="650px"
    >
      <el-form :model="editForm" label-width="90px">
        <el-form-item label="标题" required>
          <el-input v-model="editForm.title" placeholder="例如：EMMC 性能测试规范" />
        </el-form-item>

        <el-form-item label="类型" required>
          <el-select v-model="editForm.entry_type" placeholder="请选择类型" style="width: 100%">
            <el-option
              v-for="item in entryTypeOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="分类">
          <el-select
            v-model="editForm.category"
            filterable
            allow-create
            default-first-option
            clearable
            placeholder="例如：存储测试 / 网络测试"
            style="width: 100%"
          >
            <el-option
              v-for="cat in categoryOptions"
              :key="cat"
              :label="cat"
              :value="cat"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="标签">
          <el-select
            v-model="editForm.tags"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="输入标签后回车"
            style="width: 100%"
          >
            <el-option
              v-for="tag in tagOptions"
              :key="tag"
              :label="tag"
              :value="tag"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="状态" required>
          <el-select v-model="editForm.status" placeholder="请选择状态" style="width: 100%">
            <el-option
              v-for="item in statusOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="内容">
          <el-input
            v-model="editForm.content"
            type="textarea"
            :rows="8"
            placeholder="输入知识库正文内容"
          />
        </el-form-item>

        <el-form-item label="来源">
          <el-input v-model="editForm.source_type" placeholder="例如：manual / upload / ai_extracted" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEntry">保存</el-button>
      </template>
    </el-dialog>

    <!-- 上传弹窗 -->
    <el-dialog
      v-model="uploadVisible"
      title="上传测试资料"
      width="550px"
    >
      <el-form :model="uploadForm" label-width="80px">
        <el-form-item label="标题" required>
          <el-input v-model="uploadForm.title" placeholder="资料标题" />
        </el-form-item>

        <el-form-item label="分类">
          <el-select
            v-model="uploadForm.category"
            filterable
            allow-create
            default-first-option
            clearable
            placeholder="例如：测试规范 / 操作手册"
            style="width: 100%"
          >
            <el-option
              v-for="cat in categoryOptions"
              :key="cat"
              :label="cat"
              :value="cat"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="标签">
          <el-select
            v-model="uploadForm.tags"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="输入标签后回车"
            style="width: 100%"
          >
            <el-option
              v-for="tag in tagOptions"
              :key="tag"
              :label="tag"
              :value="tag"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="文件" required>
          <el-upload
            ref="uploadRef"
            action="#"
            :auto-upload="false"
            :on-change="handleFileChange"
            :limit="1"
            drag
            accept=".txt,.md,.pdf,.docx,.xlsx,.xls,.png,.jpg,.jpeg,.webp"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">
              拖拽文件到此处或 <em>点击上传</em>
            </div>
            <template #tip>
              <div class="el-upload__tip">
                支持 txt / md / pdf / docx / xlsx / 图片，单个文件不超过 20MB
              </div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="submitUpload">上传并解析</el-button>
      </template>
    </el-dialog>

    <!-- 转换向导弹窗 -->
    <el-dialog
      v-model="convertVisible"
      title="转为测试资产"
      width="700px"
      :close-on-click-modal="false"
    >
      <el-steps :active="convertStep" finish-status="success" simple>
        <el-step title="选择类型" />
        <el-step title="AI 预览" />
        <el-step title="确认转换" />
      </el-steps>

      <div v-if="convertStep === 0" style="margin-top: 20px">
        <el-form :model="convertForm" label-width="100px">
          <el-form-item label="目标资产">
            <el-radio-group v-model="convertForm.target_type">
              <el-radio label="test_item">测试项</el-radio>
              <el-radio label="failure_pattern">失败模式</el-radio>
              <el-radio label="baseline">统计基线</el-radio>
              <el-radio label="rule">判定规则</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="补充要求">
            <el-input
              v-model="convertForm.extra_hint"
              type="textarea"
              :rows="3"
              placeholder="可选：告诉 AI 需要重点提取什么，例如‘提取 fio 参数和判定阈值’"
            />
          </el-form-item>
        </el-form>
      </div>

      <div v-else-if="convertStep === 1" style="margin-top: 20px">
        <el-alert
          v-if="convertLoading"
          title="正在使用 AI 解析资料内容，请稍候..."
          type="info"
          :closable="false"
          show-icon
        />
        <div v-else>
          <el-alert
            title="请检查并修正 AI 解析结果，确认无误后点击下一步"
            type="warning"
            :closable="false"
            show-icon
            style="margin-bottom: 15px"
          />
          <el-input
            v-model="convertPreviewText"
            type="textarea"
            :rows="18"
            placeholder="AI 预览结果将以 JSON 形式展示"
          />
        </div>
      </div>

      <div v-else style="margin-top: 20px">
        <el-result icon="success" title="预览完成" sub-title="点击下方按钮完成转换">
          <template #extra>
            <el-descriptions :column="1" border>
              <el-descriptions-item label="目标类型">
                {{ convertTypeLabel(convertForm.target_type) }}
              </el-descriptions-item>
              <el-descriptions-item label="来源条目">
                {{ convertingEntry?.title }}
              </el-descriptions-item>
            </el-descriptions>
          </template>
        </el-result>
      </div>

      <template #footer>
        <el-button @click="convertVisible = false">取消</el-button>
        <el-button v-if="convertStep > 0" @click="convertStep--">上一步</el-button>
        <el-button
          v-if="convertStep === 0"
          type="primary"
          :loading="convertLoading"
          @click="generateConvertPreview"
        >
          生成预览
        </el-button>
        <el-button
          v-if="convertStep === 1"
          type="primary"
          :disabled="convertLoading"
          @click="validateAndNext"
        >
          下一步
        </el-button>
        <el-button
          v-if="convertStep === 2"
          type="success"
          :loading="convertSaving"
          @click="submitConvert"
        >
          确认转换
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Search, RefreshRight, Upload, Plus, MoreFilled, Edit, Delete,
  Folder, View, CircleCheck, CircleClose, UploadFilled, MagicStick
} from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import { formatDateTime } from '@/utils/datetime'
import { isSuccessResponse } from '@/api/client'
import {
  getKnowledgeEntries,
  getKnowledgeEntry,
  createKnowledgeEntry,
  updateKnowledgeEntry,
  deleteKnowledgeEntry,
  uploadKnowledgeDocument,
  searchKnowledge,
  embedKnowledgeEntry,
  extractKnowledgeEntry,
  getKnowledgeCategories,
  getKnowledgeTags,
  previewConvertKnowledgeEntry,
  convertKnowledgeEntry
} from '@/api/knowledge'

const userStore = useUserStore()
const isAdmin = computed(() => userStore.userInfo?.role === 'admin')

const loading = ref(false)
const saving = ref(false)
const uploading = ref(false)
const searching = ref(false)
const embedding = ref(false)
const extracting = ref(false)
const entries = ref([])
const total = ref(0)
const allTags = ref([])

// 语义搜索
const isSemanticMode = ref(false)
const semanticQuery = ref('')
const searchResults = ref([])

const searchForm = reactive({
  keyword: '',
  entry_type: '',
  status: '',
  category: '',
  tag: '',
  page: 1,
  page_size: 12
})

const entryTypeOptions = [
  { value: 'document', label: '文档资料' },
  { value: 'test_case', label: '测试用例' },
  { value: 'device_profile', label: '设备画像' },
  { value: 'rule', label: '判定规则' },
  { value: 'failure_pattern', label: '失败模式' },
  { value: 'baseline', label: '基线指标' },
  { value: 'skill', label: '执行技能' }
]

const statusOptions = [
  { value: 'draft', label: '草稿' },
  { value: 'approved', label: '已审核' },
  { value: 'rejected', label: '已拒绝' },
  { value: 'deprecated', label: '已废弃' }
]

const entryTypeColor = (type) => {
  const map = {
    document: 'info',
    test_case: 'success',
    device_profile: 'warning',
    rule: 'primary',
    failure_pattern: 'danger',
    baseline: '',
    skill: 'success'
  }
  return map[type] || 'info'
}

const entryTypeLabel = (type) => {
  const item = entryTypeOptions.find(i => i.value === type)
  return item ? item.label : type
}

const statusColor = (status) => {
  const map = {
    draft: 'info',
    approved: 'success',
    rejected: 'danger',
    deprecated: ''
  }
  return map[status] || 'info'
}

const statusLabel = (status) => {
  const item = statusOptions.find(i => i.value === status)
  return item ? item.label : status
}

const formatTime = (time) => {
  return formatDateTime(time, 'YYYY-MM-DD HH:mm')
}

const formatMetaValue = (value) => {
  if (typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}

const collectTags = () => {
  const set = new Set()
  entries.value.forEach(entry => {
    (entry.tags || []).forEach(tag => set.add(tag))
  })
  allTags.value = Array.from(set).slice(0, 30)
}

const fetchEntries = async () => {
  loading.value = true
  try {
    const params = { ...searchForm }
    Object.keys(params).forEach(key => {
      if (params[key] === '') delete params[key]
    })
    const res = await getKnowledgeEntries(params)
    if (isSuccessResponse(res)) {
      entries.value = res.data?.items || []
      total.value = res.data?.total || 0
      collectTags()
    }
  } catch (error) {
    console.error('获取知识库失败:', error)
  } finally {
    loading.value = false
  }
}

const resetSearch = () => {
  searchForm.keyword = ''
  searchForm.entry_type = ''
  searchForm.status = ''
  searchForm.category = ''
  searchForm.tag = ''
  searchForm.page = 1
  fetchEntries()
}

const handleSemanticSearch = async () => {
  if (!semanticQuery.value.trim()) {
    ElMessage.warning('请输入语义搜索内容')
    return
  }
  searching.value = true
  isSemanticMode.value = true
  try {
    const res = await searchKnowledge({
      query: semanticQuery.value.trim(),
      top_k: 20,
      entry_type: searchForm.entry_type || undefined,
      category: searchForm.category || undefined,
      status: searchForm.status || undefined,
      tag: searchForm.tag || undefined
    })
    if (isSuccessResponse(res)) {
      searchResults.value = res.data?.items || []
    }
  } catch (error) {
    console.error('语义搜索失败:', error)
  } finally {
    searching.value = false
  }
}

const exitSemanticSearch = () => {
  isSemanticMode.value = false
  semanticQuery.value = ''
  searchResults.value = []
}

const openDetailById = async (id) => {
  try {
    const res = await getKnowledgeEntry(id)
    if (isSuccessResponse(res)) {
      currentEntry.value = res.data
      detailVisible.value = true
    }
  } catch (error) {
    console.error('获取详情失败:', error)
  }
}

// 详情
const detailVisible = ref(false)
const currentEntry = ref(null)

const openDetail = async (entry) => {
  try {
    const res = await getKnowledgeEntry(entry.id)
    if (isSuccessResponse(res)) {
      currentEntry.value = res.data
      detailVisible.value = true
    }
  } catch (error) {
    console.error('获取详情失败:', error)
  }
}

// 编辑
const editVisible = ref(false)
const editingEntry = ref(null)
const editForm = reactive({
  title: '',
  entry_type: 'document',
  category: '',
  tags: [],
  status: 'draft',
  content: '',
  source_type: 'manual'
})

const openEditDialog = (entry = null) => {
  editingEntry.value = entry
  if (entry) {
    Object.assign(editForm, {
      title: entry.title,
      entry_type: entry.entry_type,
      category: entry.category || '',
      tags: entry.tags || [],
      status: entry.status,
      content: entry.content || '',
      source_type: entry.source_type || 'manual'
    })
  } else {
    Object.assign(editForm, {
      title: '',
      entry_type: 'document',
      category: '',
      tags: [],
      status: 'draft',
      content: '',
      source_type: 'manual'
    })
  }
  editVisible.value = true
}

const saveEntry = async () => {
  if (!editForm.title || !editForm.entry_type || !editForm.status) {
    ElMessage.warning('请填写必填项')
    return
  }
  saving.value = true
  try {
    if (editingEntry.value) {
      await updateKnowledgeEntry(editingEntry.value.id, editForm)
      ElMessage.success('更新成功')
    } else {
      await createKnowledgeEntry(editForm)
      ElMessage.success('创建成功')
    }
    editVisible.value = false
    fetchEntries()
  } catch (error) {
    console.error('保存知识条目失败:', error)
  } finally {
    saving.value = false
  }
}

const handleCommand = async (command, entry) => {
  if (command === 'edit') {
    openEditDialog(entry)
  } else if (command === 'delete') {
    try {
      await ElMessageBox.confirm(`确定删除 "${entry.title}" 吗？`, '提示', { type: 'warning' })
      await deleteKnowledgeEntry(entry.id)
      ElMessage.success('删除成功')
      fetchEntries()
    } catch (error) {
      if (error !== 'cancel') {
        console.error('删除知识条目失败:', error)
      }
    }
  }
}

const handleEmbed = async (id) => {
  embedding.value = true
  try {
    const res = await embedKnowledgeEntry(id)
    if (isSuccessResponse(res)) {
      ElMessage.success(res.data?.has_embedding ? '嵌入生成成功' : '嵌入未启用或生成失败')
    }
  } catch (error) {
    console.error('生成嵌入失败:', error)
  } finally {
    embedding.value = false
  }
}

const handleExtract = async (id) => {
  extracting.value = true
  try {
    const res = await extractKnowledgeEntry(id)
    if (isSuccessResponse(res)) {
      ElMessage.success('AI 提取完成')
      if (currentEntry.value) {
        currentEntry.value.meta = {
          ...(currentEntry.value.meta || {}),
          ai_extracted: res.data
        }
      }
    }
  } catch (error) {
    console.error('AI 提取失败:', error)
  } finally {
    extracting.value = false
  }
}

// 分类 / 标签建议
const categoryOptions = ref([])
const tagOptions = ref([])

const loadCategoriesAndTags = async () => {
  try {
    const [catRes, tagRes] = await Promise.all([
      getKnowledgeCategories(),
      getKnowledgeTags()
    ])
    if (isSuccessResponse(catRes)) {
      categoryOptions.value = catRes.data || []
    }
    if (isSuccessResponse(tagRes)) {
      tagOptions.value = tagRes.data || []
    }
  } catch (error) {
    console.error('加载分类标签失败:', error)
  }
}

// 转为测试资产
const convertVisible = ref(false)
const convertStep = ref(0)
const convertLoading = ref(false)
const convertSaving = ref(false)
const convertingEntry = ref(null)
const convertForm = reactive({
  target_type: 'test_item',
  extra_hint: ''
})
const convertPreviewText = ref('')

const convertTypeLabel = (type) => {
  const map = {
    test_item: '测试项',
    failure_pattern: '失败模式',
    baseline: '统计基线',
    rule: '判定规则'
  }
  return map[type] || type
}

const openConvertDialog = (entry) => {
  convertingEntry.value = entry
  convertForm.target_type = 'test_item'
  convertForm.extra_hint = ''
  convertPreviewText.value = ''
  convertStep.value = 0
  convertVisible.value = true
}

const generateConvertPreview = async () => {
  if (!convertingEntry.value) return
  convertLoading.value = true
  try {
    const res = await previewConvertKnowledgeEntry(convertingEntry.value.id, {
      target_type: convertForm.target_type,
      extra_hint: convertForm.extra_hint
    })
    if (isSuccessResponse(res)) {
      convertPreviewText.value = JSON.stringify(res.data?.preview_data || {}, null, 2)
      convertStep.value = 1
    }
  } catch (error) {
    console.error('生成预览失败:', error)
    ElMessage.error('生成预览失败，请检查 LLM 配置')
  } finally {
    convertLoading.value = false
  }
}

const validateAndNext = () => {
  try {
    JSON.parse(convertPreviewText.value)
    convertStep.value = 2
  } catch (e) {
    ElMessage.error('预览内容不是合法 JSON，请修正')
  }
}

const submitConvert = async () => {
  if (!convertingEntry.value) return
  let previewData
  try {
    previewData = JSON.parse(convertPreviewText.value)
  } catch (e) {
    ElMessage.error('预览内容不是合法 JSON')
    return
  }
  convertSaving.value = true
  try {
    const res = await convertKnowledgeEntry(convertingEntry.value.id, {
      target_type: convertForm.target_type,
      preview_data: previewData
    })
    if (isSuccessResponse(res)) {
      ElMessage.success('转换成功')
      convertVisible.value = false
      detailVisible.value = false
    }
  } catch (error) {
    console.error('转换失败:', error)
    ElMessage.error('转换失败')
  } finally {
    convertSaving.value = false
  }
}

// 上传
const uploadVisible = ref(false)
const uploadRef = ref(null)
const uploadForm = reactive({
  title: '',
  category: '',
  tags: [],
  file: null
})

const openUploadDialog = () => {
  uploadForm.title = ''
  uploadForm.category = ''
  uploadForm.tags = []
  uploadForm.file = null
  uploadRef.value?.clearFiles?.()
  uploadVisible.value = true
}

const handleFileChange = (file) => {
  uploadForm.file = file.raw
}

const submitUpload = async () => {
  if (!uploadForm.title || !uploadForm.file) {
    ElMessage.warning('请填写标题并选择文件')
    return
  }
  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('title', uploadForm.title)
    formData.append('category', uploadForm.category)
    formData.append('tags', (uploadForm.tags || []).join(','))
    formData.append('file', uploadForm.file)
    await uploadKnowledgeDocument(formData)
    ElMessage.success('上传并解析成功')
    uploadVisible.value = false
    fetchEntries()
  } catch (error) {
    console.error('上传失败:', error)
  } finally {
    uploading.value = false
  }
}

onMounted(() => {
  fetchEntries()
  loadCategoriesAndTags()
})
</script>

<style scoped lang="scss">
.search-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;

  .search-actions {
    margin-left: auto;
    display: flex;
    gap: 10px;
  }
}

.semantic-search-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding: 16px;
  background: linear-gradient(135deg, var(--tp-primary-soft) 0%, transparent 100%);
  border: 1px solid var(--tp-primary-soft);
  border-radius: 12px;

  .semantic-tip {
    font-size: 12px;
    color: var(--tp-text-tertiary);
    margin-left: auto;
  }
}

.search-summary {
  font-size: 14px;
  color: var(--tp-text-secondary);
  margin-bottom: 16px;
}

.search-result-card {
  position: relative;
  overflow: hidden;

  .score-badge {
    position: absolute;
    top: 12px;
    right: 12px;
    background: var(--tp-primary);
    color: #fff;
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 10px;
    z-index: 1;
  }

  .score-breakdown {
    font-size: 11px;
    color: var(--tp-text-tertiary);
    margin-bottom: 10px;
  }
}

.tag-filter {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 20px;
  padding: 12px 16px;
  background-color: var(--tp-bg-elevated);
  border: 1px solid var(--tp-border);
  border-radius: 12px;

  .filter-label {
    font-size: 13px;
    color: var(--tp-text-secondary);
  }

  .filter-tag {
    font-size: 12px;
  }
}

.knowledge-card {
  height: 100%;
  display: flex;
  flex-direction: column;

  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 12px;

    .title-wrapper {
      display: flex;
      align-items: center;
      gap: 8px;
      flex: 1;
      min-width: 0;
    }

    .entry-title {
      font-weight: 600;
      font-size: 15px;
      color: var(--tp-text);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }

  .card-meta {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 10px;

    .meta-item {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 12px;
      color: var(--tp-text-secondary);
    }
  }

  .card-tags {
    margin-bottom: 10px;

    .tag-item {
      margin-right: 6px;
      margin-bottom: 4px;
    }
  }

  .card-content-preview {
    flex: 1;
    font-size: 13px;
    color: var(--tp-text-secondary);
    line-height: 1.6;
    min-height: 60px;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
    margin-bottom: 12px;
  }

  .card-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-top: 10px;
    border-top: 1px solid var(--tp-border-light);
    font-size: 12px;
    color: var(--tp-text-tertiary);
    margin-bottom: 10px;

    .stats {
      display: flex;
      gap: 12px;

      .stat-item {
        display: inline-flex;
        align-items: center;
        gap: 3px;
      }
    }
  }

  .card-actions {
    display: flex;
    justify-content: flex-end;
  }
}

.knowledge-detail-dialog {
  .detail-header {
    margin-bottom: 14px;
  }

  .detail-tags {
    margin-bottom: 14px;
  }

  .detail-content {
    background-color: var(--tp-bg-page);
    border: 1px solid var(--tp-border);
    border-radius: 8px;
    padding: 16px;
    max-height: 420px;
    overflow-y: auto;
    margin-bottom: 16px;

    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-all;
      font-family: inherit;
      font-size: 14px;
      line-height: 1.7;
      color: var(--tp-text);
    }
  }

  .detail-meta {
    margin-bottom: 16px;

    .meta-title {
      font-size: 13px;
      font-weight: 600;
      color: var(--tp-text-secondary);
      margin-bottom: 10px;
    }
  }

  .detail-test-cases {
    margin-bottom: 16px;

    .test-case-list {
      max-height: 400px;
      overflow-y: auto;
    }

    .case-steps {
      white-space: pre-wrap;
      word-break: break-all;
      margin: 0;
      font-family: inherit;
      font-size: 13px;
    }
  }

  .detail-stats {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    font-size: 12px;
    color: var(--tp-text-tertiary);
  }
}
</style>
