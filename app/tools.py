from concurrent.futures import ThreadPoolExecutor

from ddgs import DDGS


def execute_web_search(
    query: str,
    max_results: int = 5
) -> list[dict]:

    try:

        search = DDGS()

        results = search.text(

            query,

            max_results=max_results,

            safesearch="moderate",
        )

        formatted_results = []


        for item in results or []:

            formatted_results.append(

                {
                    "query": query,

                    "title":
                        item.get(
                            "title",
                            "Untitled"
                        ),

                    "url":
                        item.get(
                            "href",
                            ""
                        ),

                    "snippet":
                        item.get(
                            "body",
                            ""
                        ),
                }
            )


        return formatted_results


    except Exception as exc:

        return [

            {

                "query": query,

                "title": "Search Error",

                "url": "",

                "snippet":
                    f"Search failed: {exc}",
            }
        ]


def execute_web_searches(
    queries: list[str],
    max_results: int = 5,
) -> list[dict]:
    """Run independent searches concurrently and preserve query order."""
    if not queries:
        return []

    with ThreadPoolExecutor(max_workers=min(len(queries), 4)) as executor:
        batches = list(
            executor.map(
                lambda query: execute_web_search(query, max_results),
                queries,
            )
        )

    return [result for batch in batches for result in batch]
