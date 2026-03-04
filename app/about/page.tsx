import Navbar from '@/components/Navbar'
import Footer from '@/components/Footer'
import { Heart, Users, Target, Sparkles } from 'lucide-react'

export default function About() {
  const team = [
    { name: 'Development Team', role: 'Full Stack Development', emoji: '👨‍💻' },
    { name: 'Design Team', role: 'UI/UX Design', emoji: '🎨' },
    { name: 'AI Team', role: 'Algorithm Optimization', emoji: '🤖' }
  ]

  const values = [
    {
      icon: Heart,
      title: 'User First',
      description: 'We always put user experience at the core, creating truly useful products'
    },
    {
      icon: Users,
      title: 'Open & Transparent',
      description: 'Open source code, accepting community supervision, protecting user privacy'
    },
    {
      icon: Target,
      title: 'Quality Focused',
      description: 'Pursuing excellent product quality, continuously optimizing user experience'
    },
    {
      icon: Sparkles,
      title: 'Innovation Driven',
      description: 'Using the latest AI technology to provide intelligent services for users'
    }
  ]

  return (
    <main className="min-h-screen">
      <Navbar />
      
      <section className="pt-24 pb-16 px-4 sm:px-6 lg:px-8 bg-primary-50">
        <div className="max-w-7xl mx-auto text-center">
          <h1 className="text-5xl font-bold font-display mb-4 gradient-text">
            About Us
          </h1>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto">
            We are dedicated to using AI technology to help people improve focus, making work and study more efficient
          </p>
        </div>
      </section>

      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-white">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-4xl font-bold font-display mb-6 gradient-text">
            Our Mission
          </h2>
          <p className="text-xl text-gray-600 leading-relaxed mb-8">
            In this era of information explosion, focus has become a scarce resource. We hope to use AI technology
            to help everyone better manage their attention and improve work and study efficiency.
          </p>
          <div className="text-6xl">🦊</div>
        </div>
      </section>

      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-gray-50">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-4xl font-bold font-display mb-12 text-center gradient-text">
            Core Values
          </h2>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
            {values.map((value, index) => {
              const Icon = value.icon
              return (
                <div key={index} className="card text-center">
                  <div className="w-16 h-16 bg-primary-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
                    <Icon className="w-8 h-8 text-primary-500" />
                  </div>
                  <h3 className="text-xl font-semibold mb-2">{value.title}</h3>
                  <p className="text-gray-600">{value.description}</p>
                </div>
              )
            })}
          </div>
        </div>
      </section>

      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-white">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-4xl font-bold font-display mb-12 text-center gradient-text">
            Our Team
          </h2>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {team.map((member, index) => (
              <div key={index} className="card text-center">
                <div className="text-6xl mb-4">{member.emoji}</div>
                <h3 className="text-xl font-semibold mb-2">{member.name}</h3>
                <p className="text-gray-600">{member.role}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-gray-50">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-4xl font-bold font-display mb-8 text-center gradient-text">
            Our Story
          </h2>
          
          <div className="card">
            <div className="prose prose-lg max-w-none text-gray-600">
              <p className="mb-4">
                The FoxMate project started with a simple idea: How can we make focus training more fun?
              </p>
              <p className="mb-4">
                We found that traditional focus tools are often too serious and lack human touch. So we decided to create a
                cute desktop pet that uses AI technology to provide intelligent companionship for users.
              </p>
              <p className="mb-4">
                After months of development and optimization, FoxMate was finally born. It can not only monitor your focus state
                but also provide personalized conversation prompts based on your performance, making focus no longer boring.
              </p>
              <p>
                We believe that everyone has unlimited potential, and FoxMate is the little helper to help you unleash that potential.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-white">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-4xl font-bold font-display mb-6 gradient-text">
            Contact Us
          </h2>
          <p className="text-xl text-gray-600 mb-8">
            Have any questions or suggestions? We'd love to hear from you
          </p>
          
          <div className="card max-w-md mx-auto">
            <form className="space-y-4">
              <div>
                <input
                  type="email"
                  placeholder="Your Email"
                  className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:border-primary-500 focus:ring-2 focus:ring-primary-200 outline-none"
                />
              </div>
              <div>
                <textarea
                  placeholder="Your Message"
                  rows={4}
                  className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:border-primary-500 focus:ring-2 focus:ring-primary-200 outline-none resize-none"
                ></textarea>
              </div>
              <button type="submit" className="btn-primary w-full cursor-pointer">
                Send Message
              </button>
            </form>
          </div>
        </div>
      </section>

      <Footer />
    </main>
  )
}
