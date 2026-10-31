import { useEffect, useId, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  ArrowLeft,
  Check,
  CircleHelp,
  ClipboardCheck,
  Ruler,
  ScanLine,
  TriangleAlert,
  X,
} from 'lucide-react'
import { gatesApi, jobsApi, partsApi } from '../api'

type Measurement = {
  feature_id: string
  feature_type?: string | null
  nominal?: number | null
  measured?: number | null
  deviation?: number | null
  tol_plus?: number | null
  tol_minus?: number | null
  within_tolerance?: boolean | null
}

type GeometryAnnotation = {
  feature_id: string
  kind: 'circle' | 'ellipse' | 'line' | 'polygon'
  points: Array<{ x: number; y: number }>
  radius?: number
  rx?: number
  ry?: number
  rotation?: number
  diameter_px?: number
  label?: string
  status?: ReviewStatus
  confidence?: number
}

type Gate1Data = {
  measurements?: Measurement[]
  captured_image_id?: string | null
  captured_image_url?: string | null
  overlay_image_url?: string | null
  overlay_uri?: string | null
  geometry_annotations?: GeometryAnnotation[]
  geometry_status?: 'detected' | 'uncertain' | 'unavailable'
  geometry_dimensions_px?: { length: number; width: number; calibrated_mm: boolean } | null
  geometry_reason?: string | null
}

type ReferenceImages = {
  cad: string | null
  part: string | null
}

type ReviewStatus = 'pass' | 'fail' | 'warning' | 'unavailable'

function errorMessage(error: any, fallback: string) {
  return error?.response?.data?.detail ?? error?.message ?? fallback
}

function formatValue(value: number | null | undefined, digits = 3) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—'
}

