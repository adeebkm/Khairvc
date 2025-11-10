'use client'

import { motion } from 'framer-motion'
import { useInView } from 'framer-motion'
import { useRef } from 'react'
import { Mail, TrendingUp, FileSearch, Shield } from 'lucide-react'

interface AgentCard {
  icon: React.ReactNode
  title: string
  description: string
  features: string[]
}

const agents: AgentCard[] = [
  {
    icon: <Mail className="w-8 h-8" />,
    title: 'Email Replier and Follow-up',
    description: 'Intelligent email management for VC operations',
    features: [
      'Reduce turnaround up to 80 percent',
      'Intelligent prioritization',
      'Auto-draft personalized responses',
    ],
  },
  {
    icon: <TrendingUp className="w-8 h-8" />,
    title: 'Portfolio Manager',
    description: 'Real-time insights into your portfolio health',
    features: [
      'Real-time portfolio health',
      'Automated metrics and reports',
      'KPI alerts',
    ],
  },
  {
    icon: <FileSearch className="w-8 h-8" />,
    title: 'Dealflow Evaluator',
    description: 'AI-powered deal analysis and due diligence',
    features: [
      'Market comparison',
      'Risk scoring',
      'Due diligence automation',
    ],
  },
  {
    icon: <Shield className="w-8 h-8" />,
    title: 'Compliance and Reporting',
    description: 'Automated compliance and LP reporting',
    features: [
      'LP reporting',
      'Regulatory compliance',
      'Complete audit trail',
    ],
  },
]

export default function Agents() {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: '-100px' })

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1,
      },
    },
  }

  const cardVariants = {
    hidden: { opacity: 0, y: 30 },
    visible: {
      opacity: 1,
      y: 0,
      transition: {
        duration: 0.5,
        ease: 'easeOut',
      },
    },
  }

  return (
    <section id="agents" className="py-32 relative">
      <div className="container mx-auto px-6 lg:px-8">
        <motion.div
          ref={ref}
          variants={containerVariants}
          initial="hidden"
          animate={isInView ? 'visible' : 'hidden'}
          className="max-w-6xl mx-auto"
        >
          {/* Section Header */}
          <motion.div
            variants={cardVariants}
            className="text-center mb-16"
          >
            <h2 className="text-4xl md:text-5xl font-bold mb-4 text-text-primary">
              AI Agents for Every VC Operation
            </h2>
            <p className="text-xl text-text-secondary max-w-2xl mx-auto">
              Four powerful agents designed to automate and optimize your
              venture capital workflow
            </p>
          </motion.div>

          {/* Agents Grid */}
          <div className="grid md:grid-cols-2 gap-6">
            {agents.map((agent, index) => (
              <motion.div
                key={index}
                variants={cardVariants}
                className="glass rounded-2xl p-8 border border-line group cursor-pointer"
                whileHover={{
                  scale: 1.02,
                  y: -8,
                  boxShadow: '0 20px 40px rgba(124, 169, 255, 0.1)',
                }}
                transition={{ duration: 0.3 }}
              >
                <div className="flex items-start gap-6">
                  <div className="flex-shrink-0 w-16 h-16 rounded-xl bg-primary/10 flex items-center justify-center text-primary group-hover:bg-primary/20 transition-colors duration-300">
                    {agent.icon}
                  </div>
                  <div className="flex-1">
                    <h3 className="text-2xl font-semibold text-text-primary mb-3">
                      {agent.title}
                    </h3>
                    <p className="text-text-secondary mb-4">
                      {agent.description}
                    </p>
                    <ul className="space-y-2">
                      {agent.features.map((feature, featureIndex) => (
                        <li
                          key={featureIndex}
                          className="flex items-center gap-2 text-sm text-text-secondary"
                        >
                          <span className="w-1.5 h-1.5 rounded-full bg-success" />
                          {feature}
                        </li>
                      ))}
                    </ul>
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

