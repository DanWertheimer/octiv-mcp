"""Tests for OctivClient HTTP methods using mocked httpx via respx."""

import json
import time

import httpx
import pytest
import respx

import server as srv
from server import API_BASE, OctivClient

ME_RESPONSE = {
    "id": 42,
    "userTenants": [{"tenantId": 101134, "defaultLocationId": 1091}],
}
TOKEN_RESPONSE = {
    "accessToken": "tok123",
    "expiresIn": 31536000,
}
CLASS_DATES_RESPONSE = {"data": [], "meta": {}}
PROGRAMMES_RESPONSE = {"data": [{"id": 195, "name": "CrossFit", "description": "WODs"}], "meta": {}}
WODS_RESPONSE = {"data": [], "meta": {}}


@pytest.fixture(autouse=True)
def clean_cache(tmp_path, monkeypatch):
    """Redirect token/user caches to a temp directory for each test."""
    monkeypatch.setattr(srv, "TOKEN_CACHE_PATH", tmp_path / "token.json")
    monkeypatch.setattr(srv, "USER_CACHE_PATH", tmp_path / "user.json")


@pytest.fixture
def client():
    c = OctivClient()
    c._token = None
    c._user_info = None
    return c


# ── Token management ──────────────────────────────────────────────────────────


@respx.mock
async def test_get_token_performs_login(client):
    respx.post(f"{API_BASE}/api/login").mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
    token = await client.get_token()
    assert token == "tok123"


async def test_get_token_uses_cached_token(client):
    srv.TOKEN_CACHE_PATH.write_text(
        json.dumps(
            {
                "access_token": "cached-token",
                "expires_at": time.time() + 7200,
            }
        )
    )
    token = await client.get_token()
    assert token == "cached-token"


async def test_get_token_ignores_expired_cache(client):
    srv.TOKEN_CACHE_PATH.write_text(
        json.dumps(
            {
                "access_token": "old-token",
                "expires_at": time.time() + 100,  # < 1-hour buffer → treated as expired
            }
        )
    )
    with respx.mock:
        respx.post(f"{API_BASE}/api/login").mock(
            return_value=httpx.Response(200, json=TOKEN_RESPONSE)
        )
        token = await client.get_token()
    assert token == "tok123"


async def test_invalidate_token_clears_state(client):
    srv.TOKEN_CACHE_PATH.write_text(
        json.dumps(
            {
                "access_token": "tok",
                "expires_at": time.time() + 7200,
            }
        )
    )
    client._token = "tok"
    client._invalidate_token()
    assert client._token is None
    assert not srv.TOKEN_CACHE_PATH.exists()


# ── get_me ───────────────────────────────────────────────────────────────────


@respx.mock
async def test_get_me_fetches_and_returns(client):
    respx.post(f"{API_BASE}/api/login").mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
    respx.get(f"{API_BASE}/api/users/me").mock(return_value=httpx.Response(200, json=ME_RESPONSE))
    me = await client.get_me()
    assert me["id"] == 42


async def test_get_me_uses_cache(client):
    srv.USER_CACHE_PATH.write_text(json.dumps(ME_RESPONSE))
    me = await client.get_me()
    assert me["id"] == 42


# ── _extract_gym_ids ──────────────────────────────────────────────────────────


def test_extract_gym_ids_reads_from_profile(client, monkeypatch):
    monkeypatch.delenv("OCTIV_TENANT_ID", raising=False)
    monkeypatch.delenv("OCTIV_LOCATION_ID", raising=False)
    tenant, location = client._extract_gym_ids(ME_RESPONSE)
    assert tenant == "101134"
    assert location == "1091"


def test_extract_gym_ids_env_vars_override_profile(client, monkeypatch):
    monkeypatch.setenv("OCTIV_TENANT_ID", "999999")
    monkeypatch.setenv("OCTIV_LOCATION_ID", "888")
    tenant, location = client._extract_gym_ids(ME_RESPONSE)
    assert tenant == "999999"
    assert location == "888"


def test_extract_gym_ids_raises_when_tenant_missing(client, monkeypatch):
    monkeypatch.delenv("OCTIV_TENANT_ID", raising=False)
    monkeypatch.delenv("OCTIV_LOCATION_ID", raising=False)
    with pytest.raises(ValueError, match="tenant ID"):
        client._extract_gym_ids({"id": 42})


def test_extract_gym_ids_raises_when_location_missing(client, monkeypatch):
    monkeypatch.delenv("OCTIV_TENANT_ID", raising=False)
    monkeypatch.delenv("OCTIV_LOCATION_ID", raising=False)
    me_no_location = {"id": 42, "userTenants": [{"tenantId": 101134}]}
    with pytest.raises(ValueError, match="location ID"):
        client._extract_gym_ids(me_no_location)


# ── get_class_dates ───────────────────────────────────────────────────────────


