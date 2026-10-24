"""Qt Quick workbench; the PDF pipeline remains in the existing worker."""

import hashlib
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pymupdf
from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtWidgets import QApplication, QFileDialog

from .pipeline import create
from .storage import project, read, root, save
from .ui_settings import DEFAULTS, load as load_settings, store as store_settings


OUTPUTS = {"Korean.pdf", "Bilingual.pdf", "FigureLegends.html", ""}
ACTIVE = {"queued", "preparing", "translating", "validating"}
STAGES = {
    "Parse PDF and Create Intermediate Representation": "원문 PDF 구조 읽기",
    "LayoutParser": "원문 페이지 구조 분석",
    "ParagraphFinder": "문단 찾기",
    "StylesAndFormulas": "수식과 글자 스타일 읽기",
    "DetectScannedFile": "스캔 페이지 확인",
    "Parse Page Layout": "페이지 배치 분석",
    "Parse Table": "표 구조 분석",
    "Parse Paragraphs": "문단 구분",
    "Parse Formulas and Styles": "수식과 글자 스타일 분석",
    "Automatic Term Extraction": "학술 용어 확인",
    "Typesetting": "한국어 문장 배치",
    "Add Fonts": "한국어 글꼴 적용",
    "Generate drawing instructions": "PDF 페이지 구성",
    "Subset font": "글꼴 정리",
    "Save PDF": "번역 PDF 저장",
}


def _stage_label(stage, phase):
    if stage == "Translate Paragraphs":
        return {"draft": "Hy-MT2 초벌 번역", "replay": "검수한 번역을 PDF에 배치"}.get(
            phase, "한국어 문단 번역"
        )
    return STAGES.get(stage, stage)


def _page_status(state, active, total):
    selected = state.get("selected") or []
    pages = [page for page in state.get("current_source_pages", [])
             if type(page) is int and page > 0]
    if pages and active:
        shown = ", ".join(f"{page}쪽" for page in pages[:3])
        if len(pages) > 3:
            shown += f" 외 {len(pages) - 3}쪽"
        positions = {page + 1: index + 1 for index, page in enumerate(selected)}
        ordinals = [positions[page] for page in pages if page in positions]
        where = (f"선택한 {len(selected)}쪽 중 " +
                 (f"{ordinals[0]}번째" if len(ordinals) == 1 else f"{len(ordinals)}쪽 동시 처리")) if ordinals else "원문 페이지 번호"
        return "처리 중인 원문", shown, where
    if active and state.get("work_phase") == "review":
        return "원문 위치", "문장별 검수 중", "검수는 페이지 순서와 별도로 진행됩니다."
    count = len(selected) or total
    return "작업 범위", f"{count}쪽" if count else "대기", (
        "현재 단계는 페이지별 위치를 제공하지 않습니다." if active else "번역을 시작하면 현재 페이지가 표시됩니다."
    )


def _preview(path, page=0):
    """Render only a small local thumbnail, reusing it until the PDF changes."""
    path = Path(path)
    if not path.is_file():
        return ""
    stat = path.stat()
    key = hashlib.sha256(
        f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{page}".encode()
    ).hexdigest()[:20]
    cache = root() / "ui-preview"
    cache.mkdir(exist_ok=True)
    thumbnail = cache / f"{key}.png"
    if not thumbnail.exists():
        with pymupdf.open(path) as document:
            if not len(document):
                return ""
            sheet = document[min(max(page, 0), len(document) - 1)]
            scale = min(1.4, 900 / max(sheet.rect.width, sheet.rect.height))
            sheet.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).save(thumbnail)
    return QUrl.fromLocalFile(str(thumbnail)).toString()


