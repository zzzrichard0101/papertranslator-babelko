"""Exact, narrow duration equivalence; never relax signs or unrelated numbers."""
from fractions import Fraction
from decimal import Decimal,localcontext
import collections,re

WORDS=dict(zero=0,one=1,two=2,three=3,four=4,five=5,six=6,seven=7,eight=8,nine=9,ten=10,
           eleven=11,twelve=12,thirteen=13,fourteen=14,fifteen=15,sixteen=16,seventeen=17,eighteen=18,nineteen=19,
           twenty=20,thirty=30,forty=40,fifty=50,sixty=60,seventy=70,eighty=80,ninety=90)


def expand_scale_ranges(text):
    """A shared quantity suffix applies to both endpoints: 1-5 million."""
    number=r'[-+−]?\d+(?:\.\d+)?'
    units=r'(?:thousand|million|billion|trillion|[KMB])\b|백만|천만|천|만|억|조'
    return re.sub(r'(?<![\w.])('+number+r')\s*(?:[-–~]|\bto\b)\s*('+number+r')\s*('+units+r')',
                  r'\1\3 to \2\3',text,flags=re.I)


def equivalent_scales(source,target):
    """Mask only exactly paired large quantities, e.g. 2 billion == 20억."""
    source,target=expand_scale_ranges(source),expand_scale_ranges(target)
    word_number='|'.join(sorted(WORDS,key=len,reverse=True))
    en=list(re.finditer(r'(?<![\w])([-+−]?\d+(?:\.\d+)?\s*|(?:'+word_number+
        r')\s+)(thousand|million|billion|trillion)\b',source,re.I))
    ko=list(re.finditer(r'(?<![\w])([-+−]?\d+(?:\.\d+)?)\s*(천|만|억|조)',target))
    factors=dict(thousand=1000,million=1000000,billion=1000000000,trillion=1000000000000,천=1000,만=10000,억=100000000,조=1000000000000)
    used=set();a=[];b=[]
    for original in en:
        raw=original[1].strip();multiplier=WORDS.get(raw.lower())
        amount=Fraction(multiplier if multiplier is not None else raw.replace('−','-'))*factors[original[2].lower()]
        match=next((i for i,t in enumerate(ko) if i not in used and Fraction(t[1].replace('−','-'))*factors[t[2]]==amount),None)
        if match is not None:used.add(match);a.append(original.span());b.append(ko[match].span())
    def mask(text,spans):
        chars=list(text)
        for start,end in spans:chars[start:end]=' '*(end-start)
        return ''.join(chars)
    return mask(source,a),mask(target,b)


def equivalent_decades(source,target):
    """Pair only an explicit ten-year interval with its Korean numeral form."""
    originals=list(re.finditer(r'\b(?:a|one|(?:(?:the\s+)?(?:last|past|previous)))\s+decade\b',source,re.I))
    targets=list(re.finditer(r'(?<!\d)10\s*년(?!대)',target))
    n=min(len(originals),len(targets))
    def mask(text,matches):
        chars=list(text)
        for match in matches[:n]:chars[match.start():match.end()]=' '*(match.end()-match.start())
        return ''.join(chars)
    return mask(source,originals),mask(target,targets)


def equivalent_clocks(source,target):
    """Pair exact 24-hour times with Korean 오전/오후 clock notation."""
    originals=list(re.finditer(r'(?<![\w:])([01]?\d|2[0-3]):([0-5]\d)(?!\d)',source))
    targets=list(re.finditer(r'(?<![가-힣])(?:오전|오후)\s*(1[0-2]|\d)\s*시(?:\s*([0-5]?\d)\s*분)?',target))
    used=set();left=[];right=[]
    for original in originals:
        hour,minute=int(original[1]),int(original[2])
        partner=next((i for i,item in enumerate(targets)
            if i not in used and (int(item[1])%12+(12 if item[0].startswith('오후') else 0))==hour
            and int(item[2] or 0)==minute),None)
        if partner is not None:
            used.add(partner);left.append(original.span());right.append(targets[partner].span())
    def mask(text,spans):
        chars=list(text)
        for start,end in spans:chars[start:end]=' '*(end-start)
        return ''.join(chars)
    return mask(source,left),mask(target,right)


