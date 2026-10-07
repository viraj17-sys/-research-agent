# 🔎 AI Web Research & Summary Agent

An Agentic AI mini project that autonomously researches a user-provided topic, evaluates web evidence, performs additional searches when information is insufficient, and generates a structured research report.

---

## Project Objective

The system demonstrates how an AI agent can:

1. Understand a research goal
2. Plan search queries
3. Use an external web-search tool
4. Evaluate collected evidence
5. Decide whether additional research is required
6. Generate a final research report

---

# Architecture

User Topic
    ↓
Query Planner
    ↓
DuckDuckGo Search
    ↓
Evidence Evaluator
    ↓
Sufficient?
   /      \
 NO        YES
 ↓          ↓
Search     Report
Again      Writer
 ↓
Evaluate
Again

---

# Technology Stack

- Python
- LangGraph
- LangChain
- Gemini API
- Groq API
- DuckDuckGo Search
- Pydantic
- Streamlit

---

# AI Models

Gemini is used for:

- Query planning
- Research evaluation
- Follow-up query generation

Groq is used for:

- Final report generation

---

# Agentic Behavior

The most important agentic component is the evaluation loop.

After searching, Gemini evaluates the collected evidence.

If the evidence is insufficient, the system generates a new search query and executes another search.

If the evidence is sufficient, the system generates the final report.

---

# Project Structure

```text
research-agent/
│
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
├── main.py
├── ui.py
│
└── app/
    ├── config.py
    ├── state.py
    ├── tools.py
    │
    └── agent/
        ├── nodes.py
        ├── edges.py
        └── graph.py