"""
Deprecation of API endpoints and fields (ADR 0022): a route marked as deprecated keeps working and tells every
caller when it will go. Dependencies add the standard `Deprecation` and `Sunset` headers and a `Link` to what
replaces it; the same facts belong in the OpenAPI file (`deprecated=True`) and in the changelog.
"""

from collections.abc import Awaitable, Callable

from fastapi import Response

DEPRECATION_HEADER = "Deprecation"
SUNSET_HEADER = "Sunset"
LINK_HEADER = "Link"


def deprecated(sunset: str, replacement: str | None = None) -> Callable[[Response], Awaitable[None]]:
    """`sunset` is an HTTP date (for example "Wed, 06 May 2027 00:00:00 GMT"); `replacement` is a path."""

    async def mark(response: Response) -> None:
        response.headers[DEPRECATION_HEADER] = "true"
        response.headers[SUNSET_HEADER] = sunset
        if replacement:
            response.headers[LINK_HEADER] = f'<{replacement}>; rel="successor-version"'

    return mark
