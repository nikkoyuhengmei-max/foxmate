import Link from 'next/link'
import Navbar from '@/components/Navbar'
import Footer from '@/components/Footer'
import FadeCarousel from '@/components/FadeCarousel'
import ScrollToTop from '@/components/ScrollToTop'
import { 
  Star,
  ChevronRight
} from 'lucide-react'
import type { Metadata } from 'next'
import { config } from '@/lib/config'

export const metadata: Metadata = {
  title: 'FoxMate AI - Your Cute Focus Companion | Stay Focused & Productive',
  description: 'FoxMate AI helps you stay focused with real-time focus tracking, adorable fox reactions, and productivity insights. Boost your productivity today!',
  keywords: 'focus tracker, productivity app, AI companion, fox companion, work efficiency, time management, focus app',
  openGraph: {
    title: 'FoxMate AI - Your Cute Focus Companion',
    description: 'Stay focused and productive with your adorable fox companion. Real-time focus tracking, emotional support, and productivity insights.',
    url: 'https://foxmate.ai',
    siteName: 'FoxMate AI',
    images: [
      {
        url: '/og-image.jpg',
        width: 1200,
        height: 630,
        alt: 'FoxMate AI - Your Cute Focus Companion',
      },
    ],
    locale: 'en_US',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'FoxMate AI - Your Cute Focus Companion',
    description: 'Stay focused and productive with your adorable fox companion.',
    images: ['/og-image.jpg'],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      'max-video-preview': -1,
      'max-image-preview': 'large',
      'max-snippet': -1,
    },
  },
}

