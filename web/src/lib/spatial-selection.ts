import { ref } from 'vue'
import type { RiskEventData } from '@/data/RiskEventData'

export type SpatialEvidenceView = 'map' | 'ortho' | 'pointcloud' | 'comparison' | 'mask'
export type SpatialSelectionSource = 'route' | 'list' | 'map' | 'ortho' | 'comparison' | 'detail'

const validViews = new Set<SpatialEvidenceView>(['map', 'ortho', 'pointcloud', 'comparison', 'mask'])

export function useSpatialSelection() {
  const selectedRiskId = ref<string | null>(null)
  const selectedRegionId = ref<string | null>(null)
  const hoveredRiskId = ref<string | null>(null)
  const activeView = ref<SpatialEvidenceView>('map')
  const source = ref<SpatialSelectionSource>('route')

  function restoreFromUrl() {
    if (typeof window === 'undefined') return
    const params = new URLSearchParams(window.location.search)
    selectedRiskId.value = params.get('riskId')
    selectedRegionId.value = params.get('regionId')
    const view = params.get('view') as SpatialEvidenceView | null
    if (view && validViews.has(view)) activeView.value = view
  }

  function syncUrl() {
    if (typeof window === 'undefined') return
    const url = new URL(window.location.href)
    if (selectedRiskId.value) url.searchParams.set('riskId', selectedRiskId.value)
    else url.searchParams.delete('riskId')
    if (selectedRegionId.value) url.searchParams.set('regionId', selectedRegionId.value)
    else url.searchParams.delete('regionId')
    url.searchParams.set('view', activeView.value)
    window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`)
  }

  function selectRisk(risk: RiskEventData | null, nextSource: SpatialSelectionSource) {
    selectedRiskId.value = risk?.id || null
    selectedRegionId.value = risk?.candidateRegionId || null
    source.value = nextSource
    syncUrl()
  }

  function hoverRisk(riskId: string | null) {
    hoveredRiskId.value = riskId
  }

  function setView(view: SpatialEvidenceView) {
    activeView.value = view
    syncUrl()
  }

  return { selectedRiskId, selectedRegionId, hoveredRiskId, activeView, source, restoreFromUrl, selectRisk, hoverRisk, setView, syncUrl }
}
