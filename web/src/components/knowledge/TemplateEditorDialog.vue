
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { TemplateService } from '@/data/TemplateService'
import type { TemplateData } from '@/data/TemplateData'
import { toast } from 'vue-sonner'

const props = defineProps<{
  templateId: string | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'saved'): void
}>()

const isLoading = ref(false)
const formData = ref<Partial<TemplateData>>({
  name: '',
  type: 'dispatch',
  applicableRiskLevels: ['high'],
  content: '',
  isEnabled: true
})

onMounted(() => {
  if (props.templateId) {
    const template = TemplateService.getById(props.templateId)
    if (template) {
      formData.value = { ...template }
    }
  }
})

const isEditMode = computed(() => !!props.templateId)
const dialogTitle = computed(() => isEditMode.value ? '编辑模板' : '新建模板')

const riskLevelOptions = [
  { value: 'high', label: '高风险' },
  { value: 'medium', label: '中风险' },
  { value: 'low', label: '低风险' },
  { value: 'review_required', label: '待复核' }
]

const toggleRiskLevel = (level: string) => {
  const levels = formData.value.applicableRiskLevels || []
  const index = levels.indexOf(level as any)
  if (index > -1) {
    levels.splice(index, 1)
  } else {
    levels.push(level as any)
  }
  formData.value.applicableRiskLevels = [...levels]
}

const isRiskLevelSelected = (level: string) => {
  return (formData.value.applicableRiskLevels || []).includes(level as any)
}

const handleSubmit = async () => {
  if (!formData.value.name?.trim()) {
    toast.error('请输入模板名称')
    return
  }
  if (!formData.value.content?.trim()) {
    toast.error('请输入模板内容')
    return
  }
  if (!formData.value.applicableRiskLevels || formData.value.applicableRiskLevels.length === 0) {
    toast.error('请至少选择一个适用风险等级')
    return
  }

  isLoading.value = true
  try {
    const allTemplates = TemplateService.getAll()
    let updatedTemplates: TemplateData[]

    if (isEditMode.value && props.templateId) {
      updatedTemplates = allTemplates.map(t => 
        t.id === props.templateId 
          ? {
              ...t,
              name: formData.value.name!,
              type: formData.value.type!,
              applicableRiskLevels: formData.value.applicableRiskLevels!,
              content: formData.value.content!,
              isEnabled: formData.value.isEnabled!,
              updatedAt: new Date().toISOString()
            }
          : t
      )
    } else {
      const newTemplate: TemplateData = {
        id: `tpl-${Date.now()}`,
        name: formData.value.name!,
        type: formData.value.type!,
        applicableRiskLevels: formData.value.applicableRiskLevels!,
        content: formData.value.content!,
        callCount: 0,
        isEnabled: formData.value.isEnabled!,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      }
      updatedTemplates = [...allTemplates, newTemplate]
    }

    TemplateService.savePersisted(updatedTemplates)
    toast.success(isEditMode.value ? '模板已更新' : '模板已创建')
    emit('saved')
    emit('close')
  } catch (error) {
    toast.error('保存失败，请重试')
    console.error(error)
  } finally {
    isLoading.value = false
  }
}

const handleCancel = () => {
  emit('close')
}
</script>

<template>
  <Dialog open @update:open="handleCancel">
    <DialogContent class="max-w-2xl max-h-[80vh] flex flex-col">
      <DialogHeader class="flex-shrink-0">
        <DialogTitle class="text-xl">{{ dialogTitle }}</DialogTitle>
      </DialogHeader>

      <div class="flex-1 overflow-y-auto min-h-0 space-y-6 px-6 py-4">
        <!-- Template Name -->
        <div class="space-y-2">
          <Label for="template-name" class="text-label">模板名称 *</Label>
          <Input
            id="template-name"
            v-model="formData.name"
            placeholder="例如：高风险处置模板"
            class="bg-card/50 border-border"
          />
        </div>

        <!-- Template Type -->
        <div class="space-y-2">
          <Label for="template-type" class="text-label">模板类型 *</Label>
          <Select v-model="formData.type">
            <SelectTrigger id="template-type" class="bg-card/50 border-border">
              <SelectValue placeholder="选择类型" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="dispatch">处置建议</SelectItem>
              <SelectItem value="review">复核建议</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <!-- Applicable Risk Levels -->
        <div class="space-y-3">
          <Label class="text-label">适用风险等级 *</Label>
          <div class="grid grid-cols-2 gap-3 p-4 surface-base">
            <div v-for="option in riskLevelOptions" :key="option.value" class="flex items-center gap-2">
              <Checkbox
                :id="`risk-${option.value}`"
                :checked="isRiskLevelSelected(option.value)"
                @update:checked="toggleRiskLevel(option.value)"
              />
              <Label :for="`risk-${option.value}`" class="text-sm cursor-pointer">
                {{ option.label }}
              </Label>
            </div>
          </div>
        </div>

        <!-- Template Content -->
        <div class="space-y-2">
          <Label for="template-content" class="text-label">模板内容 *</Label>
          <Textarea
            id="template-content"
            v-model="formData.content"
            placeholder="输入模板文本内容..."
            class="bg-card/50 border-border min-h-[120px] resize-none"
          />
        </div>

        <!-- Enabled Status -->
        <div class="flex items-center justify-between p-4 surface-base">
          <div class="space-y-1">
            <Label class="text-label">启用此模板</Label>
            <p class="text-caption text-muted-foreground">禁用后该模板将不再被推荐使用</p>
          </div>
          <Switch v-model="formData.isEnabled" />
        </div>
      </div>

      <DialogFooter class="flex-shrink-0 border-t border-border pt-4 px-6 pb-4 flex justify-end gap-3">
        <Button 
          variant="outline" 
          @click="handleCancel"
          :disabled="isLoading"
        >
          取消
        </Button>
        <Button 
          class="bg-primary hover:bg-primary-hover text-primary-foreground"
          @click="handleSubmit"
          :disabled="isLoading"
        >
          <SafeIcon v-if="isLoading" name="Loader2" :size="16" class="mr-2 animate-spin" />
          {{ isLoading ? '保存中...' : '保存' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
