export interface RoleData {
  id: string
  name: string
  code: string
  description: string
  permissionCount: number
  isSystem: boolean
  createdAt: string
  updatedAt: string
}

export type RoleFilterKey = keyof Pick<RoleData, 'isSystem'>
