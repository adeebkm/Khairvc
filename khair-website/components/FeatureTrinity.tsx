'use client'

import { motion } from 'framer-motion'
import { useInView } from 'framer-motion'
import { useRef } from 'react'

const fadeInVariants = {
  hidden: { opacity: 0, y: 40 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, ease: 'easeOut' },
  },
}

function FeatureSection({
  headline,
  copy,
  visual,
  reverse = false,
}: {
  headline: string
  copy: string
  visual: React.ReactNode
  reverse?: boolean
}) {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: '-100px' })

  return (
    <motion.div
      ref={ref}
      initial="hidden"
      animate={isInView ? 'visible' : 'hidden'}
      variants={fadeInVariants}
      className={`grid lg:grid-cols-2 gap-12 lg:gap-16 items-center ${
        reverse ? 'lg:flex-row-reverse' : ''
      }`}
    >
      <div className={`space-y-6 ${reverse ? 'lg:order-2' : ''}`}>
        <h2 className="text-3xl md:text-4xl font-bold tracking-tight">
          {headline}
        </h2>
        <p className="text-lg text-text-secondary leading-relaxed max-w-lg">
          {copy}
        </p>
      </div>
      <div className={reverse ? 'lg:order-1' : ''}>{visual}</div>
    </motion.div>
  )
}

// Animated Email List Visual
function TriageVisual() {
  const emails = [
    { tag: 'Seed', category: 'Fintech', urgent: true, subject: 'Intro: AI Payments Startup' },
    { tag: 'Series A', category: 'SaaS', urgent: false, subject: 'Follow-up: Enterprise CRM' },
    { tag: 'Pre-seed', category: 'Climate', urgent: false, subject: 'Deck: Carbon Credits Platform' },
  ]

  return (
    <div className="card p-6 space-y-3">
      {emails.map((email, index) => (
        <motion.div
          key={index}
          initial={{ opacity: 0, x: -30 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true }}
          transition={{ delay: index * 0.2, duration: 0.5 }}
          className="flex items-center gap-3 p-3 rounded-lg bg-surface-hover/50 hover:bg-surface-hover transition-colors"
        >
          <div className="flex-1">
            <p className="text-sm font-medium">{email.subject}</p>
          </div>
          <div className="flex gap-2">
            <span className="px-2 py-0.5 text-[10px] rounded bg-primary/10 text-primary border border-primary/20">
              {email.tag}
            </span>
            <span className="px-2 py-0.5 text-[10px] rounded bg-surface text-text-secondary">
              {email.category}
            </span>
            {email.urgent && (
              <span className="px-2 py-0.5 text-[10px] rounded bg-red-500/10 text-red-400 border border-red-500/20">
                Urgent
              </span>
            )}
          </div>
        </motion.div>
      ))}
    </div>
  )
}

// WhatsApp + Email Visual
function WhatsAppVisual() {
  return (
    <div className="grid grid-cols-2 gap-4">
      {/* iPhone WhatsApp Chat */}
      <div className="card p-4 space-y-3">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-6 h-6 rounded-full bg-[#25D366] flex items-center justify-center">
            <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 24 24">
              <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
            </svg>
          </div>
          <span className="text-xs font-medium">WhatsApp</span>
        </div>
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.3 }}
          className="bg-[#25D366]/10 rounded-lg p-3"
        >
          <p className="text-xs text-text-secondary">You:</p>
          <p className="text-sm mt-1">&ldquo;Tell Sam we pass&rdquo;</p>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.6 }}
          className="bg-surface-hover rounded-lg p-3"
        >
          <p className="text-xs text-text-secondary">Khair:</p>
          <p className="text-sm mt-1">✓ Drafting polite rejection...</p>
        </motion.div>
      </div>

      {/* Desktop Email Draft */}
      <div className="card p-4 space-y-3">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-6 h-6 rounded-full bg-surface-hover flex items-center justify-center text-sm">
            📧
          </div>
          <span className="text-xs font-medium">Email Draft</span>
        </div>
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ delay: 0.9 }}
          className="space-y-2"
        >
          <p className="text-xs text-text-secondary">To: sam@startup.com</p>
          <p className="text-xs text-text-secondary">Subject: Re: Intro Request</p>
          <div className="border-t border-surface-hover pt-2 mt-2">
            <p className="text-sm text-text-secondary">
              Hi Sam, thank you for thinking of us. After careful consideration, we&apos;ve decided to pass at this stage...
            </p>
          </div>
        </motion.div>
      </div>
    </div>
  )
}

// Calendar Visual
function SchedulingVisual() {
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
  const slots = ['9am', '10am', '11am', '2pm', '3pm', '4pm']

  return (
    <div className="card p-6">
      <div className="grid grid-cols-6 gap-2 text-xs text-center">
        <div></div>
        {days.map((day) => (
          <div key={day} className="text-text-secondary font-medium py-2">
            {day}
          </div>
        ))}
        {slots.map((slot) => (
          <>
            <div key={`label-${slot}`} className="text-text-secondary py-2 text-right pr-2">
              {slot}
            </div>
            {days.map((day, dayIndex) => {
              const isConfirmed = day === 'Thu' && slot === '2pm'
              return (
                <motion.div
                  key={`${day}-${slot}`}
                  initial={{ scale: 1 }}
                  whileInView={
                    isConfirmed
                      ? {
                          scale: [1, 1.1, 1],
                          boxShadow: [
                            '0 0 0 rgba(0, 229, 255, 0)',
                            '0 0 20px rgba(0, 229, 255, 0.5)',
                            '0 0 20px rgba(0, 229, 255, 0.3)',
                          ],
                        }
                      : {}
                  }
                  viewport={{ once: true }}
                  transition={{ delay: 0.8, duration: 0.5 }}
                  className={`py-2 rounded ${
                    isConfirmed
                      ? 'bg-secondary/20 text-secondary border border-secondary/40'
                      : dayIndex % 3 === 0
                      ? 'bg-surface-hover/30'
                      : 'bg-surface/50'
                  }`}
                >
                  {isConfirmed && '✓'}
                </motion.div>
              )
            })}
          </>
        ))}
      </div>
    </div>
  )
}

export default function FeatureTrinity() {
  return (
    <section className="py-24 px-6">
      <div className="max-w-7xl mx-auto space-y-32">
        {/* Feature A: Triage */}
        <FeatureSection
          headline="Deal Flow, Detected."
          copy="Separates warm intros from cold blasts. Our AI knows your thesis, stage, and portfolio."
          visual={<TriageVisual />}
        />

        {/* Feature B: WhatsApp */}
        <FeatureSection
          headline="Run Your Fund from WhatsApp."
          copy="Too early? Just text Khair 'Tell Sam we pass.' It drafts the polite rejection instantly."
          visual={<WhatsAppVisual />}
          reverse
        />

        {/* Feature C: Scheduling */}
        <FeatureSection
          headline="No More Calendar Ping-Pong."
          copy="Khair negotiates slots, protects focus time, and handles timezone math."
          visual={<SchedulingVisual />}
        />
      </div>
    </section>
  )
}

