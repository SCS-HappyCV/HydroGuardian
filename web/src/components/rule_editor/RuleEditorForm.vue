
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
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Separator } from '@/components/ui/separator'
import PageHeader from '@/components/common/PageHeader.vue'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { toast } from 'vue-sonner'
import { cn } from '@/lib/utils'
import * as RuleService from '@/data/RuleService'
import type { RuleData } from '@/data/RuleData'

const isClient = ref(true)
const ruleId = ref<string | null>(null)
const isEditMode = ref(false)
const showDeleteDialog = ref(false)
const showTestDialog = ref(false)
const showVersionHistory = ref(false)
const showPreview = ref(false)
const isSaving = ref(false)

const formData = ref<RuleData>({
  id: '',
  name: '',
  version: 'v1.0',
  category: 'hydrology',
  conditionSummary: '',
  isActive: true,
  hitCount: 0,
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
})

const testInput = ref('')
const testResult = ref<{ passed: boolean; message: string } | null>(null)

const breadcrumb = computed(() => [
  { label: '知识库管理', href: './knowledge.html' },
  { label: isEditMode.value ? '编辑规则' : '新建规则' },
])

const pageTitle = computed(() => isEditMode.value ? '编辑规则' : '新建规则')

const pageSubtitle = computed(() => {
  if (isEditMode.value) {
    return `规则ID: ${formData.value.id} · 版本: ${formData.value.version}`
  }
  return '创建新的风险判定规则'
})

const versionHistory = computed(() => {
  return [
    { version: formData.value.version, date: formData.value.updatedAt, author: '系统管理员', changes: '当前版本' },
    { version: 'v0.9', date: '2026-05-10T00:00:00Z', author: '系统管理员', changes: '优化条件判定逻辑' },
    { version: 'v0.8', date: '2026-05-01T00:00:00Z', author: '系统管理员', changes: '初始版本' },
  ]
})

const allRules = ref<RuleData[]>(RuleService.getAll())

onMounted(() => {
  isClient.value = false
  requestAnimationFrame(() => {
    const params = new URLSearchParams(window.location.search)
    const paramRuleId = params.get('ruleId')

    if (paramRuleId) {
      const rule = RuleService.getById(paramRuleId)
      if (rule) {
        formData.value = { ...rule }
        isEditMode.value = true
        ruleId.value = paramRuleId
      } else {
        toast.error('规则不存在，已进入新建模式')
        isEditMode.value = false
      }
    } else {
      isEditMode.value = false
      formData.value = {
        id: `rule-${Date.now()}`,
        name: '',
        version: 'v1.0',
        category: 'hydrology',
        conditionSummary: '',
        isActive: true,
        hitCount: 0,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      }
    }
    isClient.value = true
  })
})

const handleSave = async () => {
  if (!formData.value.name.trim()) {
    toast.error('请输入规则名称')
    return
  }

  if (!formData.value.conditionSummary.trim()) {
    toast.error('请输入规则条件说明')
    return
  }

  isSaving.value = true
  try {
    formData.value.updatedAt = new Date().toISOString()

    const allRulesData = RuleService.getAll()
    const existingIndex = allRulesData.findIndex(r => r.id === formData.value.id)

    if (existingIndex >= 0) {
      allRulesData[existingIndex] = formData.value
    } else {
      allRulesData.push(formData.value)
    }

    RuleService.savePersisted(allRulesData)
    allRules.value = allRulesData

    toast.success(isEditMode.value ? '规则已更新' : '规则已创建')
    setTimeout(() => {
      window.location.href = './knowledge.html'
    }, 800)
  } catch (error) {
    toast.error('保存失败，请重试')
  } finally {
    isSaving.value = false
  }
}

const handleCancel = () => {
  window.location.href = './knowledge.html'
}

const handleDelete = () => {
  showDeleteDialog.value = true
}

const confirmDelete = () => {
  try {
    const allRulesData = RuleService.getAll()
    const filtered = allRulesData.filter(r => r.id !== formData.value.id)
    RuleService.savePersisted(filtered)
    allRules.value = filtered

    toast.success('规则已删除')
    setTimeout(() => {
      window.location.href = './knowledge.html'
    }, 800)
  } catch (error) {
    toast.error('删除失败，请重试')
  } finally {
    showDeleteDialog.value = false
  }
}

