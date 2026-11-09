import logging
from typing import Annotated, Any

from duckduckgo_async_search import DuckDuckGoSearch
from pydantic import BaseModel, ConfigDict, Field, field_validator, ValidationError
from fastmcp.exceptions import ToolError
from fastmcp.tools import tool

MAX_QUERY_LENGTH = 500
MAX_RESULTS_LIMIT = 25
DEFAULT_RESULTS_LIMIT = 5

logger = logging.getLogger(__name__)

ddg_client = DuckDuckGoSearch(
    ddg_backends=["auto"]
)


class DDGResult(BaseModel):
    """A single DuckDuckGo search result.

    Built from external parser output, so it is deliberately lenient:
    constructing it never raises. Use `from_raw` to skip unusable entries
    with a warning in the log.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str = Field(
        default="",
        title="Title",
        description="Search result title",
        examples=["Python (programming language) - Wikipedia"],
    )
    url: str = Field(
        default="",
        title="URL",
        description="Search result URL",
        examples=["https://en.wikipedia.org/wiki/Python_(programming_language)"],
    )
    snippet: str = Field(
        default="",
        title="Snippet",
        description="Short text excerpt from the result",
        examples=["Python is a high-level, general-purpose programming language..."],
    )

    @field_validator("title", "url", "snippet", mode="before")
    @classmethod
    def _to_clean_str(cls, value: Any) -> str:
        """Turn None / non-str into a stripped string, never raise."""
        if value is None:
            return ""
        return str(value).strip()

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "DDGResult | None":
        """Build a result from a raw parser dict.

        Returns None (and logs a warning) if the entry is unusable.
        """
        try:
            result = cls.model_validate(raw)
        except ValidationError:
            logger.warning("Dropped malformed DDG result: %r", raw)
            return None

        if not result.url.startswith(("http://", "https://")):
            logger.warning("Dropped DDG result with bad URL: %r", raw)
            return None

        return result


def _item_to_raw_dict(item: object) -> dict[str, object]:
    """Extract the fields we care about from an arbitrary DDG result object."""
    return {
        "title": getattr(item, "title", None),
        "url": getattr(item, "url", None),
        "snippet": getattr(item, "snippet", None),
    }


async def _search_ddg(query: str, max_results: int) -> list[DDGResult]:
    """Call the DDG library and normalize the output.

    Never raises on search failure — logs and returns whatever is usable.
    """
    try:
        raw_items = await ddg_client.top_n_result(
            query=query,
            n=max_results,
        )
    except Exception:
        logger.exception(
            "DDG search failed: query=%r",
            query,
        )
        return []

    if not raw_items:
        return []

    results: list[DDGResult] = []
    for item in raw_items:
        result = DDGResult.from_raw(_item_to_raw_dict(item))
        if result is not None:
            results.append(result)

    return results


@tool
async def search_ddg(
    query: Annotated[
        str,
        Field(
            description="Search query string. Must be non-empty after stripping whitespace.",
            min_length=1,
            max_length=MAX_QUERY_LENGTH,
        ),
    ],
    max_results: Annotated[
        int,
        Field(
            description="Maximum number of results to return.",
            ge=1,
            le=MAX_RESULTS_LIMIT,
        ),
    ] = DEFAULT_RESULTS_LIMIT,
) -> list[DDGResult]:
    """Search DuckDuckGo and return up to `max_results` results.

    Returns an empty list (instead of raising) when the upstream search fails,
    so the model can decide how to proceed. Only invalid input raises ToolError.
    """
    query = query.strip()

    if not query:
        raise ToolError("query must not be empty")

    result = await _search_ddg(query=query, max_results=max_results)
    return result
