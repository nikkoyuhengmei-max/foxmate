import Navbar from '@/components/Navbar'
import Footer from '@/components/Footer'
import { MessageCircle, BarChart2, Heart, Shield, Sparkles, TrendingUp } from 'lucide-react'

export default function Features() {
  const features = [
    {
      icon: MessageCircle,
      title: 'AI Smart Conversation',
      description: 'FoxMate intelligently generates conversation prompts based on your focus state.',
      details: [
        'When focused: Encourages you to keep going',
        'When distracted: Gently reminds you to return to focus',
        'Provides personalized suggestions based on window title',
        'Supports both Chinese and English conversation'
      ],
      color: 'primary'
    },
    {
      icon: BarChart2,
      title: 'Focus Monitoring',
      description: 'Scientifically calculates your focus level through keyboard and mouse activity.',
      details: [
        'Real-time focus score display',
        'Records focus duration',
        'Generates focus reports',
        'Data visualization'
      ],
      color: 'secondary'
    },
    {
      icon: Heart,
      title: 'Cute Desktop Pet',
      description: 'Your cute FoxMate will accompany you on your desktop.',
      details: [
        '6 states: Sleep, Distracted, Neutral, Focused, Energetic, Celebrating',
        'Adorable animation effects',
        'Draggable position',
        'Transparent background, won\'t block your work'
      ],
      color: 'primary'
    },
    {
      icon: Shield,
      title: 'Privacy Protection',
      description: 'All data stored locally, safe and reliable.',
      details: [
        'Local data storage',
        'No personal information uploaded',
        'Open source code, auditable',
        'Data export functionality'
      ],
      color: 'secondary'
    },
    {
      icon: Sparkles,
      title: 'AI Powered',
      description: 'Uses advanced AI models to provide intelligent services.',
      details: [
        'SBERT semantic understanding',
        'Machine learning prediction',
        'Continuous learning optimization',
        'Personalized recommendations'
      ],
      color: 'primary'
    },
    {
      icon: TrendingUp,
      title: 'Growth Tracking',
      description: 'Witness every step of your progress.',
      details: [
        'Focus duration statistics',
        'Growth curve display',
        'Achievement system',
        'Goal setting'
      ],
      color: 'secondary'
    }
  ]

  return (
    <main className="min-h-screen">
      <Navbar />
      
      <section className="pt-24 pb-16 px-4 sm:px-6 lg:px-8 bg-primary-50">
        <div className="max-w-7xl mx-auto text-center">
          <h1 className="text-5xl font-bold font-display mb-4 gradient-text">
            Features
          </h1>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto">
            FoxMate provides comprehensive focus enhancement services
          </p>
        </div>
      </section>

      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-white">
        <div className="max-w-7xl mx-auto">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
            {features.map((feature, index) => {
              const Icon = feature.icon
              const colorClass = feature.color === 'primary' ? 'bg-primary-100 text-primary-500' : 'bg-secondary-100 text-secondary-500'
              
              return (
                <div key={index} className="card">
                  <div className="flex items-start space-x-4">
                    <div className={`w-16 h-16 ${colorClass} rounded-2xl flex items-center justify-center flex-shrink-0`}>
                      <Icon className="w-8 h-8" />
                    </div>
                    <div className="flex-1">
                      <h3 className="text-2xl font-semibold mb-2">{feature.title}</h3>
                      <p className="text-gray-600 mb-4">{feature.description}</p>
                      <ul className="space-y-2">
                        {feature.details.map((detail, idx) => (
                          <li key={idx} className="flex items-center text-gray-700">
                            <svg className="w-5 h-5 text-green-500 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                            </svg>
                            {detail}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </section>

      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-gray-50">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-4xl font-bold font-display mb-4 gradient-text">
              App Screenshots
            </h2>
            <p className="text-xl text-gray-600">
              See how FoxMate looks in action
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="card p-0 overflow-hidden">
              <div className="bg-primary-100 h-64 flex items-center justify-center">
                <div className="text-center">
                  <div className="text-6xl mb-4">🦊</div>
                  <p className="text-gray-600 font-medium">Desktop Pet</p>
                </div>
              </div>
            </div>
            
            <div className="card p-0 overflow-hidden">
              <div className="bg-secondary-100 h-64 flex items-center justify-center">
                <div className="text-center">
                  <div className="text-6xl mb-4">💬</div>
                  <p className="text-gray-600 font-medium">Smart Chat</p>
                </div>
              </div>
            </div>
            
            <div className="card p-0 overflow-hidden">
              <div className="bg-primary-100 h-64 flex items-center justify-center">
                <div className="text-center">
                  <div className="text-6xl mb-4">📊</div>
                  <p className="text-gray-600 font-medium">Data Statistics</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <Footer />
    </main>
  )
}
