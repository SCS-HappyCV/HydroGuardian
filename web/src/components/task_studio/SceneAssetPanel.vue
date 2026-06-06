<!-- 场景资产面板：集中管理真实 API 执行所需的数据模式、sceneId 和上传资产。 -->
<script setup lang="ts">
import { isDataMode, type DataMode } from '@/lib/runtime-mode'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'

type FileField = 'imageFile' | 'pointCloudFile' | 'preImageFile' | 'postImageFile'

defineProps<{
  dataMode: DataMode
  sceneId: string
  sceneSampleFileId: string
  imageFile: File | null
  pointCloudFile: File | null
  preImageFile: File | null
  postImageFile: File | null
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:dataMode', value: DataMode): void
  (e: 'update:sceneId', value: string): void
  (e: 'update:sceneSampleFileId', value: string): void
  (e: 'update:imageFile', value: File | null): void
  (e: 'update:pointCloudFile', value: File | null): void
  (e: 'update:preImageFile', value: File | null): void
  (e: 'update:postImageFile', value: File | null): void
  (e: 'change'): void
}>()

// 切换 mock/api/hybrid 模式，并把选择同步给父组件持久化。
function handleModeChange(value: string): void {
  if (!isDataMode(value)) return
  emit('update:dataMode', value)
  emit('change')
}

// 更新 sceneId，后续真实任务会用它命中或注册后端 scene manifest。
function handleSceneIdChange(value: string | number): void {
  emit('update:sceneId', String(value))
  emit('change')
}

// 更新已有 SceneTensorSample 文件 ID，适合跳过前端上传直接注册 manifest。
function handleSceneSampleFileIdChange(value: string | number): void {
  emit('update:sceneSampleFileId', String(value))
  emit('change')
}

// 按文件字段派发更新事件，避免动态事件名削弱类型约束。
function emitFileUpdate(field: FileField, file: File | null): void {
  if (field === 'imageFile') emit('update:imageFile', file)
  if (field === 'pointCloudFile') emit('update:pointCloudFile', file)
  if (field === 'preImageFile') emit('update:preImageFile', file)
  if (field === 'postImageFile') emit('update:postImageFile', file)
}

// 处理原生文件选择事件，只取单文件并立即同步到父组件。
function handleFileChange(event: Event, field: FileField): void {
  const target = event.target as HTMLInputElement
  emitFileUpdate(field, target.files?.[0] ?? null)
  emit('change')
}

// 清空指定文件字段，方便用户重新选择同一类型资产。
function clearFile(field: FileField): void {
  emitFileUpdate(field, null)
  emit('change')
}

// 生成文件名展示文案，未选择时保持统一占位。
function getFileName(file: File | null): string {
  return file?.name || '未选择文件'
}
</script>

