<script setup lang="ts">
import { computed, ref } from 'vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Checkbox } from '@/components/ui/checkbox'
import SafeIcon from '@/components/common/SafeIcon.vue'
import { toast } from 'vue-sonner'
import { setAuthSession } from '@/lib/auth'
import { authApi } from '@/lib/auth-api'

type AuthTab = 'login' | 'register'

const activeTab = ref<AuthTab>('login')
const showPassword = ref(false)
const showConfirmPassword = ref(false)
const isSubmitting = ref(false)
const isHydrated = ref(false)
const rememberedEmailKey = 'remembered_login_email'

const loginSchema = toTypedSchema(
  z.object({
    loginEmail: z.string().email('请输入有效的邮箱地址'),
    loginPassword: z.string().min(6, '密码至少 6 个字符'),
    rememberMe: z.boolean().default(false),
  }),
)

const registerSchema = toTypedSchema(
  z.object({
    registerName: z.string().min(2, '用户名至少 2 个字符').max(20, '用户名最多 20 个字符'),
    registerEmail: z.string().email('请输入有效的邮箱地址'),
    registerPassword: z
      .string()
      .min(8, '密码至少 8 个字符')
      .regex(/[A-Z]/, '密码必须包含大写字母')
      .regex(/[0-9]/, '密码必须包含数字'),
    registerConfirm: z.string(),
    agreeTerms: z.boolean().refine((val) => val === true, '请勾选同意服务条款'),
  }).refine((data) => data.registerPassword === data.registerConfirm, {
    message: '两次输入的密码不一致',
    path: ['registerConfirm'],
  }),
)

const loginForm = useForm({
  validationSchema: loginSchema,
  initialValues: {
    loginEmail: '',
    loginPassword: '',
    rememberMe: false,
  },
})

const registerForm = useForm({
  validationSchema: registerSchema,
  initialValues: {
    registerName: '',
    registerEmail: '',
    registerPassword: '',
    registerConfirm: '',
    agreeTerms: false,
  },
})

const [loginEmail, loginEmailProps] = loginForm.defineField('loginEmail')
const [loginPassword, loginPasswordProps] = loginForm.defineField('loginPassword')
const [registerName, registerNameProps] = registerForm.defineField('registerName')
const [registerEmail, registerEmailProps] = registerForm.defineField('registerEmail')
const [registerPassword, registerPasswordProps] = registerForm.defineField('registerPassword')
const [registerConfirm, registerConfirmProps] = registerForm.defineField('registerConfirm')

const rememberMe = computed<boolean>({
  get: () => Boolean(loginForm.values.rememberMe),
  set: (value) => loginForm.setFieldValue('rememberMe', value),
})

const agreeTerms = computed<boolean>({
  get: () => Boolean(registerForm.values.agreeTerms),
  set: (value) => registerForm.setFieldValue('agreeTerms', value),
})

const handleTabChange = (value: string | number) => {
  const nextTab = value as AuthTab
  activeTab.value = nextTab

  if (nextTab === 'register') {
    registerForm.resetForm({
      values: {
        registerName: '',
        registerEmail: '',
        registerPassword: '',
        registerConfirm: '',
        agreeTerms: false,
      },
    })
  }
}

const handleLoginSubmit = loginForm.handleSubmit(async (values) => {
  isSubmitting.value = true
  try {
    const payload = await authApi.login({
      email: values.loginEmail.trim(),
      password: values.loginPassword,
      rememberMe: values.rememberMe,
    })

    const authUser = payload.data?.user ?? {
      id: 'user-001',
      name: '系统管理员',
      email: values.loginEmail.trim(),
      role: 'admin',
      department: '安全运营部',
      avatarUrl: 'https://spark-builder.s3.cn-north-1.amazonaws.com.cn/image/2026/5/25/77fefb85-a38b-48f8-8e7d-e7a6df12426d.png',
    }

    setAuthSession({
      token: payload.data?.token || `token_${Date.now()}`,
      user: authUser,
    })

    if (values.rememberMe) {
      localStorage.setItem(rememberedEmailKey, values.loginEmail.trim())
    } else {
      localStorage.removeItem(rememberedEmailKey)
    }

    toast.success('登录成功，正在跳转...')

    setTimeout(() => {
      const redirectUrl = sessionStorage.getItem('auth_redirect_url') || './dashboard.html'
      sessionStorage.removeItem('auth_redirect_url')
      window.location.href = redirectUrl
    }, 600)
  } catch (error) {
    const message = error instanceof Error ? error.message : '登录失败，请重试'
    toast.error(message)
  } finally {
    isSubmitting.value = false
  }
})

