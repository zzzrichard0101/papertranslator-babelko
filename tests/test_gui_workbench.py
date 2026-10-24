import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QMetaObject, QObject

from babelko.gui import Window


def test_workbench_loads_settings_and_previous_checkpoint(monkeypatch, tmp_path):
    monkeypatch.setenv("BABELKO_HOME", str(tmp_path))
    folder = tmp_path / "jobs" / "saved"
    folder.mkdir(parents=True)
    (folder / "state.json").write_text(json.dumps({
        "status": "cancelled", "stage": "취소됨", "progress": 42,
        "title": "Saved paper", "source": "", "destination": str(tmp_path / "results"),
        "pages": "3-5", "ocr": "auto", "mode": "hybrid",
    }), encoding="utf-8")
    (tmp_path / "last_job.json").write_text(json.dumps({"folder": str(folder)}), encoding="utf-8")

    app = QApplication.instance() or QApplication([])
    window = Window()
    try:
        assert window._window.isVisible()
        assert window.job["progress"] == 42
        assert window.job["canResume"] is True
        assert window.form["pages"] == "3-5"
        navigation = window._window.findChild(QObject, "settingsNavigation")
        theme_choice = window._window.findChild(QObject, "nightThemeChoice")
        assert navigation is not None and theme_choice is not None
        assert QMetaObject.invokeMethod(navigation, "clicked")
        assert window._window.property("page") == 2
        assert QMetaObject.invokeMethod(theme_choice, "clicked")
        window.setSetting("preview_layout", "focus")
        assert window.settings["theme"] == "night"
        assert window.settings["preview_layout"] == "focus"
        assert json.loads((tmp_path / "ui-settings.json").read_text(encoding="utf-8"))["theme"] == "night"
        window.resetSettings()
        assert window.settings["theme"] == "paper"

        class StartingWorker:
            pid = 424242
            def poll(self):
                return None

        window.worker = StartingWorker()
        window.refresh()
        assert window.job["active"] is True
        assert window.job["canResume"] is False
        window.setForm("pages", "1")
        assert window.form["pages"] == "3-5"
        window.worker = None
        window.refresh()
        window.setForm("source", str(tmp_path / "another.pdf"))
        assert window.folder is None
        assert window.job["progress"] == 0
        assert window.job["canResume"] is False
        assert window.koreanPreview == ""

        new_job = tmp_path / "jobs" / "new"
        new_job.mkdir()
        (new_job / "state.json").write_text(json.dumps({
            "status": "queued", "stage": "대기", "progress": 0,
            "title": "Another paper", "source": str(tmp_path / "another.pdf"),
        }), encoding="utf-8")
        monkeypatch.setattr("babelko.gui.create", lambda *args: new_job)
        monkeypatch.setattr("babelko.gui.subprocess.Popen", lambda *args, **kwargs: StartingWorker())
        window.startTranslation()
        assert window.folder == new_job
        assert window.job["active"] is True
        window.cancelTranslation()
        assert (new_job / "cancel").is_file()
    finally:
        window.close()
        app.processEvents()


def test_workbench_displays_actual_page_and_review_progress(monkeypatch,tmp_path):
    import psutil
    from babelko.storage import save

    monkeypatch.setenv("BABELKO_HOME",str(tmp_path))
    folder=tmp_path/"jobs"/"active"
    folder.mkdir(parents=True)
    state={
        "status":"translating", "stage":"Translate Paragraphs", "progress":48,
        "pid":os.getpid(), "process_created":psutil.Process().create_time(),
        "selected":[0,2,4], "current_source_pages":[3],
        "stage_current":7, "stage_total":20, "work_phase":"draft",
        "title":"Three page sample", "source":"", "destination":str(tmp_path/"results"),
    }
    save(folder/"state.json",state)
    save(tmp_path/"last_job.json",{"folder":str(folder)})
    app=QApplication.instance() or QApplication([])
    window=Window()
    try:
        assert window.job["stageDisplay"]=="Hy-MT2 초벌 번역"
        assert window.job["pageValue"]=="3쪽"
        assert "2번째" in window.job["pageCaption"]
        assert window.job["stepDetail"]=="현재 단계 7 / 20 문단"
        state.update(stage="Qwen 문장별 양방향 대조 8/20",work_phase="review",current_source_pages=[])
        save(folder/"state.json",state)
        window.refresh()
        assert window.job["pageValue"]=="문장별 검수 중"
        assert window.job["stepDetail"]=="현재 단계 8 / 20 검수 항목"
    finally:
        window.close()
        app.processEvents()
