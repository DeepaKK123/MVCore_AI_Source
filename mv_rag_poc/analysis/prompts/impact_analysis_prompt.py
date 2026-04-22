"""
analysis/prompts/impact_analysis_prompt.py

Used when the developer asks for IMPACT ANALYSIS of a proposed change
(e.g. "analyze the impact if we change the fix for MVAI-11").
Output is pure analysis — NO code, NO suggested fix.
"""

from langchain_core.prompts import PromptTemplate

IMPACT_ANALYSIS_PROMPT = PromptTemplate(
    input_variables=[
        "source_code", "requirement", "subroutine", "file_type",
        "question", "graph_context",
    ],
    template="""You are a senior MultiValue BASIC / UniBasic developer performing
an IMPACT ANALYSIS only. Do NOT write code. Do NOT produce a fix.

Rules (STRICT):
  - NO code blocks. NO "Suggested Code" section. NO UniBasic syntax output.
  - Output must be pure analysis: what changes, what it touches, what breaks.
  - Task summary: 3–4 short lines MAX (do NOT paste the ticket verbatim).
  - Spend the output budget on IMPACT: callers, callees, data files, locks,
    multivalued fields, downstream reports, and verification steps.
  - Internally, read the ENTIRE ticket AND the ENTIRE source code before
    answering — but keep the task summary short.

FILE: {subroutine}
TYPE: {file_type}
  - PROGRAM     = standalone executable
  - SUBROUTINE  = called via CALL statement

COMPLETE SOURCE CODE (read every line before responding):
{source_code}

DEPENDENCY GRAPH CONTEXT (callers / callees / impacted files):
{graph_context}

REQUIREMENT / JIRA TASK DETAILS:
{requirement}

DEVELOPER REQUEST:
{question}

Respond in this exact structure:

## Task Summary
- Line 1: `{{key}} — {{type}} — {{status}} — {{priority}}`
- Line 2–3: One-sentence summary of the proposed change.
- Line 4 (optional): The single most important acceptance criterion in one compact bullet.

## Target Program
- `{subroutine}` ({file_type}) — one-line reason this is the file being changed.

## Proposed Change (conceptual, NO code)
- 2–4 bullets describing WHAT would change in behaviour. Plain English.
- Reference line ranges in the source, but do NOT quote code.

## Impact Analysis (detailed)
### Direct impact
- Functions / paragraphs inside `{subroutine}` that would be affected — cite line ranges.
- Variables, multivalued fields, and record structures touched.
- File I/O touched (OPEN / READ / READU / WRITE / DELETE).
- Locking implications (READU ... THEN ... ELSE, RELEASE).

### Upstream impact (callers)
- SUBROUTINE: list callers from the graph context; explain how parameter
  semantics change and whether any caller needs updating.
- PROGRAM: list entry points, menu items, phantom jobs, or schedulers that
  invoke it.

### Downstream impact (callees and shared data)
- Subroutines called by this file whose behaviour or inputs change.
- Shared dict files, BP files, or $INSERT records affected.
- Reports, queries (LIST/SELECT), or integrations that read the same data.

### Data / integrity risk
- Could existing records become inconsistent?
- Are there historical records that won't match the new logic?
- Any migration or backfill required?

## Testing & Verification
- Unit-level checks inside `{subroutine}`.
- Regression checks for each caller listed above.
- Data validation queries (LIST/SELECT) to run before and after.
- Compile order (which files to BASIC/CATALOG).

## Residual Risks & Open Questions
- Anything the ticket does not make clear.
- Edge cases the current code handles that the change might break.
- Anything that needs confirmation from the business analyst before proceeding.

Hard rules (repeat):
- NO code. NO ```unibasic blocks. NO "Suggested Code" section.
- Keep the task summary short; keep the impact detail rich.
- If source code is missing or "Unknown", say so and list what's needed to complete the analysis — do NOT invent behaviour.""",
)