function formatDeviation(value: number | null | undefined) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(3)}`
}

function statusFor(measurement?: Measurement): ReviewStatus {
  if (!measurement) return 'unavailable'
  if (typeof measurement.within_tolerance !== 'boolean') return 'unavailable'
  if (!measurement.within_tolerance) return 'fail'

  const upper = measurement.tol_plus
  const lower = measurement.tol_minus
  const deviation = measurement.deviation
  if (typeof upper !== 'number' || typeof lower !== 'number' || typeof deviation !== 'number') {
    return 'pass'
  }

  const allowed = Math.max(Math.abs(upper), Math.abs(lower))
  return allowed > 0 && Math.abs(deviation) / allowed >= 0.8 ? 'warning' : 'pass'
}

function toleranceLabel(measurement: Measurement) {
  const { tol_plus: upper, tol_minus: lower } = measurement
  const { nominal } = measurement
  if (
    typeof nominal !== 'number'
    || typeof upper !== 'number'
    || typeof lower !== 'number'
    || !Number.isFinite(nominal)
    || !Number.isFinite(upper)
    || !Number.isFinite(lower)
  ) return '—'
  return `${(nominal - Math.abs(lower)).toFixed(3)} to ${(nominal + Math.abs(upper)).toFixed(3)} mm`
}

function browserImageUrl(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const candidate = value.trim()
  if (/^(https?:\/\/|\/|blob:|data:image\/)/i.test(candidate)) return candidate
  return null
}

function statusLabel(status: ReviewStatus) {
  if (status === 'pass') return 'Within tolerance'
  if (status === 'fail') return 'Out of tolerance'
  if (status === 'warning') return 'Near limit'
  return 'Unavailable'
}

function MeasurementStatus({ status }: { status: ReviewStatus }) {
  const Icon = status === 'pass' ? Check : status === 'fail' ? X : status === 'warning' ? TriangleAlert : CircleHelp
  return (
    <span className={`gate1-status gate1-status-${status}`}>
      <Icon size={13} strokeWidth={2} />
      {statusLabel(status)}
    </span>
  )
}

function GeometryOverlay({
  annotations,
  measurements,
  width,
  height,
  selectedFeatureId,
}: {
  annotations: GeometryAnnotation[]
  measurements: Measurement[]
  width: number
  height: number
  selectedFeatureId: string | null
}) {
  const markerId = useId().replace(/:/g, '')
  const measurementById = new Map(measurements.map((measurement) => [measurement.feature_id, measurement]))
  const colorByStatus: Record<ReviewStatus, string> = {
    pass: '#36805d',
    warning: '#c17a21',
    fail: '#c3443e',
    unavailable: '#3975a4',
  }
  const colorFor = (id: string) => {
    const status = statusFor(measurementById.get(id))
    return colorByStatus[status]
  }

  return (
    <svg
      className="gate1-geometry-overlay"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      aria-label="Geometry annotations supplied by the inspection data"
    >
      <defs>
        {(Object.entries(colorByStatus) as Array<[ReviewStatus, string]>).map(([status, color]) => (
          <marker
            key={status}
            id={`${markerId}-${status}`}
            markerWidth="7"
            markerHeight="7"
            refX="3.5"
            refY="3.5"
            orient="auto-start-reverse"
            markerUnits="strokeWidth"
          >
            <path d="M 0 0 L 7 3.5 L 0 7 z" fill={color} />
          </marker>
        ))}
      </defs>
      {annotations.map((annotation, index) => {
        const measurement = measurementById.get(annotation.feature_id)
        const status = measurement
          ? statusFor(measurement)
          : annotation.status ?? 'unavailable'
        const color = measurement ? colorFor(annotation.feature_id) : colorByStatus[status]
        const selected = selectedFeatureId === annotation.feature_id
        const measuredLabel = typeof measurement?.measured === 'number'
          ? `${annotation.kind === 'circle' || annotation.kind === 'ellipse' ? 'Ø' : ''}${formatValue(measurement.measured)} mm`
          : typeof annotation.diameter_px === 'number'
            ? `Ø${annotation.diameter_px.toFixed(1)} px`
            : null
        const nominalLabel = typeof measurement?.nominal === 'number'
          ? `REF ${formatValue(measurement.nominal)} mm`
          : null
        const deviationLabel = typeof measurement?.deviation === 'number'
          ? `Δ ${formatDeviation(measurement.deviation)} mm`
          : null
        const points = annotation.points ?? []
        const scaledPoints = points.map((point) => ({
          x: point.x * width,
          y: point.y * height,
        }))

        if ((annotation.kind === 'circle' || annotation.kind === 'ellipse') && scaledPoints[0]) {
          const center = scaledPoints[0]
          const radiusX = (annotation.rx ?? annotation.radius ?? 0) * Math.min(width, height)
          const radiusY = (annotation.ry ?? annotation.radius ?? 0) * Math.min(width, height)
          const angle = ((annotation.rotation ?? 0) * Math.PI) / 180
          const diameterX = radiusX * Math.cos(angle)
          const diameterY = radiusX * Math.sin(angle)
          return (
            <g key={`${annotation.feature_id}-${index}`}>
              {annotation.kind === 'ellipse' ? (
                <ellipse
                  cx={center.x}
                  cy={center.y}
                  rx={radiusX}
                  ry={radiusY}
                  transform={`rotate(${annotation.rotation ?? 0} ${center.x} ${center.y})`}
                  fill="none"
                  stroke={color}
                  strokeWidth={selected ? Math.max(width / 350, 2) : Math.max(width / 500, 1)}
                />
              ) : (
                <circle
                  cx={center.x}
                  cy={center.y}
                  r={radiusX}
                  fill="none"
                  stroke={color}
                  strokeWidth={selected ? Math.max(width / 350, 2) : Math.max(width / 500, 1)}
                />
              )}
              <line
                x1={center.x - diameterX}
                y1={center.y - diameterY}
                x2={center.x + diameterX}
                y2={center.y + diameterY}
                stroke={color}
                strokeWidth={Math.max(width / 850, 1)}
                markerStart={`url(#${markerId}-${status})`}
                markerEnd={`url(#${markerId}-${status})`}
              />
              <path
                d={`M ${center.x - width * 0.015} ${center.y} H ${center.x + width * 0.015} M ${center.x} ${center.y - height * 0.015} V ${center.y + height * 0.015}`}
                stroke={color}
                strokeWidth={Math.max(width / 700, 1)}
              />
              {(annotation.label || measuredLabel) && (
                <text x={center.x + width * 0.02} y={center.y - height * 0.02} fill={color}>
                  {measuredLabel ? `${annotation.feature_id} · ${measuredLabel}` : annotation.label}
                  {nominalLabel && <tspan x={center.x + width * 0.02} dy="1.2em">{nominalLabel}</tspan>}
                  {deviationLabel && <tspan x={center.x + width * 0.02} dy="1.2em">{deviationLabel}</tspan>}
                </text>
              )}
            </g>
          )
        }

        if (annotation.kind === 'line' && scaledPoints.length >= 2) {
          const [start, end] = scaledPoints
          return (
            <g key={`${annotation.feature_id}-${index}`}>
              <line
                x1={start.x}
                y1={start.y}
                x2={end.x}
                y2={end.y}
                stroke={color}
                strokeWidth={Math.max(width / 500, 1)}
                markerStart={`url(#${markerId}-${status})`}
                markerEnd={`url(#${markerId}-${status})`}
              />
              <path
                d={`M ${start.x} ${start.y - height * 0.01} V ${start.y + height * 0.01} M ${end.x} ${end.y - height * 0.01} V ${end.y + height * 0.01}`}
                stroke={color}
                strokeWidth={Math.max(width / 700, 1)}
              />
              {(annotation.label || measuredLabel) && (
                <text x={(start.x + end.x) / 2} y={(start.y + end.y) / 2 - height * 0.015} fill={color}>
                  {measuredLabel ? `${annotation.feature_id} · ${measuredLabel}` : annotation.label}
                  {nominalLabel && <tspan x={(start.x + end.x) / 2} dy="1.2em">{nominalLabel}</tspan>}
                  {deviationLabel && <tspan x={(start.x + end.x) / 2} dy="1.2em">{deviationLabel}</tspan>}
                </text>
              )}
            </g>
          )
        }

        if (annotation.kind === 'polygon' && scaledPoints.length >= 3) {
          return (
            <g key={`${annotation.feature_id}-${index}`}>
              <polygon
                points={scaledPoints.map((point) => `${point.x},${point.y}`).join(' ')}
                fill="none"
                stroke={color}
                strokeWidth={selected ? Math.max(width / 350, 2) : Math.max(width / 500, 1)}
              />
              {(annotation.label || measuredLabel) && (
                <text x={scaledPoints[0].x} y={scaledPoints[0].y - height * 0.015} fill={color}>
                  {measuredLabel ? `${annotation.feature_id} · ${measuredLabel}` : annotation.label}
                  {nominalLabel && <tspan x={scaledPoints[0].x} dy="1.2em">{nominalLabel}</tspan>}
                  {deviationLabel && <tspan x={scaledPoints[0].x} dy="1.2em">{deviationLabel}</tspan>}
                </text>
              )}
            </g>
          )
        }
        return null
      })}
    </svg>
  )
}

