'use client'

import { LanguageProvider } from '@/components/LanguageContext'

export default function ClientLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <LanguageProvider>{children}</LanguageProvider>
}