class Window(QObject):
    settingsChanged = Signal()
    formChanged = Signal()
    jobChanged = Signal()
    previewsChanged = Signal()
    errorRaised = Signal(str)

    def __init__(self):
        super().__init__()
        self._settings = load_settings()
        self._form = {
            "source": "",
            "destination": str(root() / "results"),
            "pages": "",
            "ocr": "auto",
            "mode": "hybrid",
            "experimental": False,
        }
        Path(self._form["destination"]).mkdir(parents=True, exist_ok=True)
        self._job = {
            "status": "ready", "stage": "준비됨", "progress": 0,
            "details": "PDF를 선택해 새 번역을 시작하세요.",
            "stageDisplay": "준비됨", "stepDetail": "", "pageTitle": "작업 범위",
            "pageValue": "대기", "pageCaption": "번역을 시작하면 현재 페이지가 표시됩니다.",
            "active": False, "canResume": False, "hasOutput": False,
            "hasKorean": False, "hasBilingual": False, "hasLegends": False,
            "title": "", "sourcePages": 0,
        }
        self._source_preview = ""
        self._korean_preview = ""
        self.folder = None
        self.worker = None
        self._job_source = ""
        self._preview_output = None
        self._load_last_job()
        self._load_fonts()
        self.engine = QQmlApplicationEngine()
        self.engine.rootContext().setContextProperty("backend", self)
        self.engine.load(str(Path(__file__).parent / "ui" / "Main.qml"))
        if not self.engine.rootObjects():
            raise RuntimeError("BabelKO 화면을 불러올 수 없습니다.")
        self._window = self.engine.rootObjects()[0]
        if not isinstance(self._window, QQuickWindow):
            raise RuntimeError("BabelKO 화면 창을 만들 수 없습니다.")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.refresh()

    def _load_fonts(self):
        font_roots = [root() / "assets/fonts"]
        if os.environ.get("LOCALAPPDATA"):
            font_roots.append(Path(os.environ["LOCALAPPDATA"]) / "PaperTranslatorBabelKO/assets/fonts")
        for font_root in font_roots:
            for name in ("SourceHanSansKR-Regular.ttf", "SourceHanSansKR-Bold.ttf"):
                if (font_root / name).is_file():
                    QFontDatabase.addApplicationFont(str(font_root / name))

    def _load_last_job(self):
        try:
            folder = Path(read(root() / "last_job.json")["folder"])
            state = read(folder / "state.json")
        except (OSError, KeyError, TypeError, ValueError):
            return
        self.folder = folder
        self._job_source = state.get("source", "")
        self._form.update(
            source=state.get("source", ""),
            destination=state.get("destination", self._form["destination"]),
            pages=state.get("pages", ""),
            ocr=state.get("ocr", "auto"),
            mode=state.get("mode", "hybrid"),
            experimental=bool((state.get("snapshot") or {}).get("experimental_pipeline", False)),
        )
        self._update_source_preview()

    @Property("QVariantMap", notify=settingsChanged)
    def settings(self):
        return self._settings

    @Property("QVariantMap", notify=formChanged)
    def form(self):
        return self._form

    @Property("QVariantMap", notify=jobChanged)
    def job(self):
        return self._job

    @Property(str, notify=previewsChanged)
    def sourcePreview(self):
        return self._source_preview

    @Property(str, notify=previewsChanged)
    def koreanPreview(self):
        return self._korean_preview

    @Slot(str, "QVariant")
    def setSetting(self, key, value):
        if key not in DEFAULTS:
            return
        candidate = dict(self._settings)
        candidate[key] = value
        updated = store_settings(candidate)
        if updated != self._settings:
            self._settings = updated
            self.settingsChanged.emit()

    @Slot()
    def resetSettings(self):
        self._settings = store_settings(DEFAULTS)
        self.settingsChanged.emit()

    @Slot(str, "QVariant")
    def setForm(self, key, value):
        if key not in self._form:
            return
        if self._job["active"]:
            return
        if key == "experimental":
            value = bool(value)
        else:
            value = str(value)
        if key == "ocr" and value not in {"auto", "off", "force"}:
            return
        if key == "mode" and value not in {"hybrid", "qwen"}:
            return
        if self._form[key] == value:
            return
        if key == "source" and self.folder and Path(value).resolve() != Path(self._job_source).resolve():
            self.folder = None
            self.worker = None
            self._job_source = ""
            self._preview_output = None
            self._korean_preview = ""
            self._job = {
                "status": "ready", "stage": "준비됨", "progress": 0,
                "details": "PDF를 선택해 새 번역을 시작하세요.",
                "stageDisplay": "준비됨", "stepDetail": "", "pageTitle": "작업 범위",
                "pageValue": "대기", "pageCaption": "번역을 시작하면 현재 페이지가 표시됩니다.",
                "active": False, "canResume": False, "hasOutput": False,
                "hasKorean": False, "hasBilingual": False, "hasLegends": False,
                "title": "", "sourcePages": 0,
            }
            self.previewsChanged.emit()
        self._form[key] = value
        self.formChanged.emit()
        if key == "source":
            self._update_source_preview()

    @Slot(str)
    def setSourceUrl(self, url):
        path = QUrl(url).toLocalFile()
        if path and Path(path).suffix.lower() == ".pdf":
            self.setForm("source", path)
        else:
            self.errorRaised.emit("PDF 파일을 놓아주세요.")

    @Slot()
    def pickSource(self):
        if self._job["active"]:
            return
        path, _ = QFileDialog.getOpenFileName(None, "PDF 선택", str(Path.home()), "PDF (*.pdf)")
        if path:
            self.setForm("source", path)

    @Slot()
    def pickDestination(self):
        if self._job["active"]:
            return
        path = QFileDialog.getExistingDirectory(None, "결과 폴더 선택", self._form["destination"])
        if path:
            self.setForm("destination", path)

    def _update_source_preview(self):
        source = Path(self._form["source"])
        self._source_preview = ""
        if source.is_file() and source.suffix.lower() == ".pdf":
            try:
                self._source_preview = _preview(source)
                with pymupdf.open(source) as document:
                    self._job["sourcePages"] = len(document)
            except (OSError, RuntimeError, ValueError):
                self._job["sourcePages"] = 0
        else:
            self._job["sourcePages"] = 0
        self._job["title"] = source.stem if self._form["source"] else ""
        self.previewsChanged.emit()
        self.jobChanged.emit()

    def _launch(self):
        save(root() / "last_job.json", {"folder": str(self.folder)})
        python = project() / ".venv/Scripts/python.exe"
        self.worker = subprocess.Popen(
            [str(python if python.is_file() else sys.executable), "-m", "babelko.worker", str(self.folder)],
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            cwd=project(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.refresh()

    @Slot()
    def startTranslation(self):
        try:
            self.folder = create(
                self._form["source"], self._form["destination"], self._form["pages"],
                self._form["ocr"], self._form["mode"],
                self._form["experimental"] and self._form["mode"] == "hybrid",
            )
            self._job_source = self._form["source"]
            self._korean_preview = ""
            self._preview_output = None
            self.previewsChanged.emit()
            self._launch()
        except Exception as exc:
            self.errorRaised.emit(str(exc))

    @Slot()
    def cancelTranslation(self):
        if self.folder and self._job["active"]:
            (self.folder / "cancel").touch()
            self._job = {**self._job, "stage": "취소 요청됨 · 진행 중인 처리 정리 중"}
            self.jobChanged.emit()

    @Slot()
    def resumeTranslation(self):
        if not self.folder or not self._job["canResume"]:
            return
        try:
            (self.folder / "cancel").unlink(missing_ok=True)
            self._launch()
        except Exception as exc:
            self.errorRaised.emit(str(exc))

    @Slot()
    def refresh(self):
        if not self.folder or not (self.folder / "state.json").is_file():
            return
        try:
            state = read(self.folder / "state.json")
        except (OSError, ValueError):
            return
        status = state.get("status", "ready")
        active = status in ACTIVE
        starting = bool(self.worker and self.worker.poll() is None and state.get("pid") != self.worker.pid)
        if starting:
            status = "preparing"
            active = True
            state["stage"] = "번역 프로세스 시작 중"
        if active and state.get("pid"):
            try:
                process = psutil.Process(state["pid"])
                alive = abs(process.create_time() - state["process_created"]) < 1
            except (psutil.Error, KeyError, TypeError):
                alive = False
            if not alive and not starting:
                status = "failed"
                active = False
                state["stage"] = "이전 실행이 중단되었습니다. 다시 시작하면 번역 캐시를 사용합니다."
        elapsed = max(0, float(state.get("elapsed_seconds") or 0))
        if active:
            elapsed += max(0, time.time() - (self.folder / "state.json").stat().st_mtime)
        elapsed = int(elapsed)
        details = f"경과 {elapsed // 60}분 {elapsed % 60}초"
        if state.get("error"):
            details += " · " + str(state["error"])
        output = state.get("output")
        has_output = bool(output and Path(output).is_dir())
        output_dir = Path(output) if has_output else None
        stage = str(state.get("stage", "대기"))
        phase = state.get("work_phase")
        page_title, page_value, page_caption = _page_status(
            state, active, self._job["sourcePages"]
        )
        current, total = state.get("stage_current"), state.get("stage_total")
        review_match = re.search(r"(?<!\d)(\d+)/(\d+)", stage) if phase == "review" else None
        if review_match:
            current, total = map(int, review_match.groups())
        step_detail = (f"현재 단계 {int(current):,} / {int(total):,} " +
                       ("문단" if stage == "Translate Paragraphs" else "검수 항목" if review_match else "항목")) \
                      if type(current) is int and type(total) is int and total > 0 else ""
        self._job = {
            "status": status,
            "stage": stage,
            "stageDisplay": _stage_label(stage, phase),
            "stepDetail": step_detail,
            "pageTitle": page_title,
            "pageValue": page_value,
            "pageCaption": page_caption,
            "progress": max(0, min(100, round(state.get("progress") or 0))),
            "details": details,
            "active": active,
            "canResume": not active and status in {"failed", "cancelled", "partial"},
            "hasOutput": has_output,
            "hasKorean": bool(output_dir and (output_dir / "Korean.pdf").is_file()),
            "hasBilingual": bool(output_dir and (output_dir / "Bilingual.pdf").is_file()),
            "hasLegends": bool(output_dir and (output_dir / "FigureLegends.html").is_file()),
            "title": state.get("title", self._job["title"]),
            "sourcePages": self._job["sourcePages"],
        }
        self.jobChanged.emit()
        if has_output:
            korean = Path(output) / "Korean.pdf"
            if korean.is_file():
                stamp = (str(korean), korean.stat().st_size, korean.stat().st_mtime_ns)
                if stamp != self._preview_output:
                    try:
                        self._korean_preview = _preview(korean)
                        self._preview_output = stamp
                        self.previewsChanged.emit()
                    except (OSError, RuntimeError, ValueError):
                        pass

    @Slot(str)
    def openResult(self, name):
        if name not in OUTPUTS or not self.folder:
            return
        try:
            output = read(self.folder / "state.json").get("output")
            if output:
                path = Path(output) / name
                if path.exists():
                    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        except (OSError, ValueError):
            return

    def show(self):
        self._window.show()

    def close(self):
        self._window.close()

    def grab(self):
        return self._window.grabWindow()


def main():
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    sys.exit(app.exec())