const handleRegisterSubmit = registerForm.handleSubmit(async (values) => {
  isSubmitting.value = true
  try {
    await authApi.register({
      name: values.registerName.trim(),
      email: values.registerEmail.trim(),
      password: values.registerPassword,
      confirmPassword: values.registerConfirm,
      agreeTerms: values.agreeTerms,
    })

    toast.success('注册成功，请登录')

    registerForm.resetForm({
      values: {
        registerName: '',
        registerEmail: '',
        registerPassword: '',
        registerConfirm: '',
        agreeTerms: false,
      },
    })
    activeTab.value = 'login'
    loginForm.setFieldValue('loginEmail', values.registerEmail.trim())
  } catch (error) {
    const message = error instanceof Error ? error.message : '注册失败，请重试'
    toast.error(message)
  } finally {
    isSubmitting.value = false
  }
})

const handleForgotPassword = () => {
  toast.info('密码重置功能开发中，请联系管理员')
}

const togglePasswordVisibility = () => {
  showPassword.value = !showPassword.value
}

const toggleConfirmPasswordVisibility = () => {
  showConfirmPassword.value = !showConfirmPassword.value
}

onMounted(() => {
  const params = new URLSearchParams(window.location.search)
  const redirectUrl = params.get('redirectUrl')
  if (redirectUrl) {
    sessionStorage.setItem('auth_redirect_url', redirectUrl)
  }

  const rememberedEmail = localStorage.getItem(rememberedEmailKey)
  if (rememberedEmail) {
    loginForm.setFieldValue('loginEmail', rememberedEmail)
    loginForm.setFieldValue('rememberMe', true)
  }

  isHydrated.value = true
})
</script>

