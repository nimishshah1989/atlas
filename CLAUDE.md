# Project ATLAS — Backend Development

## What is ATLAS
Market intelligence, instrument selection, and investment simulation platform built on the JIP Data Core (24M+ rows, 30+ tables). Backend-first development.

## Architecture
- **Backend:** Python FastAPI on port 8010 (separate from existing marketpulse on 8000)
- **Database:** PostgreSQL RDS Mumbai (read-only against JIP Data Core tables)
- **New tables:** atlas_briefings, atlas_simulations, atlas_watchlists
- **ORM:** Raw asyncpg for complex read queries, SQLAlchemy 2.0 async for ATLAS-owned tables
- **Deploy:** Same EC2 as marketpulse, Docker, GitHub Actions CI/CD

## Dev spec
Full specification: ~/Downloads/ATLAS-dev-spec-v2.md

## Conventions
- Follow all rules from ~/.claude/CLAUDE.md (financial domain, database, Python backend)
- Stock is the atom — everything builds from instrument-level data upward
- No modifications to JIP Data Core tables — read only
- All money values: Decimal, never float
- Indian formatting: lakh/crore, IST timezone
- Backend first, always. No frontend until APIs are proven.
