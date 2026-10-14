"""Short Anvil call traces for the retry prompt."""


def format_call_trace(node, depth: int = 0, max_lines: int = 40) -> str:
    """Render a callTracer tree as indented lines."""
    lines: list[str] = []

    def walk(item, level: int) -> None:
        if len(lines) >= max_lines or not isinstance(item, dict):
            return
        kind = item.get("type", "CALL")
        to_addr = item.get("to") or item.get("from") or ""
        selector = (item.get("input") or "")[:10]
        err = item.get("error") or item.get("revertReason") or ""
        pad = "  " * level
        extra = f" {err}" if err else ""
        lines.append(f"{pad}{kind} {to_addr} {selector}{extra}".rstrip())
        for child in item.get("calls") or []:
            walk(child, level + 1)

    walk(node, depth)
    if not lines:
        return ""
    return "\n".join(lines)


def trace_call(w3, tx: dict) -> str:
    """Best-effort debug_traceCall. Empty string when the node has no tracer."""
    try:
        response = w3.provider.make_request(
            "debug_traceCall",
            [tx, "latest", {"tracer": "callTracer"}],
        )
        result = response.get("result") if isinstance(response, dict) else None
        if result is None:
            return ""
        return format_call_trace(result)[:2500]
    except Exception as exc:
        return f"(trace unavailable: {exc})"


def trace_transaction(w3, tx_hash: str) -> str:
    """Best-effort debug_traceTransaction for a mined hash."""
    try:
        response = w3.provider.make_request(
            "debug_traceTransaction",
            [tx_hash, {"tracer": "callTracer"}],
        )
        result = response.get("result") if isinstance(response, dict) else None
        if result is None:
            return ""
        return format_call_trace(result)[:2500]
    except Exception as exc:
        return f"(trace unavailable: {exc})"
