<template>
  <section class="page" data-module="maint">
    <header class="page-head">
      <div>
        <h2>设备检修管理</h2>
        <p class="page-desc">维护检修单，围绕检修单号、关联设备、检修类型、计划开始日做登记、筛选与状态流转；验收材料按检修单号批量报送、逐条确认后整组归档。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记检修单</button>
        <button class="btn" type="button" @click="openSubmit()">验收材料归档</button>
        <button class="btn" type="button" @click="exportRows">导出设备检修清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <button class="link" type="button" @click="openSubmit(String(row['检修单号'] ?? ''))">
              报送验收材料
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无设备检修数据，可先登记检修单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条设备检修记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div style="margin-top: 20px">
      <header class="page-head" style="margin-bottom: 8px">
        <div>
          <h3 style="margin: 0; font-size: 15px">验收材料归档批次</h3>
          <p class="page-desc">整组进度按实际条目实时汇总（已确认/总数）；验收人员逐条确认，缺材料或格式不对可单条驳回，全部通过并签字后整组归档。</p>
        </div>
      </header>

      <form class="filter-bar" @submit.prevent="loadArchives">
        <label class="filter-item">
          <span>检修单号</span>
          <input v-model="archiveFilters.keyword" placeholder="按检修单号检索" />
        </label>
        <label class="filter-item">
          <span>归档状态</span>
          <select v-model="archiveFilters.status">
            <option value="">全部</option>
            <option v-for="status in archiveStatuses" :key="status" :value="status">{{ status }}</option>
          </select>
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetArchiveFilters">重置条件</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th>批次</th>
            <th>检修单号</th>
            <th>报送人</th>
            <th>报送时间</th>
            <th>整组进度</th>
            <th>待确认</th>
            <th>已驳回</th>
            <th>整组状态</th>
            <th>验收签字</th>
            <th>归档时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="group in archiveGroups" :key="group.id">
            <td>#{{ group.id }}</td>
            <td>{{ group['检修单号'] }}</td>
            <td>{{ group['报送人'] }}</td>
            <td>{{ group['报送时间'] }}</td>
            <td>{{ group.progress }}</td>
            <td>{{ group.pending }}</td>
            <td>{{ group.rejected }}</td>
            <td><em class="tag" :class="archiveStatusClass(group.status)">{{ group.status }}</em></td>
            <td>{{ group['验收人签字'] ?? '—' }}</td>
            <td>{{ group['归档时间'] ?? '—' }}</td>
            <td class="row-actions">
              <button class="link" type="button" @click="openReview(group)">查看 / 验收</button>
            </td>
          </tr>
          <tr v-if="!archiveGroups.length">
            <td colspan="11" class="empty-state">暂无验收材料归档批次</td>
          </tr>
        </tbody>
      </table>

      <footer class="page-foot">
        <span>共 {{ archiveTotal }} 个归档批次</span>
      </footer>
    </div>

    <ArchiveDialog
      v-if="dialog.visible"
      :mode="dialog.mode"
      :initial-order="dialog.initialOrder"
      :group="dialog.group"
      @close="dialog.visible = false"
      @changed="onDialogChanged"
    />
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'
import ArchiveDialog from './ArchiveDialog.vue'

type Row = Record<string, string | number | null>
interface ArchiveItem {
  id: number
  status: string
  reject_reason: string | null
  [key: string]: unknown
}
interface ArchiveGroup {
  id: number
  status: string
  progress: string
  pending: number
  rejected: number
  items: ArchiveItem[]
  [key: string]: unknown
}

const ENDPOINT = '/api/maint'
const columns = ["检修单号", "关联设备", "检修类型", "计划开始日", "实际完成日", "检修人员", "验收人员", "检修状态"]
const actions = ["受理检修", "提交验收", "确认验收"]
const statuses = ["待受理", "检修中", "待验收", "已验收"]
const archiveStatuses = ["验收中", "待归档", "已归档", "已退回"]
const stats = [{"label": "待受理检修", "value": 0}, {"label": "检修中设备", "value": 0}, {"label": "本月验收单数", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const archiveGroups = ref<ArchiveGroup[]>([])
const archiveTotal = ref(0)
const archiveFilters = ref<{ keyword: string; status: string }>({ keyword: '', status: '' })

const dialog = ref<{ visible: boolean; mode: 'submit' | 'review'; initialOrder: string; group?: ArchiveGroup }>({
  visible: false,
  mode: 'submit',
  initialOrder: '',
})

function resetFilters() {
  filters.value = {}
  void reload()
}

function resetArchiveFilters() {
  archiveFilters.value = { keyword: '', status: '' }
  void loadArchives()
}

function archiveStatusClass(status: string): string {
  const map: Record<string, string> = {
    验收中: 'review',
    待归档: 'ready',
    已归档: 'archived',
    已退回: 'returned',
  }
  return map[status] ?? ''
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '检修单登记入口尚未接入审批流'
}

function openSubmit(orderNo = '') {
  dialog.value = { visible: true, mode: 'submit', initialOrder: orderNo }
}

function openReview(group: ArchiveGroup) {
  dialog.value = { visible: true, mode: 'review', initialOrder: '', group }
}

async function onDialogChanged() {
  await loadArchives()
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('设备检修动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '设备检修操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('检修单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '设备检修列表读取失败'
  }
}

async function loadArchives() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  if (archiveFilters.value.keyword) params.set('keyword', archiveFilters.value.keyword)
  if (archiveFilters.value.status) params.set('status', archiveFilters.value.status)
  try {
    const response = await request(`${ENDPOINT}/archives?${params.toString()}`)
    if (!response.ok) {
      throw new Error('验收材料归档批次读取失败')
    }
    const payload = await response.json()
    archiveGroups.value = payload.items ?? []
    archiveTotal.value = payload.total ?? archiveGroups.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '验收材料归档批次读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadArchives()
})
</script>