const handleTestRule = () => {
  if (!testInput.value.trim()) {
    toast.error('请输入测试数据')
    return
  }

  try {
    const passed = testInput.value.toLowerCase().includes('trigger')
    testResult.value = {
      passed,
      message: passed ? '✓ 规则触发成功' : '✗ 规则未触发',
    }
    toast.success('测试完成')
  } catch (error) {
    toast.error('测试失败')
  }
}

const handleCopyRule = () => {
  const newRule: RuleData = {
    ...formData.value,
    id: `rule-${Date.now()}`,
    name: `${formData.value.name} (副本)`,
    version: 'v1.0',
    hitCount: 0,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  }

  const allRulesData = RuleService.getAll()
  allRulesData.push(newRule)
  RuleService.savePersisted(allRulesData)
  allRules.value = allRulesData

  toast.success('已复制到新规则')
  setTimeout(() => {
    window.location.href = `./rule-editor.html?ruleId=${newRule.id}`
  }, 800)
}
</script>

<template>
  <div v-if="isClient" class="h-full flex flex-col bg-background overflow-hidden">
    <PageHeader 
      :title="pageTitle"
      :subtitle="pageSubtitle"
      :breadcrumb="breadcrumb"
    >
      <template #actions>
        <div class="flex items-center gap-2">
          <Button 
            variant="outline" 
            size="sm"
            @click="handleCopyRule"
            class="gap-2"
          >
            <SafeIcon name="Copy" :size="16" />
            复制规则
          </Button>
          <Button 
            variant="outline" 
            size="sm"
            @click="() => showTestDialog = true"
            class="gap-2"
          >
            <SafeIcon name="Play" :size="16" />
            测试规则
          </Button>
          <Button 
            v-if="isEditMode"
            variant="destructive" 
            size="sm"
            @click="handleDelete"
            class="gap-2"
          >
            <SafeIcon name="Trash2" :size="16" />
            删除
          </Button>
        </div>
      </template>
    </PageHeader>

    <div class="flex-1 overflow-y-auto min-h-0">
      <div class="page-body max-w-4xl mx-auto">
        <Tabs default-value="editor" class="w-full">
          <TabsList class="grid w-full max-w-md grid-cols-3 mb-6">
            <TabsTrigger value="editor" class="gap-2">
              <SafeIcon name="FileText" :size="16" />
              编辑
            </TabsTrigger>
            <TabsTrigger value="preview" class="gap-2">
              <SafeIcon name="Eye" :size="16" />
              预览
            </TabsTrigger>
            <TabsTrigger v-if="isEditMode" value="history" class="gap-2">
              <SafeIcon name="History" :size="16" />
              历史
            </TabsTrigger>
          </TabsList>

          <TabsContent value="editor" class="space-y-6">
            <div class="form-section space-y-4">
              <h3 class="text-section-title">基本信息</h3>
              
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div class="space-y-2">
                  <Label for="name" class="text-label">规则名称 *</Label>
                  <Input
                    id="name"
                    v-model="formData.name"
                    placeholder="例如：连续水位上升触发"
                    class="bg-input/50 border-border focus:ring-primary"
                  />
                </div>

                <div class="space-y-2">
                  <Label for="category" class="text-label">规则类别 *</Label>
                  <Select v-model="formData.category">
                    <SelectTrigger id="category" class="bg-input/50 border-border">
                      <SelectValue placeholder="选择类别" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="hydrology">水文学</SelectItem>
                      <SelectItem value="structure">结构工程</SelectItem>
                      <SelectItem value="operation">运营管理</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div class="space-y-2">
                  <Label for="version" class="text-label">版本号</Label>
                  <Input
                    id="version"
                    v-model="formData.version"
                    placeholder="v1.0"
                    class="bg-input/50 border-border focus:ring-primary"
                  />
                </div>

                <div class="space-y-2">
                  <Label for="status" class="text-label">状态</Label>
                  <Select :model-value="formData.isActive ? 'active' : 'inactive'" @update:model-value="(val) => formData.isActive = val === 'active'">
                    <SelectTrigger id="status" class="bg-input/50 border-border">
                      <SelectValue placeholder="选择状态" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="active">启用</SelectItem>
                      <SelectItem value="inactive">禁用</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>

            <Separator class="opacity-30" />

            <div class="form-section space-y-4">
              <h3 class="text-section-title">规则条件</h3>
              
              <div class="space-y-2">
                <Label for="condition" class="text-label">条件说明 *</Label>
                <p class="text-caption text-muted-foreground">
                  详细描述规则的触发条件和判定逻辑
                </p>
                <Textarea
                  id="condition"
                  v-model="formData.conditionSummary"
                  placeholder="例如：连续 3 次采样水位上升且超过阈值 1.5m，或单次上升超过 2.0m"
                  class="min-h-[120px] bg-input/50 border-border focus:ring-primary font-mono text-sm"
                />
              </div>

              <div class="bg-muted/20 border border-border/50 rounded-[--radius] p-4 space-y-2">
                <div class="flex items-center gap-2 text-sm">
                  <SafeIcon name="Info" :size="16" class="text-accent" />
                  <span class="font-medium text-foreground">规则编写建议</span>
                </div>
                <ul class="text-xs text-muted-foreground space-y-1 ml-6 list-disc">
                  <li>使用清晰的逻辑表达式（AND、OR、NOT）</li>
                  <li>指定具体的数值阈值和时间窗口</li>
                  <li>包含异常情况的处理说明</li>
                  <li>标注规则的适用范围和限制条件</li>
                </ul>
              </div>
            </div>

            <Separator class="opacity-30" />

            <div class="form-section space-y-4">
              <h3 class="text-section-title">高级配置</h3>
              
              <div class="space-y-3">
                <div class="flex items-center justify-between p-3 bg-muted/20 rounded-[--radius] border border-border/50">
                  <div>
                    <p class="text-sm font-medium text-foreground">触发次数</p>
                    <p class="text-xs text-muted-foreground mt-0.5">该规则已触发 {{ formData.hitCount }} 次</p>
                  </div>
                  <span class="text-lg font-bold text-primary">{{ formData.hitCount }}</span>
                </div>

                <div class="flex items-center justify-between p-3 bg-muted/20 rounded-[--radius] border border-border/50">
                  <div>
                    <p class="text-sm font-medium text-foreground">创建时间</p>
                    <p class="text-xs text-muted-foreground mt-0.5">{{ new Date(formData.createdAt).toLocaleString('zh-CN') }}</p>
                  </div>
                </div>

                <div class="flex items-center justify-between p-3 bg-muted/20 rounded-[--radius] border border-border/50">
                  <div>
                    <p class="text-sm font-medium text-foreground">最后更新</p>
                    <p class="text-xs text-muted-foreground mt-0.5">{{ new Date(formData.updatedAt).toLocaleString('zh-CN') }}</p>
                  </div>
                </div>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="preview" class="space-y-6">
            <div class="form-section space-y-4">
              <h3 class="text-section-title">规则逻辑预览</h3>
              
              <div class="bg-muted/30 border border-border/50 rounded-[--radius] p-6 space-y-4 font-mono text-sm">
                <div class="space-y-2">
                  <p class="text-muted-foreground text-xs uppercase tracking-wider">规则名称</p>
                  <p class="text-foreground text-base font-semibold">{{ formData.name || '(未命名)' }}</p>
                </div>

                <Separator class="opacity-20" />

                <div class="space-y-2">
                  <p class="text-muted-foreground text-xs uppercase tracking-wider">类别</p>
                  <p class="text-foreground">{{ { hydrology: '水文学', structure: '结构工程', operation: '运营管理' }[formData.category] }}</p>
                </div>

                <Separator class="opacity-20" />

                <div class="space-y-2">
                  <p class="text-muted-foreground text-xs uppercase tracking-wider">条件逻辑</p>
                  <div class="bg-background/50 p-3 rounded border border-border/30 min-h-[100px] whitespace-pre-wrap break-words text-xs leading-relaxed">
                    {{ formData.conditionSummary || '(未定义)' }}
                  </div>
                </div>

                <Separator class="opacity-20" />

                <div class="space-y-2">
                  <p class="text-muted-foreground text-xs uppercase tracking-wider">状态</p>
                  <p class="text-foreground">{{ formData.isActive ? '✓ 启用' : '✗ 禁用' }}</p>
                </div>
              </div>
            </div>
          </TabsContent>

          <TabsContent v-if="isEditMode" value="history" class="space-y-6">
            <div class="form-section space-y-4">
              <h3 class="text-section-title">版本历史</h3>
              
              <div class="space-y-3">
                <div 
                  v-for="(version, index) in versionHistory" 
                  :key="index"
                  class="flex gap-4 pb-4"
                  :class="index < versionHistory.length - 1 && 'border-b border-border/30'"
                >
                  <div class="flex flex-col items-center">
                    <div :class="cn('w-3 h-3 rounded-full', index === 0 ? 'bg-primary' : 'bg-muted')"/>
                    <div v-if="index < versionHistory.length - 1" class="w-0.5 h-8 bg-border/30 mt-1" />
                  </div>
                  
                  <div class="flex-1 pt-1">
                    <div class="flex items-center justify-between">
                      <p class="font-medium text-foreground">{{ version.version }}</p>
                      <p class="text-xs text-muted-foreground">{{ new Date(version.date).toLocaleString('zh-CN') }}</p>
                    </div>
                    <p class="text-sm text-muted-foreground mt-1">{{ version.changes }}</p>
                    <p class="text-xs text-muted-foreground mt-2">作者: {{ version.author }}</p>
                  </div>
                </div>
              </div>
            </div>
          </TabsContent>
        </Tabs>

        <Separator class="opacity-30 my-8" />

        <div class="flex items-center justify-end gap-3 pb-4">
          <Button 
            variant="outline" 
            @click="handleCancel"
            class="px-6"
          >
            取消
          </Button>
          <Button 
            @click="handleSave"
            :disabled="isSaving"
            class="px-6 gap-2"
          >
            <SafeIcon v-if="isSaving" name="Loader2" :size="16" class="animate-spin" />
            {{ isSaving ? '保存中...' : '保存规则' }}
          </Button>
        </div>
      </div>
    </div>

    <AlertDialog :open="showDeleteDialog" @update:open="showDeleteDialog = $event">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>删除规则</AlertDialogTitle>
          <AlertDialogDescription>
            确定要删除规则 "{{ formData.name }}" 吗？此操作无法撤销。
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>取消</AlertDialogCancel>
          <AlertDialogAction @click="confirmDelete" class="bg-destructive hover:bg-destructive/90">
            删除
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <Dialog :open="showTestDialog" @update:open="showTestDialog = $event">
      <DialogContent class="max-w-md">
        <DialogHeader>
          <DialogTitle>测试规则</DialogTitle>
          <DialogDescription>
            输入测试数据来验证规则逻辑
          </DialogDescription>
        </DialogHeader>

        <div class="space-y-4">
          <div class="space-y-2">
            <Label for="test-input" class="text-label">测试数据</Label>
            <Textarea
              id="test-input"
              v-model="testInput"
              placeholder="输入包含 'trigger' 的文本来模拟规则触发"
              class="min-h-[100px] bg-input/50 border-border focus:ring-primary font-mono text-sm"
            />
          </div>

          <div v-if="testResult" :class="cn('p-3 rounded-[--radius] border', testResult.passed ? 'bg-[hsl(var(--success))]/10 border-[hsl(var(--success))]/30' : 'bg-destructive/10 border-destructive/30')">
            <p :class="cn('text-sm font-medium', testResult.passed ? 'text-[hsl(var(--success))]' : 'text-destructive')">
              {{ testResult.message }}
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" @click="() => showTestDialog = false">
            关闭
          </Button>
          <Button @click="handleTestRule" class="gap-2">
            <SafeIcon name="Play" :size="16" />
            执行测试
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
