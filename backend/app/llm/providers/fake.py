"""
Fake LLM provider for CI / mock mode.
Returns the infographic scenario exactly:
Rank 1: Improper Bending Force (92%), Rank 2: Material Inconsistency (78%), Rank 3: Tool Wear (71%).
"""
from __future__ import annotations


MOCK_RESPONSE = {
    "candidates": [
        {
            "cause": "Improper Bending Force / Over Bending",
            "rationale": (
                "The detected deformation and dimensional inaccuracy strongly suggest "
                "excessive or improperly calibrated bending force. Retrieved RCA documents "
                "confirm this pattern for SPCC steel bending operations."
            ),
            "effect": "Deformation, Dimensional Inaccuracy",
            "precautions": [
                "Optimize bending parameters to material specification",
                "Use proper tooling and punch/die sets",
                "Regular machine calibration and force verification",
            ],
            "corrective_actions": [
                "Re-set the press-brake bending force and angle to the material specification",
                "Re-inspect the affected lot for deformation and dimensional deviation",
            ],
            "preventive_actions": [
                "Add bending-force verification to the machine calibration schedule",
                "Control bending parameters per material batch",
            ],
            "verification": "Re-inspect the next 30 parts; no deformation and all dimensions within tolerance",
            "citations": ["seed-001", "seed-004"],
        },
        {
            "cause": "Material Inconsistency / Hardness Variation",
            "rationale": (
                "Hardness variation in the incoming material can cause unpredictable "
                "springback and cracking. Material certificate verification is required."
            ),
            "effect": "Cracking, Springback, Dimensional Variation",
            "precautions": [
                "Verify material certificates against specification",
                "Conduct incoming material hardness inspection",
                "Perform supplier quality audit",
            ],
            "corrective_actions": [
                "Quarantine the affected material batch and check its certificate",
                "Run a hardness test on retained samples",
            ],
            "preventive_actions": [
                "Introduce incoming material hardness inspection",
                "Audit the supplier and tighten the material specification",
            ],
            "verification": "Hardness within specification on the next three batches",
            "citations": ["seed-002"],
        },
        {
            "cause": "Tool Wear / Die Damage",
            "rationale": (
                "Progressive die wear causes scratches, dents, and edge burrs. "
                "Preventive maintenance schedule should be implemented."
            ),
            "effect": "Surface Defects, Edge Burrs, Dimensional Shift",
            "precautions": [
                "Implement regular tooling inspection schedule",
                "Perform preventive maintenance per cycle count",
                "Regrind or replace worn dies proactively",
            ],
            "corrective_actions": [
                "Inspect and regrind or replace the worn die or punch",
                "Remove scratched parts from the lot",
            ],
            "preventive_actions": [
                "Set a preventive-maintenance interval based on cycle count",
                "Add a tool-condition check to the start-of-shift routine",
            ],
            "verification": "No new scratches or dents over the next production run",
            "citations": ["seed-003"],
        },
    ]
}


class FakeLLMProvider:
    """Fake LLM for mock mode — returns deterministic root cause predictions."""

    async def generate_root_causes(
        self,
        context: dict,
        evidence: dict,
        regenerate: bool = False,
    ) -> list[dict]:
        """Return the mock candidates list, tagged so offline output is never mistaken for AI output."""
        return [{**c, "model_version": "fake-offline"} for c in MOCK_RESPONSE["candidates"]]
