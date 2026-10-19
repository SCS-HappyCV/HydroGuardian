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
  <section class="rounded-2xl border border-white/[0.08] bg-card/60 p-5 shadow-card">
    <div class="flex items-center justify-between gap-3">
      <div class="flex items-center gap-2">
        <span class="grid h-7 w-7 place-items-center rounded-lg bg-accent/10 text-xs font-semibold text-accent">2</span>
        <div><h3 class="text-sm font-semibold text-foreground">上传巡查数据</h3><p class="mt-0.5 text-[11px] text-muted-foreground">选择点云、单期影像或前后两期影像</p></div>
      </div>
      <span class="rounded-full border border-white/[0.08] bg-white/[0.03] px-2.5 py-1 text-[10px] text-muted-foreground">按任务选择即可</span>
    </div>

    <div class="mt-4 grid gap-3 sm:grid-cols-2">
      <label class="group rounded-xl border border-white/[0.08] bg-black/10 p-3 transition hover:border-primary/30">
        <span class="flex items-center gap-2 text-xs font-medium text-card-foreground"><SafeIcon name="Cuboid" :size="15" class="text-violet-300"/>点云数据</span>
        <input :disabled="disabled" type="file" accept=".ply,.pcd,.las,.laz,.xyz,.txt,.json" class="mt-2 block w-full text-[11px] text-muted-foreground file:mr-2 file:rounded-md file:border-0 file:bg-primary/10 file:px-2.5 file:py-1.5 file:text-[11px] file:text-primary" @change="handleFileChange($event, 'pointCloudFile')" />
        <span class="mt-2 flex items-center justify-between gap-2 text-[10px] text-muted-foreground"><span class="truncate">{{ getFileName(pointCloudFile) }}</span><button v-if="pointCloudFile" type="button" class="text-primary hover:underline" @click.prevent="clearFile('pointCloudFile')">移除</button></span>
      </label>
      <label class="group rounded-xl border border-white/[0.08] bg-black/10 p-3 transition hover:border-primary/30">
        <span class="flex items-center gap-2 text-xs font-medium text-card-foreground"><SafeIcon name="Image" :size="15" class="text-primary"/>单期影像</span>
        <input :disabled="disabled" type="file" accept="image/*,.tif,.tiff" class="mt-2 block w-full text-[11px] text-muted-foreground file:mr-2 file:rounded-md file:border-0 file:bg-primary/10 file:px-2.5 file:py-1.5 file:text-[11px] file:text-primary" @change="handleFileChange($event, 'imageFile')" />
        <span class="mt-2 flex items-center justify-between gap-2 text-[10px] text-muted-foreground"><span class="truncate">{{ getFileName(imageFile) }}</span><button v-if="imageFile" type="button" class="text-primary hover:underline" @click.prevent="clearFile('imageFile')">移除</button></span>
      </label>
      <div class="rounded-xl border border-white/[0.08] bg-black/10 p-3 sm:col-span-2">
        <span class="flex items-center gap-2 text-xs font-medium text-card-foreground"><SafeIcon name="Images" :size="15" class="text-accent"/>前后时相影像</span>
        <div class="mt-2 grid gap-2 sm:grid-cols-2">
          <label class="rounded-lg border border-white/[0.06] px-2.5 py-2"><span class="text-[10px] text-muted-foreground">前时相</span><input :disabled="disabled" type="file" accept="image/*,.tif,.tiff" class="mt-1 block w-full text-[10px] text-muted-foreground file:mr-1 file:rounded file:border-0 file:bg-accent/10 file:px-2 file:py-1 file:text-[10px] file:text-accent" @change="handleFileChange($event, 'preImageFile')" /><span class="mt-1 flex justify-between gap-2 text-[10px] text-muted-foreground"><span class="truncate">{{ getFileName(preImageFile) }}</span><button v-if="preImageFile" type="button" class="text-accent hover:underline" @click.prevent="clearFile('preImageFile')">移除</button></span></label>
          <label class="rounded-lg border border-white/[0.06] px-2.5 py-2"><span class="text-[10px] text-muted-foreground">后时相</span><input :disabled="disabled" type="file" accept="image/*,.tif,.tiff" class="mt-1 block w-full text-[10px] text-muted-foreground file:mr-1 file:rounded file:border-0 file:bg-accent/10 file:px-2 file:py-1 file:text-[10px] file:text-accent" @change="handleFileChange($event, 'postImageFile')" /><span class="mt-1 flex justify-between gap-2 text-[10px] text-muted-foreground"><span class="truncate">{{ getFileName(postImageFile) }}</span><button v-if="postImageFile" type="button" class="text-accent hover:underline" @click.prevent="clearFile('postImageFile')">移除</button></span></label>
        </div>
      </div>
    </div>

    <details class="mt-3 rounded-xl border border-white/[0.06] bg-black/10 px-3 py-2.5">
      <summary class="cursor-pointer text-xs text-muted-foreground">数据来源设置</summary>
      <div class="mt-3 grid gap-3 sm:grid-cols-3">
        <div class="space-y-1.5"><Label class="text-[11px]">运行方式</Label><Select :model-value="dataMode" :disabled="disabled" @update:model-value="handleModeChange"><SelectTrigger class="h-9 border-border bg-muted/20"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="mock">预置场景</SelectItem><SelectItem value="api">实时分析</SelectItem><SelectItem value="hybrid">自动保障</SelectItem></SelectContent></Select></div>
        <div class="space-y-1.5"><Label class="text-[11px]">场景标识</Label><Input :model-value="sceneId" :disabled="disabled" class="h-9 border-border bg-muted/20" @update:model-value="handleSceneIdChange" /></div>
        <div class="space-y-1.5"><Label class="text-[11px]">已有样本标识</Label><Input :model-value="sceneSampleFileId" :disabled="disabled" placeholder="可选" class="h-9 border-border bg-muted/20" @update:model-value="handleSceneSampleFileIdChange" /></div>
      </div>
    </details>
  </section>
</template>
