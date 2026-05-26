export interface DatasetData {
  id: string
  name: string
  code: string
  description: string
  sourceType: 'gis' | 'sensor' | 'manual'
  status: 'ready' | 'syncing' | 'offline'
  createdAt: string
  updatedAt: string
}

export type DatasetFilterKey = keyof Pick<DatasetData, 'sourceType' | 'status'>
