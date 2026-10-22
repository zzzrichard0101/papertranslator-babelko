"""CPU reader serial/parallel comparison on identical synthetic page pixels."""
import argparse,json,multiprocessing,time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import pymupdf as fitz
from babelko.storage import save
from babelko.scan_evidence import Reader,recognize_task


def main(output,pages):
    output.mkdir(parents=True,exist_ok=False);source=output/'reader-control.pdf'
    with fitz.open() as doc:
        for n in range(pages):
            p=doc.new_page(width=600,height=800)
            p.insert_text((40,50),'Research methods and analytical records',fontsize=17)
            for line in range(24):p.insert_text((40,100+line*25),f'Research record {line+1}: Interview transcripts and consent forms.',fontsize=11)
        doc.save(source)
    start=time.perf_counter();reader=Reader();serial=[]
    with fitz.open(source) as doc:
        for page in doc:serial.append(reader.recognize(page))
    seconds_serial=time.perf_counter()-start
    tasks=[(str(source.resolve()),n,[[0,0,600,800]],str(output/'cancel')) for n in range(pages)]
    start=time.perf_counter()
    with ProcessPoolExecutor(max_workers=2,mp_context=multiprocessing.get_context('spawn')) as pool:parallel=list(pool.map(recognize_task,tasks))
    seconds_parallel=time.perf_counter()-start
    def canonical(rows):return [[(r['text'],tuple(round(x,4) for x in r['bbox']),round(r['score'],5)) for r in page] for page in rows]
    equal=canonical(serial)==canonical(parallel)
    result=dict(pages=pages,serial_seconds=round(seconds_serial,3),parallel_seconds=round(seconds_parallel,3),outputs_equal=equal,
        scope='Synthetic printed pages; includes process/model startup, not whole-job or scanned-book throughput.')
    save(output/'summary.json',result);print(json.dumps(result),flush=True)
    if not equal:raise RuntimeError('OCR parallel output differs; do not promote')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--pages',type=int,default=8)
    args=parser.parse_args();main(args.output,args.pages)
