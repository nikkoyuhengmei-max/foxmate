'use client'

import { useState, useEffect } from 'react'

interface FadeCarouselProps {
  images: {
    src: string
    alt: string
  }[]
  autoPlay?: boolean
  interval?: number
  aspectRatio?: string
  maxWidth?: string
}

export default function FadeCarousel({ 
  images, 
  autoPlay = true, 
  interval = 4000, 
  aspectRatio = '3/4',
  maxWidth = 'max-w-md'
}: FadeCarouselProps) {
  const [currentIndex, setCurrentIndex] = useState(0)

  useEffect(() => {
    if (!autoPlay) return
    
    const timer = setInterval(() => {
      setCurrentIndex((prev) => (prev + 1) % images.length)
    }, interval)
    
    return () => clearInterval(timer)
  }, [autoPlay, interval, images.length])

  return (
    <div className={`relative w-full ${maxWidth} mx-auto`} style={{ aspectRatio }}>
      {images.map((image, index) => (
        <div
          key={index}
          className="absolute inset-0 transition-opacity duration-1000 ease-in-out"
          style={{
            opacity: index === currentIndex ? 1 : 0,
            zIndex: index === currentIndex ? 1 : 0
          }}
        >
          <img
            src={image.src}
            alt={image.alt}
            className="w-full h-full object-cover rounded-3xl shadow-2xl"
          />
        </div>
      ))}
    </div>
  )
}
