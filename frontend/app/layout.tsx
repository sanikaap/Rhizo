import type { Metadata } from 'next'
import { Inter, JetBrains_Mono, Outfit } from 'next/font/google'
import { AppShell } from '@/components/layout/app-shell'
import { Providers } from './providers'
import './globals.css'

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' })
const display = Outfit({ subsets: ['latin'], variable: '--font-display-face' })
const mono = JetBrains_Mono({ subsets: ['latin'], variable: '--font-mono-face' })

export const metadata: Metadata = {
  title: { default: 'Rhizo', template: '%s · Rhizo' },
  description: 'Change-impact and incident agent that reasons over a FalkorDB dependency graph.',
  applicationName: 'Rhizo',
  icons: {
    icon: [
      { url: '/favicon.ico', sizes: '16x16 32x32 48x48' },
      { url: '/icon.svg', type: 'image/svg+xml' },
      { url: '/icon-light-32x32.png', sizes: '32x32', type: 'image/png' },
    ],
    shortcut: '/favicon.ico',
    apple: { url: '/apple-icon.png', sizes: '180x180', type: 'image/png' },
  },
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable} ${display.variable}`}>
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  )
}
