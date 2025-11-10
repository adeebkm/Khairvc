import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Khair Capital | AI Agents Built for Venture Capitalists',
  description:
    'Automate dealflow, portfolio tracking, compliance, and investor reporting with bank-grade security. AI agents designed for VC firms.',
  keywords: [
    'venture capital',
    'AI agents',
    'dealflow automation',
    'portfolio management',
    'VC compliance',
    'investor reporting',
  ],
  authors: [{ name: 'Khair Capital' }],
  openGraph: {
    title: 'Khair Capital | AI Agents Built for Venture Capitalists',
    description:
      'Automate dealflow, portfolio tracking, compliance, and investor reporting with bank-grade security.',
    type: 'website',
    locale: 'en_US',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Khair Capital | AI Agents Built for Venture Capitalists',
    description:
      'Automate dealflow, portfolio tracking, compliance, and investor reporting with bank-grade security.',
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
    <html lang="en" className="scroll-smooth">
      <head>
        <link rel="icon" href="/logo.png" type="image/png" />
        <link rel="apple-touch-icon" href="/logo.png" />
      </head>
      <body className={inter.className}>{children}</body>
    </html>
  )
}