def equivalent_named_labels(source,target):
    """Pair a Latin proper-name suffix with a Korean name's identical suffix.

    A bare Korean word followed by -5 is never enough: the source must carry
    the same positive suffix on a capitalized name, such as Helios-1.
    """
    originals=list(re.finditer(r'(?<![A-Za-z0-9])[A-Z][A-Za-z]{2,}-(\d+)(?![A-Za-z0-9])',source))
    targets=list(re.finditer(r'(?<![가-힣])(?:[가-힣]{2,})-(\d+)(?!\d)',target))
    used=set();left=[];right=[]
    for original in originals:
        partner=next((i for i,item in enumerate(targets)
                      if i not in used and item[1]==original[1]),None)
        if partner is not None:
            used.add(partner);left.append(original.span());right.append(targets[partner].span())
    def mask(text,spans):
        chars=list(text)
        for start,end in spans:chars[start:end]=' '*(end-start)
        return ''.join(chars)
    return mask(source,left),mask(target,right)


def equivalent_scaled_numerals(source,target):
    """Pair exact K/M/B, Korean large-unit and expanded decimal quantities."""
    factors=dict(K=1000,M=1000000,B=1000000000,백만=1000000,천만=10000000,천=1000,만=10000,억=100000000,조=1000000000000)
    numeric=r'[-+−]?\d+(?:[.,]\d+)*'
    pattern=re.compile('('+numeric+r')\s*(K|M|B|백만|천만|천|만|억|조)?')
    def canonical(text):
        text=re.sub(r'(?<=[A-Za-z가-힣])[-–](?=\d+(?:\.\d+)?K(?:\b|iterations))',' ',text)
        text=expand_scale_ranges(text)
        def expanded(m):
            with localcontext() as context:
                context.prec=80
                result=Decimal(m[1].replace('−','-').replace(',',''))*dict(thousand=1000,million=1000000,billion=1000000000,trillion=1000000000000)[m[2].lower()]
                return ('+' if m[1].startswith('+') else '')+format(result.normalize(),'f')
        return re.sub('('+numeric+r')\s*(thousand|million|billion|trillion)\b',expanded,text,flags=re.I)
    source,target=canonical(source),canonical(target)
    def items(text):
        result=[]
        for m in pattern.finditer(text):
            try:amount=Fraction(m[1].replace('−','-').replace(',',''))*factors.get(m[2],1)
            except (ValueError,ZeroDivisionError):continue
            result.append((m,amount,bool(m[2])))
        return result
    originals,targets=items(source),items(target);used=set();a=[];b=[]
    for original,amount,scaled in originals:
        match=next((i for i,(t,v,s) in enumerate(targets) if i not in used and (scaled or s) and amount==v and original[1].startswith('+')==t[1].startswith('+')),None)
        if match is not None:used.add(match);a.append(original.span());b.append(targets[match][0].span())
    def mask(text,spans):
        chars=list(text)
        for start,end in spans:chars[start:end]=' '*(end-start)
        return ''.join(chars)
    unmatched_source=any(scaled and m.span() not in a for m,_,scaled in originals)
    unmatched_target=any(scaled and i not in used for i,(_,_,scaled) in enumerate(targets))
    return mask(source,a),mask(target,b),unmatched_source and unmatched_target
KOREAN=dict(한=1,두=2,세=3,네=4,다섯=5,여섯=6,일곱=7,여덟=8,아홉=9,열=10,스무=20)
WORD='(?:'+'|'.join(sorted(WORDS,key=len,reverse=True))+')'
NUMBER=r'[-+−]?(?:\d+[- ]\d+/\d+|\d+½|\d+/\d+|\d+(?:\.\d+)?)'
VALUE=r'(?:(?:'+NUMBER+'|'+WORD+r')\s+(?:thousand|million|billion)|'+NUMBER+'|'+WORD+r'\s+and\s+a\s+half|'+WORD+r'(?:[- ]'+WORD+r')?)'
EN=re.compile(r'(?<![\w])('+VALUE+r')[-\s]+(decades?|years?|months?|weeks?|days?|hours?|minutes?|seconds?)\b',re.I)
KO=re.compile(r'(?<![A-Za-z0-9_])((?:'+NUMBER+'|'+'|'.join(sorted(KOREAN,key=len,reverse=True))+r')(?:\s*[만억조])?)\s*(개월|시간|년|세(?!기)|해|달|주|일|분|초)(\s*반)?')
FACTORS={'decade':('months',120),'year':('months',12),'month':('months',1),
         'week':('days',7),'day':('days',1),'hour':('seconds',3600),'minute':('seconds',60),'second':('seconds',1),
         '년':('months',12),'해':('months',12),'세':('months',12),'개월':('months',1),'달':('months',1),
         '주':('days',7),'일':('days',1),'시간':('seconds',3600),'분':('seconds',60),'초':('seconds',1)}


