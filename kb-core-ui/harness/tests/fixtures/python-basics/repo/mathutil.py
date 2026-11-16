"""Simple math utilities."""

DEFAULT_START = 0


def add(a, b):
    """Return the sum of two numbers."""
    return a + b


class Calculator:
    """Accumulates a running total."""

    def __init__(self, total=DEFAULT_START):
        self.total = total

    def add_to(self, n):
        """Add n to the total and return the new total."""
        self.total = add(self.total, n)
        return self.total
