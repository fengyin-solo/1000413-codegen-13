<template>
  <div class="modal-mask" @click.self="$emit('close')">
    <div class="modal-card" role="dialog" aria-modal="true" aria-label="验收材料归档">
      <div class="modal-head">
        <h3>验收材料归档</h3>
        <button class="modal-close" type="button" @click="$emit('close')">×</button>
      </div>

      <div class="modal-body">
        <!-- 报送：按检修单号把照片与报告一次批量提交 -->
        <section v-if="mode === 'submit'">
          <p class="modal-tip">
            按检修单号一次性批量报送关联设备照片（jpg/jpeg/png）与检测报告（pdf/doc/docx）。
            缺材料、格式不对会逐条给出理由，整批改对后重新报送。
          </p>
          <div class="form-grid">
            <label>
              <span>检修单号 *</span>
              <input v-model="form.orderNo" :disabled="Boolean(initialOrder)" placeholder="如 MAIN-0001" />
            </label>
            <label>
              <span>报送人 *</span>
              <input v-model="form.submitter" placeholder="填写报送人员" />
            </label>
          </div>

          <table class="sub-table">
            <thead>
              <tr>
                <th style="width: 40px">#</th>
                <th style="width: 110px">材料类型 *</th>
                <th>材料名称 *</th>
                <th style="width: 220px">文件名（含扩展名）*</th>
                <th style="width: 60px">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in form.items" :key="index">
                <td>{{ index + 1 }}</td>
                <td>
                  <select v-model="item.materialType">
                    <option value="">请选择</option>
                    <option value="设备照片">设备照片</option>
                    <option value="检测报告">检测报告</option>
                  </select>
                </td>
                <td><input v-model="item.materialName" placeholder="如 1号鼓风机检修后整体照" /></td>
                <td><input v-model="item.fileName" placeholder="如 blower-01.jpg" /></td>
                <td>
                  <button class="link" type="button" @click="removeItem(index)">删除</button>
                </td>
              </tr>
            </tbody>
          </table>
          <div class="row-actions" style="margin-bottom: 10px">
            <button class="btn" type="button" @click="addItem('设备照片')">加一条设备照片</button>
            <button class="btn" type="button" @click="addItem('检测报告')">加一条检测报告</button>
          </div>

          <ul v-if="submitErrors.length" class="line-errors">
            <li v-for="(error, index) in submitErrors" :key="index">{{ error }}</li>
          </ul>
        </section>

        <!-- 验收：逐条确认 / 驳回，全部通过并签字后整组归档 -->
        <section v-else>
          <div class="archive-meta">
            <span>批次：<strong>#{{ group.id }}</strong></span>
            <span>检修单号：<strong>{{ group['检修单号'] }}</strong></span>
            <span>报送人：{{ group['报送人'] }}</span>
            <span>报送时间：{{ group['报送时间'] }}</span>
            <span>整组进度：<strong>{{ group.progress }}</strong></span>
            <span>
              状态：
              <em class="tag" :class="statusClass">{{ group.status }}</em>
            </span>
          </div>

          <table class="sub-table">
            <thead>
              <tr>
                <th style="width: 40px">#</th>
                <th style="width: 90px">材料类型</th>
                <th>材料名称</th>
                <th>文件名</th>
                <th style="width: 80px">条目状态</th>
                <th style="width: 260px">验收操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in group.items" :key="item.id">
                <td>{{ index + 1 }}</td>
                <td>{{ item['材料类型'] }}</td>
                <td>{{ item['材料名称'] }}</td>
                <td>{{ item['文件名'] }}</td>
                <td>
                  <em class="tag" :class="itemStatusClass(item.status)">{{ item.status }}</em>
                </td>
                <td>
                  <template v-if="item.status === '待验收' && group.status !== '已归档'">
                    <div class="archive-actions">
                      <button class="link" type="button" @click="confirmItem(item)">确认通过</button>
                      <button class="link" type="button" @click="toggleReject(item)">单条驳回</button>
                    </div>
                    <div v-if="rejectingId === item.id" class="reject-box">
                      <div class="quick-reasons">
                        <button
                          v-for="reason in quickReasons"
                          :key="reason"
                          class="btn ghost"
                          type="button"
                          @click="rejectItem(item, reason)"
                        >
                          {{ reason }}
                        </button>
                      </div>
                      <textarea v-model="rejectDraft" rows="2" placeholder="或填写其他驳回理由"></textarea>
                      <div class="archive-actions" style="margin-top: 6px">
                        <button class="btn primary" type="button" @click="rejectItem(item, rejectDraft)">提交驳回</button>
                        <button class="btn ghost" type="button" @click="rejectingId = null">取消</button>
                      </div>
                    </div>
                  </template>
                  <template v-else>
                    <span v-if="item['验收人签字']">签字：{{ item['验收人签字'] }}</span>
                    <span v-if="item.status === '已驳回'" class="error-text">
                      理由：{{ item['reject_reason'] }}
                    </span>
                  </template>
                </td>
              </tr>
            </tbody>
          </table>

          <div class="form-grid" style="grid-template-columns: repeat(2, minmax(0, 1fr))">
            <label>
              <span>验收人签字 *（逐条确认与整组归档都必填）</span>
              <input v-model="reviewer" placeholder="填写验收人员姓名" />
            </label>
          </div>
        </section>
      </div>

      <div class="modal-foot">
        <span v-if="feedback" :class="feedbackOk ? '' : 'error-text'" style="margin-right: auto">
          {{ feedback }}
        </span>
        <button class="btn ghost" type="button" @click="$emit('close')">关闭</button>
        <button v-if="mode === 'submit'" class="btn primary" type="button" :disabled="submitting" @click="submit">
          批量报送
        </button>
        <template v-else>
          <button
            v-if="group.status === '待归档'"
            class="btn primary"
            type="button"
            :disabled="submitting"
            @click="archive"
          >
            验收人签字并整组归档
          </button>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

