from langgraph.graph import (
    START,
    END,
    StateGraph,
)

from app.state import ResearchState

from app.agent.nodes import (
    plan_queries,
    search_web,
    evaluate_results,
    write_report,
)

from app.agent.edges import (
    route_after_evaluation,
)


def build_research_graph():

    builder = StateGraph(
        ResearchState
    )


    # -----------------------------------------
    # Register nodes
    # -----------------------------------------

    builder.add_node(
        "plan_queries",
        plan_queries
    )


    builder.add_node(
        "search_web",
        search_web
    )


    builder.add_node(
        "evaluate_results",
        evaluate_results
    )


    builder.add_node(
        "write_report",
        write_report
    )


    # -----------------------------------------
    # Starting point
    # -----------------------------------------

    builder.add_edge(

        START,

        "plan_queries"
    )


    # -----------------------------------------
    # Normal flow
    # -----------------------------------------

    builder.add_edge(

        "plan_queries",

        "search_web"
    )


    builder.add_edge(

        "search_web",

        "evaluate_results"
    )


    # -----------------------------------------
    # Agentic decision
    # -----------------------------------------

    builder.add_conditional_edges(

        "evaluate_results",

        route_after_evaluation,

        {

            "search_web":
                "search_web",

            "write_report":
                "write_report",
        },
    )


    # -----------------------------------------
    # End
    # -----------------------------------------

    builder.add_edge(

        "write_report",

        END
    )


    return builder.compile()


research_graph = (
    build_research_graph()
)