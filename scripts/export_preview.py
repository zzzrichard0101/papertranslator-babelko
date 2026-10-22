"""Explicitly export an unverified checkpoint preview, without new inference."""
import argparse,json,logging
from pathlib import Path
from babelko.preview import export

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--job',type=Path,required=True);parser.add_argument('--output',type=Path);parser.add_argument('--pages',default='')
    args=parser.parse_args();logging.basicConfig(filename=args.job/'preview-worker.log',level=logging.INFO,encoding='utf-8')
    report=export(args.job,args.output,args.pages)
    print(json.dumps({k:report[k] for k in ['status','output','unresolved_count','model_calls','choices','seconds']},ensure_ascii=False,default=str),flush=True)
