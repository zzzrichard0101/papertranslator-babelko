import argparse
from babelko.pipeline import create,run
p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('--output',required=True);p.add_argument('--pages',default='');p.add_argument('--ocr',choices=['auto','off','force'],default='auto');a=p.parse_args()
if __name__=='__main__':
    folder=create(a.source,a.output,a.pages,a.ocr);print(folder,flush=True);print(run(folder)['output'])
