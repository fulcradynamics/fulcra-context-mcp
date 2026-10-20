"""Raw datashare selector completeness shared by projections and privacy checks."""
from typing import TypeGuard


def selectors_complete(selectors: object) -> TypeGuard[list[str]]:
    return isinstance(selectors, list) and all(
        isinstance(t, str) and bool(t) and t == t.strip()
        and (not t.startswith(('file:', 'filehistory:')) or t.partition(':')[2].startswith('/'))
        for t in selectors
    )
