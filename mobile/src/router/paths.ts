export function taskDetailPath(workorderId: string) {
  return `/tabs/tasks/${encodeURIComponent(workorderId)}`
}

export function taskFeedbackPath(workorderId: string) {
  return `${taskDetailPath(workorderId)}/feedback`
}
