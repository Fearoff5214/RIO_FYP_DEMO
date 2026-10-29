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
