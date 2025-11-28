'use client'

import Image from 'next/image'
import { motion } from 'framer-motion'

export default function Navbar() {
  return (
    <motion.nav
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5, ease: 'easeOut' }}
      className="fixed top-0 left-0 right-0 z-50 glass-navbar"
    >
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center">
          <Image
            src="/logo.png"
            alt="Khair"
            width={36}
            height={36}
            className="brightness-0 invert"
          />
        </div>

        {/* Login Button */}
        <button className="px-5 py-2 text-sm font-medium text-white/80 hover:text-white transition-colors duration-200 hover:bg-surface-hover rounded-lg">
          Log In
        </button>
      </div>
    </motion.nav>
  )
}

