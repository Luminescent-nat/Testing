<template>
  <div class="page-container">
    <div class="search-bar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索用户名"
        clearable
        style="width: 300px"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      
      <el-select v-model="filterRole" placeholder="角色筛选" clearable style="width: 150px">
        <el-option label="管理员" value="admin" />
        <el-option label="普通用户" value="user" />
      </el-select>
      
      <el-select v-model="filterStatus" placeholder="状态筛选" clearable style="width: 150px">
        <el-option label="正常" value="active" />
        <el-option label="禁用" value="disabled" />
      </el-select>
      
      <el-button type="primary" @click="fetchUsers">
        <el-icon><Search /></el-icon>
        查询
        </el-button>
    </div>
    
    <el-card class="app-card">
      <el-table :data="filteredUsers" class="app-table" v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="username" label="用户名" min-width="150" />
        <el-table-column prop="role" label="角色" width="120">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : 'info'">
              {{ row.role === 'admin' ? '管理员' : '普通用户' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'">
              {{ row.status === 'active' ? '正常' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_login_at" label="最后登录" width="180">
          <template #default="{ row }">
            {{ formatTime(row.last_login_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button
              text
              type="primary"
              @click="resetPassword(row)"
            >
              重置密码
            </el-button>
            <el-button
              text
              :type="row.status === 'active' ? 'danger' : 'success'"
              @click="toggleStatus(row)"
            >
              {{ row.status === 'active' ? '禁用' : '启用' }}
            </el-button>
            <el-button
              text
              type="danger"
              @click="deleteUser(row)"
            >
              删除
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
          @change="fetchUsers"
        />
      </div>
    </el-card>
    
    <!-- 重置密码对话框 -->
    <el-dialog
      v-model="showResetDialog"
      title="重置密码"
      width="400px"
    >
      <p>为用户 <strong>{{ currentUser?.username }}</strong> 设置新密码：</p>
      <el-input
        v-model="newPassword"
        type="password"
        placeholder="请输入新密码"
        style="margin-top: 15px"
      />
      <template #footer>
        <el-button @click="showResetDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="confirmReset">
          确认
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { formatDateTime } from '@/utils/datetime'
import { isSuccessResponse } from '@/api/client'
import { getUsers, updateUser, resetUserPassword, deleteUser as deleteUserApi } from '@/api/user'

const users = ref([])
const loading = ref(false)
const searchKeyword = ref('')
const filterRole = ref('')
const filterStatus = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const showResetDialog = ref(false)
const currentUser = ref(null)
const newPassword = ref('')
const saving = ref(false)

const filteredUsers = computed(() => users.value)

const fetchUsers = async () => {
  loading.value = true
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value,
      username: searchKeyword.value || undefined,
      role: filterRole.value || undefined,
      status: filterStatus.value || undefined
    }
    const res = await getUsers(params)
    if (isSuccessResponse(res)) {
      users.value = res.data.items || []
      total.value = res.data.total || 0
    }
  } catch (error) {
    console.error('获取用户失败:', error)
  } finally {
    loading.value = false
  }
}

const formatTime = (time) => {
  return formatDateTime(time, 'YYYY-MM-DD HH:mm')
}

const resetPassword = (user) => {
  currentUser.value = user
  newPassword.value = ''
  showResetDialog.value = true
}

const confirmReset = async () => {
  if (!newPassword.value) {
    ElMessage.warning('请输入新密码')
    return
  }
  if (newPassword.value.length < 6 || newPassword.value.length > 32) {
    ElMessage.warning('密码长度应为 6-32 位')
    return
  }

  saving.value = true
  try {
    await resetUserPassword(currentUser.value.id, newPassword.value)
    ElMessage.success('密码重置成功')
    showResetDialog.value = false
  } catch (error) {
    console.error('重置失败:', error)
  } finally {
    saving.value = false
  }
}

const toggleStatus = async (user) => {
  const action = user.status === 'active' ? '禁用' : '启用'
  const nextStatus = user.status === 'active' ? 'disabled' : 'active'
  try {
    await ElMessageBox.confirm(`确定${action}用户 "${user.username}" 吗？`, '提示', {
      type: 'warning'
    })
    const res = await updateUser(user.id, { status: nextStatus })
    if (isSuccessResponse(res)) {
      ElMessage.success(`${action}成功`)
      fetchUsers()
    }
  } catch {
    // 取消
  }
}

const deleteUser = async (user) => {
  try {
    await ElMessageBox.confirm(`确定删除用户 "${user.username}" 吗？`, '警告', {
      type: 'danger'
    })
    const res = await deleteUserApi(user.id)
    if (isSuccessResponse(res)) {
      ElMessage.success('删除成功')
      fetchUsers()
    }
  } catch {
    // 取消
  }
}

onMounted(() => {
  fetchUsers()
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
