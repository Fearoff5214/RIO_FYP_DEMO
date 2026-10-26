from typing import Any, TypedDict


class InspectionState(TypedDict, total=False):
    job_id: str
    part_number: str
    part: dict | None
    image_paths: list[str]      # as uploaded
    working_paths: list[str]    # after quality auto-adjust / recapture
    source: dict                # {'type': 'upload'} | {'type': 'camera', 'device': int}
    recipe: dict                # live-camera settings in use
    recapture: bool             # set by gate 2 reject-all: take new frames at the default recipe
    quality: list[dict]
    scale_override: float | None
    dimensional: dict
    defects: list[dict]
    evidence: list[dict]
    low_evidence: bool
    rca: list[dict]
    selected_cause: dict | None
    report_data: dict
    report_paths: dict
    report_revision: int
    approver_comments: list[str]
    approver: str
    flags: list[str]
    retries: dict[str, int]     # L1..L8 counters
    status: str
    _route: Any                 # scratch: router hint set by a node