def value(text):
    text=text.lower().replace('−','-')
    large=re.fullmatch(r'(.+?)\s*(thousand|million|billion|만|억|조)',text)
    if large:return value(large[1])*dict(thousand=1000,million=1000000,billion=1000000000,만=10000,억=100000000,조=1000000000000)[large[2]]
    if text in KOREAN:return Fraction(KOREAN[text])
    mixed=re.fullmatch(r'([-+]?\d+)[- ](\d+/\d+)',text)
    if mixed:return Fraction(mixed[1])+(-1 if mixed[1].startswith('-') else 1)*Fraction(mixed[2])
    if text.endswith('½'):return Fraction(text[:-1])+Fraction(1,2)
    if re.match(r'[-+]?\d',text):return Fraction(text)
    half=text.endswith(' and a half')
    if half:text=text[:-11]
    return Fraction(sum(WORDS[w] for w in re.split('[- ]',text)))+(Fraction(1,2) if half else 0)


def _point_groups(text):
    amount=r'(?:'+VALUE+r'|[-+−]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?|(?:a|one)\s+half|half|반)'
    unit=r'(?:percentage\s+points?|percent\s+points?|%\s*(?:points?|포인트|[pP](?![A-Za-z]))|퍼센트\s*포인트)'
    pattern=re.compile(r'(?<![A-Za-z0-9_./])('+amount+r')\s*(?:(?:of\s+)?a\s+)?'+unit,re.I)
    result=[]
    for match in pattern.finditer(text):
        try:
            token=match[1].replace(',','').lower()
            result.append((match,Fraction(1,2) if token in {'half','a half','one half','반'} else value(token)))
        except (ValueError,KeyError,ZeroDivisionError):continue
    return result


def percentage_point_errors(source,target):
    """Percent and percentage-point changes are distinct even with equal digits."""
    return collections.Counter(v for _,v in _point_groups(source))!=collections.Counter(v for _,v in _point_groups(target))


def equivalent_percentage_points(source,target):
    """Pair exact word/fraction quantities without relaxing decimal precision."""
    a,b=_point_groups(source),_point_groups(target);used=set();left=[];right=[]
    for original,amount in a:
        partner=next((i for i,(m,v) in enumerate(b) if i not in used and v==amount),None)
        if partner is None:continue
        used.add(partner);translated=b[partner][0]
        if re.search(r'[A-DF-Za-df-z가-힣/½]',original[1]+translated[1]):left.append(original.span());right.append(translated.span())
    def mask(text,spans):
        chars=list(text)
        for start,end in spans:chars[start:end]=' '*(end-start)
        return ''.join(chars)
    return mask(source,left),mask(target,right)


def groups(text,pattern):
    found=[]
    for match in pattern.finditer(text):
        unit=match[2].lower().rstrip('s') if pattern is EN else match[2]
        family,factor=FACTORS[unit]
        try:amount=value(match[1])+(Fraction(1,2) if pattern is KO and match[3] else 0)
        except (ValueError,KeyError,ZeroDivisionError):continue
        item=dict(start=match.start(),end=match.end(),family=family,value=amount*factor)
        if found and found[-1]['family']==family and re.fullmatch(r'\s*(?:and\s*)?',text[found[-1]['end']:item['start']],re.I):
            found[-1]['end']=item['end'];found[-1]['value']+=item['value']
        else:found.append(item)
    return found


def equivalent_durations(source,target):
    """Mask only paired equal quantities, leaving all other numbers for strict checks."""
    # Narrative "One day, ..." is not a measured 24-hour duration. Permit the
    # exact Korean idiom only at a sentence boundary; keep "took one day" strict.
    if re.search(r'어느\s*날',target):
        source=re.sub(r'(^|[.!?]\s+)(one day)(?=,\s+(?:after|when|while|I|we|he|she|they|there)\b)',
                      lambda m:m[1]+' '*len(m[2]),source,flags=re.I)
    originals=groups(source,EN);targets=groups(target,KO);used=set();a=[];b=[];unmatched=[]
    for original in originals:
        match=next((i for i,t in enumerate(targets) if i not in used and t['family']==original['family'] and t['value']==original['value']),None)
        if match is None:unmatched.append(source[original['start']:original['end']]);continue
        used.add(match);a.append((original['start'],original['end']));b.append((targets[match]['start'],targets[match]['end']))
    def mask(text,spans):
        chars=list(text)
        for start,end in spans:chars[start:end]=' '*(end-start)
        return ''.join(chars)
    return mask(source,a),mask(target,b),unmatched


