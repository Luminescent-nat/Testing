<template>
  <div class="page-container">
    <el-row :gutter="20">
      <el-col :xs="24" :md="12">
        <el-card class="app-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <el-icon :size="20"><User /></el-icon>
              <span>个人信息</span>
            </div>
          </template>
          
          <el-descriptions :column="1" border v-loading="loading">
            <el-descriptions-item label="用户ID">{{ userInfo?.id || '-' }}</el-descriptions-item>
            <el-descriptions-item label="用户名">{{ userInfo?.username || '-' }}</el-descriptions-item>
            <el-descriptions-item label="角色">
              <el-tag :type="userInfo?.role === 'admin' ? 'danger' : 'info'">
                {{ userInfo?.role === 'admin' ? '管理员' : '普通用户' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="userInfo?.status === 'active' ? 'success' : 'warning'">
                {{ userInfo?.status === 'active' ? '正常' : '已禁用' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="PC 标识">{{ userInfo?.pc_identifier || '-' }}</el-descriptions-item>
            <el-descriptions-item label="最后登录">{{ formatTime(userInfo?.last_login_at) }}</el-descriptions-item>
            <el-descriptions-item label="注册时间">{{ formatTime(userInfo?.created_at) }}</el-descriptions-item>
          </el-descriptions>
          
          <div class="profile-actions">
            <el-button type="danger" @click="userStore.logout()">
              <el-icon><SwitchButton /></el-icon>
              退出登录
            </el-button>
          </div>
        </el-card>
      </el-col>
      
      <el-col :xs="24" :md="12">
        <el-card class="app-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <el-icon :size="20"><Lock /></el-icon>
              <span>修改密码</span>
            </div>
          </template>
          
          <el-form :model="passwordForm" label-width="100px" :rules="passwordRules" ref="passwordFormRef">
            <el-form-item label="原密码" prop="old_password">
              <el-input
                v-model="passwordForm.old_password"
                type="password"
                show-password
                placeholder="请输入原密码"
              />
            </el-form-item>
            
            <el-form-item label="新密码" prop="new_password">
              <el-input
                v-model="passwordForm.new_password"
                type="password"
                show-password
                placeholder="请输入新密码（6-32位）"
              />
            </el-form-item>
            
            <el-form-item label="确认密码" prop="confirm_password">
              <el-input
                v-model="passwordForm.confirm_password"
                type="password"
                show-password
                placeholder="请再次输入新密码"
              />
            </el-form-item>
            
            <el-form-item>
              <el-button type="primary" :loading="changing" @click="changePassword">
                修改密码
              </el-button>
              <el-button @click="resetPasswordForm">重置</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { User, Lock, SwitchButton } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import { getUserInfo, changePassword as changePasswordApi } from '@/api/auth'
import { formatDateTime } from '@/utils/datetime'

const userStore = useUserStore()
const loading = ref(false)
const userInfo = ref(null)
const changing = ref(false)
const passwordFormRef = ref(null)

const passwordForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: ''
})

const validateConfirmPassword = (rule, value, callback) => {
  if (value !== passwordForm.new_password) {
    callback(new Error('两次输入的密码不一致'))
  } else {
    callback()
  }
}

const passwordRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, max: 32, message: '密码长度应为 6-32 位', trigger: 'blur' }
  ],
  confirm_password: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    { validator: validateConfirmPassword, trigger: 'blur' }
  ]
}

const fetchUserInfo = async () => {
  loading.value = true
  try {
    const res = await getUserInfo()
    if (res.code === 200) {
      userInfo.value = res.data
      userStore.userInfo = res.data
    }
  } catch (error) {
    console.error('获取用户信息失败:', error)
    ElMessage.error('获取用户信息失败')
  } finally {
    loading.value = false
  }
}

const formatTime = (time) => {
  return formatDateTime(time, 'YYYY-MM-DD HH:mm:ss')
}

const changePassword = async () => {
  if (!passwordFormRef.value) return
  
  await passwordFormRef.value.validate(async (valid) => {
    if (!valid) return
    
    changing.value = true
    try {
      const res = await changePasswordApi({
        old_password: passwordForm.old_password,
        new_password: passwordForm.new_password
      })
      if (res.code === 200) {
        ElMessage.success('密码修改成功，请重新登录')
        userStore.logout()
      } else {
        ElMessage.error(res.message || '修改失败')
      }
    } catch (error) {
      console.error('修改密码失败:', error)
      ElMessage.error(error.message || '修改密码失败')
    } finally {
      changing.value = false
    }
  })
}

const resetPasswordForm = () => {
  passwordForm.old_password = ''
  passwordForm.new_password = ''
  passwordForm.confirm_password = ''
  passwordFormRef.value?.resetFields()
}

onMounted(() => {
  fetchUserInfo()
})
</script>

<style scoped lang="scss">
.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.profile-actions {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.el-col {
  margin-bottom: 20px;
}
</style>
