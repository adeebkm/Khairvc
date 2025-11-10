'use client'

import { motion } from 'framer-motion'
import { useInView } from 'framer-motion'
import { useRef } from 'react'
import { Link, Settings, CheckCircle } from 'lucide-react'

const steps = [
  {
    number: '01',
    icon: <Link className="w-8 h-8" />,
    title: 'Connect Your Tools',
    description:
      'Connect inbox, CRM, calendar, data room, and other essential VC tools',
  },
  {
    number: '02',
    icon: <Settings className="w-8 h-8" />,
    title: 'Configure Agents',
    description:
      "Set up AI agents and permissions tailored to your fund's workflow",
  },
  {
    number: '03',
    icon: <CheckCircle className="w-8 h-8" />,
    title: 'Deploy at Scale',
    description:
      'Review outputs, fine-tune, and deploy agents across your operations',
  },
]

export default function HowItWorks() {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: '-100px' })

  return (
    <section className="py-32 relative">
      <div className="container mx-auto px-6 lg:px-8">
        <motion.div
          ref={ref}
          initial={{ opacity: 0, y: 30 }}
          animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 30 }}
          transition={{ duration: 0.6 }}
          className="max-w-6xl mx-auto"
        >
          {/* Section Header */}
          <div className="text-center mb-20">
            <h2 className="text-4xl md:text-5xl font-bold mb-4 text-text-primary">
              How It Works
            </h2>
            <p className="text-xl text-text-secondary max-w-2xl mx-auto">
              Get started in three simple steps
            </p>
          </div>

          {/* Steps */}
          <div className="relative">
            {/* Connecting Line (Desktop) */}
            <div className="hidden md:block absolute top-24 left-0 right-0 h-0.5 bg-gradient-to-r from-primary via-accent to-primary opacity-20" />

            <div className="grid md:grid-cols-3 gap-8 md:gap-12 relative">
              {steps.map((step, index) => (
                <motion.div
                  key={index}
                  initial={{ opacity: 0, y: 30 }}
                  animate={
                    isInView
                      ? { opacity: 1, y: 0 }
                      : { opacity: 0, y: 30 }
                  }
                  transition={{ delay: index * 0.2 }}
                  className="relative"
                >
                  {/* Step Number */}
                  <div className="absolute -top-4 left-0 text-6xl font-bold text-primary/10">
                    {step.number}
                  </div>

                  {/* Step Card */}
                  <div className="glass rounded-2xl p-8 border border-line relative z-10">
                    <div className="w-16 h-16 rounded-xl bg-primary/10 flex items-center justify-center text-primary mb-6">
                      {step.icon}
                    </div>
                    <h3 className="text-2xl font-semibold text-text-primary mb-3">
                      {step.title}
                    </h3>
                    <p className="text-text-secondary leading-relaxed">
                      {step.description}
                    </p>
                  </div>

                  {/* Connector (Mobile) */}
                  {index < steps.length - 1 && (
                    <div className="md:hidden flex justify-center my-8">
                      <div className="w-0.5 h-12 bg-gradient-to-b from-primary to-accent opacity-30" />
                    </div>
                  )}
                </motion.div>
              ))}
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  )
}

