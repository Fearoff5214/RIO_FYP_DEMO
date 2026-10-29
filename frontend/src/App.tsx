import { Routes, Route, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Jobs from './pages/Jobs'
import JobDetail from './pages/JobDetail'
import Gate1Review from './pages/Gate1Review'
import LabelReview from './pages/LabelReview'
import Gate2Expert from './pages/Gate2Expert'
import Gate3Approval from './pages/Gate3Approval'
import Reports from './pages/Reports'
import KnowledgeBase from './pages/KnowledgeBase'
import Actions from './pages/Actions'
import NewJob from './pages/NewJob'

const navItems = [
  { to: '/', label: 'Dashboard' },
  { to: '/jobs', label: 'Jobs' },
  { to: '/jobs/new', label: '+ New Job' },
  { to: '/actions', label: 'Actions' },
  { to: '/kb', label: 'Knowledge Base' },
]

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="bg-novaliseo-dark border-b border-blue-900 px-6 py-3 flex items-center gap-8">
        <div>
          <span className="text-blue-400 font-bold text-xl tracking-wide">NOVALISEO</span>
          <span className="text-gray-500 text-xs ml-2">Brain Behind Intelligent Operations</span>
        </div>
        <nav className="flex gap-4 text-sm">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `px-3 py-1 rounded transition ${
                  isActive ? 'bg-blue-800 text-white' : 'text-gray-400 hover:text-white'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>

      {/* Main */}
      <main className="flex-1 p-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/jobs/new" element={<NewJob />} />
          <Route path="/jobs/:jobId" element={<JobDetail />} />
          <Route path="/jobs/:jobId/gate1" element={<Gate1Review />} />
          <Route path="/jobs/:jobId/label" element={<LabelReview />} />
          <Route path="/jobs/:jobId/gate2" element={<Gate2Expert />} />
          <Route path="/jobs/:jobId/gate3" element={<Gate3Approval />} />
          <Route path="/jobs/:jobId/reports" element={<Reports />} />
          <Route path="/actions" element={<Actions />} />
          <Route path="/kb" element={<KnowledgeBase />} />
        </Routes>
      </main>

      <footer className="text-center text-gray-700 text-xs py-3 border-t border-gray-800">
        Novaliseo · Intelligent Inspection · Accurate Insights · Superior Quality
      </footer>
    </div>
  )
}