<template>
  <div v-if="isHydrated" class="surface-raised rounded-2xl overflow-hidden">
    <Tabs :model-value="activeTab" @update:model-value="handleTabChange" class="w-full">
      <TabsList class="w-full rounded-none border-b border-border bg-transparent p-0 h-auto">
        <TabsTrigger
          value="login"
          data-tab="login"
          class="flex-1 rounded-none border-b-2 border-transparent py-4 text-sm font-medium transition-all data-[state=active]:border-primary data-[state=active]:text-foreground data-[state=inactive]:text-muted-foreground"
        >
          登录
        </TabsTrigger>
        <TabsTrigger
          value="register"
          data-tab="register"
          class="flex-1 rounded-none border-b-2 border-transparent py-4 text-sm font-medium transition-all data-[state=active]:border-primary data-[state=active]:text-foreground data-[state=inactive]:text-muted-foreground"
        >
          注册
        </TabsTrigger>
      </TabsList>

      <TabsContent value="login" class="card-padding space-y-4">
        <form @submit="handleLoginSubmit" class="space-y-4">
          <div class="space-y-2">
            <Label for="loginEmail" class="text-label">邮箱地址</Label>
            <div class="relative">
              <SafeIcon name="Mail" :size="16" class="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
              <Input
                id="loginEmail"
                v-model="loginEmail"
                v-bind="loginEmailProps"
                type="email"
                placeholder="请输入邮箱地址"
                class="pl-9 bg-muted/30 border-border focus:bg-muted/50 transition-colors"
              />
            </div>
            <p v-if="loginForm.errors.loginEmail" class="text-xs text-destructive">
              {{ loginForm.errors.loginEmail }}
            </p>
          </div>

          <div class="space-y-2">
            <Label for="loginPassword" class="text-label">密码</Label>
            <div class="relative">
              <SafeIcon name="Lock" :size="16" class="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
              <Input
                id="loginPassword"
                v-model="loginPassword"
                v-bind="loginPasswordProps"
                :type="showPassword ? 'text' : 'password'"
                placeholder="请输入密码"
                class="pl-9 pr-9 bg-muted/30 border-border focus:bg-muted/50 transition-colors"
              />
              <button
                type="button"
                @click="togglePasswordVisibility"
                class="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
              >
                <SafeIcon :name="showPassword ? 'EyeOff' : 'Eye'" :size="16" />
              </button>
            </div>
            <p v-if="loginForm.errors.loginPassword" class="text-xs text-destructive">
              {{ loginForm.errors.loginPassword }}
            </p>

            <div class="flex items-center justify-between mt-2">
              <div class="flex items-center space-x-2">
                <Checkbox id="rememberMe" v-model:checked="rememberMe" />
                <Label for="rememberMe" class="text-xs text-muted-foreground font-normal cursor-pointer select-none">记住我</Label>
              </div>
              <button
                type="button"
                @click="handleForgotPassword"
                class="text-xs text-primary hover:text-primary-hover transition-colors"
              >
                忘记密码？
              </button>
            </div>
          </div>

          <Button
            type="submit"
            :disabled="isSubmitting"
            class="w-full h-10 bg-gradient-to-r from-primary to-primary/80 hover:from-primary-hover hover:to-primary text-primary-foreground font-medium transition-all"
          >
            <SafeIcon v-if="isSubmitting" name="Loader2" :size="16" class="mr-2 animate-spin" />
            {{ isSubmitting ? '登录中...' : '登录' }}
          </Button>
        </form>

        <div class="relative my-4">
          <div class="absolute inset-0 flex items-center">
            <div class="w-full border-t border-border/50" />
          </div>
          <div class="relative flex justify-center text-xs">
            <span class="px-2 bg-card text-muted-foreground">或者</span>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <Button type="button" variant="outline" class="h-10 border-border/50 hover:bg-muted/50 transition-colors">
            <SafeIcon name="Github" :size="16" class="mr-2" />
            GitHub
          </Button>
          <Button type="button" variant="outline" class="h-10 border-border/50 hover:bg-muted/50 transition-colors">
            <SafeIcon name="Gitlab" :size="16" class="mr-2" />
            GitLab
          </Button>
        </div>
      </TabsContent>

      <TabsContent value="register" class="card-padding space-y-4">
        <form @submit="handleRegisterSubmit" class="space-y-4">
          <div class="space-y-2">
            <Label for="registerName" class="text-label">用户名</Label>
            <div class="relative">
              <SafeIcon name="User" :size="16" class="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
              <Input
                id="registerName"
                v-model="registerName"
                v-bind="registerNameProps"
                type="text"
                placeholder="请输入用户名"
                class="pl-9 bg-muted/30 border-border focus:bg-muted/50 transition-colors"
              />
            </div>
            <p v-if="registerForm.errors.registerName" class="text-xs text-destructive">
              {{ registerForm.errors.registerName }}
            </p>
          </div>

          <div class="space-y-2">
            <Label for="registerEmail" class="text-label">邮箱地址</Label>
            <div class="relative">
              <SafeIcon name="Mail" :size="16" class="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
              <Input
                id="registerEmail"
                v-model="registerEmail"
                v-bind="registerEmailProps"
                type="email"
                placeholder="请输入邮箱地址"
                class="pl-9 bg-muted/30 border-border focus:bg-muted/50 transition-colors"
              />
            </div>
            <p v-if="registerForm.errors.registerEmail" class="text-xs text-destructive">
              {{ registerForm.errors.registerEmail }}
            </p>
          </div>

          <div class="space-y-2">
            <Label for="registerPassword" class="text-label">密码</Label>
            <div class="relative">
              <SafeIcon name="Lock" :size="16" class="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
              <Input
                id="registerPassword"
                v-model="registerPassword"
                v-bind="registerPasswordProps"
                :type="showPassword ? 'text' : 'password'"
                placeholder="至少 8 位，且包含大写字母和数字"
                class="pl-9 pr-9 bg-muted/30 border-border focus:bg-muted/50 transition-colors"
              />
              <button
                type="button"
                @click="togglePasswordVisibility"
                class="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
              >
                <SafeIcon :name="showPassword ? 'EyeOff' : 'Eye'" :size="16" />
              </button>
            </div>
            <p v-if="registerForm.errors.registerPassword" class="text-xs text-destructive">
              {{ registerForm.errors.registerPassword }}
            </p>
          </div>

          <div class="space-y-2">
            <Label for="registerConfirm" class="text-label">确认密码</Label>
            <div class="relative">
              <SafeIcon name="Lock" :size="16" class="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
              <Input
                id="registerConfirm"
                v-model="registerConfirm"
                v-bind="registerConfirmProps"
                :type="showConfirmPassword ? 'text' : 'password'"
                placeholder="请再次输入密码"
                class="pl-9 pr-9 bg-muted/30 border-border focus:bg-muted/50 transition-colors"
              />
              <button
                type="button"
                @click="toggleConfirmPasswordVisibility"
                class="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
              >
                <SafeIcon :name="showConfirmPassword ? 'EyeOff' : 'Eye'" :size="16" />
              </button>
            </div>
            <p v-if="registerForm.errors.registerConfirm" class="text-xs text-destructive">
              {{ registerForm.errors.registerConfirm }}
            </p>
          </div>

          <div class="space-y-2">
            <div class="flex items-center space-x-2">
              <Checkbox id="agreeTerms" v-model:checked="agreeTerms" />
              <Label for="agreeTerms" class="text-xs text-muted-foreground font-normal cursor-pointer select-none">
                我已阅读并同意
                <a href="#" class="text-primary hover:text-primary-hover transition-colors" @click.stop>用户协议</a>
                和
                <a href="#" class="text-primary hover:text-primary-hover transition-colors" @click.stop>隐私政策</a>
              </Label>
            </div>
            <p v-if="registerForm.errors.agreeTerms" class="text-xs text-destructive">
              {{ registerForm.errors.agreeTerms }}
            </p>
          </div>

          <Button
            type="submit"
            :disabled="isSubmitting"
            class="w-full h-10 bg-gradient-to-r from-primary to-primary/80 hover:from-primary-hover hover:to-primary text-primary-foreground font-medium transition-all"
          >
            <SafeIcon v-if="isSubmitting" name="Loader2" :size="16" class="mr-2 animate-spin" />
            {{ isSubmitting ? '注册中...' : '注册' }}
          </Button>
        </form>
      </TabsContent>
    </Tabs>
  </div>
</template>

<style scoped>
form {
  animation: slideUp 0.3s ease-out;
}

@keyframes slideUp {
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
