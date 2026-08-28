"""What remains of the V2 agent loop package.

The loop itself is gone. `/advise` runs the grounded facts loop in
`app/agent_core/facts/`, and the superseded tree underneath this package --
`runner`, `constitution`, `fact_admission`, `working_set`, `arg_refs`,
`answer_boundary`, `front_door`, `progress`, plus `agent_core/tools`,
`reasoning_blocks` and `subagents` -- was retired once nothing reachable from
the running application imported any of it. Verified by tracing the live import
closure from `app.main` and `app.routes.advise`: 58 modules, none of them these.

`course_names` stays, and is the only reason this package still exists:
`app/main.py` imports `load_catalog_names` from it.

That import is also why the retirement mattered beyond tidiness. This file used
to re-export `run_agent_loop` eagerly, so the one line pulling in
`course_names` dragged the whole superseded tree -- and the V1 tool layer under
it -- into every process, behind an import nobody could see.
"""

from __future__ import annotations

__all__: list[str] = []