import { request } from '@/api/client'

interface MaterialDraft {
  materialType: string
  materialName: string
  fileName: string
}
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
  items: ArchiveItem[]
  [key: string]: unknown
}

const props = defineProps<{
  mode: 'submit' | 'review'
  initialOrder?: string
  group?: ArchiveGroup
}>()

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'changed'): void
}>()

const ENDPOINT = '/api/maint/archives'
const quickReasons = ['材料缺失', '格式不对']

const form = ref({
  orderNo: props.initialOrder ?? '',
  submitter: '',
  items: [
    { materialType: '设备照片', materialName: '', fileName: '' },
    { materialType: '检测报告', materialName: '', fileName: '' },
  ] as MaterialDraft[],
})
const submitErrors = ref<string[]>([])
const reviewer = ref('')
const rejectingId = ref<number | null>(null)
const rejectDraft = ref('')
const feedback = ref('')
const feedbackOk = ref(false)
const submitting = ref(false)

const group = computed<ArchiveGroup>(() => props.group as ArchiveGroup)
const statusClass = computed(() => {
  const map: Record<string, string> = {
    验收中: 'review',
    待归档: 'ready',
    已归档: 'archived',
    已退回: 'returned',
  }
  return map[group.value.status] ?? ''
})

function itemStatusClass(status: string): string {
  if (status === '已通过') return 'archived'
  if (status === '已驳回') return 'returned'
  return 'review'
}

function addItem(materialType: string) {
  form.value.items.push({ materialType, materialName: '', fileName: '' })
}

function removeItem(index: number) {
  form.value.items.splice(index, 1)
}

function setFeedback(message: string, ok: boolean) {
  feedback.value = message
  feedbackOk.value = ok
}

async function submit() {
  feedback.value = ''
  submitErrors.value = []
  submitting.value = true
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({
        values: {
          order_no: form.value.orderNo,
          submitter: form.value.submitter,
          items: form.value.items,
        },
      }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      submitErrors.value = (payload.errors ?? []).map(
        (error: { line: number; reason: string }) =>
          error.line > 0 ? `第 ${error.line} 条：${error.reason.replace(/^第 \d+ 条：?/, '')}` : error.reason,
      )
      if (!submitErrors.value.length) submitErrors.value = [payload.message ?? '报送未受理']
      setFeedback(payload.message ?? '报送未受理', false)
      return
    }
    emit('changed')
    emit('close')
  } catch (error) {
    setFeedback(error instanceof Error ? error.message : '报送请求失败', false)
  } finally {
    submitting.value = false
  }
}

function requireReviewer(): boolean {
  if (!reviewer.value.trim()) {
    setFeedback('验收人未签字：请先填写验收人员签字', false)
    return false
  }
  return true
}

async function postReview(item: ArchiveItem, values: Record<string, unknown>) {
  submitting.value = true
  try {
    const response = await request(
      `${ENDPOINT}/${group.value.id}/items/${item.id}/review`,
      { method: 'POST', body: JSON.stringify({ values }) },
    )
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      setFeedback(payload.message ?? '验收操作未生效', false)
      return
    }
    rejectingId.value = null
    setFeedback(payload.message ?? '操作成功', true)
    emit('changed')
  } catch (error) {
    setFeedback(error instanceof Error ? error.message : '验收请求失败', false)
  } finally {
    submitting.value = false
  }
}

function confirmItem(item: ArchiveItem) {
  if (!requireReviewer()) return
  void postReview(item, { action: '确认', reviewer: reviewer.value.trim() })
}

function toggleReject(item: ArchiveItem) {
  rejectingId.value = rejectingId.value === item.id ? null : item.id
  rejectDraft.value = ''
}

function rejectItem(item: ArchiveItem, reason: string) {
  if (!requireReviewer()) return
  const trimmed = reason.trim()
  if (!trimmed) {
    setFeedback('驳回材料必须填写理由（如：材料缺失、格式不对）', false)
    return
  }
  void postReview(item, { action: '驳回', reason: trimmed, reviewer: reviewer.value.trim() })
}

async function archive() {
  if (!requireReviewer()) return
  submitting.value = true
  try {
    const response = await request(`${ENDPOINT}/${group.value.id}/archive`, {
      method: 'POST',
      body: JSON.stringify({ values: { reviewer: reviewer.value.trim() } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      setFeedback(payload.message ?? '整组归档未生效', false)
      return
    }
    setFeedback(payload.message ?? '已整组归档', true)
    emit('changed')
  } catch (error) {
    setFeedback(error instanceof Error ? error.message : '归档请求失败', false)
  } finally {
    submitting.value = false
  }
}
</script>
