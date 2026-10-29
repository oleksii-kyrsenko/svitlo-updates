"""Public Telegram pagination and dated-article discovery, with explicit limits."""
import re,html,datetime,urllib.parse,hashlib
from bs4 import BeautifulSoup
from coverage import published_at
from documents import document_links
DAY=86400000

def telegram_page(body,url,now):
 soup=BeautifulSoup(body,'html.parser');title=soup.title.get_text() if soup.title else '';messages=[]
 for wrap in soup.select('.tgme_widget_message_wrap'):
  post=wrap.select_one('[data-post]');date=wrap.select_one('time[datetime]');text=wrap.select_one('.tgme_widget_message_text')
  if not post or not date:continue
  identifier=post.get('data-post','')
  if not re.fullmatch(r'[\w]+/\d+',identifier):continue
  try:stamp=int(datetime.datetime.fromisoformat(date['datetime'].replace('Z','+00:00')).timestamp()*1000)
  except ValueError:continue
  if stamp>now:continue
  attachments=[]
  if text:
   attachments=[urllib.parse.urljoin(url,a['href']) for a in text.select('a[href]') if re.search(r'\.(pdf|xlsx)(?:\?|$)',a['href'],re.I)][:1]
  else:
   photo=wrap.select_one('.tgme_widget_message_photo')
   if photo and (m:=re.search(r"url\(['\"]?([^)'\"]+)",photo.get('style',''))):attachments=[html.unescape(m[1])]
  messages.append({'id':identifier,'text':text.get_text(' ',strip=True) if text else '', 'sourceUrl':'https://t.me/'+identifier,'publishedAt':stamp,'attachments':attachments})
 return title,messages

def read_telegram(source,fetch,now,days=180,max_pages=6,backfill_cursor=None):
 url=source['url'];messages={};pages=0;cursor=None;oldest=None;limit_reason='page_limit';errors=[]
 for _ in range(max_pages):
  current=url+('?' if '?' not in url else '&')+'before='+str(cursor) if cursor else url
  try:
   body,_,final=fetch(current);title,found=telegram_page(body,final,now)
   if source.get('expectedTitle','').casefold() not in html.unescape(title).casefold():raise ValueError('Source title changed')
  except Exception as e:errors.append({'url':current,'error':str(e)[:160]});limit_reason='fetch_error';break
  pages+=1
  if not found:limit_reason='no_public_posts';break
  for m in found:
   if now-days*DAY<=m['publishedAt']<=now:messages[m['id']]=m
  oldest=min(m['publishedAt'] for m in found)
  next_cursor=min(int(m['id'].split('/')[1]) for m in found)
  if cursor is not None and next_cursor>=cursor:limit_reason='cursor_not_advancing';break
  if oldest<now-days*DAY:limit_reason='history_window';break
  cursor=backfill_cursor if pages==1 and backfill_cursor else next_cursor
 return sorted(messages.values(),key=lambda m:m['publishedAt'],reverse=True),{'url':url,'pages':pages,'posts':len(messages),'oldestPublishedAt':oldest,'historyDaysRequested':days,'stopReason':limit_reason,'nextBackfillCursor':cursor,'errors':errors}

def read_articles(source,fetch,now,days=180,max_pages=5):
 body,_,final=fetch(source['url']);soup=BeautifulSoup(body,'html.parser');urls=[final]
 if source.get('index'):
  urls=[]
  for a in soup.find_all('a',href=True):
   url=urllib.parse.urljoin(final,a['href']);text=a.get_text(' ',strip=True)
   if urllib.parse.urlsplit(url).netloc!=urllib.parse.urlsplit(final).netloc:continue
   if re.search('відключ|електроен|черг[аиу]|знеструм',text,re.I) and not re.search('квартир|екобус|садоч',text,re.I):urls.append(url)
  urls=list(dict.fromkeys(urls))[:max_pages]
 messages=[];errors=[];read_urls=[]
 for url in urls:
  try:
   raw=body if url==final else fetch(url)[0];read_urls.append(url);p=BeautifulSoup(raw,'html.parser');published=published_at(p)
   if not published or not now-days*DAY<=published<=now:continue
   article=p.select_one('article .entry-content, article, main') or p
   for tag in article.select('script,style,nav,header,footer'):tag.decompose()
   text=article.get_text(' ',strip=True)
   messages.append({'text':text,'sourceUrl':url,'publishedAt':published,'html':raw.decode('utf-8',errors='replace') if isinstance(raw,bytes) else raw,'documentCandidates':document_links(str(article),url,source.get('documentHosts',[]))})
  except Exception as e:errors.append({'url':url,'error':str(e)[:160]})
 return messages,{'url':final,'pages':len(urls),'posts':len(messages),'stopReason':'article_limit' if source.get('index') else 'direct_article','historyDaysRequested':days,'readUrls':read_urls,'errors':errors}
