"""Automated tests for ServiceWaze backend and PWA endpoints."""
import os
import sys
import pytest
from fastapi.testclient import TestClient

# Ensure servicewaze directory is on sys.path when running pytest from repository root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as app_module
import auth
import feeds
import push
import sources
import transport
import ussd
import whatsapp


@pytest.fixture
def client():
    with TestClient(app_module.app) as c:
        yield c


def test_module_imports():
    """Verify all core application modules import cleanly."""
    assert app_module is not None
    assert auth is not None
    assert feeds is not None
    assert push is not None
    assert sources is not None
    assert transport is not None
    assert ussd is not None
    assert whatsapp is not None


def test_root_pwa_html(client):
    """Verify root endpoint returns the PWA dashboard HTML."""
    response = client.get("/")
    assert response.status_code == 200
    assert "ServiceWaze" in response.text


def test_manifest_endpoint(client):
    """Verify webmanifest returns 200 and JSON content."""
    response = client.get("/manifest.webmanifest")
    assert response.status_code == 200
    assert "application/manifest+json" in response.headers.get("content-type", "")
    data = response.json()
    assert "ServiceWaze" in data.get("name", "")
    assert data.get("short_name") == "ServiceWaze"


def test_service_worker_endpoint(client):
    """Verify service worker script returns 200."""
    response = client.get("/sw.js")
    assert response.status_code == 200
    assert "application/javascript" in response.headers.get("content-type", "")


def test_services_directory_api(client):
    """Verify /api/services returns structured emergency and municipal services."""
    response = client.get("/api/services")
    assert response.status_code == 200
    data = response.json()
    assert "services" in data
    assert len(data["services"]) > 0


def test_ussd_simulation_api(client):
    """Verify USSD simulator endpoint returns menu options."""
    response = client.get("/api/ussd?session=test-123&input=1")
    assert response.status_code == 200
    assert "ServiceWaze" in response.text or "Soweto" in response.text


def test_openapi_docs(client):
    """Verify OpenAPI documentation endpoint works."""
    response = client.get("/docs")
    assert response.status_code == 200
