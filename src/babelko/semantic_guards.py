"""Small, high-confidence checks for contradictions a fluent model can miss.

These are failure gates, not a dictionary-based translation engine. A flagged
unit is returned to the local editor with its complete source and context.
"""
import re

REVISION='technical-contradictions-6'
STYLE=re.compile(r"<style\s+id=['\"]\d+['\"]>|</style>")
OPEN_STYLE=re.compile(r"<style\s+id=['\"]\d+['\"]>")
TOKEN=re.compile(r'\{v\d+\}')
TRAILING_ENGLISH=re.compile(r'\b(?:as|by|the|and|or|of|to|in|for|with|that|which|while|although)\s*$',re.I)


def errors(source,target):
    if not isinstance(target,str):return []
    nesting=[]
    for match in TOKEN.finditer(source):
        other=re.search(re.escape(match.group()),target)
        if other is None:continue
        source_depth=sum(-1 if tag.group().startswith('</') else 1 for tag in STYLE.finditer(source,0,match.start()))
        target_depth=sum(-1 if tag.group().startswith('</') else 1 for tag in STYLE.finditer(target,0,other.start()))
        if source_depth==0 and target_depth>0:
            nesting.append(f'수식 자리표시자 {match.group()}가 원문과 달리 번역문의 서식 태그 안에 들어가 PDF에서 누락될 수 있습니다.')
    source=STYLE.sub('',source)
    target=STYLE.sub('',target)
    found=nesting
    if re.search(r'\bnon[ -]?increasing\b',source,re.I) and not re.search(r'\bnon[ -]?decreasing\b',source,re.I):
        if re.search(r'단조\s*비\s*감소|감소하지\s*않|증가하거나\s*일정',target):
            found.append('방향 반전: non-increasing은 비증가/단조 감소이며 비감소가 아닙니다.')
    if re.search(r'\bnon[ -]?decreasing\b',source,re.I) and not re.search(r'\bnon[ -]?increasing\b',source,re.I):
        if re.search(r'단조\s*비\s*증가|증가하지\s*않|감소하거나\s*일정',target):
            found.append('방향 반전: non-decreasing은 비감소/단조 증가이며 비증가가 아닙니다.')
    if re.search(r'\bexploitation\b',source,re.I) and re.search(r'활용\s*\(\s*exploration\s*\)',target,re.I):
        found.append('개념 반전: exploitation은 활용이고 exploration은 탐색입니다. 영어 병기를 바로잡으세요.')
    if re.search(r'\bexploitation\b',source,re.I) and re.search(r'개발\s*\(\s*exploitation\s*\)',target,re.I):
        found.append('용어 오류: exploitation은 이 문맥에서 개발이 아니라 활용입니다.')
    if (re.search(r'\bexploitation\b',source,re.I) and not re.search(r'\bexploration\b',source,re.I)
            and re.search(r'탐색',target) and not re.search(r'활용',target)):
        found.append('개념 반전: 원문의 exploitation을 탐색으로 번역했습니다. 활용으로 구별하세요.')
    if (re.search(r'\bexploitation[ -]only\b',source,re.I)
            and not re.search(r'\bexploration[ -]only\b',source,re.I)
            and re.search(r'탐색\s*위주|탐색\s*만|오직\s*탐색|탐색에만\s*의존',target)):
        found.append('개념 반전: exploitation-only는 탐색 위주가 아니라 활용에만 의존함을 뜻합니다.')
    if re.search(r'\bexploration\b',source,re.I) and re.search(r'탐색\s*\(\s*exploitation\s*\)',target,re.I):
        found.append('개념 반전: exploration은 탐색이고 exploitation은 활용입니다. 영어 병기를 바로잡으세요.')
    if re.search(r'\borders? of magnitude\b',source,re.I) and re.search(r'수\s*배\s*\(\s*orders? of magnitude\s*\)',target,re.I):
        found.append('규모 오류: orders of magnitude는 단순한 수 배가 아니라 자릿수 차이입니다.')
    if re.search(r'\borders? of magnitude\b',source,re.I) and re.search(r'(?:몇|수)\s*배(?:나)?\s*(?:더\s*)?(?:크|작)',target):
        found.append('규모 오류: orders of magnitude를 몇 배/수 배로 축소했습니다.')
    if re.search(r'\bgradient[ -]dependent\b',source,re.I) and re.search(r'경도에\s*의존',target):
        found.append('용어 오류: gradient-dependent의 gradient는 경도가 아니라 기울기입니다.')
    if re.search(r'\bany\s+\w+(?:\s+\w+)?\s+containing\s*$',source,re.I) and re.search(r'포함하는\s*모든',target):
        found.append('열린 조건 범위 오류: any ... containing 뒤의 조건을 특정하지 않은 채 모든 대상으로 확대했습니다.')
    if re.search(r'[가-힣]',target) and TRAILING_ENGLISH.search(source) and TRAILING_ENGLISH.search(target):
        found.append('쪽 경계의 영어 접속어가 미번역 상태로 남았습니다. 다음 문맥을 참고해 한국어로 연결하세요.')
    first_source=TOKEN.search(source)
    first_target=TOKEN.search(target)
    if (first_source and first_target and first_source.group()==first_target.group()
            and first_source.start()<=max(32,len(source)*.08)
            and first_target.start()>max(30,len(target)*.28)):
        found.append(f'수식 자리표시자 {first_source.group()}가 원문 첫 절에서 번역문의 뒤쪽 절로 이동했습니다. 원래 절에 붙여 번역하세요.')
    for match in TOKEN.finditer(target):
        token=match.group()
        original=re.search(re.escape(token),source)
        if original is None:continue
        before_source=source[:original.start()].rstrip()
        before_target=target[:match.start()].rstrip()
        after_target=target[match.end():].lstrip()
        if re.fullmatch(r'(?:에|를|을|은|는|이|가|의|와|과|로|으로)',before_target.strip()):
            found.append(f'수식 자리표시자 {token} 앞에 한국어 조사가 단독으로 놓였습니다. 조사를 해당 값 뒤로 옮겨 문장을 재구성하세요.')
        if (before_target.endswith(('.', '!', '?')) and after_target.startswith(('.', '!', '?'))
                and not before_source.endswith(('.', '!', '?'))):
            found.append(f'수식 자리표시자 {token}가 원문의 문장 안에서 번역문의 문장 끝 뒤로 이동했습니다.')
        if (re.search(r'(?:지만|그러나|따라서)\s*$',before_target)
                and after_target.startswith((',', '，'))
                and not re.search(r'(?:but|however|therefore|thus|hence|consequently)\s*$',before_source,re.I)):
            found.append(f'수식 자리표시자 {token}가 접속어 뒤에 잘못 붙었습니다. 원문에서 수식이 수식하는 명사 옆에 두세요.')
    return found


