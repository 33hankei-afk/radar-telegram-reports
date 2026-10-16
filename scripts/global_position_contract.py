"""Shared stdlib report contract. Validation checks consistency, not source truth."""
from datetime import datetime,timedelta,timezone,date
from urllib.parse import urlparse
import hashlib,json,ipaddress,re

SCHEMA='global_position_v1';KST=timezone(timedelta(hours=9));HOUR=8
TARGETS=(
 {'id':'tuteja','name':'Shawn Tuteja','institution':'Goldman Sachs','role':'ETF·맞춤형 바스켓 변동성 트레이딩','focus':'AI·M7 과밀 / 옵션 / 포지션 비대칭'},
 {'id':'hartnett','name':'Michael Hartnett','institution':'BofA Global Research','role':'최고 투자전략가 · Flow Show','focus':'펀드 자금흐름 / 현금·과열 / 자산배분'},
 {'id':'pimco','name':'PIMCO','institution':'PIMCO','role':'기관 · Ivascyn / Balls / Wilding 등','focus':'금리·채권 / 조달·유동성 / 위험자산 배분'},
)
ASSESSMENTS=('pressure','ai_positioning','liquidity','korea_path')
LABELS={'pressure':'글로벌 주식 매수·매도 압력','ai_positioning':'AI·반도체 포지션','liquidity':'금리·조달·유동성','korea_path':'한국장 전달 경로'}
KINDS=('primary','news','community','candidate')
ACCESS=('full_text','partial_text','headline_only')
DIRECTIONS=('risk_add','risk_reduce','short_cover','hedge','mixed','unknown')
MECHANISMS=('long_liquidation','short_covering','gross_deleveraging','net_exposure','crowding',
 'cta','vol_control','dealer_gamma','fund_flows','treasury_basis','repo_margin','carry_trade','rates_credit','other')


def stamp(value):
 d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
 if d.tzinfo is None:raise ValueError('시간대 없는 시각')
 return d.astimezone(KST)

def safe_url(value):
 try:
  p=urlparse(str(value));host=(p.hostname or '').lower()
  if p.scheme!='https' or p.username or p.password or p.port not in (None,443) or not host or '.' not in host:return False
  if host.endswith(('.local','.internal','.localhost')) or host=='localhost':return False
  try:ipaddress.ip_address(host);return False
  except ValueError:pass
  return len(value)<=2500 and not re.search(r'[\x00-\x20]',value)
 except (ValueError,TypeError):return False

def canonical(obj):return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def seal(obj):
 obj=json.loads(canonical(obj));obj.pop('content_sha256',None)
 return {**obj,'content_sha256':hashlib.sha256(canonical(obj)).hexdigest()}

def expected_day(now=None):
 now=(now or datetime.now(KST)).astimezone(KST)
 return (now.date() if now.hour>=HOUR else now.date()-timedelta(days=1)).isoformat()

def next_schedule(now=None):
 now=(now or datetime.now(KST)).astimezone(KST);target=now.replace(hour=HOUR,minute=0,second=0,microsecond=0)
 return (target if now<target else target+timedelta(days=1)).isoformat()

def empty_assessments():
 return {k:{'label':'판단 자료 부족','confidence':'낮음','summary':'원문 검증 자료를 기다립니다.','evidence_ids':[],'counter_ids':[],'limitations':['전체 헤지펀드의 실제 포지션을 추정한 수치가 아닙니다.']} for k in ASSESSMENTS}

