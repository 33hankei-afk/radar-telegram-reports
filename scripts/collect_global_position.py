"""Public RSS discovery only; never promotes a headline into a portfolio judgment."""
from datetime import datetime,timedelta,timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor
import hashlib,html,json,re,sys,xml.etree.ElementTree as ET
from global_position_contract import SCHEMA,TARGETS,KST,seal,validate,empty_assessments,markdown,safe_url

QUERIES=(
 ('Shawn Tuteja','"Shawn Tuteja"'),('Michael Hartnett','"Michael Hartnett"'),
 ('PIMCO','PIMCO (Ivascyn OR Balls OR Wilding OR outlook OR flows)'),
 ('글로벌 포지션·프라임브로커','("hedge fund" OR "prime broker") (positioning OR deleveraging OR "net exposure" OR "gross exposure")'),
 ('CTA·옵션·자금흐름','(CTA OR "volatility control" OR "dealer gamma" OR "short covering" OR "fund flows") (stocks OR equity OR equities)'),
 ('국채·조달·캐리','("treasury basis" OR "basis trade" OR repo OR "margin call" OR "yen carry") ("hedge fund" OR leverage OR trade)'),
)
SOURCES=[(name,'https://news.google.com/rss/search?'+urlencode({'q':query+' when:1d','hl':'en-US','gl':'US','ceid':'US:en'}),'candidate') for name,query in QUERIES]
SOURCES += [('Reddit r/'+sub,'https://www.reddit.com/r/'+sub+'/new/.rss','community') for sub in ('stocks','investing','wallstreetbets')]
PATTERN=re.compile(r'hedge fund|positioning|deleverag|short cover|net exposure|gross exposure|prime broker|\bCTA\b|gamma|basis trade|margin call|carry trade|tuteja|hartnett|pimco',re.I)


def fetch(url):
 req=Request(url,headers={'User-Agent':'DayTradingRadar public briefing contact: local market reader','Accept':'application/rss+xml,application/atom+xml,text/xml'})
 with urlopen(req,timeout=12) as r:raw=r.read(2_000_001)
 if len(raw)>2_000_000:raise ValueError('RSS too large')
 return raw

def text(node,path,ns=None):
 one=node.find(path,ns or {});return ''.join(one.itertext()).strip() if one is not None else ''

def parse(raw,name,kind,start,end):
 root=ET.fromstring(raw);rows=[]
 if root.tag.split('}')[-1] not in ('rss','feed','RDF'):raise ValueError('not an RSS/Atom feed')
 atom={'a':'http://www.w3.org/2005/Atom'}
 items=root.findall('.//item') if root.tag.split('}')[-1]!='feed' else root.findall('a:entry',atom)
 for item in items[:100]:
  is_atom=item.tag.endswith('entry')
  title=text(item,'a:title',atom) if is_atom else text(item,'title')
  title=html.unescape(re.sub('<[^>]*>',' ',title));title=' '.join(title.split())
  if not PATTERN.search(title):continue
  if is_atom:
   link=item.find('a:link',atom);url=link.get('href','') if link is not None else ''
   value=text(item,'a:published',atom) or text(item,'a:updated',atom)
   try:published=datetime.fromisoformat(value.replace('Z','+00:00'))
   except ValueError:continue
  else:
   url=text(item,'link');value=text(item,'pubDate')
   try:published=parsedate_to_datetime(value)
   except (ValueError,TypeError):continue
  if published.tzinfo is None or not safe_url(url):continue
  published=published.astimezone(KST)
  if not start<=published<=end:continue
  publisher=text(item,'source') or name
  actors=[key for key,term in (('tuteja','tuteja'),('hartnett','hartnett'),('pimco','pimco')) if term in title.lower()]
  ident=hashlib.sha256(url.encode()).hexdigest()[:16]
  rows.append({'id':'D'+ident,'event_key':'headline:'+hashlib.sha256(title.lower().encode()).hexdigest()[:24],
   'publisher':publisher,'title_ko':title[:450],'summary_ko':'공개 RSS에서 제목·게시시각을 확인한 후보입니다. 원문 검증 전에는 발언 내용이나 실제 포지션으로 확정하지 않습니다.',
   'url':url,'published_at_kst':published.isoformat(),'published_date':published.date().isoformat(),'event_date':None,
   'actors':actors,'source_kind':'community' if kind=='community' else 'candidate','access':'headline_only','claim_type':'unverified',
   'direction':'unknown','mechanisms':[]})
 return rows

def collect(now=None,fetcher=fetch):
 now=(now or datetime.now(KST)).astimezone(KST);start=now-timedelta(hours=24)
 def work(source):
  name,url,kind=source
  try:
   rows=parse(fetcher(url),name,kind,start,now)
   return rows,{'name':name,'status':'checked','items':len(rows),'note':'RSS 후보만 확인 · 원문/GPT 분석과 구분','url':url}
  except Exception as exc:return [],{'name':name,'status':'failed','items':0,'note':type(exc).__name__,'url':url}
 entries={};coverage=[]
 with ThreadPoolExecutor(max_workers=3) as pool:
  for rows,state in pool.map(work,SOURCES):
   coverage.append(state)
   for row in rows:entries.setdefault(row['url'],row)
 obj={'schema':SCHEMA,'date_kst':now.date().isoformat(),'window_start_kst':start.isoformat(),'window_end_kst':now.isoformat(),
  'generated_at_kst':now.isoformat(),'producer':'rss_discovery','complete':any(x['status']=='checked' for x in coverage),'entries':list(entries.values())[:500],
  'core_targets':[{**t,'summary_ko':'원문 검증 일보 대기','change':'미확인','evidence_ids':[]} for t in TARGETS],
  'assessments':empty_assessments(),'coverage':coverage,
  'coverage_note':'자동 공개 RSS 후보 수집입니다. 제목만으로 실제 헤지펀드 포지션이나 매수·매도 압력을 판단하지 않습니다.'}
 return validate(seal(obj),now)

def save(obj,root):
 root=Path(root);reports=root/'reports';reports.mkdir(parents=True,exist_ok=True)
 raw=json.dumps(obj,ensure_ascii=False,indent=2)+'\n';md=markdown(obj)
 for path,value in ((reports/(obj['date_kst']+'.json'),raw),(reports/(obj['date_kst']+'.md'),md),(root/'latest.md',md),(root/'latest.json',raw)):
  tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(value,encoding='utf-8');tmp.replace(path)

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--output-root',default='global-position/discovery');args=parser.parse_args()
 result=collect();save(result,args.output_root)
 print(json.dumps({'date':result['date_kst'],'candidates':len(result['entries']),'checked':sum(r['status']=='checked' for r in result['coverage']),'failed':sum(r['status']=='failed' for r in result['coverage'])}))
