"""netverify — turn an intent into verifiable network acceptance cases."""

from .case import Case, CaseError, load_case, load_cases, validate

__all__ = ["Case", "CaseError", "load_case", "load_cases", "validate"]
__version__ = "0.1.0"
