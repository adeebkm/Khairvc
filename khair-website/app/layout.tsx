import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'

const inter = Inter({ 
  subsets: ['latin'],
  variable: '--font-inter',
})

export const metadata: Metadata = {
  title: 'Khair | AI Inbox for VCs',
  description:
    'Your inbox is a crime scene. Khair triages deal flow, runs on WhatsApp, and books meetings automatically. Designed for partners who value their time at $1,000/hour.',
  keywords: [
    'venture capital',
    'AI inbox',
    'dealflow automation',
    'VC productivity',
    'email triage',
    'WhatsApp for VCs',
  ],
  authors: [{ name: 'Khair' }],
  openGraph: {
    title: 'Khair | AI Inbox for VCs',
    description:
      'Your inbox is a crime scene. Khair triages deal flow, runs on WhatsApp, and books meetings automatically.',
    type: 'website',
    locale: 'en_US',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Khair | AI Inbox for VCs',
    description:
      'Your inbox is a crime scene. Khair triages deal flow, runs on WhatsApp, and books meetings automatically.',
  },
  robots: {
    index: true,
    follow: true,
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark scroll-smooth">
      <head>
        <link rel="icon" href="/logo.png" type="image/png" />
        <link rel="apple-touch-icon" href="/logo.png" />
      </head>
      <body className={`${inter.variable} font-sans`}>{children}</body>
    </html>
  )
}
