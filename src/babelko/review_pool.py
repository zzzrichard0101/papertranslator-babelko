"""Bounded speculative audit work; records and checkpoints stay on the owner thread."""
import copy
from concurrent.futures import ThreadPoolExecutor
from .assurance import audit_many, fingerprint


class ReviewPool:
    def __init__(self, request, cancel, workers=2):
        if workers not in (1, 2):raise ValueError('검수 동시 요청 수는 1 또는 2여야 합니다.')
        self.request=request;self.cancel=cancel;self.workers=workers;self.pending=[]
        self.executor=ThreadPoolExecutor(max_workers=workers,thread_name_prefix='babelko-audit')

    def submit(self, records):
        if len(self.pending)>=self.workers:raise RuntimeError('검수 요청 대기열 한도 초과')
        frozen=copy.deepcopy(records)
        future=self.executor.submit(audit_many,frozen,self.request,self.cancel)
        self.pending.append((list(records),[fingerprint(r) for r in frozen],future))

    def drain(self):
        # Wait for all reads before the caller can repair a candidate. A malformed
        # group falls back to the existing per-unit path, never an empty pass.
        rows=[]
        pending,self.pending=self.pending,[]
        for records,signatures,future in pending:
            try:
                outcomes=future.result()
                if [fingerprint(r) for r in records]!=signatures:
                    raise ValueError('동시 검수 중 번역 후보가 변경되었습니다.')
                rows.append((records,outcomes))
            except (ValueError,RuntimeError):rows.append((records,None))
        return rows

    def close(self):self.executor.shutdown(wait=True,cancel_futures=True)
