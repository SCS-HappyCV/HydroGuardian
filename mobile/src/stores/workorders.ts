import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { fieldWorkOrders } from '@/data/workorders'
import { runtimeConfig } from '@/config/runtime'
import { mapRemoteWorkorder } from '@/api/remoteWorkorderMapper'
import { remoteWorkorderApi } from '@/api/remoteWorkorderApi'
import { primaryFieldUser } from '@/domain/user'
import { workorderRepository } from '@/repositories/workorderRepository'
import type { MobileRiskLevel, MobileWorkOrder, MobileWorkOrderStatus } from '@/domain/workorder'

type TaskFilter = 'active' | 'reviewed' | 'closed'
type RiskFilter = 'all' | MobileRiskLevel

function cloneSeedData(): MobileWorkOrder[] {
  return fieldWorkOrders.map((item) => ({
    ...item,
    evidence: item.evidence.map((evidence) => ({ ...evidence })),
  }))
}

export const useWorkorderStore = defineStore('workorders', () => {
  const items = ref<MobileWorkOrder[]>(runtimeConfig.dataMode === 'remote' ? [] : cloneSeedData())
  const initialized = ref(false)
  const activeFilter = ref<TaskFilter>('active')
  const riskFilter = ref<RiskFilter>('all')
  const searchQuery = ref('')
  const lastRefreshedAt = ref<string | null>(null)
  const loadError = ref('')

  const filteredItems = computed(() => {
    const query = searchQuery.value.trim().toLocaleLowerCase('zh-CN')

    return items.value
      .filter((item) => activeFilter.value === 'active'
        ? ['todo', 'assigned', 'in_progress'].includes(item.status)
        : item.status === activeFilter.value)
      .filter((item) => riskFilter.value === 'all' || item.riskLevel === riskFilter.value)
      .filter((item) => !query || [item.title, item.area, item.taskId, item.summary]
        .some((value) => value.toLocaleLowerCase('zh-CN').includes(query)))
      .sort((a, b) => {
        return new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
          || new Date(b.deadline).getTime() - new Date(a.deadline).getTime()
      })
  })

  const activeCount = computed(() => items.value.filter((item) => ['todo', 'assigned', 'in_progress'].includes(item.status)).length)
  const reviewedCount = computed(() => items.value.filter((item) => item.status === 'reviewed').length)
  const closedCount = computed(() => items.value.filter((item) => item.status === 'closed').length)

  function getById(id: string) {
    return items.value.find((item) => item.id === id)
  }

  async function hydrate() {
    if (initialized.value) return
    loadError.value = ''

    try {
      const restored = await workorderRepository.load()
      if (restored?.length) items.value = restored
      if (runtimeConfig.dataMode === 'remote') {
        const remote = await remoteWorkorderApi.list()
        items.value = remote.map(mapRemoteWorkorder)
        await workorderRepository.save(items.value)
      } else if (!restored?.length) {
        await workorderRepository.save(items.value)
      }
      lastRefreshedAt.value = new Date().toISOString()
    } catch {
      loadError.value = items.value.length
        ? '最新任务暂未同步，当前展示设备内已保存的数据'
        : '任务数据读取失败，请稍后重试'
    } finally {
      initialized.value = true
    }
  }

  async function refresh() {
    initialized.value = false
    await hydrate()
  }

  async function setStatus(id: string, status: MobileWorkOrderStatus) {
    const item = getById(id)
    if (!item) return
    if (runtimeConfig.dataMode === 'remote' && item.source === 'remote') {
      const remote = status === 'assigned'
        ? await remoteWorkorderApi.assign(id, primaryFieldUser.id, primaryFieldUser.id)
        : status === 'in_progress'
          ? await remoteWorkorderApi.start(id, primaryFieldUser.id)
          : await remoteWorkorderApi.get(id)
      const mapped = mapRemoteWorkorder(remote)
      const index = items.value.findIndex((candidate) => candidate.id === id)
      if (index >= 0) items.value[index] = mapped
      await workorderRepository.save(items.value)
      return
    }
    item.status = status
    item.updatedAt = new Date().toISOString()
    item.progress = status === 'assigned' ? 40 : status === 'in_progress' ? 60 : status === 'reviewed' ? 80 : status === 'closed' ? 100 : 20
    await workorderRepository.save(items.value)
  }

  async function applyRemoteWorkorder(id: string) {
    if (runtimeConfig.dataMode !== 'remote') return false
    const remote = await remoteWorkorderApi.get(id)
    const mapped = mapRemoteWorkorder(remote)
    const index = items.value.findIndex((item) => item.id === id)
    if (index >= 0) items.value[index] = mapped
    else items.value.unshift(mapped)
    await workorderRepository.save(items.value)
    return true
  }

  async function setLocalStatus(id: string, status: MobileWorkOrderStatus) {
    const item = getById(id)
    if (!item) return
    item.status = status
    item.progress = status === 'reviewed' ? 80 : item.progress
    item.updatedAt = new Date().toISOString()
    await workorderRepository.save(items.value)
  }

  async function resetAll() {
    await workorderRepository.clear()
    items.value = runtimeConfig.dataMode === 'remote' ? [] : cloneSeedData()
    activeFilter.value = 'active'
    riskFilter.value = 'all'
    searchQuery.value = ''
    if (runtimeConfig.dataMode === 'remote') {
      initialized.value = false
      await hydrate()
    } else {
      await workorderRepository.save(items.value)
    }
  }

  return {
    items,
    initialized,
    activeFilter,
    riskFilter,
    searchQuery,
    lastRefreshedAt,
    loadError,
    filteredItems,
    activeCount,
    reviewedCount,
    closedCount,
    getById,
    hydrate,
    refresh,
    setStatus,
    setLocalStatus,
    applyRemoteWorkorder,
    resetAll,
  }
})
