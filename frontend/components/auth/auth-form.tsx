'use client'

import { useQueryClient } from '@tanstack/react-query'
import { Eye, EyeOff, Loader2 } from 'lucide-react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useState } from 'react'
import { AuthApiError, authApi, safeNext } from '@/lib/auth-client'
import { AuthLayout, Field, FormError, inputCls, submitCls } from './auth-layout'

const MIN_PASSWORD = 8
const message = (e: unknown) => (e instanceof AuthApiError ? e.message : 'Something went wrong. Try again.')

function PasswordInput({ value, onChange, show, onToggle, autoComplete, label }: {
  value: string
  onChange: (v: string) => void
  show: boolean
  onToggle?: () => void
  autoComplete: string
  label: string
}) {
  return (
    <div className="relative">
      <input
        type={show ? 'text' : 'password'}
        required
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete={autoComplete}
        aria-label={label}
        className={`${inputCls} pr-10`}
      />
      {onToggle && (
        <button type="button" onClick={onToggle} className="absolute inset-y-0 right-0 grid w-10 place-items-center text-subtle-foreground hover:text-foreground" aria-label={show ? 'Hide password' : 'Show password'}>
          {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
        </button>
      )}
    </div>
  )
}

export function AuthForm({ mode }: { mode: 'login' | 'signup' }) {
  const params = useSearchParams()
  const router = useRouter()
  const qc = useQueryClient()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [show, setShow] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const signup = mode === 'signup'
  const next = params.get('next')
  const carry = next ? `?next=${encodeURIComponent(next)}` : ''

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (signup && password.length < MIN_PASSWORD) return setError(`Password must be at least ${MIN_PASSWORD} characters.`)
    if (signup && password !== confirm) return setError('Passwords do not match.')
    setBusy(true); setError(null)
    try {
      const { user } = signup
        ? await authApi.signup({ email, password, confirmPassword: confirm })
        : await authApi.login({ email, password })
      qc.setQueryData(['me'], user)
      router.replace(safeNext(next))
      router.refresh()
    } catch (err) {
      setError(message(err))
      setBusy(false)
    }
  }

  return (
    <AuthLayout
      title={signup ? 'Create your account' : 'Welcome back'}
      subtitle={signup ? 'Map your dependencies and investigate incidents with evidence.' : 'Sign in to your Rhizo workspace.'}
      footer={signup
        ? <>Already have an account? <Link href={`/login${carry}`} className="font-semibold text-primary hover:underline">Sign in</Link></>
        : <>New to Rhizo? <Link href={`/signup${carry}`} className="font-semibold text-primary hover:underline">Create an account</Link></>}
    >
      <form onSubmit={submit} className="space-y-5" noValidate>
        <Field label="Email">
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" placeholder="you@company.com" className={inputCls} autoFocus />
        </Field>
        <Field label="Password" hint={signup ? `At least ${MIN_PASSWORD} characters.` : undefined}>
          <PasswordInput value={password} onChange={setPassword} show={show} onToggle={() => setShow((s) => !s)} autoComplete={signup ? 'new-password' : 'current-password'} label="Password" />
        </Field>
        {signup && (
          <Field label="Confirm password">
            <PasswordInput value={confirm} onChange={setConfirm} show={show} autoComplete="new-password" label="Confirm password" />
          </Field>
        )}
        <FormError message={error} />
        <button type="submit" disabled={busy} className={submitCls}>
          {busy && <Loader2 className="size-4 animate-spin" />}{signup ? 'Create account' : 'Sign in'}
        </button>
      </form>
    </AuthLayout>
  )
}
