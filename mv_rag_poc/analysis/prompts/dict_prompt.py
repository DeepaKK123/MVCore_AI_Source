"""
analysis/prompts/dict_prompt.py

Wrapped in the fine-tuned model's training template:
    ### System: / ### Instruction: / ### Response:
The instruction body keeps the full format guide and structured output spec.
"""

from langchain_core.prompts import PromptTemplate

_SYSTEM = (
    "You are a UniBasic/U2 multivalue database expert. "
    "You write accurate UniBasic subroutines, answer UniBasic syntax questions, "
    "and explain UniBasic/U2 multivalue concepts. "
    "Always use correct UniBasic/U2 syntax. "
    "Never use Python, Java, or generic BASIC syntax."
)

DICT_PROMPT = PromptTemplate(
    input_variables=["filename", "dict_context", "question"],
    template=(
        "### System:\n"
        + _SYSTEM
        + "\n\n"
        "### Instruction:\n"
        "Analyse the MultiValue dictionary file below and answer the question accurately.\n\n"
        "THIS IS THE DICTIONARY FILE FOR: {filename}\n"
        "The file content below IS the {filename} dictionary layout. "
        "Treat it as such regardless of the field names inside.\n\n"
        "MULTIVALUE DICTIONARY FORMAT GUIDE (read this before parsing):\n\n"
        "Column layout (fixed-width, values may wrap onto continuation lines — join them):\n"
        "  Field Name  | TYP | LOC / Formula      | CONV | Column Header | FORMAT | SM | ASSOC\n"
        "  (col 1-15)  |(16) |(17-30, wraps)      |(31-34)|(35-50)       |(51-57) |(58)|(59+)\n\n"
        "TYPE codes:\n"
        "  A  = Attribute — LOC is a numeric position (attribute number) in the record\n"
        "  I  = I-descriptor — LOC is a calculated formula using other fields\n"
        "  V  = Virtual — LOC is a calculated formula (synonym for I in many MV flavours)\n"
        "  PH = Phrase — LOC lists field names grouped together for reports\n"
        "  SQ = Synonym — alternate name for @ID or another field\n"
        "  X  = Cross-reference / control attribute\n\n"
        "CONVERSION (CONV) codes:\n"
        "  MD2      = Numeric, 2 decimal places (divide stored integer by 100)\n"
        "  MD0      = Numeric, no decimals\n"
        "  MD2,$    = Numeric, 2 decimal places, currency symbol\n"
        "  D2/      = Date, display as DD/MM/YY\n"
        "  D4/      = Date, display as DD/MM/YYYY\n"
        "  MCU      = Convert to uppercase\n"
        "  (blank)  = No conversion, display as stored\n\n"
        "SM (Single/Multi-value) codes:\n"
        "  S  = Single value — one value per record\n"
        "  MV = Multi-value — multiple values stored as @VM-delimited list\n"
        "  MS = Multi-subvalue — sub-values within multi-values\n\n"
        "ASSOC = Association group — MV fields sharing the same ASSOC move in sync (same row in a report)\n\n"
        "TRANS('FILE',key,attr,'X') = Lookup: read attr from FILE using key, 'X' = return empty if not found\n"
        "SUBR('name',args)          = Call external subroutine\n"
        "SUM(...)                   = Aggregate sum across multi-values\n"
        "REUSE(x)                   = Repeat last value x times\n\n"
        "Line wrapping rule: continuation lines (starting with spaces, no field name in col 1) "
        "are a direct continuation of the previous field's formula — join them to reconstruct the full value.\n\n"
        "DICTIONARY FILE CONTENT FOR {filename}:\n"
        "{dict_context}\n\n"
        "QUESTION:\n"
        "{question}\n\n"
        "Respond in this exact structure:\n\n"
        "**File:** `{filename}` — one-line purpose derived from the fields.\n\n"
        "**Fields**\n"
        "| Field | Type | Attr / Formula | Conv | Label | Multi-Value | Association |\n"
        "|-------|------|----------------|------|-------|-------------|-------------|\n"
        "One row per field. For I/V types reconstruct the full formula from wrapped lines. "
        "Mark MV/MS in Multi-Value column.\n\n"
        "**Calculated Fields**\n"
        "For each I or V field: one line explaining what it computes in plain English.\n\n"
        "**Lookups**\n"
        "For each TRANS: `Field → reads <attr> from <FILE> using <key>`. One line each.\n\n"
        "**Phrases**\n"
        "For each PH field: list the grouped fields it contains.\n\n"
        "**Notes**\n"
        "Key observations: MV associations, date/currency conversions, cross-references. "
        "Omit if nothing notable.\n\n"
        "### Response:\n"
    ),
)
