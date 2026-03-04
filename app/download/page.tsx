import Navbar from '@/components/Navbar'
import Footer from '@/components/Footer'
import { Download as DownloadIcon, Monitor, CheckCircle } from 'lucide-react'
import { config } from '@/lib/config'

export default function DownloadPage() {
  const systemRequirements = [
    'Windows 10 or higher',
    '4GB RAM (8GB recommended)',
    '500MB available disk space',
    'No Python environment required'
  ]

  const versionHistory = [
    { version: '1.0.0', date: '2024-02-26', changes: 'Initial release' }
  ]

  return (
    <main className="min-h-screen">
      <Navbar />
      
      <section className="pt-24 pb-16 px-4 sm:px-6 lg:px-8 bg-primary-50">
        <div className="max-w-7xl mx-auto text-center">
          <h1 className="text-5xl font-bold font-display mb-4 gradient-text">
            Download FoxMate
          </h1>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto mb-8">
            Choose the version that suits you and start your focus journey
          </p>
        </div>
      </section>

      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-white">
        <div className="max-w-5xl mx-auto">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div className="card border-2 border-primary-200">
              <div className="text-center mb-6">
                <div className="w-20 h-20 bg-primary-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
                  <Monitor className="w-10 h-10 text-primary-500" />
                </div>
                <h2 className="text-2xl font-bold mb-2">Windows Version</h2>
                <p className="text-gray-600">For Windows 10 and above</p>
              </div>
              
              <div className="space-y-3 mb-6">
                <div className="flex items-center text-gray-700">
                  <CheckCircle className="w-5 h-5 text-green-500 mr-2" />
                  <span>Standalone, no installation required</span>
                </div>
                <div className="flex items-center text-gray-700">
                  <CheckCircle className="w-5 h-5 text-green-500 mr-2" />
                  <span>Includes all dependencies</span>
                </div>
                <div className="flex items-center text-gray-700">
                  <CheckCircle className="w-5 h-5 text-green-500 mr-2" />
                  <span>Automatic update notifications</span>
                </div>
              </div>

              <a href={config.download.windows} className="btn-primary w-full flex items-center justify-center space-x-2 cursor-pointer">
                <DownloadIcon className="w-5 h-5" />
                <span>Download Windows Version</span>
              </a>
              
              <p className="text-center text-sm text-gray-500 mt-4">
                Version {config.download.version} | {config.download.fileSize}
              </p>
            </div>

            <div className={`card ${config.download.mac ? 'border-2 border-primary-200' : 'opacity-60'}`}>
              <div className="text-center mb-6">
                <div className={`w-20 h-20 rounded-2xl flex items-center justify-center mx-auto mb-4 ${config.download.mac ? 'bg-primary-100' : 'bg-gray-100'}`}>
                  <Monitor className={`w-10 h-10 ${config.download.mac ? 'text-primary-500' : 'text-gray-400'}`} />
                </div>
                <h2 className={`text-2xl font-bold mb-2 ${config.download.mac ? '' : 'text-gray-400'}`}>Mac Version</h2>
                <p className={config.download.mac ? 'text-gray-600' : 'text-gray-400'}>{config.download.mac ? 'For macOS 10.15 and above' : 'Coming soon'}</p>
              </div>
              
              {config.download.mac ? (
                <>
                  <div className="space-y-3 mb-6">
                    <div className="flex items-center text-gray-700">
                      <CheckCircle className="w-5 h-5 text-green-500 mr-2" />
                      <span>Native macOS support</span>
                    </div>
                    <div className="flex items-center text-gray-700">
                      <CheckCircle className="w-5 h-5 text-green-500 mr-2" />
                      <span>Includes all dependencies</span>
                    </div>
                    <div className="flex items-center text-gray-700">
                      <CheckCircle className="w-5 h-5 text-green-500 mr-2" />
                      <span>Automatic update notifications</span>
                    </div>
                  </div>
                  <a href={config.download.mac} className="btn-primary w-full flex items-center justify-center space-x-2 cursor-pointer">
                    <DownloadIcon className="w-5 h-5" />
                    <span>Download Mac Version</span>
                  </a>
                  <p className="text-center text-sm text-gray-500 mt-4">
                    Version {config.download.version} | {config.download.fileSize}
                  </p>
                </>
              ) : (
                <>
                  <div className="space-y-3 mb-6">
                    <div className="flex items-center text-gray-400">
                      <CheckCircle className="w-5 h-5 text-gray-300 mr-2" />
                      <span>In development...</span>
                    </div>
                  </div>
                  <button disabled className="btn-secondary w-full flex items-center justify-center space-x-2 opacity-50 cursor-not-allowed">
                    <DownloadIcon className="w-5 h-5" />
                    <span>Stay Tuned</span>
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      </section>

      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-gray-50">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold font-display mb-8 text-center gradient-text">
            System Requirements
          </h2>
          
          <div className="card">
            <h3 className="text-xl font-semibold mb-4">Windows System Requirements</h3>
            <ul className="space-y-3">
              {systemRequirements.map((req, index) => (
                <li key={index} className="flex items-center text-gray-700">
                  <svg className="w-5 h-5 text-green-500 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  {req}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-white">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold font-display mb-8 text-center gradient-text">
            Version History
          </h2>
          
          <div className="space-y-4">
            {versionHistory.map((version, index) => (
              <div key={index} className="card">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-xl font-semibold">Version {version.version}</h3>
                  <span className="text-gray-500">{version.date}</span>
                </div>
                <p className="text-gray-600">{version.changes}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-gray-50">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold font-display mb-8 text-center gradient-text">
            Installation Guide
          </h2>
          
          <div className="space-y-6">
            <div className="card">
              <div className="flex items-start space-x-4">
                <div className="w-10 h-10 bg-primary-500 text-white rounded-full flex items-center justify-center flex-shrink-0 font-bold">
                  1
                </div>
                <div>
                  <h3 className="text-xl font-semibold mb-2">Download the App</h3>
                  <p className="text-gray-600">Click the download button above to download the zip file</p>
                </div>
              </div>
            </div>
            
            <div className="card">
              <div className="flex items-start space-x-4">
                <div className="w-10 h-10 bg-primary-500 text-white rounded-full flex items-center justify-center flex-shrink-0 font-bold">
                  2
                </div>
                <div>
                  <h3 className="text-xl font-semibold mb-2">Extract Files</h3>
                  <p className="text-gray-600">Extract the downloaded zip file to any folder</p>
                </div>
              </div>
            </div>
            
            <div className="card">
              <div className="flex items-start space-x-4">
                <div className="w-10 h-10 bg-primary-500 text-white rounded-full flex items-center justify-center flex-shrink-0 font-bold">
                  3
                </div>
                <div>
                  <h3 className="text-xl font-semibold mb-2">Launch the App</h3>
                  <p className="text-gray-600">Double-click FoxMate AI.exe to start the application</p>
                </div>
              </div>
            </div>
            
            <div className="card">
              <div className="flex items-start space-x-4">
                <div className="w-10 h-10 bg-primary-500 text-white rounded-full flex items-center justify-center flex-shrink-0 font-bold">
                  4
                </div>
                <div>
                  <h3 className="text-xl font-semibold mb-2">Start Using</h3>
                  <p className="text-gray-600">Click the "Fox it!" button to launch FoxMate and start your focus journey</p>
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