def validate(obj,now=None):
 now=(now or datetime.now(KST)).astimezone(KST)
 if not isinstance(obj,dict) or obj.get('schema')!=SCHEMA:raise ValueError('글로벌 포지션 보고서 규격 오류')
 raw={k:v for k,v in obj.items() if k!='content_sha256'}
 if hashlib.sha256(canonical(raw)).hexdigest()!=obj.get('content_sha256'):raise ValueError('글로벌 포지션 보고서 해시 불일치')
 day=date.fromisoformat(obj['date_kst'])
 start=stamp(obj['window_start_kst']);end=stamp(obj['window_end_kst']);generated=stamp(obj['generated_at_kst'])
 if start>=end or end>generated or generated>now+timedelta(minutes=5) or generated.date()!=day:raise ValueError('보고서 수집·발행 시각 오류')
 if obj.get('producer') not in ('gpt_verified','rss_discovery'):raise ValueError('보고서 작성 방식 오류')
 if type(obj.get('complete')) is not bool:raise ValueError('보고서 완료 여부 누락')
 entries=obj.get('entries');context=obj.get('context_entries',[]);coverage=obj.get('coverage')
 if not isinstance(entries,list) or len(entries)>1000 or not isinstance(context,list) or len(context)>1000 or not isinstance(coverage,list) or not coverage:raise ValueError('원문/수집 범위 누락')
 ids={};urls=set()
 for e in entries+context:
  is_context=e in context
  if not isinstance(e,dict):raise ValueError('원문 행 오류')
  ident=e.get('id');url=e.get('url')
  if not isinstance(ident,str) or not ident or ident in ids or url in urls or not safe_url(url):raise ValueError('원문 식별자/URL 중복 또는 오류')
  for key,limit in (('publisher',200),('title_ko',500),('summary_ko',1600),('event_key',400)):
   if not isinstance(e.get(key),str) or not e[key].strip() or len(e[key])>limit:raise ValueError('원문 필수 내용 오류: '+key)
  if e.get('source_kind') not in KINDS or e.get('access') not in ACCESS or e.get('direction') not in DIRECTIONS:raise ValueError('원문 근거 등급/방향 오류')
  if e.get('claim_type') not in ('opinion','reported_flow','observed_metric','unverified'):raise ValueError('발언과 포지션 구분 누락')
  if not isinstance(e.get('actors'),list) or any(not isinstance(x,str) or not x.strip() for x in e['actors']) or not isinstance(e.get('mechanisms'),list) or any(x not in MECHANISMS for x in e['mechanisms']):raise ValueError('대상/메커니즘 오류')
  published=e.get('published_at_kst')
  if published:
   t=stamp(published)
   if (not is_context and (t>end or t<start)) or (is_context and not start-timedelta(days=30)<=t<start):raise ValueError('수집 범위 밖 게시물')
   if e.get('published_date')!=t.date().isoformat():raise ValueError('게시일·게시시각 불일치')
  else:
   d=date.fromisoformat(e['published_date'])
   if (not is_context and not start.date()<=d<=end.date()) or (is_context and not (start-timedelta(days=30)).date()<=d<=start.date()):raise ValueError('게시일 범위 오류')
  if e.get('event_date') and date.fromisoformat(e['event_date'])>end.date():raise ValueError('미래 발언일')
  if e.get('access')=='headline_only' and e.get('claim_type')!='unverified':raise ValueError('제목만 확인한 자료를 사실로 표시할 수 없음')
  if obj['producer']=='rss_discovery' and (e['access']!='headline_only' or e['claim_type']!='unverified'):raise ValueError('RSS 후보가 검증 원문으로 승격됨')
  ids[ident]=e;urls.add(url)
 for row in coverage:
  if not isinstance(row,dict) or row.get('status') not in ('checked','partial','blocked','failed') or not isinstance(row.get('name'),str) or not row['name'].strip() or not isinstance(row.get('note',''),str) or (row.get('url') is not None and not safe_url(row['url'])):raise ValueError('수집 상태 오류')
 for key in ASSESSMENTS:
  item=obj.get('assessments',{}).get(key,{})
  if not all(isinstance(item.get(k),str) and item[k].strip() for k in ('label','confidence','summary')):raise ValueError('판단 내용 누락')
  if not isinstance(item.get('limitations'),list) or any(not isinstance(x,str) for x in item['limitations']):raise ValueError('판단 한계 오류')
  for field in ('evidence_ids','counter_ids'):
   refs=item.get(field)
   if not isinstance(refs,list) or any(x not in ids for x in refs):raise ValueError('판단에 미존재 근거 포함')
   if any(ids[x]['access']=='headline_only' or ids[x]['claim_type']=='unverified' or ids[x]['source_kind']=='community' for x in refs):raise ValueError('미검증/커뮤니티 주장을 판단 근거로 승격할 수 없음')
   for x in refs:
    e=ids[x]
    if not e.get('published_at_kst') and e not in context:
     d=date.fromisoformat(e['published_date'])
     if datetime.combine(d,datetime.min.time(),KST)<start or datetime.combine(d,datetime.max.time(),KST)>end:raise ValueError('경계 날짜의 게시시각 미확인 근거')
  if not item['evidence_ids'] and item['label']!='판단 자료 부족':raise ValueError('근거 없는 시장 판단')
 if not isinstance(obj.get('core_targets'),list) or len(obj['core_targets'])!=3 or any(not isinstance(t,dict) for t in obj['core_targets']) or set(t.get('id') for t in obj['core_targets'])!={t['id'] for t in TARGETS}:raise ValueError('핵심 3대상 누락')
 for target in obj['core_targets']:
  refs=target.get('evidence_ids',[])
  if not isinstance(refs,list) or any(x not in ids or target['id'] not in ids[x]['actors'] for x in refs):raise ValueError('핵심 대상과 원문 불일치')
  if any(ids[x]['access']=='headline_only' or ids[x]['claim_type']=='unverified' or ids[x]['source_kind']=='community' for x in refs):raise ValueError('미검증 자료를 핵심 관점으로 승격할 수 없음')
  if not isinstance(target.get('summary_ko'),str) or not target['summary_ko'].strip():raise ValueError('핵심 대상 요약 누락')
  if target.get('change') not in (None,'미확인','신규 확인') and (len({ids[x]['event_key'] for x in refs})<2 or len({ids[x].get('event_date') or ids[x]['published_date'] for x in refs})<2):raise ValueError('비교 근거 없는 입장 변화')
 return obj


