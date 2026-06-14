"""Prompt text for the prospecting agent, one module per prompt type.

Each module exposes a `SYSTEM` string and a `build_user(...)` function that
returns the user-message text. Keeping prompts here (separate from the
orchestration code) makes them easy to read, diff, and tune in one place.
"""
