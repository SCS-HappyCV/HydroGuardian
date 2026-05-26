
<script setup lang="ts">
import { Button } from '@/components/ui/button';
import SafeIcon from '@/components/common/SafeIcon.vue';

interface EmptyStateProps {
  icon?: string;
  title: string;
  description?: string;
  actionLabel?: string;
  actionHref?: string;
}

const props = withDefaults(defineProps<EmptyStateProps>(), {
  icon: 'Inbox',
  description: '',
  actionLabel: '',
  actionHref: '#',
});

const handleAction = () => {
  if (props.actionHref && props.actionHref !== '#') {
    window.location.href = props.actionHref;
  }
};
</script>

<template>
  <div class="empty-state w-full h-full flex flex-col items-center justify-center p-8">
    <div class="mb-6 rounded-full bg-muted/30 p-6 ring-1 ring-border shadow-sm">
      <SafeIcon 
        :name="icon" 
        :size="48" 
        :stroke-width="1.5" 
        class="text-muted-foreground/60"
      />
    </div>
    
    <div class="max-w-md space-y-2">
      <h3 class="text-xl font-semibold text-foreground">
        {{ title }}
      </h3>
      <p v-if="description" class="text-sm text-muted-foreground leading-relaxed">
        {{ description }}
      </p>
    </div>

    <div v-if="actionLabel" class="mt-8">
      <Button 
        variant="outline" 
        class="interactive px-8 py-5 text-base border-primary/20 hover:bg-primary/10 hover:border-primary/40 text-primary"
        @click="handleAction"
      >
        {{ actionLabel }}
      </Button>
    </div>
  </div>
</template>

<style scoped>
.empty-state {
  animation: fadeIn 0.4s ease-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