def equivalent_fractions(source,target):
    """Pair explicit word fractions with exact Korean/percent representations."""
    denominators={'half':2,'halves':2,'third':3,'thirds':3,'quarter':4,'quarters':4,
                  'fourth':4,'fourths':4,'fifth':5,'fifths':5,'sixth':6,'sixths':6,
                  'seventh':7,'sevenths':7,'eighth':8,'eighths':8,'ninth':9,'ninths':9,'tenth':10,'tenths':10}
    nums=r'(?:\d+(?:\.\d+)?|'+WORD+r'|an?|a)'
    pattern=re.compile(r'(?<!\w)(?P<sign>minus\s+|negative\s+|[+−-]\s*)?(?P<num>'+nums+r')(?P<sep>[-\s]+)(?P<den>'+
                       '|'.join(sorted(denominators,key=len,reverse=True))+r')\b',re.I)
    originals=[]
    for match in pattern.finditer(source):
        following=source[match.end():]
        if following.startswith('-') or re.match(r'\s*(?:of\s+(?:a|an|the)\s+)?(?:years?|days?|hours?|months?|weeks?|minutes?|seconds?|per\s+cent|percent)\b',following,re.I):continue
        if match['den'].lower().startswith('quarter') and '-' not in match['sep'] and not re.match(r'\s+of\b',following,re.I):continue
        if match['num'].lower() in {'a','an'} and re.search(r'\band\s+$',source[:match.start()],re.I):continue
        numerator=Fraction(1) if match['num'].lower() in {'a','an'} else value(match['num'])
        sign=-1 if match['sign'] and match['sign'].strip().lower() in {'minus','negative','-','−'} else 1
        originals.append((match.start(),match.end(),sign*numerator/denominators[match['den'].lower()]))
    sino=dict(일=1,이=2,삼=3,사=4,오=5,육=6,칠=7,팔=8,구=9,십=10)
    korean={**KOREAN,**sino}
    token=r'[+−-]?(?:\d+|'+'|'.join(sorted(korean,key=len,reverse=True))+r')'
    def number(text):
        sign=-1 if text.startswith(('-','−')) else 1;text=text.lstrip('+−-')
        return sign*(Fraction(korean[text]) if text in korean else Fraction(text))
    targets=[]
    fraction=re.compile(r'(?<!\d)(?P<sign>마이너스\s*|음의\s*)?(?P<den>'+token+r')\s*분의\s*(?P<num>'+token+r')')
    for match in fraction.finditer(target):
        if re.match(r'\s*%',target[match.end():]):continue
        try:amount=number(match['num'])/number(match['den'])*(-1 if match['sign'] else 1)
        except ZeroDivisionError:continue
        targets.append((match.start(),match.end(),amount))
    # Korean counters/particles directly after a fraction ("1/4만") are valid.
    # Only ASCII identifier continuations make the fraction part of a token.
    for match in re.finditer(r'(?<![A-Za-z0-9_/:.])([-+−]?\d+)\s*/\s*(\d+)(?![A-Za-z0-9_/]|\s*%)',target):
        if int(match[2]):targets.append((match.start(),match.end(),Fraction(match[1].replace('−','-'))/int(match[2])))
    for match in re.finditer(r'(?<![A-Za-z0-9_./])[-+−]?\d+(?:\.\d+)?\s*%',target):
        targets.append((match.start(),match.end(),Fraction(match[0][:-1].strip().replace('−','-'))/100))
    for match in re.finditer(r'절반|반수',target):targets.append((match.start(),match.end(),Fraction(1,2)))
    used=set();a=[];b=[];unmatched=[]
    for start,end,amount in originals:
        partner=next((i for i,t in enumerate(targets) if i not in used and t[2]==amount),None)
        if partner is None:
            if targets:unmatched.append(source[start:end])
            continue
        used.add(partner);a.append((start,end));b.append(targets[partner][:2])
    def mask(text,spans):
        chars=list(text)
        for start,end in spans:chars[start:end]=' '*(end-start)
        return ''.join(chars)
    return mask(source,a),mask(target,b),unmatched
