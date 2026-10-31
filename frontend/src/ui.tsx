import type { ReactNode } from 'react'

export const STATUS_TONE: Record<string, string> = {
  CREATED: 'status-neutral',
  CAPTURING: 'status-blue',
  DIMENSIONAL: 'status-blue',
  AWAIT_GATE1: 'status-amber',
  DEFECT_DETECTION: 'status-violet',
  AWAIT_LABEL_REVIEW: 'status-orange',
  RETRIEVAL: 'status-blue',
  PREDICTION: 'status-violet',
  AWAIT_GATE2: 'status-violet',
  REPORTING: 'status-teal',
  AWAIT_GATE3: 'status-teal',
  OUTPUT: 'status-green',
  CLOSED: 'status-green',
  ON_HOLD: 'status-red',
  FAILED: 'status-red',
}

export function StatusPill({ status }: { status: string }) {
  return <span className={`status-pill ${STATUS_TONE[status] ?? 'status-neutral'}`}>{status.replace(/_/g, ' ')}</span>
}

export function PageHeading({
  section,
  title,
  description,
  action,
}: {
  section: string
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <header className="page-heading">
      <div>
        <div className="crumbs"><span>QUALITY OPS</span><span>/</span><b>{section.toUpperCase()}</b></div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action}
    </header>
  )
}

export function Loading() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading">
      <div className="skeleton h-14 w-full max-w-sm" />
      <div className="skeleton h-48 w-full" />
    </div>
  )
}

export function Panel({ title, sub, children, className = '' }: { title?: string; sub?: string; children: ReactNode; className?: string }) {
  return (
    <section className={`panel ${className}`}>
      {title && (
        <div className="panel-head">
          <div>
            <h2 className="panel-title">{title}</h2>
            {sub && <p className="panel-sub">{sub}</p>}
          </div>
        </div>
      )}
      <div className="panel-body">{children}</div>
    </section>
  )
}

export function Empty({ icon, title, hint }: { icon: ReactNode; title: string; hint?: string }) {
  return (
    <div className="empty">
      <div className="icon-tile">{icon}</div>
      <p>{title}</p>
      {hint && <p>{hint}</p>}
    </div>
  )
}

export const DOWNLOAD_STYLES = { pdf: 'status-blue', xlsx: 'status-green', docx: 'status-violet' } as const
