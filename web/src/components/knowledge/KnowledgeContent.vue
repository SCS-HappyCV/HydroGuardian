
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import PageHeader from '@/components/common/PageHeader.vue'
import SafeIcon from '@/components/common/SafeIcon.vue'
import RuleList from './RuleList.vue'
import TemplateList from './TemplateList.vue'
import RuleEditorDialog from './RuleEditorDialog.vue'
import TemplateEditorDialog from './TemplateEditorDialog.vue'

const isClient = ref(true)
const activeTab = ref('rules')
const showRuleEditor = ref(false)
const showTemplateEditor = ref(false)
const editingRuleId = ref<string | null>(null)
const editingTemplateId = ref<string | null>(null)

onMounted(() => {
  isClient.value = false
  requestAnimationFrame(() => {
    const params = new URLSearchParams(window.location.search)
    const tab = params.get('activeTab')
    if (tab === 'templates') {
      activeTab.value = 'templates'
    }
    isClient.value = true
  })
})

const handleTabChange = (tab: string) => {
  activeTab.value = tab
  history.replaceState(null, '', `./knowledge.html?activeTab=${tab}`)
}

const openRuleEditor = (ruleId: string | null = null) => {
  editingRuleId.value = ruleId
  showRuleEditor.value = true
}

const closeRuleEditor = () => {
  showRuleEditor.value = false
  editingRuleId.value = null
}

const openTemplateEditor = (templateId: string | null = null) => {
  editingTemplateId.value = templateId
  showTemplateEditor.value = true
}

const closeTemplateEditor = () => {
  showTemplateEditor.value = false
  editingTemplateId.value = null
}

const handleRuleRefresh = () => {
  closeRuleEditor()
}

const handleTemplateRefresh = () => {
  closeTemplateEditor()
}
</script>

<template>
  <div v-if="isClient" class="flex flex-col h-full min-h-0 bg-background">
    <PageHeader 
      title="知识库管理"
      subtitle="管理风险判定规则和处置建议模板"
      :breadcrumb="[
        { label: '首页', href: './dashboard.html' },
        { label: '知识库管理' }
      ]"
    />

    <div class="flex-1 overflow-y-auto min-h-0 page-body">
      <Tabs 
        :model-value="activeTab" 
        @update:model-value="handleTabChange"
        class="w-full h-full flex flex-col"
      >
        <TabsList class="grid w-full max-w-md grid-cols-2 bg-card/50 border border-border p-1 rounded-lg mb-6">
          <TabsTrigger value="rules" class="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">
            <SafeIcon name="BookOpen" :size="16" class="mr-2" />
            规则管理
          </TabsTrigger>
          <TabsTrigger value="templates" class="data-[state=active]:bg-primary data-[state=active]:text-primary-foreground">
            <SafeIcon name="FileText" :size="16" class="mr-2" />
            建议模板
          </TabsTrigger>
        </TabsList>

        <TabsContent value="rules" class="flex-1 min-h-0 mt-0">
          <div class="flex flex-col h-full gap-4">
            <div class="flex items-center justify-between">
              <h2 class="text-section-title">风险判定规则</h2>
              <Button 
                class="gap-2 bg-primary hover:bg-primary-hover text-primary-foreground"
                @click="openRuleEditor(null)"
              >
                <SafeIcon name="Plus" :size="16" />
                新建规则
              </Button>
            </div>
            <RuleList 
              @edit="openRuleEditor"
              @refresh="handleRuleRefresh"
            />
          </div>
        </TabsContent>

        <TabsContent value="templates" class="flex-1 min-h-0 mt-0">
          <div class="flex flex-col h-full gap-4">
            <div class="flex items-center justify-between">
              <h2 class="text-section-title">处置建议模板</h2>
              <Button 
                class="gap-2 bg-primary hover:bg-primary-hover text-primary-foreground"
                @click="openTemplateEditor(null)"
              >
                <SafeIcon name="Plus" :size="16" />
                新建模板
              </Button>
            </div>
            <TemplateList 
              @edit="openTemplateEditor"
              @refresh="handleTemplateRefresh"
            />
          </div>
        </TabsContent>
      </Tabs>
    </div>

    <RuleEditorDialog 
      v-if="showRuleEditor"
      :rule-id="editingRuleId"
      @close="closeRuleEditor"
      @saved="handleRuleRefresh"
    />

    <TemplateEditorDialog 
      v-if="showTemplateEditor"
      :template-id="editingTemplateId"
      @close="closeTemplateEditor"
      @saved="handleTemplateRefresh"
    />
  </div>
</template>
