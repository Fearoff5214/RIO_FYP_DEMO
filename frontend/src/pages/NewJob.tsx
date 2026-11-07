import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertCircle,
  Camera,
  Check,
  FileImage,
  Layers,
  LoaderCircle,
  Maximize2,
  Move,
  RefreshCw,
  ScanLine,
  Upload,
  Video,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import { demoApi, jobsApi, partsApi, rcaApi, type LiveDefect, type LiveDetection, type RcaResult, type RcaStatus } from '../api'

type Verification = {
  status: 'Match' | 'Mismatch' | 'Needs Manual Inspection'
  score: number | null
  threshold: number
  feature_matches: number
  feature_match_percent?: number | null
  geometric_inliers: number | null
  edge_overlap: number | null
  alignment_status?: 'aligned' | 'required'
  visualizations?: {
    aligned_overlay?: string
    difference_image?: string
    difference_heatmap?: string
    matched_features?: string
  }
  reference_kind?: 'physical_part' | 'cad_drawing'
  differences: string[]
  verification_id: string
}

type References = {
  configured: boolean
  part_name: string
  drawing_rev: string
  score_threshold: number
}

function errorMessage(error: any, fallback: string) {
  return error?.response?.data?.detail ?? error?.message ?? fallback
}

function formatPercent(value: number | null | undefined) {
  return value == null ? 'Not available' : `${(value * 100).toFixed(1)}%`
}

function formatCount(value: number | null | undefined) {
  return value == null ? 'Not available' : String(value)
}

const DEMO_SECONDS_PER_FRAME = 6

const DEFECT_COLORS: Record<string, string> = {
  scratch: '#fbc02d',
  dent: '#fb8c00',
  crack: '#e53935',
  deformation: '#00bcd4',
  size_mismatch: '#1671b8',
  crazing: '#8e44ad',
  inclusion: '#6d4c8d',
  patches: '#2e7d8f',
  pitted_surface: '#7b6d3a',
  'rolled-in_scale': '#607d8b',
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: '#e53935',
  high: '#f57c00',
  moderate: '#fbc02d',
  low: '#2eaf75',
  minor: '#2eaf75',
}

function defectColor(defect: LiveDefect) {
  return (defect.severity && SEVERITY_COLORS[defect.severity.toLowerCase()])
    || DEFECT_COLORS[defect.defect_type]
    || '#1671b8'
}

