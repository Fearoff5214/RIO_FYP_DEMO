import { useEffect, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, LoaderCircle, ScanLine, Search, Sparkles } from 'lucide-react'
import { gatesApi, jobsApi, kbApi, rcaApi, type RcaResult } from '../api'

type JobContext = {
  status?: string
  part_number?: string | null
  dimensional_status?: string | null
  defects?: Array<{
    defect_id: string
    defect_type: string
    severity: string
    confidence: number
    size_mm2?: number | null
  }>
  measurements?: Array<{
    feature_id: string
    nominal: number
    measured: number
    deviation: number
    within_tolerance: boolean
  }>
  flags?: string[]
}

type Gate2Context = {
  top3?: Array<{
    rank: number
    cause: string
    effect: string
    confidence_cal: number
    corrective_actions?: string[]
  }>
}

type KnowledgeResult = {
  chunk_id?: string
  text?: string
  score?: number
  defect_type?: string | null
  cause?: string | null
}

type KnowledgeSearchResponse = {
  results?: KnowledgeResult[]
}

type LiveInspectionContext = {
  partNumber: string
  detectedCount: number
  selectedDefect: { id: string; type: string; confidence: number; note: string | null } | null
  analysis: { cause: string; actions: string[] } | null
}

export default function EngineeringAssistant({ jobId, pathname }: { jobId?: string; pathname: string }) {
  const [question, setQuestion] = useState('')
  const [liveContext, setLiveContext] = useState<LiveInspectionContext | null>(null)
  useEffect(() => {
    const updateContext = (event: Event) => {
      setLiveContext((event as CustomEvent<LiveInspectionContext | null>).detail)
    }
    window.addEventListener('novaliseo-live-context', updateContext)
    const savedContext = sessionStorage.getItem('novaliseo-live-context')
    if (savedContext) setLiveContext(JSON.parse(savedContext) as LiveInspectionContext)
    return () => window.removeEventListener('novaliseo-live-context', updateContext)
  }, [])
  const jobQuery = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => jobsApi.get(jobId!).then((response) => response.data as JobContext),
    enabled: Boolean(jobId),
    refetchInterval: 5_000,
  })
  const isGate2 = Boolean(jobId && pathname.includes('/gate2'))
  const gate2Query = useQuery({
    queryKey: ['gate2', jobId],
    queryFn: () => gatesApi.getGate2(jobId!).then((response) => response.data as Gate2Context),
    enabled: isGate2,
  })
  const analysis = useMutation({
    mutationFn: () => {
      const job = jobQuery.data as JobContext
      return rcaApi.analyze({
        defects: (job.defects ?? []).map((defect) => ({
          defect_type: defect.defect_type,
          confidence: defect.confidence,
        })),
        measurements: job.measurements ?? [],
      }).then((response) => response.data)
    },
  })
  const knowledgeSearch = useMutation({
    mutationFn: (query: string) => kbApi.search(query).then((response) => response.data as KnowledgeSearchResponse),
  })

  const job = jobQuery.data as JobContext | undefined
  const defects = job?.defects ?? []
  const criticalCount = defects.filter((defect) => defect.severity.toLowerCase() === 'critical').length
  const outOfTolerance = (job?.measurements ?? []).filter((measurement) => !measurement.within_tolerance)
  const rankedCauses = (gate2Query.data as Gate2Context | undefined)?.top3 ?? []
  const result = analysis.data as RcaResult | undefined

  return (
    <aside className="assistant-rail" aria-label="AI engineering assistant">
      <div className="assistant-heading">
        <span className="assistant-mark"><Sparkles size={16} /></span>
        <div><strong>AI Engineering Assistant</strong><small>INSPECTION INTELLIGENCE</small></div>
      </div>

      {!jobId && !liveContext ? (
        <div className="assistant-empty">
          <ScanLine size={18} />
          <strong>No inspection selected</strong>
          <span>Inspection findings and AI analysis will appear here when a job is open.</span>
        </div>
      ) : !jobId && liveContext ? (
        <section className="assistant-section assistant-live-context">
          <div className="assistant-section-title">LIVE INSPECTION <span>PRE-VERIFICATION</span></div>
          <strong className="assistant-part">{liveContext.partNumber || 'Part number unavailable'}</strong>
          <div className="assistant-checks">
            <div><ScanLine size={14} /><span>{liveContext.detectedCount} defect{liveContext.detectedCount === 1 ? '' : 's'} detected</span></div>
          </div>
          {liveContext.selectedDefect ? (
            <article className="assistant-cause assistant-selected-defect">
              <div><span>SELECTED REGION · {liveContext.selectedDefect.id}</span><strong>{Math.round(liveContext.selectedDefect.confidence * 100)}%</strong></div>
              <b>{liveContext.selectedDefect.type.replace(/_/g, ' ')}</b>
              {liveContext.selectedDefect.note && <p>{liveContext.selectedDefect.note}</p>}
            </article>
          ) : <p className="assistant-muted">Select a detected region to load its context here.</p>}
          {liveContext.analysis && (
            <div className="assistant-analysis-result assistant-live-analysis">
              <span>ROOT CAUSE</span><strong>{liveContext.analysis.cause}</strong>
              {liveContext.analysis.actions.length > 0 && <div><span>RECOMMENDED ACTIONS</span><ul>{liveContext.analysis.actions.slice(0, 3).map((action) => <li key={action}>{action}</li>)}</ul></div>}
            </div>
          )}
          <div className="assistant-suggested-questions">
            {[
              'Why was this defect detected?',
              'Show the zoomed view of the critical defect.',
              'What is the probable root cause?',
              'Which defect requires immediate attention?',
              'What corrective action is recommended?',
              'Compare the reference and captured images.',
            ].map((prompt) => (
              <button type="button" key={prompt} onClick={() => setQuestion(prompt)}>{prompt}</button>
            ))}
          </div>
        </section>
      ) : jobQuery.isLoading ? (
        <div className="assistant-state"><LoaderCircle size={15} className="animate-spin" /> Loading inspection data</div>
      ) : jobQuery.isError || !job ? (
        <div className="assistant-state assistant-state-warning"><AlertTriangle size={15} /> Could not load this inspection's analysis context.</div>
      ) : (
        <>
          <section className="assistant-section">
            <div className="assistant-section-title">CURRENT INSPECTION <span>{job.status?.replace(/_/g, ' ') ?? 'STATUS UNAVAILABLE'}</span></div>
            <strong className="assistant-part">{job.part_number ?? 'Part number unavailable'}</strong>
            <div className="assistant-checks">
              <div><CheckCircle2 size={14} /><span>{defects.length} detected defect{defects.length === 1 ? '' : 's'}</span></div>
              <div className={criticalCount ? 'assistant-warning' : ''}><AlertTriangle size={14} /><span>{criticalCount} critical region{criticalCount === 1 ? '' : 's'}</span></div>
              <div className={outOfTolerance.length ? 'assistant-warning' : ''}><ScanLine size={14} /><span>{outOfTolerance.length} out-of-tolerance measurement{outOfTolerance.length === 1 ? '' : 's'}</span></div>
            </div>
            {job.flags && job.flags.length > 0 && <p className="assistant-flags">Flags: {job.flags.join(', ').replace(/_/g, ' ')}</p>}
          </section>

          {isGate2 && (
            <section className="assistant-section">
              <div className="assistant-section-title">ROOT CAUSE PREDICTIONS</div>
              {gate2Query.isLoading ? <p className="assistant-muted">Loading ranked predictions…</p> : rankedCauses.length ? rankedCauses.slice(0, 3).map((cause) => (
                <article className="assistant-cause" key={cause.rank}>
                  <div><span>RANK {cause.rank}</span><strong>{Math.round(cause.confidence_cal * 100)}%</strong></div>
                  <b>{cause.cause}</b>
                  <p>{cause.effect}</p>
                </article>
              )) : <p className="assistant-muted">No ranked predictions were returned for this inspection.</p>}
            </section>
          )}

          <section className="assistant-section assistant-analysis-section">
            <div className="assistant-section-title">AI ANALYSIS</div>
            {result ? (
              <div className="assistant-analysis-result">
                {!result.ai_used && <p className="assistant-state-warning">AI analysis is unavailable; the service returned its offline response.</p>}
                <span>ROOT CAUSE</span>
                <strong>{result.root_cause.cause}</strong>
                {result.root_cause.rationale && <p>{result.root_cause.rationale}</p>}
                {result.root_cause.corrective_actions.length > 0 && (
                  <div><span>RECOMMENDED ACTIONS</span><ul>{result.root_cause.corrective_actions.slice(0, 3).map((action) => <li key={action}>{action}</li>)}</ul></div>
                )}
              </div>
            ) : (
              <p className="assistant-muted">{defects.length ? 'Run an analysis using the findings recorded for this job.' : 'No defects are recorded for analysis.'}</p>
            )}
            {analysis.isError && <p className="assistant-state-warning">The root cause analysis request failed. Check the API connection and retry.</p>}
            <button
              type="button"
              className="assistant-analyze-button"
              onClick={() => analysis.mutate()}
              disabled={!defects.length || analysis.isPending}
            >
              {analysis.isPending ? <LoaderCircle size={14} className="animate-spin" /> : <Sparkles size={14} />}
              {analysis.isPending ? 'Analyzing findings…' : 'Analyze current findings'}
            </button>
          </section>

        </>
      )}
      <form
        className="assistant-query"
        onSubmit={(event) => {
          event.preventDefault()
          const query = question.trim()
          if (query) {
            const contextQuery = !jobId && liveContext?.selectedDefect
              ? `${query} Defect: ${liveContext.selectedDefect.type.replace(/_/g, ' ')}; confidence: ${Math.round(liveContext.selectedDefect.confidence * 100)}%.`
              : query
            knowledgeSearch.mutate(contextQuery)
          }
        }}
      >
        <label htmlFor="assistant-question">ASK INSPECTION GUIDANCE</label>
        <div className="assistant-query-row">
          <input
            id="assistant-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Search defects, causes, or actions"
            aria-label="Search inspection guidance"
          />
          <button type="submit" disabled={!question.trim() || knowledgeSearch.isPending} aria-label="Search inspection guidance" title="Search inspection guidance">
            {knowledgeSearch.isPending ? <LoaderCircle size={14} className="animate-spin" /> : <Search size={14} />}
          </button>
        </div>
        {knowledgeSearch.isError && <p className="assistant-query-message assistant-query-error">Knowledge-base search failed. Check the API connection and retry.</p>}
        {knowledgeSearch.data && (
          <div className="assistant-search-results" aria-live="polite">
            <span>RETRIEVED SOURCES</span>
            {knowledgeSearch.data.results?.length ? knowledgeSearch.data.results.slice(0, 3).map((source, index) => (
              <article key={source.chunk_id ?? `${source.cause}-${index}`}>
                <div><strong>{source.defect_type ?? 'Reference'}{source.cause ? ` · ${source.cause}` : ''}</strong>{typeof source.score === 'number' && <small>{source.score.toFixed(2)}</small>}</div>
                <p>{source.text}</p>
              </article>
            )) : <p className="assistant-query-message">No matching knowledge-base sources were returned.</p>}
          </div>
        )}
      </form>
    </aside>
  )
}