"""LangGraph chat agent for the demo.

Memory in Cognee + pgvector; every model call routed through TensorZero.
The agent has one tool exposed: ``vismaran_erase``, which calls the
orchestrator with a human-in-the-loop confirmation step.

Lands Day 6.
"""
