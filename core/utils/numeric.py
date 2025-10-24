"""Numeric utilities for consistent Decimal handling."""

from decimal import Decimal, getcontext

# Set precision for financial calculations
getcontext().prec = 28


def D(x) -> Decimal:
    """
    Robust Decimal conversion for ints/floats/strings/Decimals.
    
    Single source of truth for numeric conversions.
    Avoids binary floating-point artifacts by converting floats to strings first.
    
    Args:
        x: Value to convert (int, float, str, or Decimal)
    
    Returns:
        Decimal: Converted value
    
    Raises:
        TypeError: If type is not supported
    """
    if isinstance(x, Decimal):
        return x
    if isinstance(x, int):
        return Decimal(x)
    if isinstance(x, str):
        return Decimal(x)
    if isinstance(x, float):
        # Convert float to string first to avoid binary FP artifacts
        return Decimal(str(x))
    raise TypeError(f"Unsupported numeric type: {type(x)}")
