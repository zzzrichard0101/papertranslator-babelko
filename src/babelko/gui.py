import os,subprocess,sys
import psutil
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QUrl
from PySide6.QtGui import QDesktopServices,QFontDatabase,QFont
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QLineEdit,QFileDialog,QComboBox,QProgressBar,QMessageBox,QCheckBox
from .storage import root,read,save,project
from .pipeline import create


class Window(QWidget):
    def __init__(self):
        super().__init__()
        font_roots=[root()/'assets/fonts',Path(os.environ['LOCALAPPDATA'])/'PaperTranslatorBabelKO/assets/fonts']
        for font_root in font_roots:
            for name in ['SourceHanSansKR-Regular.ttf','SourceHanSansKR-Bold.ttf']:
                if (font_root/name).exists():QFontDatabase.addApplicationFont(str(font_root/name))
        self.folder=None;self.worker=None;self.setWindowTitle('BabelKO · 한국어 PDF 번역기 0.1');self.resize(950,790)
        self.setStyleSheet("QWidget{background:#f3f6f8;color:#15334a;font:15px 'Source Han Sans KR'} QLineEdit,QComboBox{background:white;border:1px solid #b8c8d3;border-radius:6px;padding:10px} QPushButton{padding:12px;background:#146f76;color:white;border:0;border-radius:6px} QPushButton:disabled{background:#bdc9ce;color:#eef2f4} QProgressBar{background:white;border:1px solid #cbd6de;text-align:center;height:24px} QProgressBar::chunk{background:#42969c} ")
        layout=QVBoxLayout(self);layout.setContentsMargins(35,25,35,30);layout.setSpacing(15)
        heading=QLabel('원래 레이아웃으로 한국어 PDF 읽기');heading.setStyleSheet('font-size:28px;font-weight:700');layout.addWidget(heading)
        layout.addWidget(QLabel('PDFMathTranslate-next + BabelDOC · 무료 로컬 다중 모델 · 별도 실험판'))
        self.source=QLineEdit();self.source.setPlaceholderText('번역할 PDF 선택')
        select=QPushButton('PDF 선택');select.clicked.connect(self.pick)
        row=QHBoxLayout();row.addWidget(self.source,1);row.addWidget(select);layout.addLayout(row)
        self.pages=QLineEdit();self.pages.setPlaceholderText('전체 쪽 · 예: 1-5,9,12-');layout.addWidget(self.pages)
        self.ocr=QComboBox();self.ocr.addItem('OCR 자동 · 스캔만 로컬 인식','auto');self.ocr.addItem('OCR 사용 안 함','off');self.ocr.addItem('모든 선택 쪽 강제 OCR','force');layout.addWidget(self.ocr)
        self.mode=QComboBox();self.mode.addItem('Hy-MT2 초벌 + Qwen 문장별 양방향 대조·재교정','hybrid');self.mode.addItem('Qwen 단일 모델 · 비교용','qwen');layout.addWidget(self.mode)
        self.experimental=QCheckBox('새 파이프라인 실험 · 동시 검수·원문 용어 문맥·PDF 위치 검사');layout.addWidget(self.experimental)
        self.mode.currentIndexChanged.connect(lambda _:self.experimental.setEnabled(self.mode.currentData()=='hybrid'))
        self.destination=QLineEdit(str(root()/'results'));Path(self.destination.text()).mkdir(exist_ok=True)
        browse=QPushButton('결과 폴더');browse.clicked.connect(self.pick_destination)
        row=QHBoxLayout();row.addWidget(self.destination,1);row.addWidget(browse);layout.addLayout(row)
        self.start=QPushButton('새 번역 시작');self.start.clicked.connect(self.begin)
        self.cancel=QPushButton('취소 · 번역 캐시 유지');self.cancel.clicked.connect(self.stop);self.cancel.setEnabled(False)
        self.resume=QPushButton('이 작업 다시 시작');self.resume.clicked.connect(self.restart);self.resume.setEnabled(False)
        row=QHBoxLayout();row.addWidget(self.start);row.addWidget(self.cancel);row.addWidget(self.resume);layout.addLayout(row)
        self.status=QLabel('준비됨');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.bar=QProgressBar();layout.addWidget(self.bar)
        self.details=QLabel('한국어 PDF · 원문을 왼쪽에 유지한 대조본 · 로컬 처리 근거를 저장합니다.');self.details.setWordWrap(True);layout.addWidget(self.details)
        row=QHBoxLayout()
        for label,file in [('한국어 PDF','Korean.pdf'),('영한 대조본','Bilingual.pdf'),('결과 폴더','')]:
            button=QPushButton(label);button.clicked.connect(lambda checked=False,file=file:self.open(file));row.addWidget(button)
        layout.addLayout(row)
        note=QLabel('기존 논문 번역기와 프로그램·작업 기록을 분리했습니다. 원본을 덮어쓰지 않습니다.\n공개 초기 실험판: 번역 의미·복잡한 표·수식·희미한 스캔의 정확도는 아직 검증 중입니다.');note.setWordWrap(True);note.setStyleSheet('color:#866a2d;font-size:13px');layout.addWidget(note)
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(500)
        last=root()/'last_job.json'
        if last.exists():
            try:self.folder=Path(read(last)['folder']);self.refresh()
            except Exception:pass
    def pick(self):
        name,_=QFileDialog.getOpenFileName(self,'PDF 선택',str(Path.home()),'PDF (*.pdf)')
        if name:self.source.setText(name)
    def pick_destination(self):
        name=QFileDialog.getExistingDirectory(self,'결과 폴더 선택',self.destination.text())
        if name:self.destination.setText(name)
    def launch(self):
        save(root()/'last_job.json',dict(folder=str(self.folder)))
        env={**os.environ,'PYTHONIOENCODING':'utf-8'}
        python=project()/'.venv/Scripts/python.exe'
        self.worker=subprocess.Popen([str(python),'-m','babelko.worker',str(self.folder)],env=env,cwd=project(),creationflags=subprocess.CREATE_NO_WINDOW)
        self.start.setEnabled(False);self.resume.setEnabled(False);self.cancel.setEnabled(True)
    def begin(self):
        try:self.folder=create(self.source.text(),self.destination.text(),self.pages.text(),self.ocr.currentData(),self.mode.currentData(),self.experimental.isChecked() and self.mode.currentData()=='hybrid');self.launch()
        except Exception as exc:QMessageBox.warning(self,'시작할 수 없음',str(exc))
    def stop(self):
        if self.folder:(self.folder/'cancel').touch();self.status.setText('취소 요청됨 · 진행 중인 처리 정리 중')
    def restart(self):
        if not self.folder:return
        try:(self.folder/'cancel').unlink(missing_ok=True);self.launch()
        except Exception as exc:QMessageBox.warning(self,'재시작할 수 없음',str(exc))
    def refresh(self):
        if not self.folder or not (self.folder/'state.json').exists():return
        try:state=read(self.folder/'state.json')
        except (OSError,ValueError):return
        active=state['status'] in {'queued','preparing','translating','validating'}
        if active and state.get('pid'):
            try:alive=psutil.pid_exists(state['pid']) and abs(psutil.Process(state['pid']).create_time()-state['process_created'])<1
            except psutil.Error:alive=False
            if not alive:state.update(status='failed',stage='이전 실행이 중단되었습니다. 다시 시작하면 번역 캐시를 사용합니다.');active=False
        self.start.setEnabled(not active);self.cancel.setEnabled(active);self.resume.setEnabled(not active and state['status'] in {'failed','cancelled'})
        self.status.setText(state.get('stage','대기'));self.bar.setValue(round(state.get('progress',0)))
        elapsed=state.get('elapsed_seconds',0);self.details.setText(f'경과 {int(elapsed//60)}분 {int(elapsed%60)}초 · '+state.get('error','쪽 구조와 원문 대응을 유지해 처리 중입니다.'))
    def open(self,file):
        if not self.folder:return
        state=read(self.folder/'state.json')
        if state.get('output'):
            path=Path(state['output'])/file
            if path.exists():QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def main():
    app=QApplication(sys.argv);window=Window();window.show();sys.exit(app.exec())
