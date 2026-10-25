import json
import os
import time

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


def test_particle_atlas_navigation_builds_word_space_and_keeps_local_blocks(monkeypatch,tmp_path):
    import pymupdf
    from babelko.storage import save

    monkeypatch.setenv("BABELKO_HOME",str(tmp_path))
    source=tmp_path/"source.pdf"
    with pymupdf.open() as document:
        document.new_page().insert_text((50,70),"First page source paragraph.")
        document.new_page().insert_text((70,90),"Second page source paragraph.")
        document.save(source)
    app=QApplication.instance() or QApplication([])
    window=Window()
    try:
        window.setForm("source",str(source))
        navigation=window._window.findChild(QObject,"atlasNavigation")
        assert navigation is not None
        assert QMetaObject.invokeMethod(navigation,"clicked")
        assert window._window.property("page")==3
        deadline=time.monotonic()+8
        while window.wordSpace["status"]=="loading" and time.monotonic()<deadline:
            app.processEvents()
            time.sleep(0.01)
        assert window.wordSpace["status"]=="ready"
        assert "paragraph" in {point["word"] for point in window.wordSpace["points"]}
        window.selectAtlasPage(0)
        assert window.atlas["total_pages"]==2
        assert window.atlas["regions"][0]["status"]=="unprocessed"
        window.selectAtlasPage(1)
        assert window.atlas["source_page"]==2
        window.selectAtlasRegion(0)
        assert "Second page" in window.atlasSelection["excerpt"]

        job=tmp_path/"jobs"/"saved"
        job.mkdir(parents=True)
        (job/"Original.pdf").write_bytes(source.read_bytes())
        save(job/"source-coverage.json",{"pages":[{"source_page":2,"suspected_missing":[
            {"box":[60,70,380,110]}]}]})
        window.folder=job
        window._job_source=str(source)
        window.selectAtlasPage(1)
        assert window.atlas["suspect_regions"]==1
        assert window.atlas["regions"][0]["status"]=="source_gap_suspected"

        output=job/"result"
        output.mkdir()
        (output/"Korean.pdf").write_bytes(source.read_bytes())
        save(job/"state.json",{"status":"completed","selected":[0],
                               "source":str(source),"output":str(output)})
        window.refresh()
        window.selectAtlasPage(0)
        assert window.atlas["regions"][0]["status"]=="output_created"
        assert window.atlas["translated_available"] is True
        window.selectAtlasPage(1)
        assert window.atlas["translated_available"] is False
    finally:
        window.close()
        app.processEvents()


def test_atlas_keeps_flat_view_available_without_3d_module(monkeypatch,tmp_path):
    monkeypatch.setenv("BABELKO_HOME",str(tmp_path))
    monkeypatch.setattr("babelko.gui.SPACE_AVAILABLE",False)
    app=QApplication.instance() or QApplication([])
    window=Window()
    try:
        assert window.supportsSpace is False
        navigation=window._window.findChild(QObject,"atlasNavigation")
        assert QMetaObject.invokeMethod(navigation,"clicked")
        assert window._window.property("page")==3
    finally:
        window.close()
        app.processEvents()
