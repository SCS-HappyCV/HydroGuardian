<script setup lang="ts">
import type { WorkorderData } from '@/data/WorkorderData'
import type { WorkorderTimelineVO } from '@/data/WorkorderTimelineService'
import type { WorkorderEvidenceData } from '@/data/WorkorderEvidenceData'
import type { WorkorderReviewVO } from '@/data/WorkorderReviewService'
import ClosureTimeline from '@/components/workorder_detail/ClosureTimeline.vue'

defineProps<{
  workorder: WorkorderData
  timeline: WorkorderTimelineVO[]
  evidence?: WorkorderEvidenceData[]
  review?: WorkorderReviewVO | null
}>()
</script>

<template>
  <ClosureTimeline
    :workorder="workorder"
    :timeline="timeline"
    :evidence="evidence"
    :review="review"
    compact
  />
</template>
