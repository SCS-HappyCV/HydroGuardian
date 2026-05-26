export interface UserData {
  id: string
  name: string
  email: string
  roleId: string
  projectId: string
  datasetId: string
  status: 'active' | 'disabled'
  avatarUrl: string
  createdAt: string
  updatedAt: string
}

export type UserFilterKey = keyof Pick<UserData, 'roleId' | 'projectId' | 'datasetId' | 'status'>
