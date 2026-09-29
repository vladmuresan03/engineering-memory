"""Read GitHub repository history as provenance-bearing sources.

The connector deliberately returns source records, not inferred decisions. Later
processing can extract engineering concepts while retaining the original API
payload and its human-readable URL.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .models import Source


_API_ROOT = "https://api.github.com"
_API_VERSION = "2022-11-28"
_NEXT_LINK = re.compile(r'<([^>]+)>\s*;[^,]*\brel="next"')


class GitHubError(RuntimeError):
    """Base class for GitHub ingestion errors."""


class GitHubAuthenticationError(GitHubError):
    """The supplied token was rejected."""


class GitHubRateLimitError(GitHubError):
    """GitHub's primary or secondary rate limit was reached."""


class GitHubRepositoryNotFoundError(GitHubError):
    """The repository is missing or inaccessible to the supplied token."""


class GitHubAPIError(GitHubError):
    """GitHub returned an unexpected response or another HTTP error."""


class _RejectRedirects(HTTPRedirectHandler):
    """Never forward a GitHub token to an unchecked redirect destination."""

    def redirect_request(self, request: Request, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> None:
        raise GitHubAPIError(
            "GitHub API redirect blocked; use the repository's current owner/repo name"
        )


def iter_repository(
    repository: str,
    token: str | None = None,
    *,
    max_items: int = 100,
    opener: Callable[..., Any] | None = None,
) -> Iterator[Source]:
    """Yield recent commits, pull requests, and issues for ``owner/repo``.

    ``max_items`` is a limit **per kind**, so at most three times this many
    sources are returned. Pull requests appearing in GitHub's issues endpoint
    do not count toward the issue limit. Requests follow GitHub's ``next`` Link
    header until each kind's limit is met. ``opener`` is an optional urlopen-like
    callable for tests and alternate transports.

    Pull requests and issues include both open and closed items, ordered by
    recent updates. Commits follow GitHub's default newest-first ordering.
    """
    owner, repo = _parse_repository(repository)
    if max_items < 0:
        raise ValueError("max_items must be non-negative")
    if max_items == 0:
        return

    canonical_repo = f"{owner.lower()}/{repo.lower()}"
    repo_path = f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"
    # urllib's default redirect handler copies Authorization to the redirect
    # request, including when Location points at a different host.
    open_request = opener or build_opener(_RejectRedirects()).open

    for kind, endpoint, params in (
        ("commit", "commits", {}),
        ("pull_request", "pulls", {"state": "all", "sort": "updated", "direction": "desc"}),
        ("issue", "issues", {"state": "all", "sort": "updated", "direction": "desc"}),
    ):
        count = 0
        page_url: str | None = _build_url(repo_path, endpoint, max_items, params)
        while page_url is not None and count < max_items:
            records, page_url = _read_page(
                page_url, token, open_request, expected_path=f"{repo_path}/{endpoint}"
            )
            for record in records:
                if kind == "issue" and "pull_request" in record:
                    continue
                yield _to_source(record, kind, canonical_repo)
                count += 1
                if count == max_items:
                    break


def _parse_repository(repository: str) -> tuple[str, str]:
    parts = repository.split("/") if isinstance(repository, str) else []
    if len(parts) != 2 or any(not part or part in (".", "..") or any(c.isspace() for c in part) for part in parts):
        raise ValueError("repository must be in 'owner/repo' form")
    return parts[0], parts[1]


def _build_url(repo_path: str, endpoint: str, max_items: int, params: dict[str, str]) -> str:
    query = urlencode({**params, "per_page": min(max_items, 100)})
    return f"{_API_ROOT}{repo_path}/{endpoint}?{query}"


def _read_page(
    url: str, token: str | None, opener: Callable[..., Any], *, expected_path: str
) -> tuple[list[dict[str, Any]], str | None]:
    _check_api_url(url, expected_path)
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": _API_VERSION,
        "User-Agent": "engineering-memory",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    try:
        with opener(request, timeout=20) as response:
            status = getattr(response, "status", 200)
            if status >= 400:
                _raise_http_error(status, response.headers, response.read())
            raw = response.read()
            link = response.headers.get("Link", "")
    except HTTPError as exc:
        _raise_http_error(exc.code, exc.headers, exc.read())
    except URLError as exc:
        raise GitHubAPIError("GitHub API request failed due to a network error") from exc

    try:
        records = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GitHubAPIError("GitHub API returned invalid JSON") from exc
    if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
        raise GitHubAPIError("GitHub API returned an unexpected list response")
    next_match = _NEXT_LINK.search(link)
    next_url = next_match.group(1) if next_match else None
    if next_url is not None:
        _check_api_url(next_url, expected_path)
    return records, next_url


def _check_api_url(url: str, expected_path: str) -> None:
    parsed = urlsplit(url)
    endpoint = expected_path.rsplit("/", 1)[-1]
    # GitHub rewrites Link headers to its numeric /repositories/{id} route.
    # Both routes stay on the GitHub API host and keep the same endpoint kind.
    path_ok = parsed.path.lower() == expected_path.lower() or bool(
        re.fullmatch(rf"/repositories/\d+/{re.escape(endpoint)}", parsed.path)
    )
    if (
        parsed.scheme != "https"
        or parsed.netloc != "api.github.com"
        or not path_ok
    ):
        raise GitHubAPIError("GitHub returned an unsafe pagination URL")


def _raise_http_error(status: int, headers: Any, body: bytes = b"") -> None:
    if status == 401:
        raise GitHubAuthenticationError("GitHub rejected the token (HTTP 401)")
    if status == 429 or (
        status == 403
        and (
            headers.get("X-RateLimit-Remaining") == "0"
            or headers.get("Retry-After") is not None
            or b"rate limit" in body.lower()
        )
    ):
        raise GitHubRateLimitError("GitHub API rate limit reached")
    if status == 404:
        raise GitHubRepositoryNotFoundError("GitHub repository was not found or is inaccessible")
    raise GitHubAPIError(f"GitHub API returned HTTP {status}")


def _to_source(record: dict[str, Any], kind: str, repository: str) -> Source:
    url = record.get("html_url")
    if not isinstance(url, str) or not url:
        raise GitHubAPIError(f"GitHub {kind} response is missing html_url")

    if kind == "commit":
        source_key = record.get("sha")
        commit = record.get("commit") or {}
        if not isinstance(commit, dict):
            raise GitHubAPIError("GitHub commit response is malformed")
        message = commit.get("message") or ""
        if not isinstance(message, str):
            message = str(message)
        title = message.splitlines()[0] if message else ""
        author = commit.get("author") or {}
        committer = commit.get("committer") or {}
        occurred_at = (committer.get("date") if isinstance(committer, dict) else None) or (
            author.get("date") if isinstance(author, dict) else None
        )
        body = message
    else:
        source_key = record.get("number")
        title = record.get("title") or ""
        body = record.get("body") or ""
        occurred_at = (
            record.get("merged_at")
            if kind == "pull_request" and record.get("merged_at")
            else record.get("created_at")
        )

    if not source_key or not isinstance(occurred_at, str) or not occurred_at:
        raise GitHubAPIError(f"GitHub {kind} response is missing an identifier or timestamp")
    return Source(
        source_id=f"github:{repository}:{kind}:{source_key}",
        title=str(title),
        body=str(body),
        source_system="github",
        source_type=kind,
        scope=repository,
        uri=url,
        occurred_at=occurred_at,
        metadata=record,
        promote_sections=(
            kind == "commit" or (
                kind == "pull_request"
                and isinstance(record.get("merged_at"), str)
                and bool(record["merged_at"])
            )
        ),
        memory_kind=(
            "Change"
            if kind == "commit" or (
                kind == "pull_request"
                and isinstance(record.get("merged_at"), str)
                and bool(record["merged_at"])
            )
            else "Event"
        ),
    )
