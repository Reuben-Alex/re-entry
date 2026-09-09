"""Custom exceptions for the PoCForge orchestrator."""


class ConfigurationError(Exception):
    """Raised when required configuration is missing."""


class CompilationFailed(Exception):
    """Raised when LLM-generated Solidity cannot be compiled after retries."""
