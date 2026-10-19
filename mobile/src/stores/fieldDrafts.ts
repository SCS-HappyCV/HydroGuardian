import { ref } from 'vue'
import { defineStore } from 'pinia'
import { createFieldDraft, type EvidencePhoto, type FieldDraft, type LocationSnapshot } from '@/domain/fieldDraft'
import { fieldDraftRepository } from '@/repositories/fieldDraftRepository'
import { evidenceFileService } from '@/services/evidenceFileService'

export const useFieldDraftStore = defineStore('field-drafts', () => {
  const items = ref<FieldDraft[]>([])
  const initialized = ref(false)

  async function hydrate() {
    if (initialized.value) return
    items.value = await fieldDraftRepository.loadAll()
    initialized.value = true
  }

  function getByWorkorderId(workorderId: string) {
    return items.value.find((draft) => draft.workorderId === workorderId)
  }

  function ensure(workorderId: string) {
    let draft = getByWorkorderId(workorderId)
    if (!draft) {
      draft = createFieldDraft(workorderId)
      items.value.push(draft)
    }
    return draft
  }

  async function persist() {
    await fieldDraftRepository.saveAll(items.value)
  }

  async function updateNote(workorderId: string, note: string) {
    const draft = ensure(workorderId)
    draft.note = note
    draft.updatedAt = new Date().toISOString()
    await persist()
  }

  async function setLocation(workorderId: string, location: LocationSnapshot) {
    const draft = ensure(workorderId)
    draft.location = location
    draft.updatedAt = new Date().toISOString()
    await persist()
  }

  async function setPhoto(workorderId: string, photo: EvidencePhoto) {
    const draft = ensure(workorderId)
    const previous = draft.photos.find((item) => item.kind === photo.kind)
    draft.photos = [...draft.photos.filter((item) => item.kind !== photo.kind), photo]
    draft.updatedAt = new Date().toISOString()
    await persist()
    if (previous && previous.path !== photo.path) await evidenceFileService.remove(previous.path)
  }

  async function setSinglePhoto(workorderId: string, photo: EvidencePhoto) {
    const draft = ensure(workorderId)
    const previousPhotos = draft.photos.filter((item) => item.path !== photo.path)
    draft.photos = [photo]
    draft.updatedAt = new Date().toISOString()
    await persist()
    await Promise.all(previousPhotos.map((item) => evidenceFileService.remove(item.path)))
  }

  async function retainSinglePhoto(workorderId: string, photoId: string) {
    const draft = ensure(workorderId)
    const photo = draft.photos.find((item) => item.id === photoId)
    if (!photo || draft.photos.length <= 1) return
    await setSinglePhoto(workorderId, photo)
  }

  async function markSubmitted(workorderId: string) {
    const draft = ensure(workorderId)
    draft.submittedAt = new Date().toISOString()
    draft.updatedAt = draft.submittedAt
    await persist()
  }

  async function clearAll() {
    await evidenceFileService.clearAll()
    await fieldDraftRepository.clear()
    items.value = []
  }

  return {
    items,
    initialized,
    hydrate,
    getByWorkorderId,
    ensure,
    updateNote,
    setLocation,
    setPhoto,
    setSinglePhoto,
    retainSinglePhoto,
    markSubmitted,
    clearAll,
  }
})
