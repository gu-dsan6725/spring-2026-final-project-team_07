# Project Proposal

## Title

SAGE: A Multi-Agent Framework for Stateful, Rule-Constrained Interactive Environments

## Overview

Large Language Models (LLMs) demonstrate strong generative capabilities but often struggle with maintaining long-term structured state, enforcing deterministic rule systems, and avoiding contradictions in multi-turn interactive environments. These limitations present challenges for building production-quality AI agent systems that must operate reliably over extended interactions.

Recent AI-driven role-playing applications, such as Everweave, showcase the creative potential of LLM-based game masters but often prioritize freeform narrative generation over formal rule adjudication and structured state management. This project is inspired by such systems, but shifts the focus toward deterministic rule enforcement, persistent state validation, and multi-agent orchestration.

We propose SAGE (Stateful Agent for Game Environments), a multi-agent architecture designed to support stateful, rule-constrained interactive simulation. The system separates narrative generation from deterministic state mutation through a structured tool layer and a schema-validated canonical world state. Multiple coordinated agents will manage orchestration, narrative presentation, rule enforcement, and state auditing. All state transitions will occur exclusively through deterministic tool calls, enabling reproducibility, validation, and systematic evaluation.

To evaluate the architecture, we will implement a constrained “rogue-lite tower climb” environment consisting of combat, puzzle, and rest floors. This environment provides a controlled and repeatable testbed for measuring rule adherence, state consistency, narrative-state alignment, and long-horizon stability across seeded simulation runs.

The goal of this project is not to build a full game engine, but rather to develop and evaluate a generalizable agent architecture for reliable multi-step interaction in structured environments. The resulting framework may extend to applications such as workflow automation, simulation systems, interactive tutoring platforms, and other domains requiring persistent state management and rule-constrained reasoning.

## Notes

Tyler: I think this project is both feasible and something that I am personally interested in. The main risk is scope creep. However, I believe this can be mitigated with the incremental implementation of system features and a flexible end state. 