"""Streamlit launcher for Ledger UI."""

from __future__ import annotations

from typing import Sequence

from ..ui.app import run


def main(argv: Sequence[str] | None = None) -> None:
    del argv
    run()
