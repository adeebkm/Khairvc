import Navbar from '@/components/Navbar'
import Hero from '@/components/Hero'
import FeatureTrinity from '@/components/FeatureTrinity'
import TrustStrip from '@/components/TrustStrip'
import Footer from '@/components/Footer'

export default function Home() {
  return (
    <main className="relative">
      <Navbar />
      <Hero />
      <FeatureTrinity />
      <TrustStrip />
      <Footer />
    </main>
  )
}
