# Literature Search Methodology

This document describes the methodology used for conducting literature reviews for the Kindred Histories project.

## Overview

The methodology uses a 4-phase approach with parallel AI agents for efficient, verified literature discovery.

## Phase 1: Launch Parallel Literature Review Agents

- Launch up to 3 agents in parallel, each focused on a specific topic area
- Each agent is given:
  - A clear topic focus (e.g., "Identity & Representation in Computing")
  - Specific subtopics to explore (e.g., "Intersectionality in HCI", "Culturally-responsive computing")
  - Instructions to find academic papers from reputable venues (CHI, CSCW, NeurIPS, EMNLP, etc.)

## Phase 2: Collect and Organize Literature

Each agent returns for each paper:
- **Paper title** - Full title
- **Authors** - First author et al. format
- **Year** - Publication year
- **Venue** - Conference or journal (e.g., CHI, NeurIPS, JASIST)
- **Relevant quote(s)** - Direct quotes showing relevance
- **Relevance justification** - Which goal or method it addresses

Target: ~6-8 papers per topic area

## Phase 3: Create LaTeX Document

Structure the Related Work section by theme:
```latex
\section{Related Work}
\subsection{Theme 1}
% Narrative integrating citations
\subsection{Theme 2}
% Narrative integrating citations

\appendix
\section{Citation Evidence}
% For each citation: quote + relevance justification
```

Create BibTeX entries with:
- Correct entry type (@inproceedings, @article, @book)
- All required fields (author, title, year, booktitle/journal)
- DOI when available

## Phase 4: Verification Agent

Launch a verification agent to check each citation:
1. **Existence check** - Web search for paper title + authors
2. **Metadata verification** - Confirm year, venue, authors are correct
3. **DOI/URL resolution** - Check that links work
4. **Flag issues** - Report papers that cannot be verified

Expected outcomes:
- Most papers verified (80-90%)
- Some papers may need metadata corrections
- A few papers may need to be removed if unverifiable

## Quality Criteria

Papers should be:
- From peer-reviewed venues (conferences, journals)
- Highly cited or from reputable venues
- Directly relevant to the system's goals or methods
- Recent enough to be relevant (last 10-15 years preferred, with foundational exceptions)

## Example Topic Areas from Previous Search

1. **Identity & Representation in Computing**
   - Intersectionality in HCI
   - Culturally-responsive computing
   - Digital humanities for marginalized communities

2. **Information Retrieval & Search Methods**
   - Faceted search systems
   - Exploratory search
   - Semantic search with embeddings

3. **LLM-Powered Systems**
   - LLM agents for information gathering
   - Retrieval-augmented generation (RAG)
   - Chain-of-thought prompting
