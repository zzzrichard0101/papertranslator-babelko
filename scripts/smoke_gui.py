import os
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from babelko.storage import project
os.environ['BABELKO_HOME']=str(project()/'work/gui-home')
from babelko.gui import Window
if __name__=='__main__':
    app=QApplication([]);w=Window();w.show()
    w.resetSettings()
    def finish():
        w.grab().save(str(project()/'work/gui.png'))
        sample=next((project()/'test_vault').glob('integration-hybrid-*/Synthetic two column and scanned table.pdf'),None)
        if sample:
            w.setForm('source',str(sample))
        QTimer.singleShot(350,finish_preview)
    def finish_preview():
        w.grab().save(str(project()/'work/gui-preview.png'))
        w._window.setProperty('page',2)
        w.setSetting('theme','night')
        QTimer.singleShot(250,finish_settings)
    def finish_settings():
        w.grab().save(str(project()/'work/gui-settings.png'))
        w.setSetting('text_scale',1.2)
        QTimer.singleShot(250,finish_large)
    def finish_large():
        w.grab().save(str(project()/'work/gui-settings-large.png'))
        w.resetSettings()
        w.close();app.quit()
    QTimer.singleShot(1000,finish);app.exec();print('GUI passed')
