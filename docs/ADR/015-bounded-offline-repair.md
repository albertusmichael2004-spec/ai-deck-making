# Bounded offline repair

Reuse Project's proven atomic commit/recovery boundary. A separate run journal points to immutable iteration candidates and specs, so interruption during repair cannot corrupt the last known candidate. Review every candidate independently; persist severity-ordered minimal patches and stop on budgets/no-op/diminishing returns. Commit once after both gates pass, with final candidate/evidence/scope guards. Reject whole-deck replacement for existing work.

Incremental compilation prepares only affected slides and imports new dependency parts under unique names, retaining existing payloads. Chart/table data must participate in protected-scope checks because workbook content can change without altering a frame's XML. Analytical refresh invalidates material claims until reasoning explicitly revalidates them.

The independent native judge identified an axis-crossing regression after a category-order style change: labels were correct but bar lengths were misleading. Restore the value origin to zero, place the perpendicular axis independently, and add deterministic origin checks plus a data-preserving axis repair. Axis crossing semantics were verified against [the python-pptx chart-axis reference](https://python-pptx.readthedocs.io/en/stable/api/chart.html#value-axes). Preserve the failed experiment journals; do not reinterpret them as passing tests.
