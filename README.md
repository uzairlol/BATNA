# BATNA: Bilateral Agent Trust & Negotiation Architecture

[![CI](https://github.com/uzairlol/BATNA/actions/workflows/ci.yml/badge.svg)](https://github.com/uzairlol/BATNA/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)

An autonomous multi-agent contract negotiation system in which two tool-using LLM agents represent principals with genuinely conflicting interests, dynamically call real data-backed tools served over **MCP (Model Context Protocol)**, are audited for reasoning-tool-action consistency by a **Theory-of-Mind (ToM) auditor**, are protected from manipulation by a **poisoning-aware structured memory system**, and escalate consequential decisions to a **human approval gate**.

---

## 🏗️ Architecture Overview

```
                        ┌──────────────────────────────────────────────┐
                        │              Human Approval Gate             │
                        │      (High-stakes & Mandate Escalations)     │
                        └──────────────────────┬───────────────────────┘
                                               │
               ┌───────────────────────────────┴───────────────────────────────┐
               ▼                                                               ▼
    ┌──────────────────────┐                                       ┌──────────────────────┐
    │     Buyer Agent      │◄═════════════════════════════════════►│     Seller Agent     │
    │  (LangGraph / LLM)   │          Bilateral Exchange           │  (LangGraph / LLM)   │
    └───┬──────────────┬───┘                                       └───┬──────────────┬───┘
        │              │                                               │              │
        │              ▼                                               │              ▼
        │     ┌──────────────────┐                                     │     ┌──────────────────┐
        │     │Structured Memory │                                     │     │Structured Memory │
        │     │  (SEAM Curator)  │                                     │     │  (SEAM Curator)  │
        │     └──────────────────┘                                     │     └──────────────────┘
        ▼                                                              ▼
┌────────────────────────────────┐                           ┌────────────────────────────────┐
│      External MCP Servers      │                           │      External MCP Servers      │
│  • FRED / BLS Market Benchmark │                           │  • FRED / BLS Market Benchmark │
│  • USAspending.gov Precedent   │                           │  • USAspending.gov Precedent   │
└────────────────────────────────┘                           └────────────────────────────────┘
               │                                                               │
               └───────────────────────────────┬───────────────────────────────┘
                                               │
                                               ▼
                                ┌──────────────────────────────┐
                                │     ToM Consistency Auditor   │
                                │  (ELICIT Provenance Check)   │
                                └──────────────────────────────┘
```

---

## ⚡ Quick Start

### 1. Prerequisites
- Python 3.11+
- Docker & Docker Compose
- Conda or virtualenv

### 2. Setup Environment
```bash
git clone https://github.com/uzairlol/BATNA.git
cd BATNA

# Install dependencies
pip install -e ".[dev]"

# Start Postgres & Redis services
docker-compose up -d
```

### 3. Run Quality Gates
```bash
# Linting
ruff check .

# Type checking
mypy src tests

# Test suite
pytest
```