export default function Home() {
  const heroImages = [
    { src: '/fMkydJ74Y.jpeg', alt: 'Cute FoxMate Companion' },
    { src: '/fMkyHhvEi.jpeg', alt: 'FoxMate Focus Work' },
    { src: '/fMkyoQYnK.jpeg', alt: 'FoxMate Celebration' }
  ]
  
  const productImages = [
    { src: '/fMsUvKcjP.jpeg', alt: 'Product Interface 1' },
    { src: '/fMsUeKCZc.jpeg', alt: 'Product Interface 2' },
    { src: '/fMsVAqFtK.jpeg', alt: 'Product Interface 3' }
  ]

  return (
    <main className="min-h-screen">
      <Navbar />
      
      <section className="pt-24 pb-20 px-4 sm:px-6 lg:px-8 bg-orange-50">
        <div className="max-w-7xl mx-auto">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center min-h-[70vh]">
            <div>
              <div className="inline-flex items-center gap-2 bg-orange-100 text-orange-600 px-4 py-2 rounded-full text-sm font-medium mb-6">
                <Star className="w-4 h-4" />
                Focus Companion
              </div>
              
              <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold font-display mb-6 leading-tight">
                Stay focused with your <span className="bg-gradient-to-r from-orange-500 to-red-500 bg-clip-text text-transparent">FoxMate companion</span>
              </h1>
              
              <p className="text-lg text-gray-600 mb-8 max-w-xl leading-relaxed">
                Transform your productivity with real-time focus tracking, personalized fox reactions, and growth insights that keep you motivated.
              </p>
              
              <div className="flex flex-col sm:flex-row gap-4 mb-12">
                <a href={config.download.windows} className="inline-flex items-center justify-center gap-2 bg-orange-500 text-white px-8 py-4 rounded-full font-semibold shadow-lg cursor-pointer transition-all duration-200 hover:bg-orange-600 hover:shadow-xl hover:-translate-y-0.5 active:translate-y-0">
                  Try Now
                </a>
                <Link href="#features" className="inline-flex items-center justify-center gap-2 bg-white text-gray-700 px-8 py-4 rounded-full font-semibold border-2 border-gray-200 cursor-pointer transition-all duration-200 hover:border-orange-300 hover:text-orange-600 hover:shadow-lg">
                  Learn More
                </Link>
              </div>
              
              <div className="bg-white rounded-3xl p-6 shadow-xl border border-gray-100">
                <div className="flex items-center gap-6 mb-4">
                  <div className="flex -space-x-3">
                    {[1, 2, 3, 4, 5].map((i) => (
                      <div key={i} className="w-12 h-12 rounded-full bg-orange-400 border-3 border-white flex items-center justify-center text-white font-bold text-sm shadow-md">
                        {String.fromCharCode(64 + i)}
                      </div>
                    ))}
                  </div>
                  <div>
                    <div className="flex items-center gap-1 mb-1">
                      {[1, 2, 3, 4, 5].map((i) => (
                        <svg key={i} className="w-5 h-5 text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
                          <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                        </svg>
                      ))}
                    </div>
                    <div className="font-semibold text-gray-800">5.0 Excellent</div>
                  </div>
                </div>
                <div className="flex items-center gap-6 pt-4 border-t border-gray-100">
                  <div className="text-center">
                    <div className="text-2xl font-bold text-orange-600">500+</div>
                    <div className="text-sm text-gray-500">Beta Users</div>
                  </div>
                  <div className="w-px h-10 bg-gray-200"></div>
                  <div className="text-center">
                    <div className="text-2xl font-bold text-orange-600">99%</div>
                    <div className="text-sm text-gray-500">Satisfaction</div>
                  </div>
                  <div className="w-px h-10 bg-gray-200"></div>
                  <div className="text-center">
                    <div className="text-2xl font-bold text-orange-600">24h</div>
                    <div className="text-sm text-gray-500">Focus Hours</div>
                  </div>
                </div>
              </div>
            </div>
            
            <div className="flex justify-center">
              <FadeCarousel images={heroImages} autoPlay={true} interval={4000} />
            </div>
          </div>
        </div>
      </section>

      <section id="features" className="py-24 px-4 sm:px-6 lg:px-8 bg-gray-50">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-4 py-2 bg-orange-100 rounded-full mb-6">
              <span className="text-orange-600 font-semibold text-sm">✨ New Experience</span>
            </div>
            <h2 className="text-4xl md:text-5xl font-bold font-display mb-6">
              Smart Focus, <span className="bg-gradient-to-r from-orange-600 to-red-600 bg-clip-text text-transparent">Completely New</span>
            </h2>
            <p className="text-xl text-gray-600 max-w-3xl mx-auto">
              FoxMateAI creates an immersive focus experience, making every minute more valuable
            </p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
            <div className="space-y-8">
              {[
                { icon: '⏰', title: 'Smart Timer', desc: 'Flexibly switch between Pomodoro Technique or free timer mode, adjust focus duration according to your habits' },
                { icon: '💕', title: 'Emotional Companion', desc: 'Little fox interacts with you through expressions and animations, encourages you when focused, reminds you when distracted' },
                { icon: '📊', title: 'Data Insights', desc: 'Detailed records of your focus habits, visually displayed through charts to help you continuously improve' }
              ].map((item, index) => (
                <div key={index} className="bg-white rounded-3xl p-6 shadow-xl border border-gray-100">
                  <div className="flex items-start gap-4">
                    <div className="w-14 h-14 bg-orange-400 rounded-2xl flex items-center justify-center flex-shrink-0 shadow-lg">
                      <div className="text-2xl">{item.icon}</div>
                    </div>
                    <div>
                      <h3 className="text-xl font-bold text-gray-800 mb-2">{item.title}</h3>
                      <p className="text-gray-600">{item.desc}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="relative">
              <FadeCarousel 
                images={productImages} 
                autoPlay={true} 
                interval={4000} 
                aspectRatio="16/9"
                maxWidth="max-w-2xl"
              />
            </div>
          </div>
        </div>
      </section>

      <section className="py-24 px-4 sm:px-6 lg:px-8 bg-white">
        <div className="max-w-7xl mx-auto">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
            <div className="space-y-8">
              <h3 className="text-3xl font-bold text-gray-800">Dynamic Fox Reactions</h3>
              <p className="text-lg text-gray-600">
                Your fox companion responds to your focus state with encouraging animations and expressions, making work fun and engaging.
              </p>
              <div className="space-y-4">
                {[
                  'Real-time emotional reactions to your focus',
                  'Encouraging animations during work sessions',
                  'Celebratory reactions to achievements'
                ].map((item, index) => (
                  <div key={index} className="flex items-center gap-4">
                    <div className="w-4 h-4 rounded-full bg-orange-500"></div>
                    <span className="text-gray-700">{item}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-6">
              {[
                { image: '/fMshiLtjn.png', title: 'Focused', subtitle: 'Happy and Alert', color: 'from-green-400 to-emerald-500', bgColor: 'bg-green-50', textColor: 'text-green-600' },
                { image: '/501453bdcef370c6.png', title: 'Distracted', subtitle: 'Gentle Nudge', color: 'from-yellow-400 to-orange-500', bgColor: 'bg-yellow-50', textColor: 'text-yellow-600' },
                { image: '/fMsff2RwY.png', title: 'Goal Achieved', subtitle: 'Celebrate', color: 'from-purple-400 to-violet-500', bgColor: 'bg-purple-50', textColor: 'text-purple-600' },
                { image: '/fMsit2H60.png', title: 'Deep Focus', subtitle: 'Support', color: 'from-orange-400 to-red-500', bgColor: 'bg-orange-50', textColor: 'text-orange-600' }
              ].map((item, index) => {
                const borderColors = ['#22c55e', '#eab308', '#a855f7', '#f97316'];
                return (
                  <div key={index} className="group">
                    <div className={`${item.bgColor} rounded-3xl p-8 text-center cursor-pointer transition-all duration-300 hover:scale-105 hover:shadow-xl`} style={{borderWidth: '2px', borderColor: borderColors[index]}}>
                      <div className="w-28 h-28 mx-auto mb-6 transition-transform duration-300 group-hover:scale-110 group-hover:animate-bounce">
                        <img
                          src={item.image}
                          alt={item.title}
                          className="w-full h-full object-contain"
                          loading="lazy"
                        />
                      </div>
                      <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full mb-3 ${item.textColor} bg-white/50 transition-all duration-300 group-hover:scale-105`}>
                        {index === 0 && <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>}
                        {index === 1 && <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" /></svg>}
                        {index === 2 && <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
                        {index === 3 && <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" /></svg>}
                        <span className="font-medium">{item.title}</span>
                      </div>
                      <p className={`${item.textColor} font-medium`}>{item.subtitle}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      <section className="py-24 px-4 sm:px-6 lg:px-8 bg-white">
        <div className="max-w-7xl mx-auto">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
            <div className="relative">
              <div className="bg-orange-50 rounded-[2rem] p-8 shadow-2xl border border-orange-100 relative z-10">
                <div className="mb-8">
                  <h3 className="text-2xl font-bold text-orange-700 mb-2">📊 Daily Focus Minutes</h3>
                  <p className="text-gray-500">Focus data statistics for the past week</p>
                </div>
                
                <div className="relative h-72">
                  <div className="absolute left-0 top-0 h-full flex flex-col justify-between text-gray-400 text-sm">
                    <span>60</span>
                    <span>45</span>
                    <span>30</span>
                    <span>15</span>
                    <span>0</span>
                  </div>
                  
                  <div className="ml-10 h-full flex flex-col justify-between">
                    {[0, 1, 2, 3, 4].map((i) => (
                      <div key={i} className="w-full border-t border-gray-200 border-dashed"></div>
                    ))}
                  </div>
                  
                  <div className="ml-10 h-full relative">
                    <svg className="absolute inset-0 w-full h-full" viewBox="0 0 400 200" preserveAspectRatio="none">
                      <defs>
                        <linearGradient id="lineGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                          <stop offset="0%" stopColor="#f97316" />
                          <stop offset="100%" stopColor="#ef4444" />
                        </linearGradient>
                        <linearGradient id="areaGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                          <stop offset="0%" stopColor="#f97316" stopOpacity="0.15" />
                          <stop offset="100%" stopColor="#ef4444" stopOpacity="0" />
                        </linearGradient>
                      </defs>
                      
                      <path d="M30,90 L90,50 L150,10 L210,30 L270,70 L330,65 L330,150 L30,150 Z" fill="url(#areaGradient)" />
                      
                      <path d="M30,90 L90,50 L150,10 L210,30 L270,70 L330,65" fill="none" stroke="url(#lineGradient)" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
                      
                      <circle cx="30" cy="90" r="6" fill="white" stroke="#f97316" strokeWidth="3" />
                      <circle cx="90" cy="50" r="6" fill="white" stroke="#f97316" strokeWidth="3" />
                      <circle cx="150" cy="10" r="8" fill="white" stroke="#ef4444" strokeWidth="3" />
                      <circle cx="210" cy="30" r="6" fill="white" stroke="#f97316" strokeWidth="3" />
                      <circle cx="270" cy="70" r="6" fill="white" stroke="#f97316" strokeWidth="3" />
                      <circle cx="330" cy="65" r="6" fill="white" stroke="#f97316" strokeWidth="3" />
                    </svg>
                  </div>
                  
                  <div className="ml-10 absolute bottom-0 w-full flex justify-around text-gray-600 font-medium text-sm">
                    <span className="text-orange-600 font-semibold">Mon</span>
                    <span>Tue</span>
                    <span className="text-red-600 font-semibold">Wed</span>
                    <span>Thu</span>
                    <span>Fri</span>
                    <span>Sat</span>
                  </div>
                </div>
                
                <div className="flex items-center justify-between mt-8 pt-6 border-t border-orange-100">
                  <div>
                    <p className="text-gray-500 text-sm">Total This Week</p>
                    <p className="text-2xl font-bold text-gray-800">6.2 Hours</p>
                  </div>
                  <div className="flex items-center gap-2 text-green-600">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                    </svg>
                    <span className="font-bold text-lg">+18%</span>
                  </div>
                </div>
              </div>
            </div>
            
            <div className="space-y-8">
              <div className="inline-flex items-center gap-2 px-4 py-2 bg-orange-100 rounded-full">
                <span className="text-orange-600 font-semibold text-sm">📈 Data Insights</span>
              </div>
              
              <h2 className="text-4xl md:text-5xl font-bold font-display">
                Focus Time <span className="bg-gradient-to-r from-orange-600 to-red-600 bg-clip-text text-transparent">Tracking & Analysis</span>
              </h2>
              
              <p className="text-xl text-gray-600 leading-relaxed">
                Monitor your daily work time with detailed time tracking, showing your weekly productivity patterns to help you continuously optimize your focus habits.
              </p>
              
              <div className="space-y-5">
                {[
                  { icon: '📊', title: 'Visual Chart Display', desc: 'Beautiful line charts visually showing daily focus time trends' },
                  { icon: '📅', title: 'Weekly/Monthly Progress', desc: 'View weekly and monthly focus data comparisons to clearly track your progress' },
                  { icon: '🎯', title: 'Productivity Insights', desc: 'Intelligent analysis of your focus patterns, providing personalized improvement suggestions' }
                ].map((item, index) => (
                  <div key={index} className="flex items-start gap-5 p-5 bg-orange-50 rounded-2xl">
                    <div className="w-12 h-12 bg-orange-500 rounded-xl flex items-center justify-center flex-shrink-0 shadow-lg">
                      <div className="text-2xl">{item.icon}</div>
                    </div>
                    <div>
                      <h4 className="text-lg font-bold text-gray-800 mb-1">{item.title}</h4>
                      <p className="text-gray-600">{item.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="py-24 px-4 sm:px-6 lg:px-8 bg-white">
        <div className="max-w-7xl mx-auto">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
            <div className="space-y-8">
              <div className="inline-flex items-center gap-2 px-6 py-3 bg-orange-500 text-white rounded-full shadow-lg">
                <span className="font-semibold">🎯 Smart Focus Monitoring</span>
              </div>
              
              <h2 className="text-4xl md:text-5xl font-bold font-display">
                Let the little fox be your
                <span className="block mt-2 bg-gradient-to-r from-orange-600 to-red-600 bg-clip-text text-transparent">
                  Focus Companion
                </span>
              </h2>
              
              <p className="text-xl text-gray-600 leading-relaxed">
                Through advanced AI vision technology, analyze your focus state in real-time. The little fox uses cute expressions and interactions to make focusing more fun and rewarding.
              </p>
              
              <div className="space-y-5">
                {[
                  { number: '01', title: 'Millisecond Real-time Detection', desc: 'Analyze your focus state every second, accurately capturing every change' },
                  { number: '02', title: 'Multi-dimensional Assessment', desc: 'Comprehensive evaluation of focus from eye movement, expression, action and other dimensions' },
                  { number: '03', title: 'Personalized Feedback', desc: 'Adjust reminder methods according to your habits to create a personalized focus experience' }
                ].map((item, index) => (
                  <div key={index} className="flex items-start gap-5 p-5 bg-orange-50 rounded-2xl">
                    <div className="w-12 h-12 bg-orange-500 rounded-xl flex items-center justify-center flex-shrink-0 shadow-lg">
                      <div className="text-xl font-bold text-white">{item.number}</div>
                    </div>
                    <div>
                      <h4 className="text-lg font-bold text-gray-800 mb-1">{item.title}</h4>
                      <p className="text-gray-600">{item.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            
            <div className="relative">
              <div className="relative bg-white rounded-[2rem] p-8 shadow-2xl border border-orange-100">
                <div className="grid grid-cols-2 gap-6 items-center mb-8">
                  <div className="bg-orange-50 rounded-2xl p-6 text-center">
                    <div className="w-36 h-36 mx-auto rounded-full overflow-hidden mb-3">
                      <img 
                        src="/fMtFShZxa.png" 
                        alt="Current State FoxMate" 
                        className="w-full h-full object-cover"
                      />
                    </div>
                    <p className="text-gray-600 font-medium text-sm">Current State FoxMate</p>
                  </div>
                  
                  <div className="flex flex-col items-center justify-center">
                    <div className="relative w-40 h-40">
                      <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
                        <circle
                          cx="50"
                          cy="50"
                          r="45"
                          fill="none"
                          stroke="#f3f4f6"
                          strokeWidth="10"
                        />
                        <circle
                          cx="50"
                          cy="50"
                          r="45"
                          fill="none"
                          stroke="url(#gaugeGradient)"
                          strokeWidth="10"
                          strokeLinecap="round"
                          strokeDasharray={`${72 * 2.83} ${28 * 2.83}`}
                        />
                        <defs>
                          <linearGradient id="gaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%" stopColor="#f97316" />
                            <stop offset="100%" stopColor="#ef4444" />
                          </linearGradient>
                        </defs>
                      </svg>
                      <div className="absolute inset-0 flex flex-col items-center justify-center">
                        <span className="text-4xl font-bold bg-gradient-to-r from-orange-600 to-red-600 bg-clip-text text-transparent">72%</span>
                        <span className="text-gray-500 mt-1 text-sm">Current Focus</span>
                      </div>
                    </div>
                  </div>
                </div>
                
                <div className="grid grid-cols-4 gap-4 mb-8">
                  {[
                    { name: 'Deep Focus', image: '/fMtAqbOD5.png' },
                    { name: 'Light Focus', image: '/fMtAZDiLZ.png' },
                    { name: 'Slightly Distracted', image: '/fMtAzbST5.png' },
                    { name: 'Distracted', image: '/fMtA8ogkM.png' }
                  ].map((item, index) => (
                    <div key={index} className="text-center p-3 bg-orange-50 rounded-xl">
                      <div className="w-16 h-16 mx-auto rounded-lg flex items-center justify-center mb-2 overflow-hidden">
                        <img 
                          src={item.image} 
                          alt={item.name}
                          className="w-full h-full object-cover"
                          loading="lazy"
                        />
                      </div>
                      <p className="text-xs text-gray-600 font-medium">{item.name}</p>
                    </div>
                  ))}
                </div>
                
                <div className="space-y-3">
                  {[
                    { label: 'Deep Focus', value: 35, color: '#ef4444' },
                    { label: 'Light Focus', value: 37, color: '#f97316' },
                    { label: 'Slightly Distracted', value: 18, color: '#fdba74' },
                    { label: 'Distracted', value: 10, color: '#fed7aa' }
                  ].map((item, index) => (
                    <div key={index} className="flex items-center gap-3">
                      <span className="text-sm text-gray-600 w-28">{item.label}</span>
                      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${item.value}%`, backgroundColor: item.color }}></div>
                      </div>
                      <span className="text-sm font-semibold text-gray-800 w-10 text-right">{item.value}%</span>
                    </div>
                  ))}
                </div>
                
                <div className="grid grid-cols-3 gap-4 mt-8 pt-6 border-t border-gray-100">
                  {[
                    { value: '2.5h', label: 'Today\'s Focus', icon: '⏰' },
                    { value: '85%', label: 'Average Level', icon: '📊' },
                    { value: '+12%', label: 'Weekly Improvement', icon: '📈' }
                  ].map((item, index) => (
                    <div key={index} className="text-center p-3 bg-red-50 rounded-xl">
                      <div className="text-xl mb-1">{item.icon}</div>
                      <div className="text-lg font-bold text-orange-700">{item.value}</div>
                      <div className="text-xs text-gray-500">{item.label}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="py-24 px-4 sm:px-6 lg:px-8 bg-gray-50">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-6 py-3 bg-orange-500 text-white rounded-full shadow-lg mb-6">
              <span className="font-semibold">📊 Real-time Data Report</span>
            </div>
            <h2 className="text-4xl md:text-5xl font-bold font-display mb-6">
              Professional <span className="bg-gradient-to-r from-orange-600 to-red-600 bg-clip-text text-transparent">Data Analysis Report</span>
            </h2>
            <p className="text-xl text-gray-600 max-w-3xl mx-auto">
              Deep insights into your focus habits, driving continuous improvement with data, making every effort clearly visible
            </p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
            <div className="relative">
              <div className="absolute -top-6 -left-6 w-40 h-40 bg-orange-500 rounded-[2rem] -z-10"></div>
              <div className="absolute -bottom-6 -right-6 w-40 h-40 bg-red-500 rounded-[2rem] -z-10"></div>
              
              <div className="bg-gray-100 rounded-[2rem] p-8 shadow-2xl relative z-10">
                <div className="flex justify-between items-start mb-8">
                  <div>
                    <h3 className="text-2xl font-bold text-gray-800 mb-1">Your Personal Report</h3>
                    <p className="text-gray-500">This Week's Focus Record</p>
                  </div>
                  <div className="text-right">
                    <div className="text-4xl font-bold bg-gradient-to-r from-orange-600 to-red-600 bg-clip-text text-transparent">+127</div>
                    <div className="text-sm text-gray-500">Focus Points</div>
                  </div>
                </div>
                
                <div className="grid grid-cols-3 gap-4 mb-8">
                  <div className="bg-green-50 rounded-2xl p-5 text-center border-2 border-green-200">
                    <div className="text-2xl mb-2">📈</div>
                    <div className="text-2xl font-bold text-green-600">94%</div>
                    <div className="text-sm text-gray-500">Goal Achieved</div>
                  </div>
                  <div className="bg-blue-50 rounded-2xl p-5 text-center border-2 border-blue-200">
                    <div className="text-2xl mb-2">⏰</div>
                    <div className="text-2xl font-bold text-blue-600">6.2h</div>
                    <div className="text-sm text-gray-500">Daily Avg</div>
                  </div>
                  <div className="bg-purple-50 rounded-2xl p-5 text-center border-2 border-purple-200">
                    <div className="text-2xl mb-2">🎯</div>
                    <div className="text-2xl font-bold text-purple-600">85%</div>
                    <div className="text-sm text-gray-500">Focus Score</div>
                  </div>
                </div>
                
                <div className="bg-white rounded-xl p-4">
                  <div className="flex justify-between items-center mb-4">
                    <span className="font-semibold text-gray-800">Weekly Progress</span>
                    <span className="text-sm text-gray-500">Last 7 days</span>
                  </div>
                  <div className="flex items-end gap-2 h-24">
                    {[65, 80, 45, 90, 75, 85, 70].map((height, i) => (
                      <div key={i} className="flex-1 bg-orange-400 rounded-t" style={{ height: `${height}%` }}></div>
                    ))}
                  </div>
                  <div className="flex justify-between mt-2 text-xs text-gray-500">
                    <span>Mon</span>
                    <span>Tue</span>
                    <span>Wed</span>
                    <span>Thu</span>
                    <span>Fri</span>
                    <span>Sat</span>
                    <span>Sun</span>
                  </div>
                </div>
              </div>
            </div>
            
            <div className="space-y-6">
              <h3 className="text-2xl font-bold text-gray-800">
                Why Choose <span className="bg-gradient-to-r from-orange-600 to-red-600 bg-clip-text text-transparent">FoxMate</span>?
              </h3>
              <p className="text-gray-600">
                Transform your productivity with AI-powered personalization and advanced analytics that adapt to your unique work style.
              </p>
              
              <div className="space-y-4">
                {[
                  { 
                    icon: '⚡', 
                    title: 'Personalized Reminders', 
                    desc: 'Smart notifications learn your schedule and peak focus times',
                    bgClass: 'bg-yellow-50',
                    borderClass: 'border-yellow-400',
                    iconBgClass: 'bg-yellow-100'
                  },
                  { 
                    icon: '🧠', 
                    title: 'AI-Powered Analysis', 
                    desc: 'Deep learning algorithms understand your work patterns and provide personalized suggestions',
                    bgClass: 'bg-orange-50',
                    borderClass: 'border-orange-400',
                    iconBgClass: 'bg-orange-100'
                  },
                  { 
                    icon: '📊', 
                    title: 'Beautiful Reports', 
                    desc: 'Intuitive visualizations and detailed progress reports make your achievements clearly visible',
                    bgClass: 'bg-red-50',
                    borderClass: 'border-red-400',
                    iconBgClass: 'bg-red-100'
                  }
                ].map((item, index) => (
                  <div key={index} className={`${item.bgClass} rounded-2xl p-6 shadow-lg border-l-4 ${item.borderClass}`}>
                    <div className="flex gap-4">
                      <div className={`w-14 h-14 ${item.iconBgClass} rounded-xl flex items-center justify-center flex-shrink-0`}>
                        <div className="text-3xl">{item.icon}</div>
                      </div>
                      <div>
                        <h4 className="text-xl font-bold text-gray-800 mb-2">{item.title}</h4>
                        <p className="text-gray-600">{item.desc}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="py-24 px-4 sm:px-6 lg:px-8 bg-orange-50">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-4 py-2 bg-orange-100 rounded-full mb-6">
              <span className="text-orange-600 font-semibold text-sm">⬇️ Free Download</span>
            </div>
            <h2 className="text-4xl md:text-5xl font-bold font-display mb-6 bg-gradient-to-r from-orange-600 to-red-600 bg-clip-text text-transparent">
              Download Now, Start Your Focus Journey
            </h2>
            <p className="text-xl text-gray-600 max-w-2xl mx-auto">
              FoxMateAI is completely free, supports Windows system, let your desktop companion be with you instantly
            </p>
          </div>

          <div className="bg-white rounded-[2rem] p-8 md:p-12 shadow-2xl border border-gray-100">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-center">
              <div>
                <div className="flex items-center gap-4 mb-6">
                  <div className="w-16 h-16 bg-orange-500 rounded-2xl flex items-center justify-center shadow-xl">
                    <div className="text-3xl">🦊</div>
                  </div>
                  <div>
                    <h3 className="text-2xl font-bold text-gray-800">FoxMate AI</h3>
                    <p className="text-gray-500">v1.0.0 Official</p>
                  </div>
                </div>
                
                <div className="space-y-3 mb-8">
                  {[
                    'Windows 10/11 Support',
                    'No internet required, runs locally',
                    'Completely free, no restrictions'
                  ].map((item, index) => (
                    <div key={index} className="flex items-center gap-3">
                      <svg className="w-5 h-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      <span className="text-gray-700">{item}</span>
                    </div>
                  ))}
                </div>
                
                <div className="flex gap-4">
                  <a href={config.download.windows} className="flex-1 bg-orange-500 text-white px-8 py-4 rounded-2xl font-bold text-lg shadow-xl flex items-center justify-center gap-3 cursor-pointer transition-all duration-200 hover:bg-orange-600 hover:shadow-2xl hover:-translate-y-0.5 active:translate-y-0">
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    Download Windows
                  </a>
                </div>
                <p className="text-sm text-gray-500 mt-4">File Size: {config.download.fileSize}</p>
              </div>
              
              <div className="bg-orange-50 rounded-2xl p-8 text-center">
                <div className="w-48 h-48 mx-auto bg-white rounded-2xl flex items-center justify-center mb-4 overflow-hidden">
                  <img 
                    src="/fMtFShZxa.png" 
                    alt="App Icon"
                    className="w-full h-full object-cover"
                  />
                </div>
                <p className="text-gray-600 font-medium">Your cute focus companion on desktop</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="py-24 px-4 sm:px-6 lg:px-8 bg-orange-500">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-4xl md:text-5xl font-bold font-display mb-6 text-white">
            Ready to start your focus journey?
          </h2>
          <p className="text-xl text-white/90 mb-8 max-w-2xl mx-auto">
            Join thousands of users using FoxMate to boost productivity. Start your focus journey today.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center mb-8">
            <a href={config.download.windows} className="inline-flex items-center justify-center gap-2 bg-white text-orange-500 px-8 py-4 rounded-full font-semibold text-lg shadow-lg cursor-pointer transition-all duration-200 hover:bg-orange-50 hover:shadow-xl hover:-translate-y-0.5 active:translate-y-0">
              Try Free Now
              <ChevronRight className="w-5 h-5" />
            </a>
            <a href={config.download.windows} className="inline-flex items-center justify-center gap-2 bg-transparent text-white border-2 border-white px-8 py-4 rounded-full font-semibold text-lg cursor-pointer transition-all duration-200 hover:bg-white/10 hover:shadow-lg">
              Download App
            </a>
          </div>
          <div className="flex items-center justify-center gap-8 text-white/80">
            {['Free Start', 'No Credit Card', 'Cancel Anytime'].map((item, index) => (
              <div key={index} className="flex items-center gap-2">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <span>{item}</span>
              </div>
            ))}
          </div>
        </div>
        
        <div className="max-w-4xl mx-auto mt-16">
          <div className="mt-12 bg-white rounded-[2rem] p-8 shadow-2xl border border-gray-100">
            <div className="text-6xl mb-4">💻</div>
            <div className="bg-orange-50 rounded-2xl p-6">
              <div className="text-2xl font-bold text-gray-800">FoxMate AI Desktop</div>
              <div className="text-gray-500 mt-2">Your cute focus companion on desktop</div>
              <div className="mt-4 flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 bg-green-500 rounded-full"></div>
                  <span className="text-sm text-gray-600">Online</span>
                </div>
                <div className="text-sm text-gray-500">v1.0.0</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <Footer />
      <ScrollToTop />
    </main>
  )
}
