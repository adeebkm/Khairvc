'use client'

import Image from 'next/image'
import Link from 'next/link'

const footerLinks = {
  Product: [
    { href: '#agents', label: 'Agents' },
    { href: '#security', label: 'Security' },
    { href: '#pricing', label: 'Pricing' },
  ],
  Agents: [
    { href: '#email-replier', label: 'Email Replier' },
    { href: '#portfolio-manager', label: 'Portfolio Manager' },
    { href: '#dealflow-evaluator', label: 'Dealflow Evaluator' },
    { href: '#compliance', label: 'Compliance & Reporting' },
  ],
  Company: [
    { href: '#about', label: 'About' },
    { href: '#blog', label: 'Blog' },
    { href: '#careers', label: 'Careers' },
    { href: '#contact', label: 'Contact' },
  ],
  Legal: [
    { href: '#privacy', label: 'Privacy Policy' },
    { href: '#terms', label: 'Terms of Service' },
    { href: '#cookies', label: 'Cookie Policy' },
  ],
  Security: [
    { href: '#compliance', label: 'Compliance' },
    { href: '#security', label: 'Security' },
    { href: '#soc2', label: 'SOC2' },
  ],
}

export default function Footer() {
  return (
    <footer className="border-t border-line bg-background">
      <div className="container mx-auto px-6 lg:px-8 py-16">
        <div className="grid grid-cols-2 md:grid-cols-6 gap-8 md:gap-12">
          {/* Logo and Brand */}
          <div className="col-span-2 md:col-span-1">
            <Link href="/" className="flex items-center space-x-3 mb-6">
              <Image
                src="/logo.png"
                alt="Khair Capital"
                width={40}
                height={40}
                className="w-10 h-10"
              />
              <span className="text-xl font-semibold text-text-primary">
                Khair Capital
              </span>
            </Link>
            <p className="text-sm text-text-secondary">
              AI agents built for venture capitalists
            </p>
          </div>

          {/* Footer Links */}
          {Object.entries(footerLinks).map(([category, links]) => (
            <div key={category}>
              <h3 className="text-sm font-semibold text-text-primary mb-4">
                {category}
              </h3>
              <ul className="space-y-3">
                {links.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className="text-sm text-text-secondary hover:text-text-primary transition-colors duration-200"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Bottom Bar */}
        <div className="mt-12 pt-8 border-t border-line flex flex-col md:flex-row justify-between items-center gap-4">
          <p className="text-sm text-text-secondary">
            © {new Date().getFullYear()} Khair Capital. All rights reserved.
          </p>
          <div className="flex items-center gap-6">
            <Link
              href="#privacy"
              className="text-sm text-text-secondary hover:text-text-primary transition-colors duration-200"
            >
              Privacy Policy
            </Link>
            <Link
              href="#terms"
              className="text-sm text-text-secondary hover:text-text-primary transition-colors duration-200"
            >
              Terms of Service
            </Link>
          </div>
        </div>
      </div>
    </footer>
  )
}

