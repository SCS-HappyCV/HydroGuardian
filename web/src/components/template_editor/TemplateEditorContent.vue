
<script setup lang="ts">
import { ref, computed, reactive } from 'vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  RadioGroup,
  RadioGroupItem,
} from '@/components/ui/radio-group'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { toast } from 'vue-sonner'
import SafeIcon from '@/components/common/SafeIcon.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import { TemplateService } from '@/data/TemplateService'
import type { TemplateData } from '@/data/TemplateData'

const isClient = ref(true)
const isLoading = ref(false)
const isSaving = ref(false)
const isDeleting = ref(false)
const templateId = ref<string | null>(null)
const isEditMode = ref(false)

const validationSchema = toTypedSchema(
  z.object({
    name: z.string().min(1, '模板名称不能为空').min(2, '模板名称至少2个字符'),
    type: z.enum(['dispatch', 'review'], { errorMap: () => ({ message: '请选择模板类型' }) }),
    applicableRiskLevels: z.array(z.enum(['high', 'medium', 'low', 'review_required'])).min(1, '至少选择一个风险等级'),
    content: z.string().min(1, '模板内容不能为空').min(10, '模板内容至少10个字符'),
  })
)

const { values, errors, setFieldValue, resetForm } = useForm({
  validationSchema,
  initialValues: {
    name: '',
    type: 'dispatch' as 'dispatch' | 'review',
    applicableRiskLevels: [] as ('high' | 'medium' | 'low' | 'review_required')[],
    content: '',
  },
})

const riskLevelOptions = [
  { value: 'high', label: '高风险' },
  { value: 'medium', label: '中风险' },
  { value: 'low', label: '低风险' },
  { value: 'review_required', label: '待复核' },
]

const typeOptions = [
  { value: 'dispatch', label: '处置建议模板' },
  { value: 'review', label: '复核建议模板' },
]

const selectedRiskLevels = computed(() => values.applicableRiskLevels || [])

const handleRiskLevelChange = (level: string, checked: boolean) => {
  const current = [...(values.applicableRiskLevels || [])]
  if (checked) {
    if (!current.includes(level as any)) {
      current.push(level as any)
    }
  } else {
    const index = current.indexOf(level as any)
    if (index > -1) {
      current.splice(index, 1)
    }
  }
  setFieldValue('applicableRiskLevels', current)
}

const loadTemplate = async (id: string) => {
  isLoading.value = true
  try {
    const template = TemplateService.getById(id)
    if (template) {
      templateId.value = id
      isEditMode.value = true
      setFieldValue('name', template.name)
      setFieldValue('type', template.type)
      setFieldValue('applicableRiskLevels', template.applicableRiskLevels)
      setFieldValue('content', template.content)
    } else {
      toast.error('模板不存在')
      setTimeout(() => {
        window.location.href = './knowledge.html'
      }, 1500)
    }
  } catch (error) {
    toast.error('加载模板失败')
    console.error(error)
  } finally {
    isLoading.value = false
  }
}

const handleSave = async () => {
  if (!values.name || !values.type || !values.applicableRiskLevels?.length || !values.content) {
    toast.error('请填写所有必填字段')
    return
  }

  isSaving.value = true
  try {
    const allTemplates = TemplateService.getAll()
    let updatedTemplates: TemplateData[]

    if (isEditMode.value && templateId.value) {
      updatedTemplates = allTemplates.map((t) =>
        t.id === templateId.value
          ? {
              ...t,
              name: values.name,
              type: values.type as 'dispatch' | 'review',
              applicableRiskLevels: values.applicableRiskLevels as ('high' | 'medium' | 'low' | 'review_required')[],
              content: values.content,
              updatedAt: new Date().toISOString(),
            }
          : t
      )
    } else {
      const newTemplate: TemplateData = {
        id: `tpl-${Date.now()}`,
        name: values.name,
        type: values.type as 'dispatch' | 'review',
        applicableRiskLevels: values.applicableRiskLevels as ('high' | 'medium' | 'low' | 'review_required')[],
        content: values.content,
        callCount: 0,
        isEnabled: true,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      }
      updatedTemplates = [...allTemplates, newTemplate]
    }

    TemplateService.savePersisted(updatedTemplates)
    toast.success(isEditMode.value ? '模板已更新' : '模板已创建')

    setTimeout(() => {
      window.location.href = './knowledge.html'
    }, 1000)
  } catch (error) {
    toast.error('保存失败，请重试')
    console.error(error)
  } finally {
    isSaving.value = false
  }
}

