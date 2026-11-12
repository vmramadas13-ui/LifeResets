import json

from fastapi.testclient import TestClient

from liferesets.main import app


def test_web_shell_and_pwa_files_are_served() -> None:
    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "LifeResets" in page.text
        assert 'id="daily-plan-form"' in page.text
        assert 'id="schedule-context"' in page.text
        assert 'id="busy-window-list"' in page.text
        assert 'id="day-start-time"' in page.text
        assert 'id="day-end-time"' in page.text
        assert "Add a busy time" in page.text
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
        assert 'id="domain-settings-form"' in page.text
        assert 'id="domain-settings"' in page.text
        assert 'id="habits-section"' in page.text
        assert 'id="habit-form"' in page.text
        assert 'id="habit-builder-preview"' in page.text
        assert 'id="habit-frequency"' in page.text
        assert 'id="habit-weekdays-field"' in page.text
        assert 'name="interval_days"' in page.text
        assert 'name="start_date"' in page.text
        assert 'name="end_date"' in page.text
        assert 'name="reminder_preference"' in page.text
        app_script = client.get("/static/app.js")
        assert app_script.status_code == 200
        assert 'editGoalSummary.textContent = "Edit goal"' in app_script.text
        assert 'editMetricSummary.textContent = "Edit measure"' in app_script.text
        assert 'method: "PATCH"' in app_script.text
        assert "suggested ${planItem.suggested_start}" in app_script.text
        assert "leave busy times clear" in app_script.text
        assert "Reschedule history ·" in app_script.text
        assert "updateHabitBuilderPreview" in app_script.text
        assert "unit is locked to keep its history accurate" in app_script.text
        assert "Dated history remains unchanged." in app_script.text
        assert "Turn next step into a task" in app_script.text
        assert "Link to an active goal" in app_script.text
        assert (
            "deleting the review answers will not delete this task"
            in app_script.text.lower()
        )
        assert 'id="reviews-section"' in page.text
        assert 'id="review-form"' in page.text
        assert 'id="reflection-consent"' in page.text
        assert 'id="awakening-form"' in page.text
        assert 'id="awakening-consent"' in page.text
        assert 'id="awakening-save-later"' in page.text
        assert 'id="awakening-assessment-panel"' in page.text
        assert 'id="awakening-baseline-panel"' in page.text
        assert 'id="domain-subareas"' in page.text
        assert 'id="goal-subarea"' in page.text
        assert 'id="awakening-baseline-consent"' in page.text
        assert 'id="awakening-baseline-form"' in page.text
        assert (
            "Linking does not copy the value or create a metric, target, "
            "goal, or score." in page.text
        )
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
