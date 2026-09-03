import logging
from typing import Optional, Dict, Any
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from src.graph.state import FinFlowState
from src.graph.nodes import (
    extract_node,
    verify_node,
    match_node,
    risk_node,
    policy_node,
    gatekeeper_node
)

logger = logging.getLogger(__name__)

# Global checkpointer for thread-level state persistence and Human-in-the-Loop resumption
memory_checkpointer = MemorySaver()


def route_gatekeeper(state: FinFlowState) -> str:
    """Routing logic after gatekeeper evaluation."""
    if state.get("requires_human_review") and not state.get("human_action"):
        # Graph pauses for Human-in-the-loop review
        return END
    return END


def create_finflow_graph(checkpointer=None):
    """
    Constructs and compiles the FinFlow LangGraph workflow.
    """
    workflow = StateGraph(FinFlowState)

    # 1. Register Nodes
    workflow.add_node("extract", extract_node)
    workflow.add_node("verify", verify_node)
    workflow.add_node("match", match_node)
    workflow.add_node("risk", risk_node)
    workflow.add_node("policy", policy_node)
    workflow.add_node("gatekeeper", gatekeeper_node)

    # 2. Define Execution Graph Edges
    workflow.add_edge(START, "extract")
    workflow.add_edge("extract", "verify")
    workflow.add_edge("verify", "match")
    workflow.add_edge("match", "risk")
    workflow.add_edge("risk", "policy")
    workflow.add_edge("policy", "gatekeeper")
    workflow.add_conditional_edges(
        "gatekeeper",
        route_gatekeeper,
        {
            END: END
        }
    )

    # Compile with checkpointer for HITL state persistence
    compiled_graph = workflow.compile(
        checkpointer=checkpointer or memory_checkpointer,
        interrupt_before=[]
    )

    return compiled_graph


# Pre-compiled default graph instance
finflow_app = create_finflow_graph()
