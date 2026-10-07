from typing import Literal

from app.state import ResearchState


def route_after_evaluation(
    state: ResearchState
) -> Literal[
    "search_web",
    "write_report"
]:

    if state.get(
        "is_sufficient",
        False
    ):

        return "write_report"


    return "search_web"