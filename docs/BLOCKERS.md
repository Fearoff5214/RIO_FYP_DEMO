# NOVALISEO — Blockers & Mocks

## BLK-001: No GPU / no YOLO defect-specific weights for sheet metal
**Status:** Open  
**Impact:** Stages 3 (defect detection) cannot run with real YOLO/SAM/Anomalib  
**Mock used:** `MockDetector` in `backend/app/cv/detectors/mock.py` — returns deterministic detections 
for the four defect classes (Dent, Scratch, Crack, Deformation) based on image hash.  
**To replace:** Set `NOVALISEO_MODE=real`, point `config/default.yaml` detection.models.yolo to your 
weights path, ensure CUDA-capable GPU with PyTorch CUDA is available.

## BLK-002: No LLM API key
**Status:** Open  
**Impact:** Stage 5 (root-cause prediction) cannot call real LLM  
**Mock used:** `FakeLLMProvider` in `backend/app/llm/providers/fake.py` — returns a fixed 3-cause JSON 
matching the infographic (Improper Bending Force 92%, Material Inconsistency 78%, Tool Wear 71%).  
**To replace:** Set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`, set `prediction.llm.provider` in config.

## BLK-003: No camera hardware
**Status:** Open  
**Impact:** Stage 1 (image capture) cannot use real industrial camera  
**Mock used:** `MockCamera` / `FolderCamera` / `UploadCamera` adapters — accept file uploads or 
pre-staged folder images.  
**To replace:** Implement `GenICamCamera` adapter in `backend/app/cv/camera/genicam.py` using 
harvesters or pypylon; set `camera.adapter=genicam` in config.

## BLK-004: No MES/QMS/ERP credentials
**Status:** Open  
**Impact:** Stage 8 output dispatch cannot reach real systems  
**Mock used:** `MockMesAdapter`, `MockQmsAdapter`, `MockErpAdapter` — log what they would send.  
**To replace:** Set endpoint URLs and auth tokens as env vars (`MES_URL`, `QMS_URL`, `ERP_URL`).

## BLK-005: No SAM (Segment Anything Model) weights
**Status:** Open  
**Impact:** SAM segmentation in Stage 3 not available  
**Mock used:** `SamSegmenter` falls back to `MockDetector` segmentation when model file missing.  
**To replace:** Download `sam_vit_b.pth` from Meta AI, set path in config.

## BLK-006: No Anomalib trained model
**Status:** Open  
**Impact:** Anomalib anomaly detection in Stage 3 not available  
**Mock used:** `AnomalibDetector` returns no detections when model missing.  
**To replace:** Train PatchCore/EfficientAD on good-part images, export model, set path in config.

## BLK-007: No DXF/PDF drawings for sample part
**Status:** Open  
**Impact:** Stage 2 dimensional checking uses synthetic generated DXF  
**Mock used:** `scripts/generate_sample_drawing.py` generates a synthetic DXF for part MS-4505-001.  
**To replace:** Upload real customer DXF/PDF drawings via Admin UI or `POST /api/v1/parts`.
