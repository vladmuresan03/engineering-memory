"""Offline contract tests for the GitHub source connector."""

from __future__ import annotations

import io
import json
import unittest
from urllib.error import HTTPError

from engineering_memory.github import (
    GitHubAPIError,
    GitHubAuthenticationError,
    GitHubRateLimitError,
    GitHubRepositoryNotFoundError,
    iter_repository,
)


class FakeResponse:
    def __init__(self, records: list[dict], *, link: str = "") -> None:
        self.status = 200
        self.headers = {"Link": link}
        self._body = io.BytesIO(json.dumps(records).encode())

    def read(self) -> bytes:
        return self._body.read()

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        self._body.close()


def commit(sha: str) -> dict:
    return {
        "sha": sha,
        "html_url": f"https://github.com/Acme/Widget/commit/{sha}",
        "commit": {
            "message": "Prefer explicit retries\n\nKeeps the worker responsive.",
            "author": {"date": "2026-01-01T12:00:00Z"},
        },
    }


def pull(number: int) -> dict:
    return {
        "number": number,
        "html_url": f"https://github.com/Acme/Widget/pull/{number}",
        "title": "Add retry policy",
        "body": "We chose bounded retries because the upstream can fail briefly.",
        "created_at": "2026-01-02T12:00:00Z",
        "merged_at": "2026-01-03T12:00:00Z",
    }


def issue(number: int) -> dict:
    return {
        "number": number,
        "html_url": f"https://github.com/Acme/Widget/issues/{number}",
        "title": "Investigate request errors",
        "body": "A few calls time out.",
        "created_at": "2026-01-04T12:00:00Z",
    }


class GitHubConnectorTests(unittest.TestCase):
    def test_converts_all_three_kinds_with_original_urls_and_payloads(self) -> None:
        seen: list[tuple[str, dict[str, str], int]] = []

        def opener(request, *, timeout):
            seen.append((request.full_url, dict(request.header_items()), timeout))
            if "/commits?" in request.full_url:
                return FakeResponse([commit("abc123")])
            if "/pulls?" in request.full_url:
                return FakeResponse([pull(7)])
            if "/issues?" in request.full_url:
                return FakeResponse([{**issue(7), "pull_request": {}}, issue(8)])
            self.fail(f"Unexpected API URL: {request.full_url}")

        sources = list(iter_repository("Acme/Widget", "secret-token", opener=opener))

        self.assertEqual([s.source_type for s in sources], ["commit", "pull_request", "issue"])
        self.assertEqual([s.source_system for s in sources], ["github"] * 3)
        self.assertEqual([s.scope for s in sources], ["acme/widget"] * 3)
        self.assertEqual([s.memory_kind for s in sources], ["Change", "Change", "Event"])
        self.assertEqual(
            [s.source_id for s in sources],
            [
                "github:acme/widget:commit:abc123",
                "github:acme/widget:pull_request:7",
                "github:acme/widget:issue:8",
            ],
        )
        self.assertEqual(sources[0].title, "Prefer explicit retries")
        self.assertIn("Keeps the worker responsive", sources[0].body)
        self.assertEqual(sources[0].occurred_at, "2026-01-01T12:00:00Z")
        self.assertEqual(sources[1].uri, "https://github.com/Acme/Widget/pull/7")
        self.assertEqual(sources[1].metadata["merged_at"], "2026-01-03T12:00:00Z")
        self.assertEqual(sources[2].uri, "https://github.com/Acme/Widget/issues/8")
        self.assertEqual(len(seen), 3)
        self.assertTrue(all(headers["Authorization"] == "Bearer secret-token" for _, headers, _ in seen))
        self.assertTrue(all(timeout == 20 for _, _, timeout in seen))
        self.assertIn("state=all", seen[1][0])
        self.assertIn("state=all", seen[2][0])

    def test_follows_next_page_for_issues_without_counting_pull_requests(self) -> None:
        requested: list[str] = []
        issue_next = "https://api.github.com/repositories/12345/issues?page=2&per_page=1"

        def opener(request, *, timeout):
            requested.append(request.full_url)
            if "/commits?" in request.full_url:
                return FakeResponse([commit("abc123")])
            if "/pulls?" in request.full_url:
                return FakeResponse([pull(7)])
            if request.full_url == issue_next:
                return FakeResponse([issue(8)])
            if "/issues?" in request.full_url:
                return FakeResponse([{**issue(7), "pull_request": {}}], link=f'<{issue_next}>; rel="next"')
            self.fail(f"Unexpected API URL: {request.full_url}")

        sources = list(iter_repository("Acme/Widget", max_items=1, opener=opener))

        self.assertEqual([s.source_type for s in sources], ["commit", "pull_request", "issue"])
        self.assertEqual(len(requested), 4)
        self.assertEqual(requested[-1], issue_next)
        self.assertTrue(all("per_page=1" in url for url in requested))

    def test_rejects_invalid_input_without_making_a_request(self) -> None:
        def opener(*_args, **_kwargs):
            self.fail("No API request expected")

        with self.assertRaises(ValueError):
            list(iter_repository("owner/repo/extra", opener=opener))
        with self.assertRaises(ValueError):
            list(iter_repository("owner/repo", max_items=-1, opener=opener))
        self.assertEqual(list(iter_repository("owner/repo", max_items=0, opener=opener)), [])

    def test_classifies_common_http_errors_without_exposing_token(self) -> None:
        cases = (
            (401, {}, b"{}", GitHubAuthenticationError),
            (403, {"X-RateLimit-Remaining": "0"}, b"{}", GitHubRateLimitError),
            (403, {}, b'{"message":"secondary rate limit exceeded"}', GitHubRateLimitError),
            (429, {}, b"{}", GitHubRateLimitError),
            (404, {}, b"{}", GitHubRepositoryNotFoundError),
        )
        for status, headers, body, expected_error in cases:
            with self.subTest(status=status):

                def opener(request, *, timeout):
                    raise HTTPError(request.full_url, status, "error", headers, io.BytesIO(body))

                with self.assertRaises(expected_error) as captured:
                    list(iter_repository("Acme/Widget", token="secret-token", opener=opener))
                self.assertNotIn("secret-token", str(captured.exception))

    def test_rejects_pagination_to_another_host_before_sending_token(self) -> None:
        requested: list[str] = []

        def opener(request, *, timeout):
            requested.append(request.full_url)
            return FakeResponse(
                [commit("abc123")],
                link='<https://example.net/steal-token>; rel="next"',
            )

        with self.assertRaises(GitHubAPIError):
            list(iter_repository("Acme/Widget", token="secret-token", max_items=2, opener=opener))
        self.assertEqual(len(requested), 1)

    def test_rejects_pagination_to_another_repository(self) -> None:
        requested: list[str] = []

        def opener(request, *, timeout):
            requested.append(request.full_url)
            return FakeResponse(
                [commit("abc123")],
                link='<https://api.github.com/repos/Other/Repo/commits?page=2>; rel="next"',
            )

        with self.assertRaises(GitHubAPIError):
            list(iter_repository("Acme/Widget", token="secret-token", max_items=2, opener=opener))
        self.assertEqual(len(requested), 1)


if __name__ == "__main__":
    unittest.main()
