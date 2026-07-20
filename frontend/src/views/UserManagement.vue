<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()

// ============== 状态 ==============
const loading = ref(false)
const error = ref('')
const success = ref('')

// 用户/角色/权限数据
const users = ref([])
const roles = ref([])
const permissions = ref([])

// 当前激活的tab
const activeTab = ref('users')

// 搜索/筛选
const searchKeyword = ref('')
const filterRole = ref('')

// 用户编辑弹窗
const showUserDialog = ref(false)
const editingUser = reactive({
  id: '',
  username: '',
  display_name: '',
  email: '',
  department: '',
  role: 'user',
})
const isEditMode = computed(() => !!editingUser.id)

// 角色权限分配弹窗
const showRolePermDialog = ref(false)
const editingRole = reactive({
  id: '',
  name: '',
  description: '',
})
const rolePermIds = ref([])

// ============== 计算属性 ==============
const filteredUsers = computed(() => {
  if (!searchKeyword.value && !filterRole.value) return users.value
  const kw = searchKeyword.value.toLowerCase()
  return users.value.filter(u => {
    const matchKw = !kw ||
      u.username?.toLowerCase().includes(kw) ||
      u.display_name?.toLowerCase().includes(kw) ||
      u.email?.toLowerCase().includes(kw)
    const matchRole = !filterRole.value || u.role === filterRole.value
    return matchKw && matchRole
  })
})

const roleMap = computed(() => {
  const m = {}
  roles.value.forEach(r => { m[r.id] = r })
  return m
})

const permMap = computed(() => {
  const m = {}
  permissions.value.forEach(p => { m[p.id] = p })
  return m
})

// ============== 方法 ==============
function showError(msg) {
  error.value = msg
  setTimeout(() => { error.value = '' }, 3000)
}

function showSuccess(msg) {
  success.value = msg
  setTimeout(() => { success.value = '' }, 3000)
}

