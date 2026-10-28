# 1. Record architecture decisions

**Status:** Accepted  
**Date:** 2026-10-28

## Context

kaushal writes into the configuration of programs it doesn't own: Claude Code, Codex, opencode, Gemini CLI. Every choice about where and how it writes has a reason that isn't visible in the code, and getting one wrong breaks someone's agent.

## Decision

Each significant decision is a short record here (context, decision, consequences), numbered, never rewritten: a later record supersedes an earlier one.

## Consequences

- A contributor can see why kaushal does something before changing it.
- The website lists them under Decisions.
