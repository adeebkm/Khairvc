'use client'

import { motion } from 'framer-motion'
import { useInView } from 'framer-motion'
import { useRef } from 'react'
import { Lock, Shield, CheckCircle2 } from 'lucide-react'

const certifications = [
  { name: 'SOC2 Type II', icon: <Shield className="w-6 h-6" /> },
  { name: 'ISO 27001', icon: <CheckCircle2 className="w-6 h-6" /> },
  { name: 'GDPR Compliance', icon: <Lock className="w-6 h-6" /> },
  { name: '256-bit Encryption', icon: <Shield className="w-6 h-6" /> },
  { name: 'SSO + RBAC', icon: <CheckCircle2 className="w-6 h-6" /> },
]

export default function Security() {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: '-100px' })

  return (
    <section id="security" className="py-32 relative">
      <div className="container mx-auto px-6 lg:px-8">
        <motion.div
          ref={ref}
          initial={{ opacity: 0, y: 30 }}
          animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 30 }}
          transition={{ duration: 0.6 }}
          className="max-w-5xl mx-auto text-center"
        >
          {/* Section Header */}
          <div className="mb-16">
            <motion.div
              initial={{ scale: 0 }}
              animate={isInView ? { scale: 1 } : { scale: 0 }}
              transition={{ delay: 0.2, type: 'spring', stiffness: 200 }}
              className="inline-block mb-6"
            >
              <div className="w-20 h-20 rounded-2xl bg-primary/10 flex items-center justify-center text-primary mx-auto">
                <Lock className="w-10 h-10" />
              </div>
            </motion.div>
            <h2 className="text-4xl md:text-5xl font-bold mb-4 text-text-primary">
              Bank-Grade Security
            </h2>
            <p className="text-xl text-text-secondary max-w-2xl mx-auto">
              Your data is protected with enterprise-level security standards
              and compliance certifications
            </p>
          </div>

          {/* Certifications Grid */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-6">
            {certifications.map((cert, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, y: 20 }}
                animate={
                  isInView
                    ? { opacity: 1, y: 0 }
                    : { opacity: 0, y: 20 }
                }
                transition={{ delay: 0.3 + index * 0.1 }}
                className="glass rounded-xl p-6 border border-line"
                whileHover={{ scale: 1.05, y: -5 }}
              >
                <div className="flex flex-col items-center gap-3">
                  <div className="text-primary">{cert.icon}</div>
                  <div className="text-sm font-medium text-text-primary text-center">
                    {cert.name}
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  )
}

