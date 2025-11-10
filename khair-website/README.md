# Khair Capital Website

Production-grade, dark-theme marketing website for Khair Capital - an enterprise AI platform that hosts secure AI agents for Venture Capital firms.

## 🚀 Quick Start

### Prerequisites

- Node.js 18+ and npm/yarn/pnpm
- Modern browser with ES6+ support

### Installation

```bash
# Install dependencies
npm install

# Run development server
npm run dev

# Build for production
npm run build

# Start production server
npm start
```

Open [http://localhost:3000](http://localhost:3000) to view the website.

## 🎨 Design System

### Color Tokens

- **Background**: `#0B0F14`
- **Surface/Cards**: `rgba(255,255,255,0.04)` with backdrop-blur
- **Primary CTA**: `#7CA9FF`
- **Accent**: `#9B8CFF`
- **High Contrast Text**: `#F4F7FA`
- **Secondary Text**: `#A9B2C1`
- **Lines**: `rgba(255,255,255,0.06)`
- **Success**: `#3EE0A1`

### Typography

- **Font**: Inter (via Next.js)
- **Headings**: Bold, high contrast
- **Body**: Regular, secondary color for hierarchy

## 📁 Project Structure

```
khair-website/
├── app/
│   ├── globals.css          # Global styles and Tailwind
│   ├── layout.tsx           # Root layout with metadata
│   └── page.tsx             # Main homepage
├── components/
│   ├── Header.tsx           # Sticky navigation header
│   ├── Footer.tsx            # Footer with links
│   └── sections/
│       ├── Hero.tsx          # Hero section with CTAs
│       ├── Agents.tsx        # 2x2 grid of AI agents
│       ├── Security.tsx      # Security certifications
│       ├── SocialProof.tsx   # VC firm logos
│       ├── HowItWorks.tsx    # Three-step process
│       └── CTA.tsx           # Final call-to-action
├── public/
│   └── logo.png             # Khair Capital logo
└── package.json
```

## ✨ Features

- **Dark Theme**: Ultra-premium dark design with glass morphism
- **Animations**: Framer Motion for smooth micro-interactions
- **Responsive**: Fully responsive (desktop, tablet, mobile)
- **Accessible**: WCAG AA contrast, reduced motion support
- **SEO Optimized**: Complete metadata, OG tags, favicon
- **Performance**: Optimized images, code splitting

## 🛠️ Tech Stack

- **Framework**: Next.js 14 (App Router)
- **Styling**: Tailwind CSS with custom tokens
- **Animations**: Framer Motion
- **Icons**: Lucide React (SVG)
- **TypeScript**: Full type safety
- **Deployment**: Ready for Vercel/Netlify

## 📝 Customization

### Update Logo

Replace `/public/logo.png` with your logo (recommended: 40x40px minimum, PNG format).

### Update VC Firm Logos

Edit `components/sections/SocialProof.tsx` to replace placeholder firm names with actual logo images.

### Modify Colors

Update color tokens in `tailwind.config.ts` to match your brand.

### Add Sections

Create new section components in `components/sections/` and import them in `app/page.tsx`.

## 🚢 Deployment

### Vercel (Recommended)

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
vercel
```

### Netlify

```bash
# Build
npm run build

# Deploy the .next folder
```

### Other Platforms

Build the project and deploy the `.next` folder:

```bash
npm run build
```

## 📄 License

Copyright © 2025 Khair Capital. All rights reserved.

