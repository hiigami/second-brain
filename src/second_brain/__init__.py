"""Local evidence capture and human-review tools."""


def main() -> None:
    """Run the same operator commands as the compatibility scripts."""
    from .cli import main as cli_main
    cli_main()
