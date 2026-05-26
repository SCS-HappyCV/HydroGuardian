
export interface ProjectMemberData {
  id: string
  projectId: string
  userId: string
  roleId: string
  assignedAt: string
  status: 'active' | 'inactive'
}

export type ProjectMemberFilterKey = keyof Pick<ProjectMemberData, 'projectId' | 'userId' | 'roleId' | 'status'>
      