def markdown(obj,now=None):
 validate(obj,now);parts=['# 글로벌 포지션 일보 · '+obj['date_kst'],
  '취합 구간: '+obj['window_start_kst']+' ~ '+obj['window_end_kst'],
  '발행: '+obj['generated_at_kst']+' · '+obj['producer'],obj.get('coverage_note','')]
 for key in ASSESSMENTS:
  a=obj['assessments'][key];parts+=['\n## '+LABELS[key],a['label']+' / 신뢰도 '+a['confidence'],a['summary'],
   '근거: '+(', '.join(a['evidence_ids']) or '없음'),'반대 근거: '+(', '.join(a['counter_ids']) or '미확인')]
  parts.extend('확인 한계: '+x for x in a['limitations'])
 parts+=['\n## 핵심 3대상']
 for t in obj['core_targets']:parts.append('- '+t.get('name',t['id'])+' / '+t['summary_ko']+' / 변화: '+str(t.get('change') or '미확인')+' / 근거: '+(', '.join(t['evidence_ids']) or '미확인'))
 parts+=['\n## 확인 원문','|ID|게시일|발언일|대상|구분|한국어 요약|원문|','|---|---|---|---|---|---|---|']
 for e in obj['entries']+obj.get('context_entries',[]):
  clean=lambda v:str(v).replace('|',' / ').replace('\n',' ')
  parts.append('|'+ '|'.join(clean(v) for v in (e['id'],e.get('published_at_kst') or e['published_date']+' (시각 미확인)',e.get('event_date') or '미확인',', '.join(e['actors']),('이전 자료 / ' if e in obj.get('context_entries',[]) else '')+e['source_kind']+' / '+e['access']+' / '+e['claim_type'],e['title_ko']+' · '+e['summary_ko'],'['+e['url']+']('+e['url']+')'))+'|')
 parts+=['\n## 수집 범위']
 for row in obj['coverage']:parts.append('- '+row['name']+' / '+row['status']+' / '+str(row.get('note','')))
 return '\n\n'.join(parts)+'\n'
