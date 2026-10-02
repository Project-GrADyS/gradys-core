"""Output helper shared by the showcases."""


def check(condition: bool, description: str) -> None:
    """Assert a showcase expectation and print it as one short line."""
    assert condition, description
    print(f"  ok  {description}")
