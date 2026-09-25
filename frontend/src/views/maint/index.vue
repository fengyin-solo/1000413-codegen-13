<template>
  <section class="page" data-module="maint">
    <header class="page-head">
      <div>
        <h2>设备检修管理</h2>
        <p class="page-desc">维护检修单，围绕检修单号、关联设备、检修类型、计划开始日做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记检修单</button>
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
  </section>

  <section class="page archive-panel">
    <header class="page-head">
      <div>
        <h2>验收材料归档</h2>
        <p class="page-desc">按检修单号把设备照片与检测报告一次批量报送，验收人逐条确认后整组归档；缺材料或格式不对的单条驳回。</p>
      </div>
    </header>

    <form class="filter-bar" @submit.prevent="submitArchive">
      <label class="filter-item">
        <span>检修单号</span>
        <input v-model="archiveForm.检修单号" placeholder="如 MAIN-0001" />
      </label>
      <label class="filter-item">
        <span>报送人</span>
        <input v-model="archiveForm.报送人" placeholder="填写报送人" />
      </label>
      <label class="filter-item">
        <span>验收人员</span>
        <input v-model="archiveForm.验收人员" placeholder="可留空，验收时再签" />
      </label>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th>材料类型</th>
          <th>材料名称</th>
          <th>文件格式</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(material, index) in archiveForm.materials" :key="index">
          <td>
            <select v-model="material.材料类型">
              <option v-for="type in materialTypes" :key="type" :value="type">{{ type }}</option>
            </select>
          </td>
          <td><input v-model="material.材料名称" placeholder="如 1号泵检修后照片.jpg" /></td>
          <td><input v-model="material.文件格式" placeholder="照片 jpg/png，报告 pdf" /></td>
          <td>
            <button class="link" type="button" @click="archiveForm.materials.splice(index, 1)">移除</button>
          </td>
        </tr>
        <tr v-if="!archiveForm.materials.length">
          <td colspan="4" class="empty-state">尚未添加材料，至少各一条设备照片与检测报告</td>
        </tr>
      </tbody>
    </table>
    <div class="archive-actions">
      <button class="btn" type="button" @click="addMaterial">添加材料</button>
      <button class="btn primary" type="button" @click="submitArchive">批量报送</button>
    </div>

    <form class="filter-bar" @submit.prevent="loadArchives">
      <label class="filter-item">
        <span>验收人员（签收用）</span>
        <input v-model="signer" placeholder="确认/驳回/归档前必填" />
      </label>
      <label class="filter-item">
        <span>检修单号</span>
        <input v-model="archiveKeyword" placeholder="按检修单号检索批次" />
      </label>
      <button class="btn" type="submit">查询</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th>批次</th>
          <th>检修单号</th>
          <th>报送人</th>
          <th>验收人员</th>
          <th>材料总数</th>
          <th>已确认</th>
          <th>已驳回</th>
          <th>待确认</th>
          <th>归档进度</th>
          <th>归档状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="batch in archives" :key="batch.id">
          <tr>
            <td>#{{ batch.id }}</td>
            <td>{{ batch.检修单号 }}</td>
            <td>{{ batch.报送人 }}</td>
            <td>{{ batch.验收人员 || '—' }}</td>
            <td>{{ batch.材料总数 }}</td>
            <td>{{ batch.已确认 }}</td>
            <td>{{ batch.已驳回 }}</td>
            <td>{{ batch.待确认 }}</td>
            <td>{{ batch.归档进度 }}</td>
            <td>{{ batch.归档状态 }}</td>
            <td class="row-actions">
              <button class="link" type="button" @click="toggleExpand(batch.id)">
                {{ expandedIds.includes(batch.id) ? '收起材料' : '查看材料' }}
              </button>
              <button
                v-if="batch.归档状态 !== '已归档'"
                class="link"
                type="button"
                @click="archiveBatch(batch)"
              >
                整组归档
              </button>
            </td>
          </tr>
          <tr v-if="expandedIds.includes(batch.id)">
            <td :colspan="11">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>材料类型</th>
                    <th>材料名称</th>
                    <th>文件格式</th>
                    <th>状态</th>
                    <th>驳回理由</th>
                    <th>可执行动作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in batch.items" :key="item.id">
                    <td>{{ item.id }}</td>
                    <td>
                      <select v-if="isEditing(batch.id, item.id)" v-model="editing!.材料类型">
                        <option v-for="type in materialTypes" :key="type" :value="type">{{ type }}</option>
                      </select>
                      <template v-else>{{ item.材料类型 }}</template>
                    </td>
                    <td>
                      <input v-if="isEditing(batch.id, item.id)" v-model="editing!.材料名称" />
                      <template v-else>{{ item.材料名称 }}</template>
                    </td>
                    <td>
                      <input v-if="isEditing(batch.id, item.id)" v-model="editing!.文件格式" />
                      <template v-else>{{ item.文件格式 }}</template>
                    </td>
                    <td>{{ item.status }}</td>
                    <td>{{ item.驳回理由 || '—' }}</td>
                    <td class="row-actions">
                      <template v-if="isEditing(batch.id, item.id)">
                        <button class="link" type="button" @click="saveResubmit(batch)">保存</button>
                        <button class="link" type="button" @click="editing = null">取消</button>
                      </template>
                      <template v-else>
                        <button
                          v-if="item.status === '待确认'"
                          class="link"
                          type="button"
                          @click="confirmItem(batch, item)"
                        >
                          确认材料
                        </button>
                        <button
                          v-if="item.status === '待确认'"
                          class="link"
                          type="button"
                          @click="rejectItem(batch, item)"
                        >
                          驳回材料
                        </button>
                        <button
                          v-if="item.status === '已驳回'"
                          class="link"
                          type="button"
                          @click="startResubmit(batch, item)"
                        >
                          重新报送
                        </button>
                      </template>
                    </td>
                  </tr>
                </tbody>
              </table>
            </td>
          </tr>
        </template>
        <tr v-if="!archives.length">
          <td :colspan="11" class="empty-state">暂无验收材料批次，可先在上方按检修单号批量报送</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ archiveTotal }} 个归档批次</span>
      <span v-if="archiveMessage" :class="archiveOk ? 'ok-text' : 'error-text'">{{ archiveMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

type MaterialDraft = { 材料类型: string; 材料名称: string; 文件格式: string }
type ArchiveItem = MaterialDraft & { id: number; status: string; 驳回理由: string }
type ArchiveBatch = {
  id: number
  检修单号: string
  报送人: string
  验收人员: string
  报送时间: string
  归档时间: string
  材料总数: number
  已确认: number
  已驳回: number
  待确认: number
  归档进度: string
  归档状态: string
  items: ArchiveItem[]
}

const ENDPOINT = '/api/maint'
const columns = ["检修单号", "关联设备", "检修类型", "计划开始日", "实际完成日", "检修人员", "验收人员", "检修状态"]
const actions = ["受理检修", "提交验收", "确认验收"]
const statuses = ["待受理", "检修中", "待验收", "已验收"]
const stats = [{"label": "待受理检修", "value": 0}, {"label": "检修中设备", "value": 0}, {"label": "本月验收单数", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const materialTypes = ["设备照片", "检测报告"]
const archives = ref<ArchiveBatch[]>([])
const archiveTotal = ref(0)
const archiveKeyword = ref('')
const archiveMessage = ref('')
const archiveOk = ref(false)
const signer = ref('')
const expandedIds = ref<number[]>([])
const editing = ref<(MaterialDraft & { batchId: number; itemId: number }) | null>(null)
const archiveForm = ref({
  检修单号: '',
  报送人: '',
  验收人员: '',
  materials: [
    { 材料类型: '设备照片', 材料名称: '', 文件格式: 'jpg' },
    { 材料类型: '检测报告', 材料名称: '', 文件格式: 'pdf' },
  ] as MaterialDraft[],
})

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '检修单登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    if (!response.ok) {
      throw new Error('设备检修动作未生效，请稍后重试')
    }
    const payload = await response.json()
    if (!payload.ok) {
      throw new Error(payload.message || '设备检修动作未生效')
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

// ---------- 验收材料归档 ----------

function addMaterial() {
  archiveForm.value.materials.push({ 材料类型: '设备照片', 材料名称: '', 文件格式: '' })
}

function toggleExpand(batchId: number) {
  const index = expandedIds.value.indexOf(batchId)
  if (index >= 0) {
    expandedIds.value.splice(index, 1)
  } else {
    expandedIds.value.push(batchId)
  }
}

function isEditing(batchId: number, itemId: number) {
  return editing.value?.batchId === batchId && editing.value?.itemId === itemId
}

function startResubmit(batch: ArchiveBatch, item: ArchiveItem) {
  editing.value = {
    batchId: batch.id,
    itemId: item.id,
    材料类型: item.材料类型,
    材料名称: item.材料名称,
    文件格式: item.文件格式,
  }
}

async function postArchive(path: string, values: Record<string, unknown>) {
  archiveMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}${path}`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    if (!response.ok) {
      throw new Error('验收材料操作未生效，请稍后重试')
    }
    const payload = await response.json()
    archiveOk.value = Boolean(payload.ok)
    archiveMessage.value = payload.message ?? ''
    if (payload.ok) {
      await loadArchives()
    }
  } catch (error) {
    archiveOk.value = false
    archiveMessage.value = error instanceof Error ? error.message : '验收材料操作失败'
  }
}

async function submitArchive() {
  const form = archiveForm.value
  await postArchive('/archives', {
    检修单号: form.检修单号,
    报送人: form.报送人,
    验收人员: form.验收人员,
    materials: form.materials,
  })
  if (archiveOk.value) {
    archiveForm.value = {
      检修单号: '',
      报送人: '',
      验收人员: '',
      materials: [
        { 材料类型: '设备照片', 材料名称: '', 文件格式: 'jpg' },
        { 材料类型: '检测报告', 材料名称: '', 文件格式: 'pdf' },
      ],
    }
  }
}

async function confirmItem(batch: ArchiveBatch, item: ArchiveItem) {
  await postArchive(`/archives/${batch.id}/items/${item.id}/actions`, {
    action: '确认材料',
    验收人员: signer.value,
  })
}

async function rejectItem(batch: ArchiveBatch, item: ArchiveItem) {
  const reason = window.prompt(`请填写材料 #${item.id} 的驳回理由（缺材料、格式不对等）`) ?? ''
  if (!reason.trim()) {
    archiveOk.value = false
    archiveMessage.value = '驳回必须填写理由（缺材料、格式不对等）'
    return
  }
  await postArchive(`/archives/${batch.id}/items/${item.id}/actions`, {
    action: '驳回材料',
    验收人员: signer.value,
    驳回理由: reason.trim(),
  })
}

async function saveResubmit(batch: ArchiveBatch) {
  if (!editing.value) {
    return
  }
  const draft = editing.value
  await postArchive(`/archives/${batch.id}/items/${draft.itemId}/actions`, {
    action: '重新报送',
    材料类型: draft.材料类型,
    材料名称: draft.材料名称,
    文件格式: draft.文件格式,
  })
  if (archiveOk.value) {
    editing.value = null
  }
}

async function archiveBatch(batch: ArchiveBatch) {
  await postArchive(`/archives/${batch.id}/actions`, {
    action: '整组归档',
    验收人员: signer.value,
  })
}

async function loadArchives() {
  const query = new URLSearchParams()
  if (archiveKeyword.value.trim()) {
    query.set('keyword', archiveKeyword.value.trim())
  }
  try {
    const response = await request(`${ENDPOINT}/archives?${query.toString()}`)
    if (!response.ok) {
      throw new Error('验收材料批次读取失败')
    }
    const payload = await response.json()
    archives.value = payload.items ?? []
    archiveTotal.value = payload.total ?? archives.value.length
  } catch (error) {
    archiveOk.value = false
    archiveMessage.value = error instanceof Error ? error.message : '验收材料批次读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadArchives()
})
</script>
