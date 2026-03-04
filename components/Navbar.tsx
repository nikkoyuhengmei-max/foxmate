'use client'

import Link from 'next/link'
import { useState } from 'react'
import { Menu, X } from 'lucide-react'
import { config } from '@/lib/config'

export default function Navbar() {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-white shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          <Link href="/" className="flex items-center space-x-2">
            <span className="text-3xl">🦊</span>
            <span className="text-xl font-bold gradient-text font-display">FoxMate</span>
          </Link>

          <div className="hidden md:flex items-center space-x-8">
            <Link href="/features" className="text-gray-700 hover:text-primary-500 transition-colors font-medium">
              Features
            </Link>
            <Link href="/download" className="text-gray-700 hover:text-primary-500 transition-colors font-medium">
              Download
            </Link>
            <Link href="/about" className="text-gray-700 hover:text-primary-500 transition-colors font-medium">
              About
            </Link>
            <a href={config.download.windows} className="btn-primary">
              Download Now
            </a>
          </div>

          <div className="md:hidden">
            <button
              onClick={() => setIsOpen(!isOpen)}
              className="text-gray-700 hover:text-primary-500 transition-colors"
            >
              {isOpen ? <X size={24} /> : <Menu size={24} />}
            </button>
          </div>
        </div>

        {isOpen && (
          <div className="md:hidden py-4 border-t border-gray-100">
            <div className="flex flex-col space-y-4">
              <Link href="/features" className="text-gray-700 hover:text-primary-500 transition-colors font-medium">
                Features
              </Link>
              <Link href="/download" className="text-gray-700 hover:text-primary-500 transition-colors font-medium">
                Download
              </Link>
              <Link href="/about" className="text-gray-700 hover:text-primary-500 transition-colors font-medium">
                About
              </Link>
              <a href={config.download.windows} className="btn-primary text-center">
                Download Now
              </a>
            </div>
          </div>
        )}
      </div>
    </nav>
  )
}