const handleDelete = async () => {
  if (!isEditMode.value || !templateId.value) return

  isDeleting.value = true
  try {
    const allTemplates = TemplateService.getAll()
    const updatedTemplates = allTemplates.filter((t) => t.id !== templateId.value)
    TemplateService.savePersisted(updatedTemplates)
    toast.success('模板已删除')

    setTimeout(() => {
      window.location.href = './knowledge.html'
    }, 1000)
  } catch (error) {
    toast.error('删除失败，请重试')
    console.error(error)
  } finally {
    isDeleting.value = false
  }
}

const handleCancel = () => {
  window.location.href = './knowledge.html'
}

onMounted(() => {
  isClient.value = false
  requestAnimationFrame(() => {
    isClient.value = true

    const params = new URLSearchParams(window.location.search)
    const id = params.get('templateId')
    if (id) {
      loadTemplate(id)
    }
  })
})
</script>

<template>
  <div v-if="isClient" class="page-body flex flex-col min-h-screen bg-background">
    <PageHeader
      title="建议模板配置"
      :subtitle="isEditMode ? '编辑现有模板' : '创建新的建议模板'"
      :breadcrumb="[
        { label: '知识库管理', href: './knowledge.html' },
        { label: isEditMode ? '编辑模板' : '新建模板' },
      ]"
    >
      <template #actions>
        <Button
          variant="outline"
          @click="handleCancel"
          :disabled="isSaving || isDeleting"
        >
          取消
        </Button>
        <Button
          v-if="isEditMode"
          variant="destructive"
          @click="() => {}"
          :disabled="isSaving || isDeleting"
        >
          <AlertDialog>
            <AlertDialogTrigger as-child>
              <button class="flex items-center gap-2">
                <SafeIcon name="Trash2" :size="16" />
                删除
              </button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>确认删除</AlertDialogTitle>
                <AlertDialogDescription>
                  此操作将永久删除该模板，且无法撤销。
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>取消</AlertDialogCancel>
                <AlertDialogAction
                  class="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  @click="handleDelete"
                  :disabled="isDeleting"
                >
                  {{ isDeleting ? '删除中...' : '确认删除' }}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </Button>
        <Button
          @click="handleSave"
          :disabled="isSaving || isLoading"
          class="bg-primary hover:bg-primary-hover"
        >
          <SafeIcon v-if="!isSaving" name="Save" :size="16" class="mr-2" />
          <span v-if="isSaving" class="inline-block animate-spin mr-2">
            <SafeIcon name="Loader2" :size="16" />
          </span>
          {{ isSaving ? '保存中...' : '保存模板' }}
        </Button>
      </template>
    </PageHeader>

    <div v-if="isLoading" class="flex-1 flex items-center justify-center">
      <div class="flex flex-col items-center gap-4">
        <div class="w-12 h-12 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
        <p class="text-muted-foreground">加载模板中...</p>
      </div>
    </div>

    <div v-else class="flex-1 overflow-y-auto min-h-0 pb-8">
      <div class="max-w-2xl mx-auto">
        <!-- 模板类型选择 -->
        <div class="form-section">
          <div class="space-y-3">
            <Label class="text-label">模板类型 *</Label>
            <RadioGroup :model-value="values.type" @update:model-value="(val) => setFieldValue('type', val)">
              <div v-for="option in typeOptions" :key="option.value" class="flex items-center space-x-3">
                <RadioGroupItem :id="`type-${option.value}`" :value="option.value" />
                <Label :for="`type-${option.value}`" class="text-sm font-normal cursor-pointer">
                  {{ option.label }}
                </Label>
              </div>
            </RadioGroup>
            <p v-if="errors.type" class="text-xs text-destructive mt-1">{{ errors.type }}</p>
          </div>
        </div>

        <!-- 模板名称 -->
        <div class="form-section">
          <div class="space-y-2">
            <Label for="name" class="text-label">模板名称 *</Label>
            <Input
              id="name"
              :model-value="values.name"
              @update:model-value="(val) => setFieldValue('name', val)"
              placeholder="例如：高风险处置模板"
              class="bg-card/50 border-border focus:ring-1 focus:ring-primary"
            />
            <p v-if="errors.name" class="text-xs text-destructive mt-1">{{ errors.name }}</p>
          </div>
        </div>

        <!-- 适用风险等级 -->
        <div class="form-section">
          <div class="space-y-3">
            <Label class="text-label">适用风险等级 *</Label>
            <div class="grid grid-cols-2 gap-3">
              <div
                v-for="level in riskLevelOptions"
                :key="level.value"
                class="flex items-center space-x-2 p-3 rounded-lg border border-border/50 hover:border-primary/30 transition-colors cursor-pointer"
                @click="handleRiskLevelChange(level.value, !selectedRiskLevels.includes(level.value as any))"
              >
                <input
                  type="checkbox"
                  :id="`level-${level.value}`"
                  :checked="selectedRiskLevels.includes(level.value as any)"
                  @change="(e) => handleRiskLevelChange(level.value, (e.target as HTMLInputElement).checked)"
                  class="w-4 h-4 rounded border-border cursor-pointer"
                />
                <Label :for="`level-${level.value}`" class="text-sm font-normal cursor-pointer flex-1">
                  {{ level.label }}
                </Label>
              </div>
            </div>
            <p v-if="errors.applicableRiskLevels" class="text-xs text-destructive mt-1">
              {{ errors.applicableRiskLevels }}
            </p>
          </div>
        </div>

        <!-- 模板内容 -->
        <div class="form-section">
          <div class="space-y-2">
            <Label for="content" class="text-label">模板内容 *</Label>
            <Textarea
              id="content"
              :model-value="values.content"
              @update:model-value="(val) => setFieldValue('content', val)"
              placeholder="输入模板的建议内容，支持Markdown格式..."
              class="min-h-[200px] bg-card/50 border-border focus:ring-1 focus:ring-primary resize-none"
            />
            <p class="text-xs text-muted-foreground mt-1">
              {{ values.content?.length || 0 }} / 1000 字符
            </p>
            <p v-if="errors.content" class="text-xs text-destructive mt-1">{{ errors.content }}</p>
          </div>
        </div>

        <!-- 模板预览 -->
        <div class="form-section">
          <div class="space-y-2">
            <Label class="text-label">内容预览</Label>
            <div class="bg-card/30 border border-border/50 rounded-lg p-4 min-h-[120px] text-sm text-card-foreground whitespace-pre-wrap break-words">
              {{ values.content || '预览内容将在此显示...' }}
            </div>
          </div>
        </div>

        <!-- 模板信息 (编辑模式) -->
        <div v-if="isEditMode" class="form-section">
          <div class="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p class="text-muted-foreground text-xs uppercase tracking-wider mb-1">模板ID</p>
              <p class="font-mono text-card-foreground">{{ templateId }}</p>
            </div>
            <div>
              <p class="text-muted-foreground text-xs uppercase tracking-wider mb-1">调用次数</p>
              <p class="font-mono text-card-foreground">{{ TemplateService.getById(templateId)?.callCount || 0 }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
