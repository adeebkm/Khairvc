'use client'

import { motion } from 'framer-motion'
import { ArrowRight } from 'lucide-react'

export default function Hero() {
  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.2,
        delayChildren: 0.3,
      },
    },
  }

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: {
        duration: 0.6,
        ease: 'easeOut',
      },
    },
  }

  const trustMetrics = [
    { value: '10x', label: 'faster response time' },
    { value: '99.9%', label: 'uptime' },
    { value: '500+', label: 'VCs trust us' },
    { value: '100%', label: 'data privacy' },
  ]

  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden pt-20">
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-background via-background to-[#0F1419] opacity-100" />
        <div className="absolute inset-0 opacity-20">
          <svg className="w-full h-full" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <pattern
                id="grid"
                width="60"
                height="60"
                patternUnits="userSpaceOnUse"
              >
                <path
                  d="M 60 0 L 0 0 0 60"
                  fill="none"
                  stroke="rgba(124, 169, 255, 0.1)"
                  strokeWidth="1"
                />
              </pattern>
            </defs>
            <rect width="100%" height="100%" fill="url(#grid)" />
          </svg>
        </div>
        <motion.div
          className="absolute inset-0"
          initial={{ opacity: 0 }}
          animate={{ opacity: 0.3 }}
          transition={{ duration: 2 }}
        >
          <svg className="w-full h-full" viewBox="0 0 1200 800">
            <motion.path
              d="M0,400 Q300,200 600,400 T1200,400"
              fill="none"
              stroke="url(#gradient1)"
              strokeWidth="2"
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 3, repeat: Infinity, repeatType: 'reverse' }}
            />
            <motion.path
              d="M0,500 Q300,300 600,500 T1200,500"
              fill="none"
              stroke="url(#gradient2)"
              strokeWidth="2"
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 4, repeat: Infinity, repeatType: 'reverse', delay: 0.5 }}
            />
            <defs>
              <linearGradient id="gradient1" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#7CA9FF" stopOpacity="0" />
                <stop offset="50%" stopColor="#7CA9FF" stopOpacity="0.5" />
                <stop offset="100%" stopColor="#7CA9FF" stopOpacity="0" />
              </linearGradient>
              <linearGradient id="gradient2" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#9B8CFF" stopOpacity="0" />
                <stop offset="50%" stopColor="#9B8CFF" stopOpacity="0.5" />
                <stop offset="100%" stopColor="#9B8CFF" stopOpacity="0" />
              </linearGradient>
            </defs>
          </svg>
        </motion.div>
      </div>
      <motion.div
        className="container mx-auto px-6 lg:px-8 relative z-10"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        <div className="max-w-4xl mx-auto text-center">
          <motion.h1
            variants={itemVariants}
            className="text-5xl md:text-6xl lg:text-7xl font-bold mb-6 leading-tight"
          >
            <span className="text-text-primary">AI Agents Built for</span>
            <br />
            <span className="text-gradient">Venture Capitalists</span>
          </motion.h1>
          <motion.p
            variants={itemVariants}
            className="text-xl md:text-2xl text-text-secondary mb-12 max-w-2xl mx-auto leading-relaxed"
          >
            Automate dealflow, portfolio tracking, compliance, and investor
            reporting with bank-grade security.
          </motion.p>
          <motion.div
            variants={itemVariants}
            className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16"
          >
            <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
              <a
                href="#demo"
                className="inline-flex items-center gap-2 px-8 py-4 bg-primary text-background rounded-lg font-semibold text-base hover:opacity-90 transition-opacity duration-200"
              >
                Request Demo
                <ArrowRight className="w-5 h-5" />
              </a>
            </motion.div>
            <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
              <a
                href="#pricing"
                className="inline-flex items-center gap-2 px-8 py-4 glass text-text-primary rounded-lg font-semibold text-base hover:bg-opacity-10 transition-all duration-200 border border-line"
              >
                View Pricing
              </a>
            </motion.div>
          </motion.div>
          <motion.div
            variants={itemVariants}
            className="grid grid-cols-2 md:grid-cols-4 gap-6 md:gap-8"
          >
            {trustMetrics.map((metric, index) => (
              <motion.div
                key={index}
                className="glass rounded-xl p-6 border border-line"
                whileHover={{ scale: 1.05, y: -5 }}
                transition={{ duration: 0.2 }}
              >
                <div className="text-3xl md:text-4xl font-bold text-primary mb-2">
                  {metric.value}
                </div>
                <div className="text-sm text-text-secondary">
                  {metric.label}
                </div>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </motion.div>
    </section>
  )
}
