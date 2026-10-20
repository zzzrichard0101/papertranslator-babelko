import sys,logging
from pathlib import Path
from .pipeline import run
if __name__=='__main__':
    folder=Path(sys.argv[1]);logging.basicConfig(filename=folder/'worker.log',level=logging.INFO,encoding='utf-8')
    try:run(folder)
    except BaseException:logging.exception('Worker failed');raise
