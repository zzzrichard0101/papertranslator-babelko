import os
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from babelko.storage import project
os.environ['BABELKO_HOME']=str(project()/'work/gui-home')
from babelko.gui import Window
if __name__=='__main__':
    app=QApplication([]);w=Window();w.show()
    def finish():
        w.grab().save(str(project()/'work/gui.png'));w.close();app.quit()
    QTimer.singleShot(1000,finish);app.exec();print('GUI passed')
