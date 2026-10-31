import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertCircle,
  ArrowRight,
  Camera,
  Check,
  CheckCircle2,
  Circle,
  CircleDot,
  FileImage,
  Focus,
  Info,
  LoaderCircle,
  RefreshCw,
  ScanLine,
  ShieldCheck,
  Upload,
  Video,
  X,
} from 'lucide-react'
import { jobsApi, partsApi } from '../api'

type Verification = {
  status: 'Match' | 'Mismatch' | 'Needs Manual Inspection'
  score: number
  threshold: number
  feature_matches: number
  geometric_inliers: number
  edge_overlap: number
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

export default function NewJob() {
  const navigate = useNavigate()
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const previousFrameRef = useRef<Uint8ClampedArray | null>(null)
  const stableFramesRef = useRef(0)
  const [partNumber, setPartNumber] = useState('MS-4505-001')
  const [cameraDevices, setCameraDevices] = useState<MediaDeviceInfo[]>([])
  const [selectedDevice, setSelectedDevice] = useState('')
  const [cameraActive, setCameraActive] = useState(false)
  const [autoCapture, setAutoCapture] = useState(false)
  const [capturedImage, setCapturedImage] = useState<Blob | null>(null)
  const [capturedPreview, setCapturedPreview] = useState('')
  const [references, setReferences] = useState<References | null>(null)
  const [referenceUrls, setReferenceUrls] = useState<{ cad: string; image: string } | null>(null)
  const [verification, setVerification] = useState<Verification | null>(null)
  const [cadUpload, setCadUpload] = useState<File | null>(null)
  const [referenceUpload, setReferenceUpload] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [referenceError, setReferenceError] = useState('')

  const attachCamera = useCallback(async (deviceId?: string) => {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('Camera access is not available. Use localhost or HTTPS and enable browser camera permissions.')
    }
    streamRef.current?.getTracks().forEach((track) => track.stop())
    const stream = await navigator.mediaDevices.getUserMedia({
      video: deviceId ? { deviceId: { exact: deviceId } } : true,
      audio: false,
    })
    streamRef.current = stream
    if (videoRef.current) {
      videoRef.current.srcObject = stream
      await videoRef.current.play()
    }
    setSelectedDevice(deviceId ?? stream.getVideoTracks()[0]?.getSettings().deviceId ?? '')
    setCameraActive(true)
  }, [])

  const startCamera = async () => {
    setError('')
    try {
      await attachCamera()
      const devices = (await navigator.mediaDevices.enumerateDevices())
        .filter((device) => device.kind === 'videoinput')
      setCameraDevices(devices)
      const iriun = devices.find((device) => /iriun/i.test(device.label))
      if (iriun) await attachCamera(iriun.deviceId)
    } catch (cameraError) {
      setError(errorMessage(cameraError, 'Could not connect to a camera. Check that Iriun Webcam is running and accessible.'))
      setCameraActive(false)
    }
  }

  const stopCamera = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    setCameraActive(false)
    setAutoCapture(false)
  }

  useEffect(() => {
    const video = videoRef.current
    const stream = streamRef.current
    if (!cameraActive || !video || !stream) return
    video.srcObject = stream
    void video.play().catch(() => {
      setError('The browser could not start the camera preview. Check camera permissions and try again.')
    })
  }, [cameraActive, selectedDevice])

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
      setCapturedPreview(URL.createObjectURL(blob))
      setVerification(null)
      setError('')
      setAutoCapture(false)
    }, 'image/jpeg', 0.92)
  }, [])

  useEffect(() => {
    let active = true
    const normalizedPart = partNumber.trim()
    setReferences(null)
    setReferenceUrls(null)
    setReferenceError('')
    if (!normalizedPart) return

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
      }
    }, 250)

    return () => {
      active = false
      window.clearTimeout(timer)
    }
  }, [partNumber])

  useEffect(() => () => {
    streamRef.current?.getTracks().forEach((track) => track.stop())
  }, [])

  useEffect(() => {
    if (capturedPreview) return () => URL.revokeObjectURL(capturedPreview)
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
    setLoading(true)
    setError('')
    setVerification(null)
    try {
      const response = await partsApi.verify(partNumber.trim(), capturedImage)
      setVerification(response.data as Verification)
    } catch (verificationError) {
      setError(errorMessage(verificationError, 'Image comparison failed.'))
    } finally {
      setLoading(false)
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

  const resultTone = verification?.status === 'Match'
    ? 'verification-result-match'
    : verification?.status === 'Mismatch'
      ? 'verification-result-mismatch'
      : 'verification-result-manual'
  const iriunDetected = cameraDevices.some((device) => /iriun/i.test(device.label))

  return (
    <div className="inspection-page space-y-5">
      <header className="page-heading">
        <div>
          <div className="crumbs"><span>QUALITY OPS</span><span>/</span><b>NEW JOB</b></div>
          <h1>Live part inspection</h1>
          <p>Verify the physical component against its registered reference before starting AI inspection.</p>
        </div>
        <div className="status-pill"><ShieldCheck size={14} /> Part verification required</div>
      </header>

      <div className="inspection-steps" aria-label="Inspection steps">
        <div className="inspection-step inspection-step-current"><span className="inspection-step-number">1</span><span>Verify part</span></div>
        <span className="inspection-step-line" />
        <div className="inspection-step"><span className="inspection-step-number">2</span><span>Inspect quality</span></div>
        <span className="inspection-step-line" />
        <div className="inspection-step"><span className="inspection-step-number">3</span><span>Review results</span></div>
      </div>

      <section className="panel flex flex-wrap items-end justify-between gap-4 p-4 sm:p-5">
        <div className="min-w-[220px] flex-1">
          <label htmlFor="part-number" className="field-label">Expected component</label>
          <input
            id="part-number"
            type="text"
            value={partNumber}
            onChange={(event) => {
              setPartNumber(event.target.value)
              setCapturedImage(null)
              setVerification(null)
              setCapturedPreview('')
            }}
            className="w-full max-w-lg px-3 text-sm"
            placeholder="Enter registered part number"
            required
          />
          {references && (
            <p className="mt-2 text-[11px] text-dim">
              <span className="font-semibold text-ink">{references.part_name}</span>
              <span className="mx-2 text-faint">·</span>
              Drawing revision {references.drawing_rev}
            </p>
          )}
        </div>
        <div className={`status-pill ${references?.configured ? 'status-green' : 'status-neutral'}`}>
          {references?.configured ? <CheckCircle2 size={14} /> : <FileImage size={14} />}
          {references?.configured ? 'Reference set ready' : 'Reference set required'}
        </div>
      </section>

      {referenceError && (
        <div role="alert" className="alert alert-warn">
          <Info size={15} className="mt-0.5 shrink-0" />{referenceError}
        </div>
      )}

      <div className="inspection-workspace">
        <section className="panel overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3.5 sm:px-5">
            <div className="flex items-center gap-2.5">
              <div className="grid h-8 w-8 place-items-center rounded-lg bg-raised text-volt"><Video size={16} /></div>
              <div>
                <h2 className="panel-title">Capture station</h2>
                <p className="mt-0.5 text-[10px] text-dim">Position the component in the camera view</p>
              </div>
            </div>
            <div className={`status-pill ${cameraActive ? 'status-green' : 'status-neutral'}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${cameraActive ? 'bg-mint' : 'bg-faint'}`} />
              {cameraActive ? (iriunDetected ? 'Iriun connected' : 'Camera connected') : 'Camera not connected'}
            </div>
          </div>

          <div className="space-y-4 p-4 sm:p-5">
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <div className="min-w-0">
                <div className="mb-2 flex items-center justify-between">
                  <span className="eyebrow">Live feed</span>
                  {cameraActive && <span className="flex items-center gap-1.5 text-[10px] text-mint"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-mint" />LIVE</span>}
                </div>
                <div className="camera-stage aspect-video">
                  {cameraActive ? (
                    <>
                      <video ref={videoRef} autoPlay playsInline muted className="relative z-[1] h-full w-full object-contain" />
                      <div className="pointer-events-none absolute inset-[12%] z-[2] rounded border border-dashed border-volt/80 shadow-[0_0_0_999px_rgba(0,0,0,0.45)]" />
                      <div className="pointer-events-none absolute bottom-2 left-2 z-[3] rounded bg-black/70 px-2 py-1 text-[9px] font-medium text-white">Center component in frame</div>
                    </>
                  ) : (
                    <div className="absolute inset-0 flex flex-col items-center justify-center px-5 text-center">
                      <div className="grid h-11 w-11 place-items-center rounded-full border border-line bg-surface text-faint"><Camera size={19} /></div>
                      <p className="mt-3 text-xs font-semibold text-dim">Camera preview is offline</p>
                      <p className="mt-1 max-w-[230px] text-[10px] leading-4 text-dim">Connect Iriun Webcam or choose another available camera to begin.</p>
                    </div>
                  )}
                </div>
                <p className="mt-2 flex items-start gap-1.5 text-[10px] leading-4 text-dim">
                  <Focus size={13} className="mt-0.5 shrink-0 text-faint" />
                  Keep the full component inside the guide and hold it steady for a clear capture.
                </p>
              </div>

              <div className="min-w-0">
                <div className="mb-2 flex items-center justify-between">
                  <span className="eyebrow">Latest capture</span>
                  {capturedImage && <span className="status-pill status-blue"><Check size={12} />Captured</span>}
                </div>
                <div className="image-stage aspect-video">
                  {capturedPreview ? (
                    <img src={capturedPreview} alt="Latest captured component" />
                  ) : (
                    <div className="flex flex-col items-center px-5 text-center">
                      <FileImage size={22} className="text-faint" />
                      <p className="mt-2 text-[11px] text-dim">Captured image will appear here</p>
                    </div>
                  )}
                </div>
                <p className="mt-2 text-[10px] leading-4 text-dim">Review the image for focus, framing, and surface visibility before comparison.</p>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
              <div className="flex flex-wrap items-center gap-2">
                {!cameraActive ? (
                  <button type="button" onClick={startCamera} className="btn-primary">
                    <Camera size={14} /> Connect camera
                  </button>
                ) : (
                  <>
                    <select
                      value={selectedDevice}
                      onChange={async (event) => {
                        try {
                          await attachCamera(event.target.value)
                        } catch (cameraError) {
                          setError(errorMessage(cameraError, 'Could not switch camera device.'))
                        }
                      }}
                      className="max-w-[210px] px-2.5 text-[11px]"
                      aria-label="Camera device"
                    >
                      {cameraDevices.map((device, index) => (
                        <option key={device.deviceId} value={device.deviceId}>
                          {device.label || `Camera ${index + 1}`}
                        </option>
                      ))}
                    </select>
                    <button type="button" onClick={captureFrame} className="btn-primary">
                      <Camera size={14} /> Capture frame
                    </button>
                    <button type="button" onClick={stopCamera} className="btn-secondary">Disconnect</button>
                  </>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-3">
                {cameraActive && cameraDevices.length > 0 && !iriunDetected && (
                  <span className="flex items-center gap-1 text-[10px] text-amber"><AlertCircle size={13} />Iriun not detected</span>
                )}
                <label className="inline-flex items-center gap-2 text-[11px] text-dim">
                  <input
                    type="checkbox"
                    checked={autoCapture}
                    onChange={(event) => setAutoCapture(event.target.checked)}
                    disabled={!references?.configured || !cameraActive}
                    className="accent-volt"
                  />
                  Auto-capture when steady
                </label>
              </div>
            </div>
            {autoCapture && <p className="flex items-center gap-1.5 text-[10px] text-volt"><LoaderCircle size={13} className="animate-spin" />Waiting for a steady, detailed camera view…</p>}
          </div>
        </section>

        <section className="panel overflow-hidden">
          <div className="flex items-center gap-2.5 border-b border-line px-4 py-3.5 sm:px-5">
            <div className="grid h-8 w-8 place-items-center rounded-lg bg-raised text-volt"><ScanLine size={16} /></div>
            <div>
              <h2 className="panel-title">Reference comparison</h2>
              <p className="mt-0.5 text-[10px] text-dim">Registered images for {partNumber || 'selected part'}</p>
            </div>
          </div>
          <div className="space-y-4 p-4 sm:p-5">
            {references?.configured && referenceUrls ? (
              <>
                <ReferenceTile label="Reference component" description="Registered part photograph" src={referenceUrls.image} alt="Registered part reference photograph" />
                <ReferenceTile label="2D CAD drawing" description={`Revision ${references.drawing_rev} · top view`} src={referenceUrls.cad} alt="Registered raster CAD drawing" />
              </>
            ) : (
              <div className="rounded-lg border border-dashed border-line bg-raised p-4">
                <div className="flex items-start gap-2.5">
                  <div className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-surface text-dim shadow-sm"><FileImage size={15} /></div>
                  <div>
                    <p className="text-xs font-semibold text-ink">Part references not configured</p>
                    <p className="mt-1 text-[10px] leading-4 text-dim">Upload the registered physical reference photo and a rasterized CAD view to enable part matching.</p>
                  </div>
                </div>
                <div className="mt-4 grid gap-3">
                  <label className="text-[10px] font-semibold text-dim">
                    2D CAD diagram <span className="font-normal text-faint">(PNG or JPG)</span>
                    <input type="file" accept="image/png,image/jpeg" onChange={(event) => setCadUpload(event.target.files?.[0] ?? null)} className="mt-1.5 block w-full rounded-md border border-line bg-surface px-2 py-2" />
                  </label>
                  <label className="text-[10px] font-semibold text-dim">
                    Reference part image <span className="font-normal text-faint">(PNG or JPG)</span>
                    <input type="file" accept="image/png,image/jpeg" onChange={(event) => setReferenceUpload(event.target.files?.[0] ?? null)} className="mt-1.5 block w-full rounded-md border border-line bg-surface px-2 py-2" />
                  </label>
                  <button type="button" onClick={configureReferences} disabled={loading || !cadUpload || !referenceUpload} className="btn-secondary w-full disabled:cursor-not-allowed disabled:opacity-50">
                    <Upload size={13} /> Save part references
                  </button>
                  <p className="text-[9px] leading-4 text-faint">Reference uploads require administrator access. Images are associated with the selected part number.</p>
                </div>
              </div>
            )}

            {references?.configured && (
              <div className="rounded-md border border-line bg-raised p-3">
                <div className="flex items-start gap-2 text-[10px] leading-4 text-dim">
                  <Info size={13} className="mt-0.5 shrink-0 text-faint" />
                  Comparison aligns geometric features and edges. Ensure the live view is clear and shows the same part orientation.
                </div>
              </div>
            )}

            <div className="border-t border-line pt-4">
              <button
                type="button"
                onClick={verifyCapture}
                disabled={!capturedImage || !references?.configured || loading}
                className="btn-primary w-full disabled:cursor-not-allowed disabled:opacity-45"
              >
                {loading ? <LoaderCircle size={14} className="animate-spin" /> : <ScanLine size={14} />}
                {loading ? 'Comparing images…' : 'Compare captured part'}
                {!loading && <ArrowRight size={14} />}
              </button>
              <button
                type="button"
                onClick={() => {
                  setVerification(null)
                  setCapturedImage(null)
                  setCapturedPreview('')
                }}
                disabled={!capturedImage || loading}
                className="btn-secondary mt-2 w-full disabled:cursor-not-allowed disabled:opacity-45"
              >
                <RefreshCw size={13} /> Clear capture and retake
              </button>
            </div>
          </div>
        </section>
      </div>

      <section className={`verification-result ${resultTone}`} aria-live="polite">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="verification-result-icon">
              {verification?.status === 'Match'
                ? <CheckCircle2 size={19} />
                : verification?.status === 'Mismatch'
                  ? <X size={19} />
                  : verification
                    ? <AlertCircle size={19} />
                    : <CircleDot size={19} />}
            </div>
            <div>
              <p className="eyebrow">Verification result</p>
              <h2 className="mt-1 text-base font-semibold">
                {verification?.status ?? 'Ready for comparison'}
              </h2>
              <p className="mt-1 max-w-xl text-[11px] leading-4 opacity-80">
                {verification
                  ? 'Review the geometric comparison and detected differences before continuing.'
                  : 'Capture the component and compare it with its registered CAD reference.'}
              </p>
            </div>
          </div>
          {verification && (
            <div className="min-w-[150px]">
              <div className="flex items-end justify-between gap-3">
                <span className="text-[10px] font-medium opacity-75">Similarity score</span>
                <span className="text-xl font-semibold tabular-nums">{(verification.score * 100).toFixed(1)}%</span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
                <div className="h-full rounded-full bg-current transition-all" style={{ width: `${Math.min(100, verification.score * 100)}%` }} />
              </div>
              <p className="mt-1 text-right text-[9px] opacity-70">Threshold {(verification.threshold * 100).toFixed(0)}%</p>
            </div>
          )}
        </div>

        {verification && (
          <>
            <div className="verification-metrics">
              <Metric label="Feature matches" value={verification.feature_matches} />
              <Metric label="Geometric inliers" value={verification.geometric_inliers} />
              <Metric label="Edge overlap" value={`${(verification.edge_overlap * 100).toFixed(1)}%`} />
            </div>
            <ul className="space-y-1.5 text-[11px]">
              {verification.differences.map((difference, index) => <li key={index} className="flex items-start gap-2"><Circle size={6} className="mt-1.5 shrink-0 fill-current" />{difference}</li>)}
            </ul>
            <div className="flex flex-wrap gap-2 border-t border-current/10 pt-3">
              {verification.status === 'Match' && (
                <button type="button" onClick={startInspection} disabled={loading} className="btn-primary  disabled:opacity-50">
                  {loading ? <LoaderCircle size={14} className="animate-spin" /> : <Check size={14} />}
                  {loading ? 'Starting inspection…' : 'Verify and start inspection'}
                </button>
              )}
              <button type="button" onClick={() => { setVerification(null); setCapturedImage(null); setCapturedPreview('') }} className="btn-secondary">
                <RefreshCw size={13} /> Capture another image
              </button>
            </div>
          </>
        )}
      </section>

      {error && <div role="alert" className="alert alert-error"><AlertCircle size={15} className="mt-0.5 shrink-0" />{error}</div>}
    </div>
  )
}

function ReferenceTile({
  label,
  description,
  src,
  alt,
}: {
  label: string
  description: string
  src: string
  alt: string
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-start justify-between gap-2">
        <div>
          <p className="text-[11px] font-semibold text-ink">{label}</p>
          <p className="mt-0.5 text-[9px] text-dim">{description}</p>
        </div>
        <span className="status-pill status-green !px-2 !py-1"><Check size={10} />Registered</span>
      </div>
      <div className="image-stage min-h-[130px]">
        <img src={src} alt={alt} />
      </div>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-current/20 bg-black/20 px-3 py-2">
      <p className="text-[9px] font-medium opacity-70">{label}</p>
      <p className="mt-1 text-sm font-semibold tabular-nums">{value}</p>
    </div>
  )
}
