"""
analysis/prompts/unibasic_general_prompt.py

Prompt is structured to match the fine-tuned model's training template exactly:
    ### System: / ### Instruction: / ### Response:
The model (qwen2.5-14b-unibasic-coder_Q4_K_M) was trained on that format.
Deviating from it causes the model to fall back to base-model behaviour.
"""

from langchain_core.prompts import PromptTemplate

# Exact system prompt used during fine-tuning — must not be changed.
_SYSTEM = (
    "You are a UniBasic/U2 multivalue database expert. "
    "You write accurate UniBasic subroutines, answer UniBasic syntax questions, "
    "and explain UniBasic/U2 multivalue concepts. "
    "Always use correct UniBasic/U2 syntax. "
    "Never use Python, Java, or generic BASIC syntax."
)

UNIBASIC_GENERAL_PROMPT = PromptTemplate(
    input_variables=["question", "syntax_context", "code_examples"],
    template=(
        "### System:\n"
        + _SYSTEM
        + "\n\n"
        "### Instruction:\n"
        "Use the UniBasic syntax reference and real codebase examples below to write "
        "accurate, idiomatic UniBasic code. Ground your answer in the patterns shown "
        "in the codebase examples — use the same variable naming conventions, "
        "error-handling style, and file-operation patterns.\n\n"
        "SYNTAX REFERENCE:\n"
        "{syntax_context}\n\n"
        "REAL CODEBASE EXAMPLES:\n"
        "{code_examples}\n\n"
        "{question}\n\n"
        "### Response:\n"
    ),
)