function DefectOverlay({
  detection,
  selectedDefectId,
  onSelect,
}: {
  detection: LiveDetection | null
  selectedDefectId?: string | null
  onSelect?: (defectId: string) => void
}) {
  if (!detection) return null
  const font = Math.max(11, detection.height / 40)
  // keep labels inside the image: shift left when the text would run past the right edge
  const clampX = (text: string, size: number, x: number) =>
    Math.max(2, Math.min(x, detection.width - text.length * size * 0.62 - 2))
  return (
    <svg
      className="defect-overlay"
      viewBox={`0 0 ${detection.width} ${detection.height}`}
      preserveAspectRatio="xMidYMid meet"
    >
      {detection.defects.map((defect) => {
        const color = defectColor(defect)
        const points = defect.polygon.map(([x, y]) => `${x},${y}`).join(' ')
        const label = `${defect.defect_type.replace('_', ' ')} ${Math.round(defect.confidence * 100)}%`
        const selected = defect.defect_id === selectedDefectId
        return (
          <g
            key={defect.defect_id}
            className={onSelect ? 'inspection-defect-target' : undefined}
            onClick={() => onSelect?.(defect.defect_id)}
          >
            <polygon points={points} fill={color} fillOpacity={selected ? 0.48 : 0.24} stroke={color} strokeWidth={selected ? 4 : 2} strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
            {defect.polygon.map(([x, y], index) => (
              <circle key={index} cx={x} cy={y} r={3} fill="#fff" stroke={color} strokeWidth={1} vectorEffect="non-scaling-stroke" />
            ))}
            <text x={clampX(label, font, defect.bbox.x1)} y={Math.max(font, defect.bbox.y1 - 4)} fill={color} fontSize={font} fontWeight={700} stroke="#000" strokeWidth={0.4} paintOrder="stroke">
              {label}
            </text>
            {defect.note && (
              <text x={clampX(defect.note, font * 0.85, defect.bbox.x1)} y={Math.min(detection.height - 4, defect.bbox.y2 + font + 2)} fill="#fff" fontSize={font * 0.85} stroke="#000" strokeWidth={0.4} paintOrder="stroke">
                {defect.note}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}

function EngineeringViewport({
  title,
  subtitle,
  status,
  zoom,
  onZoomChange,
  onFit,
  focusPoint,
  children,
}: {
  title: string
  subtitle: string
  status?: string
  zoom: number
  onZoomChange: (zoom: number) => void
  onFit: () => void
  focusPoint?: { x: number; y: number; aspectRatio: number; token: string }
  children: ReactNode
}) {
  const [panEnabled, setPanEnabled] = useState(false)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const dragStart = useRef<{ x: number; y: number; offsetX: number; offsetY: number } | null>(null)
  const stageRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!focusPoint || !stageRef.current) return
    const { width, height } = stageRef.current.getBoundingClientRect()
    const imageScale = Math.min(width / focusPoint.aspectRatio, height)
    const renderedWidth = imageScale * focusPoint.aspectRatio
    const renderedHeight = imageScale
    const marginX = (width - renderedWidth) / 2
    const marginY = (height - renderedHeight) / 2
    const nextZoom = Math.max(zoom, 1.5)
    onZoomChange(nextZoom)
    setOffset({
      x: (width / 2 - marginX - focusPoint.x * renderedWidth) * nextZoom,
      y: (height / 2 - marginY - focusPoint.y * renderedHeight) * nextZoom,
    })
  }, [focusPoint?.token, focusPoint?.x, focusPoint?.y, focusPoint?.aspectRatio, zoom, onZoomChange])

  const reset = () => {
    setOffset({ x: 0, y: 0 })
    onFit()
  }

  return (
    <section className="engineering-viewer panel">
      <header className="engineering-viewer-head">
        <div className="engineering-viewer-title">
          <strong>{title}</strong>
          <small>{subtitle}</small>
        </div>
        {status && <span className="engineering-viewer-status">{status}</span>}
      </header>
      <div
        ref={stageRef}
        className={`engineering-viewer-stage${panEnabled ? ' engineering-viewer-stage-pan' : ''}`}
        onPointerDown={(event) => {
          if (!panEnabled) return
          dragStart.current = { x: event.clientX, y: event.clientY, offsetX: offset.x, offsetY: offset.y }
          event.currentTarget.setPointerCapture(event.pointerId)
        }}
        onPointerMove={(event) => {
          if (!dragStart.current) return
          setOffset({
            x: dragStart.current.offsetX + event.clientX - dragStart.current.x,
            y: dragStart.current.offsetY + event.clientY - dragStart.current.y,
          })
        }}
        onPointerUp={() => { dragStart.current = null }}
        onPointerCancel={() => { dragStart.current = null }}
      >
        <div className="engineering-viewer-content" style={{ transform: `translate(${offset.x}px, ${offset.y}px) scale(${zoom})` }}>
          {children}
        </div>
        <div className="engineering-viewer-tools" aria-label={`${title} image controls`}>
          <button type="button" onClick={() => onZoomChange(Math.min(3, zoom + 0.2))} aria-label="Zoom in" title="Zoom in"><ZoomIn size={14} /></button>
          <button type="button" onClick={() => onZoomChange(Math.max(0.6, zoom - 0.2))} aria-label="Zoom out" title="Zoom out"><ZoomOut size={14} /></button>
          <button type="button" onClick={reset} aria-label="Fit to view" title="Fit to view"><Maximize2 size={13} /></button>
          <button type="button" className={panEnabled ? 'is-selected' : ''} onClick={() => setPanEnabled((enabled) => !enabled)} aria-label="Toggle pan" title="Toggle pan"><Move size={13} /></button>
        </div>
        <span className="engineering-viewer-zoom">{Math.round(zoom * 100)}%</span>
      </div>
    </section>
  )
}

type DefectCrop = {
  defect: LiveDefect
  src: string
  width: number
  height: number
  polygon: number[][]
}

export default function NewJob() {
  const navigate = useNavigate()
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const simulationRef = useRef<number | null>(null)
  const frameIndexRef = useRef(-1)
  const previousFrameRef = useRef<Uint8ClampedArray | null>(null)
  const stableFramesRef = useRef(0)
  const [partNumber, setPartNumber] = useState('MS-4505-001')
  const [cameraActive, setCameraActive] = useState(false)
  const [cameraSource, setCameraSource] = useState<'simulated' | 'live'>('simulated')
  const [cameraDevices, setCameraDevices] = useState<MediaDeviceInfo[]>([])
  const [selectedDevice, setSelectedDevice] = useState('')
  const [autoCapture, setAutoCapture] = useState(false)
  const [liveMarking, setLiveMarking] = useState(false)
  const [liveDetection, setLiveDetection] = useState<LiveDetection | null>(null)
  const [captureDetection, setCaptureDetection] = useState<LiveDetection | null>(null)
  const [rcaStatus, setRcaStatus] = useState<RcaStatus | null>(null)
  const [rcaResult, setRcaResult] = useState<RcaResult | null>(null)
  const [rcaDefectId, setRcaDefectId] = useState<string | null>(null)
  const [rcaLoading, setRcaLoading] = useState(false)
  const [rcaError, setRcaError] = useState('')
  const [capturedImage, setCapturedImage] = useState<Blob | null>(null)
  const [capturedPreview, setCapturedPreview] = useState('')
  const [references, setReferences] = useState<References | null>(null)
  const [referenceUrls, setReferenceUrls] = useState<{ cad: string; image: string } | null>(null)
  const [referencesLoading, setReferencesLoading] = useState(true)
  const [verification, setVerification] = useState<Verification | null>(null)
  const [verificationLoading, setVerificationLoading] = useState(false)
  const [verificationError, setVerificationError] = useState('')
  const [cadUpload, setCadUpload] = useState<File | null>(null)
  const [referenceUpload, setReferenceUpload] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [referenceError, setReferenceError] = useState('')
  const [selectedDefectId, setSelectedDefectId] = useState<string | null>(null)
  const [referenceZoom, setReferenceZoom] = useState(1)
  const [captureZoom, setCaptureZoom] = useState(1)
  const [showLiveFeed, setShowLiveFeed] = useState(false)
  const [captureWhenReady, setCaptureWhenReady] = useState(false)
  const [visualizationMode, setVisualizationMode] = useState<'original' | 'detection' | 'segmentation' | 'heatmap'>('detection')
  const [defectCrops, setDefectCrops] = useState<DefectCrop[]>([])

  const startSimulatedCamera = async () => {
    setError('')
    try {
      // Simulated input: cycle the repo's sample images through a canvas stream.
      const samples = (await demoApi.samples()).data
      if (!samples.length) throw new Error('No sample images found in the samples folder.')
      const images = await Promise.all(samples.map(async (sample) => {
        const blob = (await demoApi.sample(sample.name)).data
        return createImageBitmap(blob)
      }))
      const canvas = document.createElement('canvas')
      canvas.width = 480
      canvas.height = 480
      const context = canvas.getContext('2d')
      if (!context) throw new Error('Could not start the simulated camera.')
      const startedAt = Date.now()
      const draw = () => {
        const index = Math.floor((Date.now() - startedAt) / DEMO_SECONDS_PER_FRAME / 1000) % images.length
        if (index !== frameIndexRef.current) {
          frameIndexRef.current = index
          setLiveDetection(null)          // never leave the previous frame's highlights on the new image
        }
        context.drawImage(images[index], 0, 0, canvas.width, canvas.height)
      }
      draw()
      simulationRef.current = window.setInterval(draw, 100)
      const stream = canvas.captureStream(10)
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
      }
      setCameraSource('simulated')
      setCameraActive(true)
    } catch (cameraError) {
      setError(errorMessage(cameraError, 'Could not start the simulated camera.'))
      setCameraActive(false)
    }
  }

  const attachLiveCamera = useCallback(async (deviceId?: string) => {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('Camera access is not available. Use localhost or HTTPS and allow camera permission in the browser.')
    }
    const stream = await navigator.mediaDevices.getUserMedia({
      video: deviceId ? { deviceId: { exact: deviceId } } : true,
      audio: false,
    })
    if (simulationRef.current !== null) window.clearInterval(simulationRef.current)
    simulationRef.current = null
    const previousStream = streamRef.current
    streamRef.current = stream
    if (videoRef.current) videoRef.current.srcObject = stream
    previousStream?.getTracks().forEach((track) => track.stop())
    frameIndexRef.current = -1
    setSelectedDevice(stream.getVideoTracks()[0]?.getSettings().deviceId ?? deviceId ?? '')
    setCameraSource('live')
    setCameraActive(true)
  }, [])

  const startLiveCamera = async () => {
    setError('')
    try {
      await attachLiveCamera()
    } catch (cameraError) {
      setError(errorMessage(cameraError, 'Could not connect to a camera. Check that a camera is attached and that the browser has permission to use it.'))
      setCameraActive(false)
      return
    }

    try {
      const devices = (await navigator.mediaDevices.enumerateDevices()).filter((device) => device.kind === 'videoinput')
      setCameraDevices(devices)
      const iriun = devices.find((device) => /iriun/i.test(device.label))
      if (iriun) {
        try {
          await attachLiveCamera(iriun.deviceId)
        } catch (cameraError) {
          setError(errorMessage(cameraError, 'Could not switch to Iriun Webcam. The current camera remains connected.'))
        }
      }
    } catch (cameraError) {
      setError(errorMessage(cameraError, 'Camera connected, but the camera list could not be loaded.'))
    }
  }

  useEffect(() => {
    rcaApi.status().then((response) => setRcaStatus(response.data)).catch(() => setRcaStatus(null))
  }, [])

  const analyseDefects = captureDetection?.defects.length ? captureDetection.defects : (liveDetection?.defects ?? [])

  const analyseRootCause = async () => {
    if (!analyseDefects.length) return
    setRcaLoading(true)
    setRcaError('')
    try {
      const selectedDefect = analyseDefects.find((defect) => defect.defect_id === selectedDefectId)
      const defectsToAnalyze = selectedDefect ? [selectedDefect] : analyseDefects
      const response = await rcaApi.analyze({
        defects: defectsToAnalyze.slice(0, 20).map((defect) => ({
          defect_type: defect.defect_type,
          confidence: defect.confidence,
          note: defect.note ?? null,
        })),
      })
      setRcaResult(response.data)
      setRcaDefectId(selectedDefect?.defect_id ?? null)
    } catch (analysisError) {
      setRcaResult(null)
      setRcaError(errorMessage(analysisError, 'Root cause analysis failed.'))
    } finally {
      setRcaLoading(false)
    }
  }

  const downloadRca = async (format: string) => {
    if (!rcaResult) return
    try {
      const response = await rcaApi.download(rcaResult.documents[format])
      const url = URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = url
      link.download = `novaliseo_rca.${format}`
      link.click()
      URL.revokeObjectURL(url)
    } catch (downloadError) {
      setRcaError(errorMessage(downloadError, 'Could not download the document.'))
    }
  }

  const stopCamera = () => {
    if (simulationRef.current !== null) window.clearInterval(simulationRef.current)
    simulationRef.current = null
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    setCameraActive(false)
    setAutoCapture(false)
    setLiveMarking(false)
    setLiveDetection(null)
  }

  useEffect(() => {
    const video = videoRef.current
    const stream = streamRef.current
    if (!cameraActive || !video || !stream) return
    video.srcObject = stream
    void video.play().catch(() => {
      setError('The browser could not start the camera preview. Check camera permissions and try again.')
    })
  }, [cameraActive, selectedDevice, showLiveFeed])

  const captureFrame = useCallback(() => {
    const video = videoRef.current
    if (!video || video.videoWidth === 0 || video.videoHeight === 0) {
      setError('The camera has not produced a usable frame yet.')
      return
    }
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    const context = canvas.getContext('2d')
    if (!context) {
      setError('Could not access the image capture canvas.')
      return
    }
    context.drawImage(video, 0, 0, canvas.width, canvas.height)
    canvas.toBlob((blob) => {
      if (!blob) {
        setError('The camera frame could not be encoded.')
        return
      }
      setCapturedImage(blob)
      setVerification(null)
      setVerificationError('')
      setCaptureDetection(null)
      setSelectedDefectId(null)
      setRcaResult(null)
      setRcaDefectId(null)
      setRcaError('')
      setShowLiveFeed(false)
      partsApi.liveDetect(blob).then((response) => setCaptureDetection(response.data)).catch((detectionError) => {
        setCaptureDetection(null)
        setError(errorMessage(detectionError, 'Defect detection failed for this captured image.'))
      })
      setCapturedPreview(URL.createObjectURL(blob))
      setError('')
      setAutoCapture(false)
    }, 'image/jpeg', 0.92)
  }, [])

  useEffect(() => {
    if (!captureWhenReady) return
    let completed = false
    const interval = window.setInterval(() => {
      const video = videoRef.current
      if (!video || video.videoWidth === 0 || completed) return
      completed = true
      window.clearInterval(interval)
      window.clearTimeout(timeout)
      setCaptureWhenReady(false)
      captureFrame()
    }, 100)
    const timeout = window.setTimeout(() => {
      if (completed) return
      completed = true
      window.clearInterval(interval)
      setCaptureWhenReady(false)
      setError('The camera did not produce a usable frame in time. Check the camera connection and retry.')
    }, 5000)
    return () => {
      window.clearInterval(interval)
      window.clearTimeout(timeout)
    }
  }, [captureWhenReady, captureFrame])

  useEffect(() => {
    let active = true
    const normalizedPart = partNumber.trim()
    setReferences(null)
    setReferenceUrls(null)
    setReferenceError('')
    setVerification(null)
    setVerificationError('')
    setReferencesLoading(true)
    if (!normalizedPart) {
      setReferencesLoading(false)
      return
    }

    const timer = window.setTimeout(async () => {
      try {
        const response = await partsApi.references(normalizedPart)
        if (!active) return
        const metadata = response.data as References
        setReferences(metadata)
        if (metadata.configured) {
          const [cad, image] = await Promise.all([
            partsApi.referenceImage(normalizedPart, 'cad'),
            partsApi.referenceImage(normalizedPart, 'image'),
          ])
          if (active) {
            setReferenceUrls({
              cad: URL.createObjectURL(cad.data),
              image: URL.createObjectURL(image.data),
            })
          }
        }
      } catch (referenceFetchError) {
        if (active) setReferenceError(errorMessage(referenceFetchError, 'Could not load this part or its references.'))
      } finally {
        if (active) setReferencesLoading(false)
      }
    }, 250)

    return () => {
      active = false
      window.clearTimeout(timer)
    }
  }, [partNumber])

  useEffect(() => () => {
    if (simulationRef.current !== null) window.clearInterval(simulationRef.current)
    streamRef.current?.getTracks().forEach((track) => track.stop())
  }, [])

  useEffect(() => () => {
    if (capturedPreview) URL.revokeObjectURL(capturedPreview)
  }, [capturedPreview])

  useEffect(() => {
    if (referenceUrls) {
      return () => {
        URL.revokeObjectURL(referenceUrls.cad)
        URL.revokeObjectURL(referenceUrls.image)
      }
    }
  }, [referenceUrls])

  useEffect(() => {
    let active = true
    const detection = capturedPreview ? captureDetection : liveDetection
    if (!capturedPreview || !detection?.defects.length) {
      setDefectCrops([])
      setSelectedDefectId(null)
      return
    }

    const image = new Image()
    image.onload = () => {
      if (!active) return
      const scaleX = image.naturalWidth / detection.width
      const scaleY = image.naturalHeight / detection.height
      const crops = detection.defects.map((defect): DefectCrop | null => {
        const x1 = Math.max(0, Math.min(image.naturalWidth, defect.bbox.x1 * scaleX))
        const y1 = Math.max(0, Math.min(image.naturalHeight, defect.bbox.y1 * scaleY))
        const x2 = Math.max(0, Math.min(image.naturalWidth, defect.bbox.x2 * scaleX))
        const y2 = Math.max(0, Math.min(image.naturalHeight, defect.bbox.y2 * scaleY))
        const boxWidth = x2 - x1
        const boxHeight = y2 - y1
        if (![x1, y1, x2, y2].every(Number.isFinite) || boxWidth <= 0 || boxHeight <= 0) return null

        const aspectRatio = 1.6
        let cropWidth = boxWidth * 1.5
        let cropHeight = boxHeight * 1.5
        if (cropWidth / cropHeight < aspectRatio) cropWidth = cropHeight * aspectRatio
        else cropHeight = cropWidth / aspectRatio
        cropWidth = Math.min(image.naturalWidth, cropWidth)
        cropHeight = Math.min(image.naturalHeight, cropHeight)
        if (cropWidth / cropHeight < aspectRatio) cropWidth = Math.min(image.naturalWidth, cropHeight * aspectRatio)
        else if (cropWidth / cropHeight > aspectRatio) cropHeight = Math.min(image.naturalHeight, cropWidth / aspectRatio)

        const centerX = (x1 + x2) / 2
        const centerY = (y1 + y2) / 2
        const cropX = Math.max(0, Math.min(image.naturalWidth - cropWidth, centerX - cropWidth / 2))
        const cropY = Math.max(0, Math.min(image.naturalHeight - cropHeight, centerY - cropHeight / 2))
        const canvas = document.createElement('canvas')
        canvas.width = 640
        canvas.height = 400
        const context = canvas.getContext('2d')
        if (!context) {
          setError('Could not create the defect crop visualization. Try capturing the image again.')
          return null
        }
        const cropScale = Math.min(canvas.width / cropWidth, canvas.height / cropHeight)
        const renderedWidth = cropWidth * cropScale
        const renderedHeight = cropHeight * cropScale
        const imageOffsetX = (canvas.width - renderedWidth) / 2
        const imageOffsetY = (canvas.height - renderedHeight) / 2
        context.fillStyle = '#edf2f6'
        context.fillRect(0, 0, canvas.width, canvas.height)
        context.drawImage(image, cropX, cropY, cropWidth, cropHeight, imageOffsetX, imageOffsetY, renderedWidth, renderedHeight)
        const polygon = defect.polygon
          .filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y))
          .map(([x, y]) => [(x * scaleX - cropX) * cropScale + imageOffsetX, (y * scaleY - cropY) * cropScale + imageOffsetY])
        if (polygon.length < 3) {
          polygon.splice(0, polygon.length,
            [(x1 - cropX) * cropScale + imageOffsetX, (y1 - cropY) * cropScale + imageOffsetY],
            [(x2 - cropX) * cropScale + imageOffsetX, (y1 - cropY) * cropScale + imageOffsetY],
            [(x2 - cropX) * cropScale + imageOffsetX, (y2 - cropY) * cropScale + imageOffsetY],
            [(x1 - cropX) * cropScale + imageOffsetX, (y2 - cropY) * cropScale + imageOffsetY],
          )
        }
        return { defect, src: canvas.toDataURL('image/jpeg', 0.92), width: canvas.width, height: canvas.height, polygon }
      }).filter((crop): crop is DefectCrop => crop !== null)
      setDefectCrops(crops)
      setSelectedDefectId((current) => crops.some(({ defect }) => defect.defect_id === current)
        ? current
        : crops[0]?.defect.defect_id ?? null)
    }
    image.onerror = () => {
      if (active) setError('Could not load the captured image for defect cropping. Capture the image again.')
    }
    image.src = capturedPreview
    return () => { active = false }
  }, [capturedPreview, captureDetection, liveDetection])

  useEffect(() => {
    const selected = (captureDetection?.defects ?? []).find((defect) => defect.defect_id === selectedDefectId)
      ?? (liveDetection?.defects ?? []).find((defect) => defect.defect_id === selectedDefectId)
    const context = {
      partNumber,
      detectedCount: analyseDefects.length,
      selectedDefect: selected ? {
        id: selected.defect_id,
        type: selected.defect_type,
        confidence: selected.confidence,
        note: selected.note ?? null,
      } : null,
      analysis: rcaResult && rcaDefectId === selectedDefectId ? {
        cause: rcaResult.root_cause.cause,
        actions: rcaResult.root_cause.corrective_actions,
      } : null,
    }
    sessionStorage.setItem('novaliseo-live-context', JSON.stringify(context))
    window.dispatchEvent(new CustomEvent('novaliseo-live-context', { detail: context }))
  }, [partNumber, analyseDefects.length, selectedDefectId, captureDetection, liveDetection, rcaResult, rcaDefectId])

  useEffect(() => () => {
    sessionStorage.removeItem('novaliseo-live-context')
    window.dispatchEvent(new CustomEvent('novaliseo-live-context', { detail: null }))
  }, [])

  useEffect(() => {
    if (!liveMarking || !cameraActive) {
      setLiveDetection(null)
      return
    }
    let cancelled = false
    let inFlight = false
    const canvas = document.createElement('canvas')
    const timer = window.setInterval(() => {
      const video = videoRef.current
      if (inFlight || !video || video.videoWidth === 0) return
      const scale = Math.min(1, 640 / video.videoWidth)
      canvas.width = Math.round(video.videoWidth * scale)
      canvas.height = Math.round(video.videoHeight * scale)
      canvas.getContext('2d')?.drawImage(video, 0, 0, canvas.width, canvas.height)
      inFlight = true
      const sentFor = frameIndexRef.current
      canvas.toBlob(async (blob) => {
        try {
          if (!blob) return
          const response = await partsApi.liveDetect(blob)
          if (!cancelled && sentFor === frameIndexRef.current) setLiveDetection(response.data)   // drop stale results
        } catch (detectionError) {
          if (!cancelled) {
            setLiveDetection(null)
            setError(errorMessage(detectionError, 'Live defect detection failed. Check the API connection.'))
          }
        } finally {
          inFlight = false
        }
      }, 'image/jpeg', 0.7)
    }, 900)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [liveMarking, cameraActive])

  useEffect(() => {
    if (!autoCapture || !cameraActive) return
    previousFrameRef.current = null
    stableFramesRef.current = 0
    const canvas = document.createElement('canvas')
    canvas.width = 64
    canvas.height = 48
    const context = canvas.getContext('2d', { willReadFrequently: true })
    if (!context) {
      setError('Automatic capture is unavailable because image analysis could not start.')
      setAutoCapture(false)
      return
    }

    const timer = window.setInterval(() => {
      const video = videoRef.current
      if (!video || video.videoWidth === 0) return
      context.drawImage(video, 0, 0, canvas.width, canvas.height)
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data
      let total = 0
      let squareTotal = 0
      let delta = 0
      const previous = previousFrameRef.current
      for (let index = 0; index < pixels.length; index += 4) {
        const luminance = (pixels[index] + pixels[index + 1] + pixels[index + 2]) / 3
        total += luminance
        squareTotal += luminance * luminance
        if (previous) delta += Math.abs(luminance - (previous[index] + previous[index + 1] + previous[index + 2]) / 3)
      }
      previousFrameRef.current = new Uint8ClampedArray(pixels)
      const pixelCount = pixels.length / 4
      const contrast = Math.sqrt(Math.max(0, squareTotal / pixelCount - (total / pixelCount) ** 2))
      const frameDifference = previous ? delta / pixelCount : Infinity
      stableFramesRef.current = frameDifference < 3 && contrast > 18
        ? stableFramesRef.current + 1
        : 0
      if (stableFramesRef.current >= 6) captureFrame()
    }, 400)
    return () => window.clearInterval(timer)
  }, [autoCapture, cameraActive, captureFrame])

  const configureReferences = async () => {
    if (!cadUpload || !referenceUpload) {
      setError('Choose both a raster CAD drawing and a reference part image.')
      return
    }
    setLoading(true)
    setError('')
    try {
      await partsApi.uploadReferences(partNumber.trim(), cadUpload, referenceUpload)
      setCadUpload(null)
      setReferenceUpload(null)
      setReferenceError('')
      setError('')
      setReferences(null)
      setReferenceUrls(null)
      // Reload the saved reference previews for the selected part.
      const metadata = (await partsApi.references(partNumber.trim())).data as References
      const [cad, image] = await Promise.all([
        partsApi.referenceImage(partNumber.trim(), 'cad'),
        partsApi.referenceImage(partNumber.trim(), 'image'),
      ])
      setReferences(metadata)
      setReferenceUrls({
        cad: URL.createObjectURL(cad.data),
        image: URL.createObjectURL(image.data),
      })
    } catch (uploadError) {
      setError(errorMessage(uploadError, 'Could not save the part references.'))
    } finally {
      setLoading(false)
    }
  }

  const verifyCapture = async () => {
    if (!capturedImage) return
    setVerificationLoading(true)
    setVerificationError('')
    setError('')
    setVerification(null)
    try {
      const response = await partsApi.verify(partNumber.trim(), capturedImage)
      setVerification(response.data as Verification)
    } catch (verificationError) {
      setVerificationError(errorMessage(verificationError, 'Image comparison failed.'))
    } finally {
      setVerificationLoading(false)
    }
  }

  const startInspection = async () => {
    if (!verification || verification.status !== 'Match') return
    setLoading(true)
    setError('')
    try {
      const response = await jobsApi.create(partNumber.trim(), [], verification.verification_id)
      navigate(`/jobs/${response.data.job_id}`)
    } catch (jobError) {
      setError(errorMessage(jobError, 'Failed to start the inspection.'))
      setLoading(false)
    }
  }

  const activeDetection = showLiveFeed && cameraActive ? liveDetection : captureDetection
  const selectedCrop = defectCrops.find(({ defect }) => defect.defect_id === selectedDefectId)
  const selectedAnalysis = rcaDefectId === selectedDefectId ? rcaResult : null
  const defectsByType = (activeDetection?.defects ?? []).reduce<Record<string, number>>((counts, defect) => {
    counts[defect.defect_type] = (counts[defect.defect_type] ?? 0) + 1
    return counts
  }, {})
  const severityCount = (severity: string) => (activeDetection?.defects ?? []).filter((defect) => defect.severity?.toLowerCase() === severity).length
  const hasSeverityData = Boolean(activeDetection?.defects.length && activeDetection.defects.every((defect) => (
    typeof defect.severity === 'string'
  )))
  const selectedDefect = activeDetection?.defects.find((defect) => defect.defect_id === selectedDefectId)
  const focusPoint = selectedDefect && activeDetection ? {
    x: ((selectedDefect.bbox.x1 + selectedDefect.bbox.x2) / 2) / activeDetection.width,
    y: ((selectedDefect.bbox.y1 + selectedDefect.bbox.y2) / 2) / activeDetection.height,
    aspectRatio: activeDetection.width / activeDetection.height,
    token: selectedDefect.defect_id,
  } : undefined
  const verificationAlignmentStatus = verification?.alignment_status
    ?? (verification?.geometric_inliers != null && verification.geometric_inliers > 0 ? 'aligned' : 'required')
  const verificationScore = verificationAlignmentStatus === 'aligned' ? verification?.score : null

  return (
    <div className="live-inspection-page">
      <header className="live-inspection-heading">
        <div>
          <div className="live-inspection-kicker">QUALITY OPERATIONS <span>/</span> LIVE INSPECTION</div>
          <h1>Engineering inspection workspace</h1>
          <p>Compare the registered drawing with a live or captured component image.</p>
        </div>
        <div className="live-part-control">
          <label htmlFor="part-number">PART NUMBER</label>
          <input
            id="part-number"
            value={partNumber}
            onChange={(event) => {
              setPartNumber(event.target.value)
              setCapturedImage(null)
              setCaptureDetection(null)
              setSelectedDefectId(null)
              setRcaResult(null)
              setRcaDefectId(null)
              setVerification(null)
              setCapturedPreview('')
              setError('')
            }}
            placeholder="Registered part number"
          />
          <span className={`engineering-status-tag ${references?.configured ? 'is-ready' : ''}`}>
            {references?.configured ? 'REFERENCE READY' : 'REFERENCE REQUIRED'}
          </span>
        </div>
      </header>

      <section className="engineering-visualization-grid" aria-label="Reference and captured image comparison">
        <EngineeringViewport
          title="2D Reference Drawing"
          subtitle={`${partNumber || 'Selected part'}${references?.drawing_rev ? ` · Rev ${references.drawing_rev}` : ''}`}
          status={references?.configured ? 'REGISTERED' : undefined}
          zoom={referenceZoom}
          onZoomChange={setReferenceZoom}
          onFit={() => setReferenceZoom(1)}
        >
          {referenceUrls?.cad ? (
            <img className="engineering-image" src={referenceUrls.cad} alt={`Registered 2D CAD drawing for ${partNumber}`} />
          ) : (
            <div className="engineering-empty-visual">
              <FileImage size={26} />
              <strong>CAD drawing not available</strong>
              <span>{referenceError || 'Register a drawing for this part to compare engineering geometry.'}</span>
            </div>
          )}
        </EngineeringViewport>

        <EngineeringViewport
          title="Live Captured Image"
          subtitle={capturedPreview && !showLiveFeed ? 'Latest camera capture' : cameraActive ? 'Camera preview' : 'Capture station offline'}
          status={cameraActive ? (cameraSource === 'live' ? 'CAMERA CONNECTED' : 'SIMULATED FEED') : capturedPreview ? 'CAPTURED' : 'NOT CONNECTED'}
          zoom={captureZoom}
          onZoomChange={setCaptureZoom}
          onFit={() => setCaptureZoom(1)}
          focusPoint={focusPoint}
        >
          <div className="engineering-capture-frame">
            {showLiveFeed && cameraActive ? (
              <>
                <video ref={videoRef} autoPlay playsInline muted className="engineering-image" />
                {visualizationMode === 'detection' && <DefectOverlay detection={liveDetection} selectedDefectId={selectedDefectId} onSelect={setSelectedDefectId} />}
              </>
            ) : capturedPreview ? (
              <>
                <img className="engineering-image" src={capturedPreview} alt="Latest captured component image" />
                {visualizationMode === 'detection' && <DefectOverlay detection={captureDetection} selectedDefectId={selectedDefectId} onSelect={setSelectedDefectId} />}
              </>
            ) : cameraActive ? (
              <>
                <video ref={videoRef} autoPlay playsInline muted className="engineering-image" />
                {visualizationMode === 'detection' && <DefectOverlay detection={liveDetection} selectedDefectId={selectedDefectId} onSelect={setSelectedDefectId} />}
              </>
            ) : (
              <div className="engineering-empty-visual">
                <Camera size={27} />
                <strong>Camera preview is offline</strong>
                <span>Start a simulated feed or connect a camera to view the component.</span>
              </div>
            )}
          </div>
        </EngineeringViewport>
      </section>

      <div className="engineering-command-bar">
        <div className="engineering-camera-actions">
          <span className={`engineering-capture-state${capturedPreview ? ' is-captured' : ''}`}>
            {capturedPreview ? 'CAPTURED IMAGE READY' : cameraActive ? 'WAITING FOR CAPTURE' : 'NO CAPTURE'}
          </span>
          {!cameraActive ? (
            <>
              <button type="button" className="btn-primary" onClick={() => { setShowLiveFeed(true); void startSimulatedCamera() }}><Camera size={13} /> Start simulated camera</button>
              <button type="button" className="btn-secondary" onClick={() => { setShowLiveFeed(true); void startLiveCamera() }}><Video size={13} /> Connect camera</button>
            </>
          ) : (
            <>
              {cameraSource === 'live' && cameraDevices.length > 0 && (
                <select
                  value={selectedDevice}
                  onChange={async (event) => {
                    try { await attachLiveCamera(event.target.value) }
                    catch (cameraError) { setError(errorMessage(cameraError, 'Could not switch camera device.')) }
                  }}
                  aria-label="Camera device"
                >
                  {cameraDevices.map((device, index) => <option key={device.deviceId} value={device.deviceId}>{device.label || `Camera ${index + 1}`}</option>)}
                </select>
              )}
              <button
                type="button"
                className="btn-primary"
                onClick={() => {
                  if (capturedPreview && !showLiveFeed) {
                    setShowLiveFeed(true)
                    setCaptureWhenReady(true)
                  } else {
                    captureFrame()
                  }
                }}
              >
                <Camera size={13} /> {capturedPreview ? 'Recapture' : 'Capture frame'}
              </button>
              <button type="button" className="btn-secondary" onClick={stopCamera}>Disconnect</button>
            </>
          )}
          {capturedPreview && cameraActive && (
            <button type="button" className="btn-secondary" onClick={() => setShowLiveFeed((current) => !current)}>
              <RefreshCw size={12} /> {showLiveFeed ? 'View latest capture' : 'Return to live feed'}
            </button>
          )}
        </div>
        <div className="engineering-visual-toggles">
          <label className="engineering-mode-select">Visualization
            <select value={visualizationMode} onChange={(event) => setVisualizationMode(event.target.value as typeof visualizationMode)} aria-label="Visualization mode">
              <option value="original">Original image</option>
              <option value="detection">Detection overlay</option>
              <option value="segmentation" disabled>Segmentation overlay · unavailable</option>
              <option value="heatmap" disabled>Anomaly heatmap · unavailable</option>
            </select>
          </label>
          <label><input type="checkbox" checked={liveMarking} onChange={(event) => setLiveMarking(event.target.checked)} disabled={!cameraActive} /> Detect live</label>
          <label><input type="checkbox" checked={autoCapture} onChange={(event) => setAutoCapture(event.target.checked)} disabled={!references?.configured || !cameraActive} /> Auto-capture</label>
          <button type="button" className="btn-secondary" onClick={verifyCapture} disabled={!capturedImage || !references?.configured || !referenceUrls?.image || verificationLoading}>
            {verificationLoading ? <LoaderCircle size={13} className="animate-spin" /> : <ScanLine size={13} />} Compare images
          </button>
        </div>
      </div>

      {referenceError && <p className="live-inspection-error" role="alert">{referenceError}</p>}
      {error && <p className="live-inspection-error" role="alert"><AlertCircle size={14} />{error}</p>}

      <section className="engineering-defect-section panel" aria-label="Zoomed defect views">
        <header className="engineering-section-head">
          <div><strong>Zoomed Defect Analysis</strong><small>
            {activeDetection?.source ? `Source: ${activeDetection.source} · ` : ''}
            Original-color crops and detector outlines; severity, segmentation masks, and heatmaps are not returned by the live-detection API.
          </small></div>
          <span>{activeDetection?.defects.length ?? 0} DETECTED</span>
        </header>
        {defectCrops.length ? (
          <div className="engineering-defect-strip">
            {defectCrops.map(({ defect, src, width, height, polygon }, index) => {
              const selected = defect.defect_id === selectedDefectId
              const color = defectColor(defect)
              const scoredSeverity = defect.severity
              return (
                <button
                  type="button"
                  key={defect.defect_id}
                  className={`engineering-defect-card${selected ? ' is-selected' : ''}`}
                  style={{ '--defect-color': color } as React.CSSProperties}
                  onClick={() => setSelectedDefectId(defect.defect_id)}
                  aria-pressed={selected}
                >
                  <span className="engineering-defect-crop">
                    <img src={src} alt={`Original image crop for ${defect.defect_type}`} />
                    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
                      <polygon points={polygon.map(([x, y]) => `${x},${y}`).join(' ')} />
                      <text x="8" y="16">D{index + 1} · {defect.defect_type.replace(/_/g, ' ').toUpperCase()}</text>
                    </svg>
                  </span>
                  <span className="engineering-defect-meta">
                    <strong>DEFECT {String(index + 1).padStart(2, '0')}</strong>
                    <span className="engineering-defect-severity">{scoredSeverity ? scoredSeverity.toUpperCase() : 'SEVERITY UNAVAILABLE'}</span>
                  </span>
                  <span className="engineering-defect-name">{defect.defect_type.replace(/_/g, ' ')}</span>
                  <span className="engineering-defect-confidence">Confidence <b>{Math.round(defect.confidence * 100)}%</b></span>
                  {defect.note && <span className="engineering-defect-note">{defect.note}</span>}
                </button>
              )
            })}
          </div>
        ) : (
          <div className="engineering-defect-empty">
            <Layers size={17} />
            <span>{capturedPreview ? 'No defect regions were returned for this captured image.' : 'Capture an image or enable live detection to populate defect crops.'}</span>
          </div>
        )}
      </section>

      <section className="engineering-analysis-grid" aria-label="Inspection analysis">
        <article className="engineering-analysis-panel panel">
          <header className="engineering-section-head"><div><strong>Defect Analysis Summary</strong><small>Counts returned by live detection</small></div></header>
          <div className="engineering-count-grid">
            <div><span>Total</span><strong>{activeDetection?.defects.length ?? 0}</strong></div>
            <div className="severity-critical"><span>Critical</span><strong>{hasSeverityData ? severityCount('critical') : '—'}</strong></div>
            <div className="severity-high"><span>High</span><strong>{hasSeverityData ? severityCount('high') : '—'}</strong></div>
            <div className="severity-moderate"><span>Moderate</span><strong>{hasSeverityData ? severityCount('moderate') : '—'}</strong></div>
            <div className="severity-low"><span>Low</span><strong>{hasSeverityData ? severityCount('low') : '—'}</strong></div>
          </div>
          <div className={`engineering-inspection-status ${verification?.status === 'Match' ? 'is-pass' : verification?.status ? 'is-review' : ''}`}>
            Inspection status <strong>{verification?.status ?? 'PENDING COMPARISON'}</strong>
          </div>
          <div className="engineering-chart-list">
            {Object.entries(defectsByType).length ? Object.entries(defectsByType).map(([name, count]) => (
              <div className="engineering-chart-row" key={name}>
                <span>{name.replace(/_/g, ' ')}</span>
                <div><i style={{ width: `${Math.max(8, count / (activeDetection?.defects.length ?? 1) * 100)}%`, background: DEFECT_COLORS[name] ?? '#1671b8' }} /></div>
                <b>{count}</b>
              </div>
            )) : <p className="engineering-analysis-empty">Defect category distribution appears after detection.</p>}
          </div>
        </article>

        <article className="engineering-analysis-panel panel">
          <header className="engineering-section-head"><div><strong>Reference vs Captured</strong><small>Part verification results</small></div></header>
          {verification ? (
            <>
              <div className={`engineering-verification-result ${verification.status === 'Match' ? 'is-match' : 'is-review'}`}>
                <strong>{verificationAlignmentStatus === 'required' ? 'Alignment required' : verification.status}</strong>
                <span>Overall image similarity</span><b>{formatPercent(verificationScore)}</b>
              </div>
              <div className="engineering-comparison-metrics">
                <span>Structural Similarity (SSIM) <b>Not available</b></span>
                <span>Feature matching <b>{formatPercent(verification.feature_match_percent)}</b></span>
                <span>Geometric alignment <b>{verificationAlignmentStatus === 'aligned' ? 'Aligned' : 'Alignment required'}</b></span>
                <span>Feature matches <b>{verification.feature_matches}</b></span>
                <span>Geometric inliers <b>{formatCount(verification.geometric_inliers)}</b></span>
                <span>Edge overlap <b>{formatPercent(verification.edge_overlap)}</b></span>
                <span>Dimensional deviation <b>Not available</b></span>
                <span>Image registration <b>{verificationAlignmentStatus === 'aligned' ? 'Registered' : 'Alignment required'}</b></span>
              </div>
              {(verification.reference_kind === 'cad_drawing' ? referenceUrls?.cad : referenceUrls?.image) && capturedPreview && (
                <div className="engineering-comparison-images">
                  <figure>
                    <img
                      src={verification.reference_kind === 'cad_drawing' ? referenceUrls?.cad : referenceUrls?.image}
                      alt={verification.reference_kind === 'cad_drawing'
                        ? 'Registered CAD drawing used for comparison'
                        : 'Registered physical-part reference image used for comparison'}
                    />
                    <figcaption>{verification.reference_kind === 'cad_drawing' ? 'Registered CAD drawing' : 'Registered part reference'}</figcaption>
                  </figure>
                  <figure>
                    <img src={capturedPreview} alt="Captured component image" />
                    <figcaption>Captured image</figcaption>
                  </figure>
                </div>
              )}
              {verification.visualizations && Object.entries({
                aligned_overlay: 'Alignment preview',
                difference_image: 'Difference image',
                difference_heatmap: 'Difference heatmap',
                matched_features: 'Matched features',
              }).map(([key, title]) => {
                const src = verification.visualizations?.[key as keyof NonNullable<Verification['visualizations']>]
                return src ? (
                  <figure className="engineering-comparison-preview" key={key}>
                    <img src={src} alt={title} />
                    <figcaption>{title}</figcaption>
                  </figure>
                ) : null
              }              )}
              {verification.differences.slice(0, 2).map((difference, index) => <p className="engineering-difference" key={index}>{difference}</p>)}
              {verification.status === 'Match' && <button type="button" className="btn-primary" onClick={startInspection} disabled={loading}><Check size={13} /> Verify and start inspection</button>}
            </>
          ) : verificationLoading ? (
            <div className="engineering-analysis-empty" role="status">Comparing images...</div>
          ) : verificationError ? (
            <div className="engineering-analysis-empty" role="alert">
              <strong>Comparison failed</strong>
              <p>{verificationError}</p>
            </div>
          ) : referencesLoading ? (
            <div className="engineering-analysis-empty" role="status">Loading reference image...</div>
          ) : !references?.configured || !referenceUrls?.image ? (
            <div className="engineering-analysis-empty" role="alert">
              <strong>Reference image unavailable</strong>
              {referenceError && <p>{referenceError}</p>}
            </div>
          ) : !capturedImage ? (
            <div className="engineering-analysis-empty">Captured image unavailable</div>
          ) : (
            <div className="engineering-analysis-empty">
              <p>Compare the capture with the registered part reference to calculate alignment and image similarity.</p>
              <button type="button" className="btn-primary" onClick={verifyCapture} disabled={verificationLoading}>
                {verificationLoading ? <LoaderCircle size={13} className="animate-spin" /> : <ScanLine size={13} />}
                {verificationLoading ? 'Comparing images...' : 'Compare captured part'}
              </button>
            </div>
          )}
          {references?.configured && verification && <p className="engineering-revision">Reference drawing revision {references.drawing_rev}</p>}
        </article>

        <article className="engineering-analysis-panel engineering-rca-panel panel">
          <header className="engineering-section-head">
            <div><strong>AI Root Cause Analysis</strong><small>{rcaStatus?.ai_enabled ? `AI · ${rcaStatus.provider}` : 'Backend analysis service'}</small></div>
            <button type="button" className="btn-secondary" onClick={analyseRootCause} disabled={!analyseDefects.length || rcaLoading}>
              {rcaLoading ? <LoaderCircle size={12} className="animate-spin" /> : <ScanLine size={12} />} Analyze
            </button>
          </header>
          {selectedAnalysis ? (
            <div className="engineering-rca-content">
              {!selectedAnalysis.ai_used && <p className="engineering-rca-warning">Offline analysis response · {selectedAnalysis.model}</p>}
              <span>PROBABLE ROOT CAUSE</span><strong>{selectedAnalysis.root_cause.cause}</strong>
              {selectedAnalysis.root_cause.rationale && <p>{selectedAnalysis.root_cause.rationale}</p>}
              <span>RECOMMENDED CORRECTIVE ACTIONS</span>
              {selectedAnalysis.root_cause.corrective_actions.length
                ? <ul>{selectedAnalysis.root_cause.corrective_actions.slice(0, 3).map((action) => <li key={action}>{action}</li>)}</ul>
                : <p>No corrective actions were returned.</p>}
              {typeof selectedAnalysis.root_cause.confidence === 'number' && <small>Analysis confidence: {Math.round(selectedAnalysis.root_cause.confidence * 100)}%</small>}
              {selectedAnalysis.root_cause.citations.length > 0 && <small>Evidence: {selectedAnalysis.root_cause.citations.slice(0, 2).join(' · ')}</small>}
              {selectedCrop && <small>Selected evidence: {selectedCrop.defect.defect_type.replace(/_/g, ' ')} · {Math.round(selectedCrop.defect.confidence * 100)}% detector confidence</small>}
              <div className="engineering-rca-downloads">
                {Object.keys(selectedAnalysis.documents).map((format) => (
                  <button key={format} type="button" className="btn-secondary" onClick={() => downloadRca(format)}>
                    <Upload size={11} /> {format.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <p className="engineering-analysis-empty">{rcaError || (analyseDefects.length ? 'Run the existing AI root-cause service to analyze detected defects.' : 'Root-cause analysis is available when defect detections are returned.')}</p>
          )}
        </article>
      </section>

      {!references?.configured && (
        <details className="engineering-reference-upload">
          <summary>Register 2D drawing and reference part image</summary>
          <div className="engineering-upload-fields">
            <label>Raster CAD drawing<input type="file" accept="image/png,image/jpeg" onChange={(event) => setCadUpload(event.target.files?.[0] ?? null)} /></label>
            <label>Reference part image<input type="file" accept="image/png,image/jpeg" onChange={(event) => setReferenceUpload(event.target.files?.[0] ?? null)} /></label>
            <button type="button" className="btn-secondary" onClick={configureReferences} disabled={loading || !cadUpload || !referenceUpload}><Upload size={13} /> Save references</button>
          </div>
        </details>
      )}
    </div>
  )
}