function ImagePanel({
  number,
  title,
  subtitle,
  imageUrl,
  imageAlt,
  badge,
  measurements,
  annotations,
  note,
  selectedFeatureId,
  onLoad,
}: {
  number: string
  title: string
  subtitle: string
  imageUrl: string | null
  imageAlt: string
  badge?: string
  measurements: Measurement[]
  annotations: GeometryAnnotation[]
  note?: string
  selectedFeatureId: string | null
  onLoad?: (width: number, height: number) => void
}) {
  const [dimensions, setDimensions] = useState<{ width: number; height: number } | null>(null)

  return (
    <article className={`gate1-image-card gate1-image-card-${number}`}>
      <header className="gate1-image-heading">
        <span className="gate1-panel-index">{number}</span>
        <div className="gate1-image-title">
          <h3>{title}</h3>
          <p>{subtitle}</p>
        </div>
        {badge && <span className="gate1-image-badge">{badge}</span>}
      </header>
      <div className="gate1-image-stage">
        {imageUrl ? (
          <>
            <img
              src={imageUrl}
              alt={imageAlt}
              onLoad={(event) => {
                const { naturalWidth, naturalHeight } = event.currentTarget
                setDimensions({ width: naturalWidth, height: naturalHeight })
                onLoad?.(naturalWidth, naturalHeight)
              }}
            />
            {dimensions && annotations.length > 0 && (
              <GeometryOverlay
                annotations={annotations}
                measurements={measurements}
                width={dimensions.width}
                height={dimensions.height}
                selectedFeatureId={selectedFeatureId}
              />
            )}
          </>
        ) : (
          <div className="gate1-image-unavailable">
            <ScanLine size={23} strokeWidth={1.5} />
            <strong>Image unavailable</strong>
            <span>No browser-accessible image was supplied for this inspection.</span>
          </div>
        )}
      </div>
      {note && <p className="gate1-image-note">{note}</p>}
      {annotations.length > 0 && (
        <p className="gate1-annotation-note">
          {annotations.length} OpenCV geometry annotation{annotations.length === 1 ? '' : 's'} from this capture
        </p>
      )}
    </article>
  )
}

