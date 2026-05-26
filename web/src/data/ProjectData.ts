export interface ProjectData {
  id: string
  name: string
  code: string
  region: string
  status: 'active' | 'paused'
  createdAt: string
  updatedAt: string
}

export type ProjectFilterKey = keyof Pick<ProjectData, 'status' | 'region'>
