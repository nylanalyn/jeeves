# Caw Module Design

**Date:** 2026-03-03
**Status:** Approved

## Overview

A new `modules/caw.py` that responds to any user saying "CAW" (or variants) with a randomly chosen crow-themed message. Modelled directly on `modules/sailing.py`.

## Trigger

Two patterns checked in `on_ambient_message`:

- `\bCAW\b` (case-insensitive, whole-word) — catches "caw", "CAW", "Caw" as standalone words
- `!caw` anywhere in the message (case-insensitive)

No `target_user` filter — any user in the channel triggers it.

## Response Pool

~25 responses mixing corvid folklore and playful chaos energy. Formatted with `{title}` (the bot's title string for the triggering user). Tone: mostly fun with occasional dramatic flair.

## Cooldown & State

- Default cooldown: 5 seconds (same as sailing.py)
- Tracked via module state (`last_response_time`)
- Configurable per-channel via `get_config_value("cooldown_seconds", ...)`

## Architecture

Direct port of `sailing.py` structure:

- `setup(bot)` factory function
- `Caw(SimpleCommandModule)` class
- `_register_commands()` is a no-op (no `!commands`)
- `on_ambient_message()` handles detection and response
