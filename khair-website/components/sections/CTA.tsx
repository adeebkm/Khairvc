'use client'

import { motion } from 'framer-motion'
import { useInView } from 'framer-motion'
import { useRef } from 'react'
import { ArrowRight, Phone } from 'lucide-react'

export default function CTA() {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: '-100px' })

  return (
    <section className="py-32 relative overflow-hidden">
      {/* Background Gradient */}
      <div className="absolute inset-0 bg-gradient-to-br from-[#0F1A2A] via-background to-[#0A0E13]" />
      
      {/* Spotlight Effect */}
      <div 
        className="absolute inset-0 opacity-50"
        style={{
          background: 'radial-gradient(circle at center, rgba(124, 169, 255, 0.1) 0%, transparent 70%)'
        }}
      />
      
      <div className="container mx-auto px-6 lg:px-8 relative z-10">
        <motion.div
          ref={ref}
          initial={{ opacity: 0, y: 30 }}
          animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 30 }}
          transition={{ duration: 0.6 }}
          className="max-w-4xl mx-auto text-center"
        >
          <h2 className="text-4xl md:text-5xl lg:text-6xl font-bold mb-6 text-text-primary">
            Ready to transform your
            <br />
            <span className="text-gradient">VC operations?</span>
          </h2>
          <p className="text-xl text-text-secondary mb-12 max-w-2xl mx-auto">
            See how Khair Capital can automate your dealflow, portfolio
            management, and compliance workflows
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <motion.div
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <a
                href="#demo"
                className="inline-flex items-center gap-2 px-8 py-4 bg-primary text-background rounded-lg font-semibold text-base hover:opacity-90 transition-opacity duration-200"
              >
                Schedule a Demo
                <ArrowRight className="w-5 h-5" />
              </a>
            </motion.div>
            <motion.div
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <a
                href="#sales"
                className="inline-flex items-center gap-2 px-8 py-4 glass text-text-primary rounded-lg font-semibold text-base hover:bg-opacity-10 transition-all duration-200 border border-line"
              >
                <Phone className="w-5 h-5" />
                Talk to Sales
              </a>
            </motion.div>
          </div>
        </motion.div>
      </div>
    </section>
  )
}

