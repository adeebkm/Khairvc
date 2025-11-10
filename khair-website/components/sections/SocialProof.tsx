'use client'

import { motion } from 'framer-motion'
import { useInView } from 'framer-motion'
import { useRef } from 'react'

const vcFirms = [
  'Sequoia Capital',
  'Andreessen Horowitz',
  'Accel Partners',
  'Bessemer Venture Partners',
  'First Round Capital',
  'Greylock Partners',
]

export default function SocialProof() {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: '-50px' })

  return (
    <section className="py-20 relative">
      <div className="container mx-auto px-6 lg:px-8">
        <motion.div
          ref={ref}
          initial={{ opacity: 0 }}
          animate={isInView ? { opacity: 1 } : { opacity: 0 }}
          transition={{ duration: 0.6 }}
          className="max-w-6xl mx-auto"
        >
          <p className="text-center text-text-secondary mb-12 text-sm font-medium uppercase tracking-wider">
            Trusted by Leading Venture Capital Firms
          </p>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-8 items-center">
            {vcFirms.map((firm, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, y: 20 }}
                animate={
                  isInView
                    ? { opacity: 0.6, y: 0 }
                    : { opacity: 0, y: 20 }
                }
                transition={{ delay: index * 0.1 }}
                className="text-center"
                whileHover={{ opacity: 1 }}
              >
                <div className="text-text-secondary text-sm font-medium">
                  {firm}
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  )
}
