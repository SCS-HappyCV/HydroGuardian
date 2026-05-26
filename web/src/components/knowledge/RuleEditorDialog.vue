
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
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
import { Switch } from '@/components/ui/switch'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { RuleService } from '@/data/RuleService'
import type { RuleData } from '@/data/RuleData'
import { toast } from 'vue-sonner'

const props = defineProps<{
  ruleId: string | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'saved'): void
}>()

const isLoading = ref(false)
const formData = ref<Partial<RuleData>>({
  name: '',
  version: 'v1.0',
  category: 'hydrology',
  conditionSummary: '',
  isActive: true
})

onMounted(() => {
  if (props.ruleId) {
    const rule = RuleService.getById(props.ruleId)
    if (rule) {
      formData.value = { ...rule }
    }
  }
})

const isEditMode = computed(() => !!props.ruleId)
const dialogTitle = computed(() => isEditMode.value ? '编辑规则' : '新建规则')

const handleSubmit = async () => {
  if (!formData.value.name?.trim()) {
    toast.error('请输入规则名称')
    return
  }
  if (!formData.value.conditionSummary?.trim()) {
    toast.error('请输入触发条件')
    return
  }

  isLoading.value = true
  try {
    const allRules = RuleService.getAll()
    let updatedRules: RuleData[]

    if (isEditMode.value && props.ruleId) {
      updatedRules = allRules.map(r => 
        r.id === props.ruleId 
          ? {
              ...r,
              name: formData.value.name!,
              version: formData.value.version!,
              category: formData.value.category as any,
              conditionSummary: formData.value.conditionSummary!,
              isActive: formData.value.isActive!,
              updatedAt: new Date().toISOString()
            }
          : r
      )
    } else {
      const newRule: RuleData = {
        id: `rule-${Date.now()}`,
        name: formData.value.name!,
        version: formData.value.version!,
        category: formData.value.category as any,
        conditionSummary: formData.value.conditionSummary!,
        isActive: formData.value.isActive!,
        hitCount: 0,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      }
      updatedRules = [...allRules, newRule]
    }

    RuleService.savePersisted(updatedRules)
    toast.success(isEditMode.value ? '规则已更新' : '规则已创建')
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
        <!-- Rule Name -->
        <div class="space-y-2">
          <Label for="rule-name" class="text-label">规则名称 *</Label>
          <Input
            id="rule-name"
            v-model="formData.name"
            placeholder="例如：连续水位上升触发"
            class="bg-card/50 border-border"
          />
        </div>

        <!-- Version -->
        <div class="space-y-2">
          <Label for="rule-version" class="text-label">版本号</Label>
          <Input
            id="rule-version"
            v-model="formData.version"
            placeholder="例如：v1.0"
            class="bg-card/50 border-border"
          />
        </div>

        <!-- Category -->
        <div class="space-y-2">
          <Label for="rule-category" class="text-label">分类 *</Label>
          <Select v-model="formData.category">
            <SelectTrigger id="rule-category" class="bg-card/50 border-border">
              <SelectValue placeholder="选择分类" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="hydrology">水文监测</SelectItem>
              <SelectItem value="structure">结构安全</SelectItem>
              <SelectItem value="operation">运维管理</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <!-- Condition Summary -->
        <div class="space-y-2">
          <Label for="rule-condition" class="text-label">触发条件 *</Label>
          <Textarea
            id="rule-condition"
            v-model="formData.conditionSummary"
            placeholder="描述规则的触发条件..."
            class="bg-card/50 border-border min-h-[120px] resize-none"
          />
        </div>

        <!-- Active Status -->
        <div class="flex items-center justify-between p-4 surface-base">
          <div class="space-y-1">
            <Label class="text-label">启用此规则</Label>
            <p class="text-caption text-muted-foreground">禁用后该规则将不再参与风险判定</p>
          </div>
          <Switch v-model="formData.isActive" />
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
          {{ isLoading ? '保存中...' : '提交' }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
