"""
Load sample knowledge base documents.
Run with: python scripts/load_kb.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

KB_SAMPLES_DIR = Path(__file__).resolve().parents[1] / "kb_samples"


SAMPLE_DOCS = [
    {
        "filename": "bending_rca.txt",
        "title": "Bending Force Root Cause Analysis",
        "doc_type": "rca",
        "content": """
Improper Bending Force / Over Bending Root Cause Analysis

Defect Types: deformation, dimensional inaccuracy
Process: sheet metal bending, press brake operations

Root Cause: Improper bending force settings or over-bending beyond the material's elastic limit.

Effect: Deformation of the part, dimensional inaccuracy in bent features,
springback issues causing part to not meet dimensional tolerances.

Corrective Actions:
1. Recalibrate press brake force settings to material specification
2. Verify tonnage calculator against actual material hardness test results
3. Implement first-article inspection before production run

Preventive Actions:
1. Optimize bending parameters to material specification before production
2. Use proper tooling and punch/die sets matched to material thickness
3. Regular machine calibration and force verification schedule
4. Install force monitoring sensors on press brake

Historical Cases:
- 2023-Q1: Part MS-4505-001, deformation detected, cause confirmed as over-bending
- 2023-Q3: Part MS-3301-002, dimensional fail, cause confirmed as improper bending force
""",
    },
    {
        "filename": "material_rca.txt",
        "title": "Material Inconsistency Root Cause Analysis",
        "doc_type": "rca",
        "content": """
Material Inconsistency / Hardness Variation Root Cause Analysis

Defect Types: crack, deformation, dimensional variation
Material: SPCC steel, cold-rolled sheet metal

Root Cause: Hardness variation in incoming material lot causes unpredictable
springback behavior and susceptibility to cracking under forming operations.

Effect: Cracking at bend radius, dimensional inaccuracy due to variable springback,
surface defects from work hardening inconsistency.

Corrective Actions:
1. Verify material certificates against specification (yield strength, tensile strength, hardness)
2. Conduct incoming material hardness inspection using Rockwell or Vickers test
3. Segregate non-conforming material lots and return to supplier
4. Re-inspect all parts manufactured from suspect material lot

Preventive Actions:
1. Perform supplier quality audit on material quality control processes
2. Establish approved supplier list with material certification requirements
3. Implement sampling inspection plan for incoming material lots
4. Track material lot numbers in quality management system for traceability

Process Notes:
SPCC steel typical hardness: HRB 40-60. Variation >10 HRB within a lot indicates
inconsistent processing and should trigger incoming inspection escalation.
""",
    },
    {
        "filename": "tooling_rca.txt",
        "title": "Tool Wear and Die Damage Root Cause Analysis",
        "doc_type": "rca",
        "content": """
Tool Wear / Die Damage Root Cause Analysis

Defect Types: scratch, dent, edge burr, dimensional shift
Process: bending, stamping, forming

Root Cause: Progressive wear of punch/die tooling causes dimensional drift,
surface scratches, edge burrs and dents on formed parts.

Effect: Surface defects (scratches from worn tooling edges), dents from
damaged die surfaces, edge burrs from worn cutting edges,
gradual dimensional shift as tooling geometry changes.

Corrective Actions:
1. Inspect tooling under magnification for wear, chipping, or damage
2. Regrind worn punch/die to restore geometry within tolerance
3. Replace severely damaged tooling
4. Perform first-article inspection after tooling change

Preventive Actions:
1. Implement regular tooling inspection schedule based on production cycle count
2. Perform preventive maintenance per manufacturer-specified cycle count
3. Regrind or replace worn dies proactively before defects appear
4. Maintain tooling maintenance log and track wear progression
5. Install tooling load monitoring to detect abnormal forces indicating wear

Severity Note: Crack-like defects from die damage are classified as critical
and require immediate production stop and 100% inspection of affected parts.
""",
    },
    {
        "filename": "springback_rca.txt",
        "title": "Springback Root Cause Analysis",
        "doc_type": "rca",
        "content": """
Springback Root Cause Analysis

Defect Types: deformation, dimensional inaccuracy
Process: sheet metal bending

Root Cause: Elastic recovery of sheet metal after forming (springback)
causes the bent angle to open up beyond the intended angle.

Effect: Dimensional inaccuracy in bent angles, parts out of tolerance
on angular dimensions and related linear dimensions.

Corrective Actions:
1. Apply overbend compensation to tooling angle
2. Test material springback coefficient for each lot
3. Adjust bending program to compensate for measured springback

Preventive Actions:
1. Implement springback compensation in bending programs as standard
2. Conduct springback testing on incoming material lots
3. Use bottoming or coining process for critical angular tolerances
4. Document springback coefficients by material grade and thickness

Lubrication:
Inadequate lubrication increases friction, affects springback behavior,
and causes surface scratches. Use appropriate forming lubricant per material spec.
""",
    },
]


async def load_sample_kb() -> None:
    """Load sample KB documents."""
    from app.db.session import create_tables, _get_session_factory
    from app.rag.ingest.pipeline import ingest_document

    await create_tables()

    # Write sample files
    KB_SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    for doc in SAMPLE_DOCS:
        filepath = KB_SAMPLES_DIR / doc["filename"]
        filepath.write_text(doc["content"].strip())

    factory = _get_session_factory()
    async with factory() as db:
        for doc in SAMPLE_DOCS:
            filepath = KB_SAMPLES_DIR / doc["filename"]
            result = await ingest_document(
                file_path=filepath,
                doc_type=doc["doc_type"],
                title=doc["title"],
                meta={"process": "bending", "material": "steel"},
                db=db,
            )
            print(f"[kb] {doc['title']}: {result}")

    print("[kb] Sample knowledge base loaded.")


if __name__ == "__main__":
    asyncio.run(load_sample_kb())
