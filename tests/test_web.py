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
        assert client.get("/manifest.webmanifest").status_code == 200
        worker = client.get("/sw.js")
        assert worker.status_code == 200
        assert worker.headers["service-worker-allowed"] == "/"
        assert 'url.pathname.startsWith("/api/")' in worker.text
        assert client.get("/static/app.js").status_code == 200
        assert client.get("/static/app.css").status_code == 200
