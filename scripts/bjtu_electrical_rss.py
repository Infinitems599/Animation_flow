import asyncio,hashlib,html,json,re,xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime,timezone
from email.utils import format_datetime
from urllib.parse import urljoin
from playwright.async_api import async_playwright

BASE='https://job.bjtu.edu.cn'
URLS=[BASE+'/frontpage/bjtu/html/index.html',BASE+'/frontpage/bjtu/html/recruitmentinfoList.html',BASE+'/frontpage/bjtu/html/recruitmentFairList.html?type=3']
OUTPUT=Path('docs/bjtu-electrical.xml')
STATE=Path('docs/bjtu-electrical-state.json')
PROFILES=json.loads(Path('data/bjtu-company-profiles.json').read_text())
DIRECT=('国家电网','南方电网','南网','电科院','电力科学研究院','电气装备','金风科技','华为数字能源','南瑞','许继','中国西电','特变电工','中广核','中国广核','电力设计院')
TECH=('电气','电力','能源','光伏','储能','风电','输变电','配电','继电保护','牵引供电','电机','电力电子','变流','逆变','智能电网','电站')
def profile(s):
 for p in PROFILES:
  if any(a.lower() in s.lower() for a in p['aliases']):return p
 if re.search(r'(?<!中)国网',s) or '国家电网' in s:
  return dict(name='国家电网系统相关单位',background='公告名称显示为国家电网系统单位或专场活动；准确的招聘法人主体、岗位和用工方式，应以学校公告为准。',focus='电网运行、输配电、建设、规划、科研等（需逐岗位核实）',source='https://www.sgcc.com.cn/')
 if '南方电网' in s:
  return dict(name='南方电网系统相关单位',background='公告名称显示为南方电网系统单位或专场活动；具体企业、岗位和任职资格须以学校公告为准。',focus='电网运行、配电、新能源消纳、储能等（需逐岗位核实）',source='https://www.csg.cn/')
def accept(s):
 if len(s)<6 or len(s)>160 or '中国网安' in s:return False
 return bool(profile(s)) or any(t in s for t in DIRECT+TECH) or bool(re.search(r'(?<!中)国网',s))
def valid_url(link):
 # Do not publish generic navigation/list links as if they were individual jobs.
 return bool(re.match(r'^https://job\.bjtu\.edu\.cn/f/(?:recruitmentFair|recruitmentinfo|bilateralchosefair)/show\?',str(link),re.I))
def date(s):
 try:return format_datetime(datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(timezone.utc))
 except:return format_datetime(datetime.now(timezone.utc))
def record(out,title,link,origin):
 title=' '.join(str(title).split())
 link=urljoin(BASE,str(link or ''))
 if not accept(title) or not valid_url(link):return
 uid=hashlib.sha256(link.encode()).hexdigest()[:24]
 def quality(t):
  return (5 if t.startswith('【') else 0)-(10 if ' | ' in t or '人以上' in t else 0)-(4 if '...' in t else 0)
 if uid not in out or quality(title)>quality(out[uid]['title']):
  out[uid]={'title':title,'link':link,'id':uid,'origin':origin}
def traverse(x,out,origin,d=0):
 if d>12:return
 if isinstance(x,list):
  for v in x[:1000]:traverse(v,out,origin,d+1)
 elif isinstance(x,dict):
  keys=('recruitmentTitle','recruitTitle','fairTitle','jobTitle','title','recruitmentName','fairName','name','companyName','enterpriseName')
  name=next((x[k] for k in keys if isinstance(x.get(k),str) and len(x[k])>5),'')
  link=next((x[k] for k in ('detailUrl','url','link','href') if isinstance(x.get(k),str)),'')
  if name:record(out,name,link,origin)
  for v in x.values():
   if isinstance(v,(dict,list)):traverse(v,out,origin,d+1)
async def scrape():
 out={}
 async with async_playwright() as p:
  browser=await p.chromium.launch(args=['--no-sandbox'])
  for url in URLS:
   page=await browser.new_page(locale='zh-CN')
   responses=[]
   page.on('response',lambda r:responses.append(r))
   try:
    await page.goto(url,wait_until='domcontentloaded',timeout=35000)
    await page.wait_for_timeout(4500)
    links=await page.eval_on_selector_all('a[href]',"""els=>els.map(e=>({text:((e.title||'').length>(e.innerText||'').trim().length?e.title:e.innerText)||e.title,href:e.href}))""")
    for a in links:record(out,a['text'],a['href'],url)
    for r in responses:
     try:
      if r.request.resource_type in ('xhr','fetch') and 'json' in r.headers.get('content-type',''):
       b=await r.body()
       if len(b)<2000000:traverse(json.loads(b),out,url)
     except Exception:pass
   except Exception as e:print('Fetch error',url,str(e))
   finally:await page.close()
  await browser.close()
 return out
def main(items):
 old=json.loads(STATE.read_text()) if STATE.exists() else {'items':{}}
 old_by_link={v['link']:v for v in old.get('items',{}).values() if valid_url(v.get('link')) and accept(v.get('title',''))}
 saved={}
 now=datetime.now(timezone.utc).isoformat()
 for original in old_by_link.values():
  uid=hashlib.sha256(original['link'].encode()).hexdigest()[:24]
  original['id']=uid
  saved[uid]=original
 for uid,item in items.items():
  item['first_seen']=old_by_link.get(item['link'],{}).get('first_seen',now)
  saved[uid]=item
 if not items:raise RuntimeError('No valid new detail links found; refusing to publish stale or empty feed')
 saved=dict(sorted(saved.items(),key=lambda kv:kv[1]['first_seen'],reverse=True)[:250])
 STATE.write_text(json.dumps({'items':saved},ensure_ascii=False,indent=2)+'\n')
 feed='https://infinitems599.github.io/Animation_flow/bjtu-electrical.xml'
 ET.register_namespace('atom','http://www.w3.org/2005/Atom')
 rss=ET.Element('rss',version='2.0');channel=ET.SubElement(rss,'channel')
 for k,v in [('title','北交大电气就业情报'),('link',BASE),('description','电气能源相关招聘和宣讲会，附经公开资料核验的企业背景'),('language','zh-CN'),('lastBuildDate',date(now))]:
  ET.SubElement(channel,k).text=v
 ET.SubElement(channel,'{http://www.w3.org/2005/Atom}link',{'href':feed,'rel':'self','type':'application/rss+xml'})
 for item in saved.values():
  el=ET.SubElement(channel,'item')
  for k,v in [('title',item['title']),('link',item['link']),('guid',item['id']),('pubDate',date(item['first_seen']))]:
   ch=ET.SubElement(el,k);ch.text=v
   if k=='guid':ch.set('isPermaLink','false')
  p=profile(item['title'])
  desc='<p>来源：北京交通大学就业资讯网</p>'
  if p:
   desc+='<p><b>企业背景：</b>'+html.escape(p['background'])+'</p><p><b>电气方向：</b>'+html.escape(p['focus'])+'</p><p><a href="'+html.escape(p['source'],quote=True)+'">核验来源</a></p>'
  else:desc+='<p>企业背景待进一步核实。筛选结果不代表全部岗位均招电气专业。</p>'
  desc+='<p><a href="'+html.escape(item['link'],quote=True)+'">查看学校原始信息</a></p>'
  ET.SubElement(el,'description').text=desc
 OUTPUT.write_bytes(ET.tostring(rss,encoding='utf-8',xml_declaration=True))
 print('Items',len(saved),'discovered',len(items))
if __name__=='__main__':main(asyncio.run(scrape()))
