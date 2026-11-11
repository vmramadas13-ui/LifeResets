import json

from fastapi.testclient import TestClient

from liferesets.main import app


def test_web_shell_and_pwa_files_are_served() -> None:
    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "LifeResets" in page.text
        assert 'id="daily-plan-form"' in page.text
        assert 'id="task-options"' in page.text
        assert 'id="recovery-list"' in page.text
        assert 'id="theme-toggle"' in page.text
        assert 'id="motion-toggle"' in page.text
        assert 'id="language-toggle"' in page.text
        assert (
            'name="viewport" content="width=device-width, initial-scale=1, '
            'viewport-fit=cover"' in page.text
        )
        assert 'id="character-section"' in page.text
        assert 'class="mobile-nav"' in page.text
        assert 'id="voice-input"' in page.text
        assert 'id="speak-answer"' in page.text
        assert 'id="agent-review"' in page.text
        assert 'id="awakening-form"' in page.text
        assert 'id="awakening-consent"' in page.text
        assert 'id="awakening-save-later"' in page.text
        assert 'rel="apple-touch-icon"' in page.text
        manifest = client.get("/manifest.webmanifest")
        assert manifest.status_code == 200
        assert {item["sizes"] for item in json.loads(manifest.text)["icons"]} == {
            "192x192",
            "512x512",
        }
        assert client.get("/static/apple-touch-icon.png").status_code == 200
        assert client.get("/static/app-icon-192.png").status_code == 200
        assert client.get("/static/app-icon-512.png").status_code == 200
        worker = client.get("/sw.js")
        assert worker.status_code == 200
        assert worker.headers["service-worker-allowed"] == "/"
        assert 'url.pathname.startsWith("/api/")' in worker.text
        assert client.get("/static/app.js").status_code == 200
        assert client.get("/static/app.css").status_code == 200
