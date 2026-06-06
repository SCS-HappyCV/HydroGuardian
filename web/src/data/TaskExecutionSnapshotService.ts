// 任务执行快照服务：保存真实 API 执行结果，供监控页、风险页和历史页后续回放。

import type { TaskExecutionSnapshot } from '@/lib/api-contracts'

const STORAGE_KEY = 'hydroguardian_task_execution_snapshots'

// 读取所有本地执行快照。
export function getAll(): TaskExecutionSnapshot[] {
  if (typeof localStorage === 'undefined') return []
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) return []

  try {
    return JSON.parse(raw) as TaskExecutionSnapshot[]
  } catch {
    return []
  }
}

// 按本地任务 ID 查询执行快照。
export function getByTaskId(taskId: string): TaskExecutionSnapshot | undefined {
  return getAll().find((item) => item.localTaskId === taskId)
}

// 保存或覆盖单个执行快照。
export function saveSnapshot(snapshot: TaskExecutionSnapshot): void {
  if (typeof localStorage === 'undefined') return
  const snapshots = getAll()
  const index = snapshots.findIndex((item) => item.localTaskId === snapshot.localTaskId)

  // 同一个 localTaskId 重试时覆盖旧快照，避免监控页读到过期结果。
  if (index >= 0) {
    snapshots[index] = snapshot
  } else {
    snapshots.unshift(snapshot)
  }

  localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshots))
}

// 删除指定任务的执行快照。
export function removeByTaskId(taskId: string): void {
  if (typeof localStorage === 'undefined') return
  const snapshots = getAll().filter((item) => item.localTaskId !== taskId)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshots))
}