def repair(source,target):
    """Only replace exact, unambiguous contradictions; the caller revalidates."""
    if not isinstance(target,str):return target
    for match in TOKEN.finditer(source):
        token=match.group()
        source_depth=sum(-1 if tag.group().startswith('</') else 1 for tag in STYLE.finditer(source,0,match.start()))
        if source_depth==0:
            # A token immediately following an opening style tag can be moved
            # before that tag without changing any visible translated prose.
            target=re.sub(r'('+OPEN_STYLE.pattern+r')\s*('+re.escape(token)+r')',r'\2\1',target,count=1)
    if re.search(r'\bnon[ -]?increasing\b',source,re.I) and not re.search(r'\bnon[ -]?decreasing\b',source,re.I):
        target=re.sub(r'단조\s*비\s*감소','단조비증가',target)
    if re.search(r'\bnon[ -]?decreasing\b',source,re.I) and not re.search(r'\bnon[ -]?increasing\b',source,re.I):
        target=re.sub(r'단조\s*비\s*증가','단조비감소',target)
    if re.search(r'\bexploitation\b',source,re.I):
        target=re.sub(r'활용\s*\(\s*exploration\s*\)','활용(exploitation)',target,flags=re.I)
        target=re.sub(r'개발\s*\(\s*exploitation\s*\)','활용(exploitation)',target,flags=re.I)
    if re.search(r'\bexploitation[ -]only\b',source,re.I) and not re.search(r'\bexploration[ -]only\b',source,re.I):
        target=re.sub(r'오직\s*탐색\s*만을\s*위한|탐색\s*위주의|탐색에만\s*의존하는','활용에만 의존하는',target)
    if re.search(r'\borders? of magnitude\b',source,re.I):
        target=re.sub(r'수\s*배\s*\(\s*orders? of magnitude\s*\)','여러 자릿수(orders of magnitude)',target,flags=re.I)
        target=re.sub(r'(?:몇|수)\s*배(?:나)?(?=\s*(?:더\s*)?(?:크|작))','여러 자릿수만큼',target)
    if re.search(r'\bgradient[ -]dependent\b',source,re.I):
        target=re.sub(r'경도에\s*의존','기울기에 의존',target)
    if re.search(r'\bany\s+\w+(?:\s+\w+)?\s+containing\s*$',STYLE.sub('',source),re.I):
        target=re.sub(r'(?:다음을\s+)?포함하는\s*모든','다음을 포함하는 각각의',target)
    return target
