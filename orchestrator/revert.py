"""Parse and normalize EVM revert reasons for LLM/Tavily consumption."""
import ast
import re


def clean_revert_reason(raw: str | None) -> str:
    """
    Turn web3 exception strings into a short human-readable revert message.
    """
    if not raw:
        return "unknown"

    text = raw.strip()
    if text.startswith("(") and text.endswith(")"):
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, tuple) and parsed:
                text = str(parsed[0])
        except (SyntaxError, ValueError):
            pass

    match = re.search(
        r"execution reverted(?::|\s+)([^'\"]+|'[^']*'|\"[^\"]*\")",
        text,
        re.IGNORECASE,
    )
    if match:
        msg = match.group(1).strip().strip("'\"")
        return msg or "execution reverted"

    if len(text) > 400:
        return text[:400] + "…"
    return text
