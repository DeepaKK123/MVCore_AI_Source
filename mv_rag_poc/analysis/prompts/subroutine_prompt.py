"""
analysis/prompts/subroutine_prompt.py

Uses the fine-tuned model's training template exactly:
    ### System: / ### Instruction: / ### Response:
The analysis instruction is plain-language (no markdown headers) so the
fine-tuned model can answer in the same style as its Q&A training examples.
"""

from langchain_core.prompts import PromptTemplate

_SYSTEM = (
    "You are a UniBasic/U2 multivalue database expert. "
    "You write accurate UniBasic subroutines, answer UniBasic syntax questions, "
    "and explain UniBasic/U2 multivalue concepts. "
    "Always use correct UniBasic/U2 syntax. "
    "Never use Python, Java, or generic BASIC syntax."
)

SUBROUTINE_PROMPT = PromptTemplate(
    input_variables=["context", "graph_context", "question"],
    template=(
        "### System:\n"
        + _SYSTEM
        + "\n\n"
        "### Instruction:\n"
        "Analyze the following UniBasic program and answer these points:\n"
        "1. What is the business purpose of this program?\n"
        "2. What are the key processing steps it performs?\n"
        "3. What files does it open, read, or write?\n"
        "4. What other subroutines or programs does it call?\n"
        "5. Are there any risks or observations — such as missing error handling, "
        "record locks (READU), hard-coded values, or unclosed files?\n\n"
        "SOURCE CODE:\n"
        "{context}\n\n"
        "DEPENDENCY AND CALL GRAPH DATA:\n"
        "{graph_context}\n\n"
        "{question}\n\n"
        "### Response:\n"
    ),
)
