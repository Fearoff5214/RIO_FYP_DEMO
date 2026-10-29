import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import {
  Activity,
  ArrowUpRight,
  BookOpen,
  Boxes,
  ClipboardList,
  LayoutDashboard,
  ScanLine,
  Settings2,
  ShieldCheck,
  type LucideIcon,
} from 'lucide-react'
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

type NavigationItem = {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
}

const primaryNavigation: NavigationItem[] = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/jobs', label: 'Inspection history', icon: ClipboardList },
  { to: '/jobs/new', label: 'Live inspection', icon: ScanLine },
]

const operationsNavigation: NavigationItem[] = [
  { to: '/actions', label: 'Corrective actions', icon: Settings2 },
  { to: '/kb', label: 'Knowledge base', icon: BookOpen },
]

const routeTitles: Record<string, string> = {
  '/': 'Overview',
  '/jobs': 'Inspection history',
  '/jobs/new': 'Live inspection',
  '/actions': 'Corrective actions',
  '/kb': 'Knowledge base',
}

function currentTitle(pathname: string) {
  if (routeTitles[pathname]) return routeTitles[pathname]
  if (pathname.includes('/gate1')) return 'Dimensional review'
  if (pathname.includes('/gate2')) return 'Root cause review'
  if (pathname.includes('/gate3')) return 'Report approval'
  if (pathname.includes('/label')) return 'Detection review'
  if (pathname.includes('/reports')) return 'Inspection report'
  return 'Inspection details'
}

function SidebarLink({ item }: { item: NavigationItem }) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.to}
      end={item.end ?? item.to === '/jobs'}
      className={({ isActive }) => `sidebar-link${isActive ? ' sidebar-link-active' : ''}`}
    >
      <Icon size={17} strokeWidth={1.8} />
      <span>{item.label}</span>
      {item.to === '/jobs/new' && <ArrowUpRight size={14} className="sidebar-link-end" />}
    </NavLink>
  )
}

export default function App() {
  const location = useLocation()
  const title = currentTitle(location.pathname)

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <NavLink to="/" className="brand-lockup" aria-label="Novaliseo overview">
          <div className="brand-mark"><Boxes size={21} strokeWidth={1.8} /></div>
          <div>
            <div className="brand-name">NOVALISEO</div>
            <div className="brand-caption">QUALITY INTELLIGENCE</div>
          </div>
        </NavLink>

        <div className="sidebar-section-label">WORKSPACE</div>
        <nav className="sidebar-nav" aria-label="Workspace navigation">
          {primaryNavigation.map((item) => <SidebarLink key={item.to} item={item} />)}
        </nav>

        <div className="sidebar-section-label sidebar-section-spaced">OPERATIONS</div>
        <nav className="sidebar-nav" aria-label="Operations navigation">
          {operationsNavigation.map((item) => <SidebarLink key={item.to} item={item} />)}
        </nav>

        <div className="sidebar-bottom">
          <div className="sidebar-quality-mark"><ShieldCheck size={17} /></div>
          <div>
            <p className="sidebar-bottom-title">Quality, in focus.</p>
            <p className="sidebar-bottom-copy">Intelligent inspection for better manufacturing decisions.</p>
          </div>
        </div>
      </aside>

      <div className="app-main">
        <header className="app-topbar">
          <div className="topbar-context">
            <span className="topbar-eyebrow">MANUFACTURING QUALITY</span>
            <span className="topbar-divider">/</span>
            <span className="topbar-title">{title}</span>
          </div>
          <div className="topbar-workspace">
            <Activity size={15} />
            <span>Inspection workspace</span>
          </div>
        </header>

        <main className="app-content">
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
        <footer className="app-footer">
          <span>Novaliseo</span>
          <span>Intelligent inspection · Accurate insights · Superior quality</span>
        </footer>
      </div>
    </div>
  )
}
