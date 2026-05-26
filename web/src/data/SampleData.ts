export interface SampleData {
  id: string
  name: string
  zoneId: string
  sampleType: 'image' | 'sensor' | 'manual'
  collectedAt: string
  status: 'available' | 'archived'
}

export type SampleFilterKey = keyof Pick<SampleData, 'zoneId' | 'sampleType' | 'status'>
