# NOVALISEO API Reference

Full interactive docs: http://localhost:8000/docs (Swagger UI)

## Base URL
`/api/v1` — All routes require JWT (Bearer) except health endpoints.
In mock/dev mode, auth is bypassed (dev-user/admin role injected).

## Key Endpoints

| Method | Route | Role | Description |
|--------|-------|------|-------------|
| POST | `/auth/token` | public | Login → JWT |
| POST | `/auth/register` | public | Register user |
| POST | `/jobs` | operator+ | Start inspection |
| GET | `/jobs` | all | List jobs |
| GET | `/jobs/{id}` | all | Job detail + state |
| GET | `/jobs/{id}/events` | all | SSE live status stream |
| POST | `/jobs/{id}/rescan` | operator | L1 PN correction |
| GET/POST | `/gates/1/{id}` | engineer | Dimensional Gate 1 |
| GET/POST | `/gates/label/{id}` | engineer | Label review gate |
| GET/POST | `/gates/2/{id}` | expert | RCA Gate 2 |
| GET/POST | `/gates/3/{id}` | approver | Report Gate 3 |
| GET | `/reports/{job_id}` | all | Report metadata |
| GET | `/reports/{job_id}/download?fmt=pdf\|xlsx\|docx` | all | Download |
| GET/PATCH | `/actions` | engineer+ | Corrective actions |
| POST | `/kb/documents` | admin/expert | Upload KB document |
| GET | `/kb/documents` | all | List documents |
| GET | `/kb/search?q=...` | all | Semantic search |
| POST | `/kb/reindex` | admin | Re-embed all chunks |
| GET/POST | `/parts` | admin | Part master |
| GET | `/dashboard/kpis` | all | Pass rate, defect mix |
| GET | `/audit` | auditor/admin | Audit trail |
| GET | `/healthz` | public | Health check |
| GET | `/readyz` | public | Readiness check |

## Human Gate Payloads

### Gate 1 (POST /gates/1/{job_id})
```json
{
  "decision": "confirm|reject|override",
  "reason_code": "required_if_override",
  "comments": "optional",
  "overrides": [{"feature_id": "H1", "within_tolerance": true}]
}
```

### Gate 2 (POST /gates/2/{job_id})
```json
{
  "decision": "accept|edit|reject_all",
  "selected_rank": 1,
  "edited_cause": "optional if edit",
  "reason": "optional",
  "corrective": ["Action 1", "Action 2"],
  "preventive": ["Prevention 1"],
  "next": "reinspect|manual_rca"
}
```

### Gate 3 (POST /gates/3/{job_id})
```json
{
  "decision": "approve|reject",
  "comments": "required if reject"
}
```

### Root cause analysis with a picture of the part
Every RCA document (DOCX / PDF / Markdown) embeds a picture of the part. With defects it shows them
marked; for a good part it shows the part under a "no defect" banner and the report states
"NO DEFECT FOUND" with the measurements that were checked (no AI call is made).

- `POST /rca/analyze` JSON: `defects` (may be empty), optional `evidence_image` (base64 JPEG/PNG of the
  part) and per-defect `bbox` / `polygon` to mark them.
- `POST /rca/pointcloud` multipart: `scan` (PLY, ASCII PCD, XYZ/PTS/CSV or NPY; millimetres; X length,
  Y width with the flange at Y=0, Z up; translation only, no rotation). Checks length, width, height,
  bend angle, hole diameter/position, cracks (slot walls), dents and scratches against drawing
  MS-4505-001. Returns the same body as `/rca/analyze` plus `scan: {points, spacing_mm}`.
  A scan whose size is far from 120 x 80 x 50 mm is rejected with 422.
- Response: `status` (`DEFECT` | `NO_DEFECT`), `root_cause` (null when no defect), `image_url`,
  `documents`. `GET /rca/{rca_id}/image` serves the picture.

Sample scans: `py scripts/make_bracket_pointclouds.py` writes `docs/demo/pointclouds/*.ply`.