export default function Gate1Review() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const [decision, setDecision] = useState<'confirm' | 'reject' | 'override'>('confirm')
  const [reasonCode, setReasonCode] = useState('')
  const [comments, setComments] = useState('')
  const [referenceImages, setReferenceImages] = useState<ReferenceImages>({ cad: null, part: null })
  const [referenceError, setReferenceError] = useState('')
  const [capturedAssetUrl, setCapturedAssetUrl] = useState<string | null>(null)
  const [captureError, setCaptureError] = useState('')
  const [selectedFeatureId, setSelectedFeatureId] = useState<string | null>(null)

  const gateQuery = useQuery({
    queryKey: ['gate1', jobId],
    queryFn: () => gatesApi.getGate1(jobId!).then((response) => response.data as Gate1Data),
    enabled: Boolean(jobId),
  })
  const jobQuery = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => jobsApi.get(jobId!).then((response) => response.data),
    enabled: Boolean(jobId),
  })

  const partNumber = jobQuery.data?.part_number as string | undefined
  useEffect(() => {
    let active = true
    let objectUrls: string[] = []
    setReferenceImages({ cad: null, part: null })
    setReferenceError('')
    if (!partNumber) return

    const loadImages = async () => {
      try {
        const metadata = (await partsApi.references(partNumber)).data
        if (!metadata.configured) return
        const [cad, part] = await Promise.all([
          partsApi.referenceImage(partNumber, 'cad'),
          partsApi.referenceImage(partNumber, 'image'),
        ])
        if (!active) return
        objectUrls = [URL.createObjectURL(cad.data), URL.createObjectURL(part.data)]
        setReferenceImages({ cad: objectUrls[0], part: objectUrls[1] })
      } catch (error) {
        if (active) setReferenceError(errorMessage(error, 'Could not load the registered part images.'))
      }
    }

    void loadImages()
    return () => {
      active = false
      objectUrls.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [partNumber])

  const submit = useMutation({
    mutationFn: (payload: { decision: string; reason_code?: string; comments: string }) =>
      gatesApi.submitGate1(jobId!, payload),
    onSuccess: () => navigate(`/jobs/${jobId}`),
  })

  const data = gateQuery.data ?? {}
  const measurements = Array.isArray(data.measurements) ? data.measurements : []
  useEffect(() => {
    let active = true
    let objectUrl: string | null = null
    setCapturedAssetUrl(null)
    setCaptureError('')

    if (!jobId || !data.captured_image_id) return

    jobsApi.captureImage(jobId, data.captured_image_id)
      .then((response) => {
        objectUrl = URL.createObjectURL(response.data)
        if (active) setCapturedAssetUrl(objectUrl)
        else URL.revokeObjectURL(objectUrl)
      })
      .catch((error) => {
        if (active) setCaptureError(errorMessage(error, 'Could not load the stored inspection capture.'))
      })

    return () => {
      active = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [jobId, data.captured_image_id])

  const passCount = measurements.filter((measurement) => statusFor(measurement) === 'pass').length
  const warningCount = measurements.filter((measurement) => statusFor(measurement) === 'warning').length
  const failCount = measurements.filter((measurement) => statusFor(measurement) === 'fail').length
  const unavailableCount = measurements.filter((measurement) => statusFor(measurement) === 'unavailable').length
  const allStatusesAvailable = measurements.length > 0 && unavailableCount === 0
  const overallStatus: ReviewStatus = !allStatusesAvailable
    ? 'unavailable'
    : failCount > 0
      ? 'fail'
      : warningCount > 0
        ? 'warning'
        : 'pass'
  const capturedImage = browserImageUrl(data.captured_image_url) ?? capturedAssetUrl
  const overlayImage = browserImageUrl(data.overlay_image_url)
  const overlayIsServerLocal = typeof data.overlay_uri === 'string' && !browserImageUrl(data.overlay_uri)
  const displayImage = capturedImage ?? overlayImage ?? referenceImages.part
  const displayImageLabel = capturedImage
    ? 'Captured component image with computer-vision annotations'
    : overlayImage
      ? 'Inspection dimensional overlay'
      : 'Registered component reference photograph'
  const annotations = Array.isArray(data.geometry_annotations) ? data.geometry_annotations : []
  const geometryFeatureIds = new Set(annotations.map((annotation) => annotation.feature_id))

  if (gateQuery.isLoading || jobQuery.isLoading) {
    return <div className="gate1-state-message">Loading dimensional inspection data…</div>
  }

  if (gateQuery.isError || jobQuery.isError) {
    const error = gateQuery.error ?? jobQuery.error
    return (
      <div className="gate1-state-message gate1-state-error" role="alert">
        <strong>Could not load the dimensional review.</strong>
        <span>{errorMessage(error, 'Please check the API connection and try again.')}</span>
        <button type="button" className="btn-secondary" onClick={() => {
          void gateQuery.refetch()
          void jobQuery.refetch()
        }}>Retry</button>
      </div>
    )
  }

  return (
    <div className="gate1-page">
      <header className="gate1-page-heading">
        <div>
          <div className="gate1-breadcrumb">QUALITY OPERATIONS <span>/</span> DIMENSIONAL REVIEW</div>
          <h1>2D dimensional inspection</h1>
          <p>Compare the registered engineering drawing with inspection images and measured feature results.</p>
        </div>
        <Link to={`/jobs/${jobId}`} className="gate1-back-link"><ArrowLeft size={15} /> Job details</Link>
      </header>

      <section className={`gate1-result-banner gate1-result-${overallStatus}`} aria-live="polite">
        <div className="gate1-result-symbol">
          {overallStatus === 'pass' ? <Check size={19} /> : overallStatus === 'fail' ? <X size={19} /> : overallStatus === 'warning' ? <TriangleAlert size={19} /> : <CircleHelp size={19} />}
        </div>
        <div className="gate1-result-copy">
          <span className="gate1-eyebrow">DIMENSIONAL INSPECTION RESULT</span>
          <strong>
            {overallStatus === 'pass' ? 'PASS' : overallStatus === 'fail' ? 'FAIL' : overallStatus === 'warning' ? 'PASS · NEAR LIMIT' : 'RESULT UNAVAILABLE'}
          </strong>
          <span>
            {allStatusesAvailable
              ? `${measurements.length} measured features reviewed`
              : 'A complete result requires inspection measurements with tolerance status.'}
          </span>
        </div>
        <div className="gate1-result-counts">
          <span className="gate1-count gate1-count-pass"><Check size={13} />{passCount} Within</span>
          <span className="gate1-count gate1-count-warning"><TriangleAlert size={13} />{warningCount} Near limit</span>
          <span className="gate1-count gate1-count-fail"><X size={13} />{failCount} Out</span>
          {unavailableCount > 0 && <span className="gate1-count gate1-count-neutral"><CircleHelp size={13} />{unavailableCount} Unavailable</span>}
        </div>
      </section>

      <section className="gate1-comparison panel">
        <div className="gate1-section-heading">
          <div className="gate1-section-title">
            <span className="gate1-section-icon"><Ruler size={17} /></span>
            <div>
              <h2>Drawing and component comparison</h2>
              <p>{partNumber ? `Part ${partNumber}` : 'Registered part'} · dimensions shown in millimetres</p>
            </div>
          </div>
          <div className="gate1-legend" aria-label="Measurement color key">
            <span><i className="gate1-legend-blue" />Reference / geometry</span>
            <span><i className="gate1-legend-green" />Within tolerance</span>
            <span><i className="gate1-legend-orange" />Near limit</span>
            <span><i className="gate1-legend-red" />Out of tolerance</span>
          </div>
        </div>

        <ol className="gate1-inspection-flow" aria-label="Dimensional inspection sequence">
          <li><span>01</span>Reference drawing</li>
          <li><span>02</span>Captured component</li>
          <li><span>03</span>Computer-vision geometry</li>
          <li><span>04</span>Tolerance analysis</li>
        </ol>

        <div className="gate1-comparison-grid">
          <ImagePanel
            number="01"
            title="Reference 2D CAD drawing"
            subtitle="Registered drawing · dimensions as supplied"
            imageUrl={referenceImages.cad}
            imageAlt="Registered raster CAD drawing for the selected part"
            badge="REFERENCE"
            measurements={measurements}
            annotations={[]}
            selectedFeatureId={selectedFeatureId}
            note={referenceError || 'Drawing annotations are preserved in the registered source image.'}
          />
          <ImagePanel
            number="02"
            title={capturedImage ? 'Captured component image' : overlayImage ? 'Inspection overlay' : 'Registered component reference'}
            subtitle={capturedImage
              ? data.geometry_status === 'uncertain'
                ? 'OpenCV geometry candidate · verify highlighted features'
                : data.geometry_status === 'detected'
                  ? 'OpenCV geometry detection · image-space dimensions'
                  : 'No reliable contour isolated from this capture'
              : overlayImage
                ? 'Computer-vision dimensional overlay'
                : 'Registered part photo'}
            imageUrl={displayImage}
            imageAlt={displayImageLabel}
            badge={overlayImage || capturedImage ? 'INSPECTION' : referenceImages.part ? 'REFERENCE ONLY' : undefined}
            measurements={measurements}
            annotations={capturedImage ? annotations : []}
            selectedFeatureId={selectedFeatureId}
            note={
              capturedImage
                ? captureError || data.geometry_reason || (annotations.length > 0
                  ? 'Contours and circular-feature candidates are extracted from this capture. Dimensions are image-space only unless calibrated.'
                  : 'No contour or circular features could be isolated from this capture.')
                : overlayImage
                  ? 'This inspection overlay is shown as supplied. No captured-image geometry is available to align.'
                : overlayIsServerLocal
                  ? 'The API returned a server-local overlay path, which this browser cannot display. The registered photo is reference-only, not the inspected part.'
                  : captureError || 'No browser-accessible capture is available for this job. The registered photo is reference-only, not the inspected part.'
            }
          />
        </div>
        {capturedImage && data.geometry_dimensions_px && (
          <div className={`gate1-geometry-summary${data.geometry_status === 'uncertain' ? ' gate1-geometry-summary-warning' : ''}`}>
            <div>
              <span>Detected image-space length</span>
              <strong>{data.geometry_dimensions_px.length.toFixed(1)} px</strong>
            </div>
            <div>
              <span>Detected image-space width</span>
              <strong>{data.geometry_dimensions_px.width.toFixed(1)} px</strong>
            </div>
            <div>
              <span>Physical calibration</span>
              <strong>Unavailable · px only</strong>
            </div>
            <span className="gate1-geometry-summary-state">
              {data.geometry_status === 'uncertain' ? 'Contour candidate · verify' : 'Image geometry extracted'}
            </span>
          </div>
        )}
        {referenceError && <p className="gate1-reference-error" role="status">{referenceError}</p>}
      </section>

      <section className="gate1-measurements panel">
        <div className="gate1-section-heading gate1-table-heading">
          <div className="gate1-section-title">
            <span className="gate1-section-icon"><ClipboardCheck size={17} /></span>
            <div>
              <h2>Measured feature results</h2>
              <p>Expected dimensions, measured values and tolerance status returned by the inspection workflow.</p>
            </div>
          </div>
          <span className="gate1-feature-count">{measurements.length} feature{measurements.length === 1 ? '' : 's'}</span>
        </div>
        <div className="gate1-table-wrap">
          <table className="gate1-table">
            <thead>
              <tr>
                <th scope="col">Feature</th>
                <th scope="col">Expected</th>
                <th scope="col">Actual</th>
                <th scope="col">Deviation</th>
                <th scope="col">Allowed range</th>
                <th scope="col">Inspection status</th>
              </tr>
            </thead>
            <tbody>
              {measurements.map((measurement) => {
                const status = statusFor(measurement)
                return (
                  <tr key={measurement.feature_id} className={`gate1-row-${status}`}>
                    <th scope="row">
                      <button
                        type="button"
                        className={`gate1-feature-select${selectedFeatureId === measurement.feature_id ? ' gate1-feature-selected' : ''}`}
                        onClick={() => setSelectedFeatureId((current) => current === measurement.feature_id ? null : measurement.feature_id)}
                        aria-pressed={selectedFeatureId === measurement.feature_id}
                        disabled={!geometryFeatureIds.has(measurement.feature_id)}
                        title={geometryFeatureIds.has(measurement.feature_id)
                          ? 'Highlight this feature in the inspection image'
                          : 'No inspected geometry is mapped to this measurement ID'}
                      >
                        <span className="gate1-feature-id">{measurement.feature_id}</span>
                      </button>
                      {measurement.feature_type && <span className="gate1-feature-type">{measurement.feature_type}</span>}
                    </th>
                    <td>{formatValue(measurement.nominal)} <span className="gate1-unit">mm</span></td>
                    <td className="gate1-actual-value">{formatValue(measurement.measured)} <span className="gate1-unit">mm</span></td>
                    <td className="gate1-deviation">{formatDeviation(measurement.deviation)} <span className="gate1-unit">mm</span></td>
                    <td className="gate1-tolerance">{toleranceLabel(measurement)}</td>
                    <td><MeasurementStatus status={status} /></td>
                  </tr>
                )
              })}
              {measurements.length === 0 && (
                <tr>
                  <td colSpan={6} className="gate1-empty-row">
                    No measurement rows were returned for this job. Values and status are not inferred.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="gate1-decision panel">
        <div className="gate1-section-heading">
          <div className="gate1-section-title">
            <span className="gate1-section-icon"><ClipboardCheck size={17} /></span>
            <div>
              <h2>Engineer decision</h2>
              <p>Record the review decision for this dimensional inspection.</p>
            </div>
          </div>
          <span className="gate1-job-id">JOB {jobId}</span>
        </div>

        <div className="gate1-decision-body">
          <div className="gate1-decision-options" role="group" aria-label="Review decision">
            {(['confirm', 'reject', 'override'] as const).map((option) => (
              <button
                type="button"
                key={option}
                onClick={() => setDecision(option)}
                className={`gate1-decision-button${decision === option ? ' gate1-decision-selected' : ''}`}
                aria-pressed={decision === option}
              >
                {option === 'confirm' ? <Check size={15} /> : option === 'reject' ? <X size={15} /> : <TriangleAlert size={15} />}
                {option === 'confirm' ? 'Confirm result' : option === 'reject' ? 'Reject / remeasure' : 'Override result'}
              </button>
            ))}
          </div>

          {decision === 'override' && (
            <label className="gate1-form-field">
              <span>Reason code <b>Required</b></span>
              <input
                value={reasonCode}
                onChange={(event) => setReasonCode(event.target.value)}
                placeholder="e.g. calibration_error"
              />
            </label>
          )}

          <label className="gate1-form-field">
            <span>Review comments <small>Optional</small></span>
            <textarea
              value={comments}
              onChange={(event) => setComments(event.target.value)}
              rows={3}
              placeholder="Add context for the inspection record"
            />
          </label>

          {submit.isError && (
            <p className="gate1-submit-error" role="alert">
              {errorMessage(submit.error, 'Could not submit the review decision.')}
            </p>
          )}

          <div className="gate1-submit-row">
            <p>Submission records your decision and returns to the job summary.</p>
            <button
              type="button"
              onClick={() => submit.mutate({ decision, reason_code: reasonCode || undefined, comments })}
              disabled={submit.isPending || (decision === 'override' && !reasonCode.trim())}
              className="btn-primary gate1-submit-button"
            >
              {submit.isPending ? 'Submitting…' : 'Submit decision'}
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}