@respx.mock
async def test_get_class_dates_returns_data(client):
    respx.post(f"{API_BASE}/api/login").mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
    respx.get(f"{API_BASE}/api/users/me").mock(return_value=httpx.Response(200, json=ME_RESPONSE))
    respx.get(f"{API_BASE}/class-dates").mock(
        return_value=httpx.Response(200, json=CLASS_DATES_RESPONSE)
    )
    result = await client.get_class_dates("2026-03-20", "2026-03-26")
    assert "data" in result


@respx.mock
async def test_get_class_dates_401_invalidates_token(client):
    respx.post(f"{API_BASE}/api/login").mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
    respx.get(f"{API_BASE}/api/users/me").mock(return_value=httpx.Response(200, json=ME_RESPONSE))
    respx.get(f"{API_BASE}/class-dates").mock(return_value=httpx.Response(401))
    with pytest.raises(ValueError, match="Authentication expired"):
        await client.get_class_dates("2026-03-20", "2026-03-26")
    assert client._token is None


# ── get_programmes ────────────────────────────────────────────────────────────


@respx.mock
async def test_get_programmes_returns_list(client):
    respx.post(f"{API_BASE}/api/login").mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
    respx.get(f"{API_BASE}/api/users/me").mock(return_value=httpx.Response(200, json=ME_RESPONSE))
    respx.get(f"{API_BASE}/api/programmes").mock(
        return_value=httpx.Response(200, json=PROGRAMMES_RESPONSE)
    )
    result = await client.get_programmes()
    assert result["data"][0]["id"] == 195
    assert result["data"][0]["name"] == "CrossFit"


@respx.mock
async def test_get_programmes_401_invalidates_token(client):
    respx.post(f"{API_BASE}/api/login").mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
    respx.get(f"{API_BASE}/api/users/me").mock(return_value=httpx.Response(200, json=ME_RESPONSE))
    respx.get(f"{API_BASE}/api/programmes").mock(return_value=httpx.Response(401))
    with pytest.raises(ValueError, match="Authentication expired"):
        await client.get_programmes()
    assert client._token is None


# ── get_wods ──────────────────────────────────────────────────────────────────


@respx.mock
async def test_get_wods_returns_data(client):
    respx.post(f"{API_BASE}/api/login").mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
    respx.get(f"{API_BASE}/api/users/me").mock(return_value=httpx.Response(200, json=ME_RESPONSE))
    respx.get(f"{API_BASE}/api/wods").mock(return_value=httpx.Response(200, json=WODS_RESPONSE))
    result = await client.get_wods("2026-03-19", "2026-03-20")
    assert "data" in result


@respx.mock
async def test_get_wods_omits_programme_ids_when_not_set(client, monkeypatch):
    monkeypatch.delenv("OCTIV_PROGRAMME_IDS", raising=False)
    respx.post(f"{API_BASE}/api/login").mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
    respx.get(f"{API_BASE}/api/users/me").mock(return_value=httpx.Response(200, json=ME_RESPONSE))
    route = respx.get(f"{API_BASE}/api/wods").mock(
        return_value=httpx.Response(200, json=WODS_RESPONSE)
    )
    await client.get_wods("2026-03-19", "2026-03-20")
    assert "programmeIds" not in str(route.calls.last.request.url)


@respx.mock
async def test_get_wods_uses_env_programme_ids(client, monkeypatch):
    monkeypatch.setenv("OCTIV_PROGRAMME_IDS", "999")
    respx.post(f"{API_BASE}/api/login").mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
    respx.get(f"{API_BASE}/api/users/me").mock(return_value=httpx.Response(200, json=ME_RESPONSE))
    route = respx.get(f"{API_BASE}/api/wods").mock(
        return_value=httpx.Response(200, json=WODS_RESPONSE)
    )
    await client.get_wods("2026-03-19", "2026-03-20")
    assert "999" in str(route.calls.last.request.url)


@respx.mock
async def test_get_wods_accepts_explicit_programme_ids(client):
    respx.post(f"{API_BASE}/api/login").mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
    respx.get(f"{API_BASE}/api/users/me").mock(return_value=httpx.Response(200, json=ME_RESPONSE))
    route = respx.get(f"{API_BASE}/api/wods").mock(
        return_value=httpx.Response(200, json=WODS_RESPONSE)
    )
    await client.get_wods("2026-03-19", "2026-03-20", programme_ids="195,196")
    url = str(route.calls.last.request.url)
    assert "195%2C196" in url or "195,196" in url


@respx.mock
async def test_get_wods_401_invalidates_token(client):
    respx.post(f"{API_BASE}/api/login").mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))
    respx.get(f"{API_BASE}/api/users/me").mock(return_value=httpx.Response(200, json=ME_RESPONSE))
    respx.get(f"{API_BASE}/api/wods").mock(return_value=httpx.Response(401))
    with pytest.raises(ValueError, match="Authentication expired"):
        await client.get_wods("2026-03-19", "2026-03-20")
    assert client._token is None
