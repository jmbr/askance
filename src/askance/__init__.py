"""Askance: an MCP server for hypothesis testing, backed by SciPy and statsmodels."""

from askance.hypothesis import (
    POWER_DESIGNS,
    TESTS,
    AskanceError,
    adjust_p_values,
    analyze_power,
    list_tests,
    run_binomial_test,
    run_contingency_test,
    run_samples_test,
)

__all__ = [
    "POWER_DESIGNS",
    "TESTS",
    "AskanceError",
    "adjust_p_values",
    "analyze_power",
    "list_tests",
    "run_binomial_test",
    "run_contingency_test",
    "run_samples_test",
]