async function loadUsers() {
  loading.value = true
  try {
    const data = await api.getUsers()
    users.value = data.users || []
  } catch (e) {
    showError('加载用户列表失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

async function loadRoles() {
  try {
    const data = await api.getRoles()
    roles.value = data.roles || []
  } catch (e) {
    showError('加载角色列表失败: ' + e.message)
  }
}

async function loadPermissions() {
  try {
    const data = await api.getAllPermissions()
    permissions.value = data.permissions || []
  } catch (e) {
    showError('加载权限列表失败: ' + e.message)
  }
}

async function loadAll() {
  loading.value = true
  await Promise.all([loadUsers(), loadRoles(), loadPermissions()])
  loading.value = false
}

// ============== 用户CRUD ==============
function openCreateUserDialog() {
  Object.assign(editingUser, {
    id: '', username: '', display_name: '', email: '', department: '', role: 'user',
  })
  showUserDialog.value = true
}

function openEditUserDialog(user) {
  Object.assign(editingUser, user)
  showUserDialog.value = true
}

async function saveUser() {
  if (!editingUser.username || !editingUser.display_name) {
    showError('用户名和显示名称必填')
    return
  }
  try {
    if (isEditMode.value) {
      await api.updateUser(editingUser.id, {
        display_name: editingUser.display_name,
        email: editingUser.email,
        department: editingUser.department,
        role: editingUser.role,
      })
      showSuccess('用户更新成功')
    } else {
      await api.createUser({
        username: editingUser.username,
        display_name: editingUser.display_name,
        email: editingUser.email,
        department: editingUser.department,
        role: editingUser.role,
      })
      showSuccess('用户创建成功')
    }
    showUserDialog.value = false
    await loadUsers()
  } catch (e) {
    showError('保存失败: ' + e.message)
  }
}

async function deleteUser(user) {
  if (!confirm(`确认删除用户 "${user.username}"？此操作不可恢复。`)) return
  try {
    await api.deleteUser(user.id)
    showSuccess('用户已删除')
    await loadUsers()
  } catch (e) {
    showError('删除失败: ' + e.message)
  }
}

async function resetPassword(user) {
  if (!confirm(`确认重置用户 "${user.username}" 的密码？重置后新密码为：${user.username}123`)) return
  try {
    await api.resetUserPassword(user.id, { new_password: `${user.username}123` })
    showSuccess('密码已重置')
  } catch (e) {
    showError('重置失败: ' + e.message)
  }
}

// ============== 角色权限分配 ==============
async function openRolePermDialog(role) {
  Object.assign(editingRole, role)
  try {
    const data = await api.getRolePermissions(role.id)
    rolePermIds.value = data.permission_ids || []
  } catch (e) {
    showError('加载角色权限失败: ' + e.message)
    return
  }
  showRolePermDialog.value = true
}

function togglePermission(permId) {
  const idx = rolePermIds.value.indexOf(permId)
  if (idx >= 0) {
    rolePermIds.value.splice(idx, 1)
  } else {
    rolePermIds.value.push(permId)
  }
}

async function saveRolePermissions() {
  try {
    await api.updateRolePermissions(editingRole.id, rolePermIds.value)
    showSuccess(`角色 "${editingRole.name}" 权限已更新`)
    showRolePermDialog.value = false
    await loadRoles()
  } catch (e) {
    showError('保存失败: ' + e.message)
  }
}

// ============== 生命周期 ==============
onMounted(() => {
  loadAll()
})
</script>

<template>
  <div class="user-mgmt">
    <div class="page-header">
      <h2>👥 用户权限管理</h2>
      <div class="header-actions">
        <button class="btn btn-primary" @click="openCreateUserDialog" v-if="activeTab === 'users'">
          ➕ 新增用户
        </button>
      </div>
    </div>

    <div v-if="error" class="alert alert-error">{{ error }}</div>
    <div v-if="success" class="alert alert-success">{{ success }}</div>

    <!-- Tab切换 -->
    <div class="tab-bar">
      <button class="tab-btn" :class="{ active: activeTab === 'users' }" @click="activeTab = 'users'">
        👤 用户列表 ({{ users.length }})
      </button>
      <button class="tab-btn" :class="{ active: activeTab === 'roles' }" @click="activeTab = 'roles'">
        🎭 角色管理 ({{ roles.length }})
      </button>
      <button class="tab-btn" :class="{ active: activeTab === 'permissions' }" @click="activeTab = 'permissions'">
        🔑 权限列表 ({{ permissions.length }})
      </button>
    </div>

    <div v-if="loading" class="loading">加载中...</div>

    <!-- 用户列表 -->
    <div v-if="activeTab === 'users' && !loading" class="tab-content">
      <div class="filter-bar">
        <input
          v-model="searchKeyword"
          class="input"
          placeholder="搜索用户名/显示名/邮箱..."
        />
        <select v-model="filterRole" class="input select">
          <option value="">全部角色</option>
          <option v-for="r in roles" :key="r.id" :value="r.id">{{ r.name }}</option>
        </select>
      </div>

      <div class="table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th>用户名</th>
              <th>显示名</th>
              <th>角色</th>
              <th>部门</th>
              <th>邮箱</th>
              <th>最近登录</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in filteredUsers" :key="u.id">
              <td class="mono">{{ u.username }}</td>
              <td>{{ u.display_name }}</td>
              <td>
                <span class="role-badge" :class="u.role">{{ roleMap[u.role]?.name || u.role }}</span>
              </td>
              <td>{{ u.department || '-' }}</td>
              <td class="mono">{{ u.email || '-' }}</td>
              <td class="mono">{{ u.last_login_at || '从未登录' }}</td>
              <td class="actions">
                <button class="btn btn-sm" @click="openEditUserDialog(u)">编辑</button>
                <button class="btn btn-sm" @click="resetPassword(u)">重置密码</button>
                <button
                  v-if="u.username !== 'admin' && u.id !== authStore.user?.id"
                  class="btn btn-sm btn-danger"
                  @click="deleteUser(u)"
                >删除</button>
              </td>
            </tr>
            <tr v-if="filteredUsers.length === 0">
              <td colspan="7" class="empty">暂无数据</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 角色管理 -->
    <div v-if="activeTab === 'roles' && !loading" class="tab-content">
      <div class="table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th>角色ID</th>
              <th>角色名</th>
              <th>说明</th>
              <th>权限数</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in roles" :key="r.id">
              <td class="mono">{{ r.id }}</td>
              <td>{{ r.name }}</td>
              <td>{{ r.description || '-' }}</td>
              <td>
                <span class="perm-count">{{ r.permission_count }}</span>
              </td>
              <td class="actions">
                <button class="btn btn-sm" @click="openRolePermDialog(r)">分配权限</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="hint">
        💡 admin 角色拥有全部权限（无需分配），engineer/user 角色可通过"分配权限"自定义
      </div>
    </div>

    <!-- 权限列表 -->
    <div v-if="activeTab === 'permissions' && !loading" class="tab-content">
      <div class="table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th>权限ID</th>
              <th>权限名</th>
              <th>说明</th>
              <th>资源</th>
              <th>动作</th>
              <th>已分配角色数</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in permissions" :key="p.id">
              <td class="mono">{{ p.id }}</td>
              <td>{{ p.name }}</td>
              <td>{{ p.description || '-' }}</td>
              <td class="mono">{{ p.resource || '-' }}</td>
              <td class="mono">{{ p.action || '-' }}</td>
              <td><span class="perm-count">{{ p.role_count }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 用户编辑弹窗 -->
    <div v-if="showUserDialog" class="modal-overlay" @click.self="showUserDialog = false">
      <div class="modal">
        <div class="modal-header">
          <h3>{{ isEditMode ? '编辑用户' : '新增用户' }}</h3>
          <button class="close-btn" @click="showUserDialog = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>用户名 *</label>
            <input v-model="editingUser.username" class="input" :disabled="isEditMode" placeholder="登录用户名" />
          </div>
          <div class="form-group">
            <label>显示名 *</label>
            <input v-model="editingUser.display_name" class="input" placeholder="中文名/显示名" />
          </div>
          <div class="form-group">
            <label>角色 *</label>
            <select v-model="editingUser.role" class="input select">
              <option v-for="r in roles" :key="r.id" :value="r.id">{{ r.name }}</option>
            </select>
          </div>
          <div class="form-group">
            <label>部门</label>
            <input v-model="editingUser.department" class="input" placeholder="如：IT部/设备部/生产部" />
          </div>
          <div class="form-group">
            <label>邮箱</label>
            <input v-model="editingUser.email" class="input" placeholder="user@company.com" />
          </div>
          <div v-if="!isEditMode" class="hint">
            💡 初始密码为：<code>{{ editingUser.username || 'username' }}123</code>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn" @click="showUserDialog = false">取消</button>
          <button class="btn btn-primary" @click="saveUser">保存</button>
        </div>
      </div>
    </div>

    <!-- 角色权限分配弹窗 -->
    <div v-if="showRolePermDialog" class="modal-overlay" @click.self="showRolePermDialog = false">
      <div class="modal">
        <div class="modal-header">
          <h3>分配权限 - {{ editingRole.name }}</h3>
          <button class="close-btn" @click="showRolePermDialog = false">×</button>
        </div>
        <div class="modal-body">
          <div class="perm-grid">
            <label
              v-for="p in permissions"
              :key="p.id"
              class="perm-item"
              :class="{ checked: rolePermIds.includes(p.id) }"
            >
              <input
                type="checkbox"
                :checked="rolePermIds.includes(p.id)"
                @change="togglePermission(p.id)"
              />
              <div class="perm-info">
                <div class="perm-name">{{ p.name }}</div>
                <div class="perm-id">{{ p.id }}</div>
              </div>
            </label>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn" @click="showRolePermDialog = false">取消</button>
          <button class="btn btn-primary" @click="saveRolePermissions">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.user-mgmt {
  padding: 16px;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.page-header h2 {
  margin: 0;
  font-size: 18px;
  color: var(--text);
}

.alert {
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
}
.alert-error { background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); }
.alert-success { background: rgba(34, 197, 94, 0.15); color: #22c55e; border: 1px solid rgba(34, 197, 94, 0.3); }

.tab-bar {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--border);
}
.tab-btn {
  padding: 8px 16px;
  border: none;
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  font-size: 13px;
}
.tab-btn.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

.tab-content { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 10px; }

.filter-bar { display: flex; gap: 10px; }
.input {
  flex: 1;
  padding: 8px 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  font-size: 13px;
  outline: none;
}
.input:focus { border-color: var(--accent); }
.input:disabled { opacity: 0.5; cursor: not-allowed; }
.select { flex: 0 0 180px; }

.table-wrapper {
  flex: 1;
  overflow: auto;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.data-table thead th {
  position: sticky;
  top: 0;
  background: var(--panel);
  text-align: left;
  padding: 10px 12px;
  color: var(--text-dim);
  font-weight: 600;
  border-bottom: 1px solid var(--border);
  z-index: 1;
}
.data-table tbody td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  color: var(--text);
}
.data-table tbody tr:hover { background: rgba(0, 212, 255, 0.05); }
.mono { font-family: 'Consolas', monospace; font-size: 12px; }
.empty { text-align: center; color: var(--text-dim); padding: 20px; }

.role-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}
.role-badge.admin { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.role-badge.engineer { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
.role-badge.user { background: rgba(0, 212, 255, 0.15); color: var(--accent); }

.perm-count {
  display: inline-block;
  min-width: 24px;
  padding: 2px 8px;
  background: rgba(0, 212, 255, 0.1);
  color: var(--accent);
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  text-align: center;
}

.actions { white-space: nowrap; }
.btn {
  padding: 6px 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text);
  cursor: pointer;
  font-size: 12px;
  margin-right: 4px;
}
.btn:hover { border-color: var(--accent); color: var(--accent); }
.btn-sm { padding: 4px 8px; font-size: 11px; }
.btn-primary { background: rgba(0, 212, 255, 0.15); color: var(--accent); border-color: var(--accent); }
.btn-danger { color: #ef4444; border-color: rgba(239, 68, 68, 0.3); }
.btn-danger:hover { background: rgba(239, 68, 68, 0.1); border-color: #ef4444; }

.hint { font-size: 12px; color: var(--text-dim); padding: 8px 12px; }
.hint code { background: var(--bg); padding: 2px 6px; border-radius: 3px; color: var(--accent); }

.loading { padding: 20px; text-align: center; color: var(--text-dim); }

/* 弹窗 */
.modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  width: 480px;
  max-width: 90vw;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}
.modal-header {
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.modal-header h3 { margin: 0; font-size: 15px; color: var(--text); }
.close-btn {
  background: transparent;
  border: none;
  color: var(--text-dim);
  font-size: 20px;
  cursor: pointer;
  padding: 0 8px;
}
.close-btn:hover { color: var(--text); }
.modal-body { padding: 16px 18px; overflow: auto; }
.modal-footer {
  padding: 12px 18px;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.form-group { margin-bottom: 12px; }
.form-group label {
  display: block;
  margin-bottom: 4px;
  font-size: 12px;
  color: var(--text-dim);
}

.perm-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.perm-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
}
.perm-item:hover { border-color: var(--accent); }
.perm-item.checked { background: rgba(0, 212, 255, 0.1); border-color: var(--accent); }
.perm-item input { margin: 0; }
.perm-info { flex: 1; }
.perm-name { font-size: 13px; color: var(--text); }
.perm-id { font-size: 11px; color: var(--text-dim); font-family: monospace; }
</style>
