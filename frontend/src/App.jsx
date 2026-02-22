import { useState } from 'react'
import LandingPage from './pages/LandingPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'

export default function App() {
  const [view, setView] = useState('landing')

  if (view === 'platform') {
    return <DashboardPage onHome={() => setView('landing')} />
  }
  return <LandingPage onEnter={() => setView('platform')} />
}
