'use client'

import { motion } from 'framer-motion'

const fadeUpVariants = {
  hidden: { opacity: 0, y: 30 },
  visible: (delay: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, ease: 'easeOut', delay },
  }),
}

// Floating card component for 3D visual stack
function FloatingCard({
  children,
  className,
  delay = 0,
  yOffset = 0,
}: {
  children: React.ReactNode
  className?: string
  delay?: number
  yOffset?: number
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 40 }}
      animate={{
        opacity: 1,
        y: [yOffset, yOffset - 15, yOffset],
      }}
      transition={{
        opacity: { duration: 0.8, delay },
        y: {
          duration: 5,
          repeat: Infinity,
          repeatType: 'reverse',
          ease: 'easeInOut',
          delay: delay + 0.5,
        },
      }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

export default function Hero() {
  return (
    <section className="relative min-h-screen pt-24 pb-16 overflow-hidden">
      {/* Background gradient */}
      <div className="absolute inset-0 bg-gradient-to-b from-primary/5 via-transparent to-transparent pointer-events-none" />
      
      <div className="max-w-7xl mx-auto px-6 grid lg:grid-cols-2 gap-12 lg:gap-8 items-center min-h-[90vh]">
        {/* Left Column - Text Content */}
        <div className="space-y-8">
          {/* Badge */}
          <motion.div
            variants={fadeUpVariants}
            initial="hidden"
            animate="visible"
            custom={0}
          >
            <span className="inline-flex items-center px-4 py-1.5 rounded-full text-sm font-medium bg-primary/15 text-primary border border-primary/20">
              Built for VCs by VCs
            </span>
          </motion.div>

          {/* Headline */}
          <motion.h1
            variants={fadeUpVariants}
            initial="hidden"
            animate="visible"
            custom={0.1}
            className="text-5xl md:text-6xl lg:text-7xl font-bold tracking-tight leading-[1.1]"
          >
            Your inbox is a{' '}
            <span className="text-gradient">crime scene.</span>
          </motion.h1>

          {/* Subhead */}
          <motion.p
            variants={fadeUpVariants}
            initial="hidden"
            animate="visible"
            custom={0.2}
            className="text-xl text-text-secondary max-w-xl leading-relaxed"
          >
            We fixed it. Khair triages deal flow, runs on WhatsApp, and books meetings automatically.
          </motion.p>

          {/* Value Anchor */}
          <motion.p
            variants={fadeUpVariants}
            initial="hidden"
            animate="visible"
            custom={0.25}
            className="text-lg text-text-secondary/80 italic"
          >
            Designed for partners who value their time at $1,000/hour.
          </motion.p>

          {/* CTAs */}
          <motion.div
            variants={fadeUpVariants}
            initial="hidden"
            animate="visible"
            custom={0.3}
            className="flex flex-wrap gap-4"
          >
            <button className="btn-primary glow-primary">
              Request Access
            </button>
            <button className="btn-ghost">
              Watch Workflow
            </button>
          </motion.div>

          {/* Social Proof */}
          <motion.div
            variants={fadeUpVariants}
            initial="hidden"
            animate="visible"
            custom={0.4}
            className="flex items-center gap-2 text-sm text-text-secondary"
          >
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-success"></span>
            </span>
            <span>53 funds on the private list</span>
          </motion.div>
        </div>

        {/* Right Column - Email Client Visual */}
        <motion.div 
          initial={{ opacity: 0, x: 40 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.8, delay: 0.3 }}
          className="relative lg:pl-8"
        >
          <div className="relative">
            {/* Main Email Client */}
            <div className="card p-0 overflow-hidden shadow-2xl transform rotate-1 hover:rotate-0 transition-transform duration-500">
              {/* Header */}
              <div className="bg-surface px-4 py-3 border-b border-surface-hover flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-lg font-semibold">Khair</span>
                  <span className="px-2.5 py-1 text-xs font-medium rounded bg-primary/20 text-primary border border-primary/30">
                    [Deal Flow]
                  </span>
                </div>
                <div className="flex items-center gap-2 text-text-secondary text-xs">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                  <span>Search emails...</span>
                </div>
              </div>

              {/* Email List */}
              <div className="divide-y divide-surface-hover">
                {[
                  { sender: 'Founders Only: Exelaine AI', subject: 'Does Exelaine Fourteen, This outlin...', tag: 'Deal Flow', tagColor: 'bg-primary/20 text-primary' },
                  { sender: 'Nation Team', subject: 'Nation Team not applied! How to eliminate arrival in Head...', tag: 'Deal Flow', tagColor: 'bg-primary/20 text-primary' },
                  { sender: 'Re: No Subject', subject: 'Ni Mohammed. Thanks for flagging and...', tag: 'Spam', tagColor: 'bg-red-500/20 text-red-400' },
                  { sender: 'Re: Fual: Institutional', subject: 'Franchise inquiry Mi Rene, Thank for resolving on and chatting...', tag: 'Deal Flow', tagColor: 'bg-primary/20 text-primary' },
                  { sender: 'Re: Fual: Institutional', subject: 'Tumehe inquiry Ni Celka Naww for keeping us in on the Leg...', tag: 'General', tagColor: 'bg-emerald-500/20 text-emerald-400' },
                  { sender: 'Re: Fual: You\'ve invited', subject: 'To tranquil-creative Ni Gade Pere, you\'ve been invited on the Rang...', tag: 'Networking', tagColor: 'bg-amber-500/20 text-amber-400' },
                ].map((email, index) => (
                  <motion.div
                    key={index}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.5 + index * 0.1 }}
                    className="px-4 py-2.5 flex items-center gap-3 hover:bg-surface-hover/50 cursor-pointer text-xs"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-white truncate">{email.sender}</p>
                      <p className="text-text-secondary truncate">{email.subject}</p>
                    </div>
                    <span className={`px-2 py-0.5 text-[10px] font-medium rounded shrink-0 ${email.tagColor}`}>
                      {email.tag}
                    </span>
                  </motion.div>
                ))}
              </div>
            </div>

            {/* WhatsApp Overlay */}
            <FloatingCard
              delay={0.8}
              yOffset={0}
              className="absolute -left-4 top-20 w-[220px] z-10"
            >
              <div className="card p-3 shadow-xl border-[#25D366]/30">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-6 h-6 rounded-full bg-[#25D366] flex items-center justify-center">
                    <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
                    </svg>
                  </div>
                  <span className="text-xs font-medium">Reply to Sam:</span>
                </div>
                <p className="text-sm text-white">&ldquo;Pass, too early.&rdquo;</p>
              </div>
            </FloatingCard>

            {/* Calendar Overlay */}
            <FloatingCard
              delay={1}
              yOffset={0}
              className="absolute -right-2 bottom-4 w-[200px] z-10"
            >
              <div className="card p-3 shadow-xl border-secondary/30 bg-surface/90">
                <div className="flex items-center gap-2 mb-2">
                  <svg className="w-4 h-4 text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                  <span className="text-xs font-medium text-secondary">Meeting Confirmed</span>
                </div>
                <p className="text-[10px] text-text-secondary">Tuesday 5:30 AM</p>
              </div>
            </FloatingCard>
          </div>
        </motion.div>
      </div>
    </section>
  )
}

