import Header from '@/components/Header'
import Hero from '@/components/sections/Hero'
import Agents from '@/components/sections/Agents'
import Security from '@/components/sections/Security'
import SocialProof from '@/components/sections/SocialProof'
import HowItWorks from '@/components/sections/HowItWorks'
import CTA from '@/components/sections/CTA'
import Footer from '@/components/Footer'

export default function Home() {
  return (
    <main className="min-h-screen">
      <Header />
      <Hero />
      <Agents />
      <Security />
      <SocialProof />
      <HowItWorks />
      <CTA />
      <Footer />
    </main>
  )
}