<template>
  <div class="surface-base card-padding space-y-4">
    <h3 class="text-item-title flex items-center gap-2">
      <SafeIcon name="DatabaseZap" :size="18" class="text-accent" />
      场景资产
    </h3>

    <div class="space-y-3">
      <div class="space-y-2">
        <Label class="text-label">运行模式</Label>
        <Select :model-value="dataMode" :disabled="disabled" @update:model-value="handleModeChange">
          <SelectTrigger class="bg-muted/20 border-border">
            <SelectValue placeholder="选择运行模式" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="mock">Mock 演示</SelectItem>
            <SelectItem value="api">真实 API</SelectItem>
            <SelectItem value="hybrid">混合回退</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div class="space-y-2">
        <Label class="text-label">Scene ID</Label>
        <Input
          :model-value="sceneId"
          :disabled="disabled"
          placeholder="例如 scene-binhai-001"
          class="bg-muted/20 border-border"
          @update:model-value="handleSceneIdChange"
        />
      </div>

      <div class="space-y-2">
        <Label class="text-label">已有样本 File ID</Label>
        <Input
          :model-value="sceneSampleFileId"
          :disabled="disabled"
          placeholder="已有 SceneTensorSample 可填"
          class="bg-muted/20 border-border"
          @update:model-value="handleSceneSampleFileIdChange"
        />
      </div>
    </div>

    <div class="space-y-3 pt-2 border-t border-border/50">
      <div class="space-y-2">
        <Label class="text-label">正射影像</Label>
        <input :disabled="disabled" type="file" accept="image/*" class="flex h-10 w-full rounded-md border border-border bg-muted/20 px-3 py-2 text-sm file:border-0 file:bg-transparent file:text-foreground file:text-sm file:font-medium disabled:cursor-not-allowed disabled:opacity-50" @change="handleFileChange($event, 'imageFile')" />
        <div class="flex items-center justify-between gap-2 text-xs text-muted-foreground">
          <span class="truncate">{{ getFileName(imageFile) }}</span>
          <Button v-if="imageFile" variant="ghost" size="sm" class="h-7 px-2" :disabled="disabled" @click="clearFile('imageFile')">清空</Button>
        </div>
      </div>

      <div class="space-y-2">
        <Label class="text-label">点云文件</Label>
        <input :disabled="disabled" type="file" accept=".ply,.pcd,.las,.laz,.xyz,.txt,.json" class="flex h-10 w-full rounded-md border border-border bg-muted/20 px-3 py-2 text-sm file:border-0 file:bg-transparent file:text-foreground file:text-sm file:font-medium disabled:cursor-not-allowed disabled:opacity-50" @change="handleFileChange($event, 'pointCloudFile')" />
        <div class="flex items-center justify-between gap-2 text-xs text-muted-foreground">
          <span class="truncate">{{ getFileName(pointCloudFile) }}</span>
          <Button v-if="pointCloudFile" variant="ghost" size="sm" class="h-7 px-2" :disabled="disabled" @click="clearFile('pointCloudFile')">清空</Button>
        </div>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div class="space-y-2">
          <Label class="text-label">灾前影像</Label>
          <input :disabled="disabled" type="file" accept="image/*" class="flex h-10 w-full rounded-md border border-border bg-muted/20 px-3 py-2 text-sm file:border-0 file:bg-transparent file:text-foreground file:text-sm file:font-medium disabled:cursor-not-allowed disabled:opacity-50" @change="handleFileChange($event, 'preImageFile')" />
          <div class="flex items-center justify-between gap-2 text-xs text-muted-foreground">
            <span class="truncate">{{ getFileName(preImageFile) }}</span>
            <Button v-if="preImageFile" variant="ghost" size="sm" class="h-7 px-2" :disabled="disabled" @click="clearFile('preImageFile')">清空</Button>
          </div>
        </div>

        <div class="space-y-2">
          <Label class="text-label">灾后影像</Label>
          <input :disabled="disabled" type="file" accept="image/*" class="flex h-10 w-full rounded-md border border-border bg-muted/20 px-3 py-2 text-sm file:border-0 file:bg-transparent file:text-foreground file:text-sm file:font-medium disabled:cursor-not-allowed disabled:opacity-50" @change="handleFileChange($event, 'postImageFile')" />
          <div class="flex items-center justify-between gap-2 text-xs text-muted-foreground">
            <span class="truncate">{{ getFileName(postImageFile) }}</span>
            <Button v-if="postImageFile" variant="ghost" size="sm" class="h-7 px-2" :disabled="disabled" @click="clearFile('postImageFile')">清空</Button>
          </div>
        </div>
      </div>
    </div>

    <div class="rounded-md border border-border/60 bg-muted/20 px-3 py-2 text-xs text-muted-foreground leading-relaxed">
      Mock 模式只创建本地任务；真实 API 会优先使用已填样本 File ID，或上传影像和点云后预处理；混合模式在 API 异常时回退到本地演示。
    </div>
  </div>
</template>
