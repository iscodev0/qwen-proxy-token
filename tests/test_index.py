"""Tests for the main web UI route (GET /)."""

from __future__ import annotations


class TestIndexPage:
    """GET / — the main SPA web UI."""

    async def test_index_returns_html(self, test_client):
        """GET / returns an HTML page without auth."""
        resp = await test_client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    async def test_index_contains_auth_forms(self, test_client):
        """The HTML page contains login/register form elements."""
        resp = await test_client.get("/")
        body = resp.text

        # Auth section elements
        assert "Log In" in body
        assert "Register" in body
        assert "Create Account" in body

    async def test_index_contains_main_app_elements(self, test_client):
        """The HTML page contains the main app shell elements."""
        resp = await test_client.get("/")
        body = resp.text

        # Main app sections
        assert "Dashboard" in body
        assert "Credentials" in body
        assert "API Playground" in body
        assert "API Examples" in body

    async def test_index_contains_provider_sections(self, test_client):
        """The HTML page contains provider credential capture sections."""
        resp = await test_client.get("/")
        body = resp.text

        assert "Meta AI" in body
        assert "Z.ai" in body

    async def test_index_contains_tailwind_cdn(self, test_client):
        """The page loads Tailwind CSS from CDN."""
        resp = await test_client.get("/")
        body = resp.text

        assert "cdn.tailwindcss.com" in body

    async def test_index_has_no_server_errors(self, test_client):
        """The page has no server-side errors."""
        resp = await test_client.get("/")
        # Check for common error indicators in the response
        body_lower = resp.text.lower()
        assert "internal server error" not in body_lower
        assert resp.status_code == 200
