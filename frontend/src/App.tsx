import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import {
  Activity,
  ArrowUpRight,
  BookOpen,
  Boxes,
  ClipboardList,
  FolderOpen,
  Plus,
  LayoutDashboard,
  Moon,
  ScanLine,
  Settings2,
  Sun,
  UserRound,
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
import EngineeringAssistant from './components/EngineeringAssistant'
import { jobsApi } from './api'

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

const workflowSteps = ['Verify Part', 'Capture Image', 'Detect Defects', 'Diagnose Root Cause', 'Generate Report']

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
      className={({ isActive }) => {
        const active = isActive && (item.to !== '/jobs' || item.label === 'Inspection history')
        return `sidebar-link${active ? ' sidebar-link-active' : ''}`
      }}
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
  const [theme, setTheme] = useState<'light' | 'dark'>(() => (
    localStorage.getItem('novaliseo-theme') === 'dark' ? 'dark' : 'light'
  ))
  const jobId = location.pathname.match(/^\/jobs\/([^/]+)/)?.[1]
  const inspectionId = jobId && jobId !== 'new' ? jobId : null
  const analysisNavigation: NavigationItem[] = [
    { to: inspectionId ? `/jobs/${inspectionId}/label` : '/jobs', label: 'Defect detection', icon: ScanLine },
    { to: inspectionId ? `/jobs/${inspectionId}/gate2` : '/jobs', label: 'Root cause analysis', icon: Activity },
    { to: '/actions', label: 'Corrective actions', icon: Settings2 },
    { to: '/kb', label: 'Knowledge base', icon: BookOpen },
  ]
  const engineeringNavigation: NavigationItem[] = [
    { to: inspectionId ? `/jobs/${inspectionId}/gate1` : '/jobs', label: 'Image comparison', icon: ScanLine },
    { to: inspectionId ? `/jobs/${inspectionId}/label` : '/jobs', label: 'Defect visualization', icon: Boxes },
    { to: inspectionId ? `/jobs/${inspectionId}/reports` : '/jobs', label: 'Inspection results', icon: ClipboardList },
  ]
  const { data: activeJob } = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => jobsApi.get(jobId!).then((response) => response.data as { status?: string }),
    enabled: Boolean(jobId && jobId !== 'new'),
    refetchInterval: 5_000,
  })
  const activeStep = location.pathname.includes('/gate1') ? 1
    : location.pathname.includes('/label') ? 2
      : location.pathname.includes('/gate2') ? 3
        : location.pathname.includes('/gate3') || location.pathname.includes('/reports') ? 4
          : location.pathname === '/jobs/new' ? 0
            : -1

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('novaliseo-theme', theme)
  }, [theme])

  return (
    <div className="app-shell">
      <header className="app-topbar">
        <Link to="/" className="brand-lockup" aria-label="Novaliseo overview">
          <div className="brand-mark"><Boxes size={20} strokeWidth={1.8} /></div>
          <div className="brand-copy">
            <div className="brand-name">NOVALISEO</div>
            <div className="brand-caption">QUALITY INTELLIGENCE</div>
          </div>
        </Link>

        <nav className="workflow-nav" aria-label="Inspection workflow">
          {workflowSteps.map((step, index) => {
            const target = index === 0 ? '/jobs/new'
              : jobId && jobId !== 'new'
                ? [`/jobs/${jobId}/gate1`, `/jobs/${jobId}/label`, `/jobs/${jobId}/gate2`, `/jobs/${jobId}/reports`][index - 1]
                : '/jobs'
            return (
              <div key={step} className={`workflow-nav-step${activeStep === index ? ' workflow-nav-step-active' : ''}${activeStep > index ? ' workflow-nav-step-done' : ''}`}>
                <Link to={target} aria-current={activeStep === index ? 'step' : undefined}>
                  <span className="workflow-nav-number">{index + 1}</span>
                  <span className="workflow-nav-copy"><strong>{step}</strong><small>{['Part setup', 'Image capture', 'Detection review', 'Root cause', 'Report approval'][index]}</small></span>
                </Link>
                {index < workflowSteps.length - 1 && <span className="workflow-nav-arrow" aria-hidden="true">›</span>}
              </div>
            )
          })}
        </nav>

        <div className="topbar-actions">
          <Link to="/jobs/new" className="topbar-action topbar-action-primary"><Plus size={14} /> New</Link>
          <Link to="/jobs" className="topbar-action"><FolderOpen size={14} /> Open</Link>
          <button
            type="button"
            className="topbar-icon-button"
            onClick={() => setTheme((current) => current === 'light' ? 'dark' : 'light')}
            title={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
            aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
          >
            {theme === 'light' ? <Moon size={16} /> : <Sun size={16} />}
          </button>
          <Link to="/kb" className="topbar-icon-button" title="Help and knowledge base" aria-label="Help and knowledge base"><BookOpen size={16} /></Link>
          <span className="topbar-user"><UserRound size={15} /><span>Quality Engineer</span></span>
        </div>
      </header>

      <aside className="app-sidebar">
        <div className="sidebar-section-label">PROJECT</div>
        <nav className="sidebar-nav" aria-label="Workspace navigation">
          {primaryNavigation.map((item) => <SidebarLink key={item.to} item={item} />)}
        </nav>

        <div className="sidebar-section-label sidebar-section-spaced">QUALITY ANALYSIS</div>
        <nav className="sidebar-nav" aria-label="Operations navigation">
          {analysisNavigation.map((item) => <SidebarLink key={`${item.to}-${item.label}`} item={item} />)}
        </nav>
        <div className="sidebar-section-label sidebar-section-spaced">ENGINEERING TOOLS</div>
        <nav className="sidebar-nav" aria-label="Engineering tools navigation">
          {engineeringNavigation.map((item) => <SidebarLink key={`${item.to}-${item.label}`} item={item} />)}
        </nav>
        <div className="sidebar-live-state"><span className="sidebar-live-dot" /><span>WORKSPACE</span><strong>READY</strong></div>
      </aside>

      <div className="app-main">
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
      </div>

      <EngineeringAssistant jobId={jobId && jobId !== 'new' ? jobId : undefined} pathname={location.pathname} />

      <footer className="app-footer">
        <span className="footer-ready"><span className="sidebar-live-dot" /> UI READY</span>
        <span>Workspace: {title}</span>
        <span>{jobId && jobId !== 'new' ? `Job ${jobId.slice(0, 8).toUpperCase()} · ${activeJob?.status?.replace(/_/g, ' ') ?? 'STATUS UNAVAILABLE'}` : 'No active inspection'}</span>
        <span><Activity size={12} /> Novaliseo Quality Intelligence</span>
      </footer>
    </div>
  )
}
