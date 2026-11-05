"""Normalize an actual operator-linked anonymous Zaporizhzhia getData capture.

Only independently scoped typed roads and literal houses can be positive. Other
house encodings never generate addresses; they can only veto literal addresses
already observed elsewhere in the same public dictionary.
"""
import argparse, hashlib, json, re, time, unicodedata
from pathlib import Path
from official_rosters import Links, literal_house

PARENT='https://www.zoe.com.ua/outage/'
APP=re.compile(r'https://script\.google\.com/macros/s/[-\w]+/exec')
TYPES=[('вулиця',r'вулиця\s+|вул\.\s*|вул\s+'),('провулок',r'провулок\s+|пров\.\s*|пров\s+'),('проспект',r'проспект\s+|просп\.\s*|пр-т\s+'),('бульвар',r'бульвар\s+|бул\.\s*'),('площа',r'площа\s+|пл\.\s*'),('набережна',r'набережна\s+|наб\.\s*'),('проїзд',r'проїзд\s+|пр-д\s+'),('шосе',r'шосе\s+'),('тупик',r'тупик\s+|туп\.\s*')]
SCOPE=re.compile(r'(?:^|[\s(,;])(?:с\.|село\b|смт\b|селище\b|м\.|місто\b|район\b|р-н\b|область\b|СТ\b|СНТ\b|садівництв\w*|квартал\b|ЖК\b|ОСББ\b|ТОВ\b|ФОП\b|гараж\w*|дач\w*|острів\b|промзон\w*|частков\w*)',re.I)

def sha(value):return hashlib.sha256(value).hexdigest()
def clean(value):return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(value))).strip()
def name_key(value):return re.sub(r'\s+',' ',re.sub(r'[’ʼ`\x27]','',re.sub(r'\([^)]*\)',' ',clean(value).casefold()))).strip()
def source_street_hash(value):
    value=unicodedata.normalize('NFKC',value).casefold();value=re.sub(r'\([^)]*\)',' ',value);value=re.sub(r'[’ʼ`\x27]','',value)
    aliases=[('street',r'вулиця\s+|вул\.\s*|вул\s+'),('lane',r'провулок\s+|пров\.\s*|пров\s+'),('avenue',r'проспект\s+|просп\.\s*|пр-т\s+'),('boulevard',r'бульвар\s+|бул\.\s*'),('square',r'площа\s+|пл\.\s*'),('embankment',r'набережна\s+|наб\.\s*')]
    for kind,pattern in aliases:
        match=re.match(r'^(?:'+pattern+r')',value,re.I)
        if match:value=kind+'|'+value[match.end():];break
    return sha(re.sub(r'\s+',' ',value).strip().encode())
def road(value):
    value=clean(value)
    if SCOPE.search(value):return None
    for kind,pattern in TYPES:
        match=re.match(r'^(?:'+pattern+r')',value,re.I)
        if match:
            name=value[match.end():].strip()
            if name and re.search(r'[А-Яа-яІіЇїЄєҐґA-Za-z]',name):return {'key':kind+'|'+name_key(name),'name':kind+' '+name,'sourceHash':source_street_hash(value)}
    return None
def hkey(value):
    value=re.sub(r'[\s№]','',unicodedata.normalize('NFKC',str(value))).casefold().translate(str.maketrans({'a':'а','c':'с','e':'е','o':'о','p':'р','x':'х'}))
    return re.sub(r'(\d)[‐‑‒–—-](?=[а-яіїєґ]$)',r'\1',value)
def queue(value):
    value=clean(value).replace(',','.') if value is not None else ''
    return value if re.fullmatch(r'[1-6]\.[12]',value) else None
def possible_house(label,house):
    # This predicate never emits a house. It only checks an existing literal
    # candidate against uncertainty (ranges, pipe lists, entrances, etc.).
    number=re.match(r'\d+',hkey(house))
    if not number:return True
    n=int(number[0]);ranges=[(int(m[1]),int(m[2])) for m in re.finditer(r'(?<!\d)(\d{1,4})[А-Яа-яІіЇїЄєҐґA-Za-z]?\s*[-–—]\s*(\d{1,4})',label)]
    if any(min(a,b)<=n<=max(a,b) for a,b in ranges):return True
    numbers={int(v) for v in re.findall(r'(?<!\d)\d{1,4}(?!\d)',label)}
    return not numbers or n in numbers

def verify_projection(p,path,now):
    if p.get('schemaVersion')!=1 or p.get('operatorId')!='zaporizhzhia' or p.get('regionId')!='UA-23' or p.get('settlement')!='Запоріжжя' or not APP.fullmatch(p.get('sourceUrl','')):raise ValueError('unexpected_city_projection')
    a=p['authority'];at=p['checkedAt'];expiry=p['expiresAt']
    if a.get('sourceUrl')!=PARENT or not 0<a['checkedAt']<=at<=now<expiry or a['expiresAt']!=a['checkedAt']+86400000 or expiry!=min(at+86400000,a['expiresAt']):raise ValueError('expired_or_renewed_authority')
    folder=Path(path).parent;original=folder/('reviewed-authority-original.html' if 'previously-reviewed' in a.get('method','') else 'official-parent-attempt.html');raw=original.read_bytes()
    if sha(raw)!=a['sha256']:raise ValueError('official_authority_original_hash_mismatch')
    links=Links();links.feed(raw.decode('utf8'));matches=[label for url,label in links.links if url==p['sourceUrl'] and re.search(r'Дізнатися\s+свою\s+чергу.*м\.\s*Запоріжжя',label,re.I)]
    if not matches or p.get('officialCityScopeLabel') not in matches:raise ValueError('explicit_operator_city_scope_missing')
    f=p['frontendSchema'];front=(folder/'official-public-frontend-functions.json').read_bytes()
    if sha(front)!=f['sha256'] or f.get('sourceUrl')!=p['sourceUrl'] or f.get('GPVcolumn')!=2 or f.get('partialExemptionsColumn')!=3 or f.get('GAVcolumnNeverSubstituted')!=4:raise ValueError('frontend_schema_original_mismatch')
    code=json.loads(front)
    for name,pattern in [('loadData',r'streetData\s*=\s*data'),('loadData',r'getData\s*\('),('loadHouses',r'row\[0\]\s*===\s*street'),('loadHouses',r'row\[1\]'),('showQueue',r'row\[0\]\s*===\s*street\s*&&\s*row\[1\]\s*===\s*house'),('showQueue',r'gpvQueue\s*=\s*row\[2\]'),('showQueue',r'zova\s*=\s*row\[3\]'),('showQueue',r'gavQueue\s*=\s*row\[4\]')]:
        if not re.search(pattern,code.get(name,'')):raise ValueError('independent_row_or_GPV_semantics_not_verified')
    return {'operatorCityScopeLabel':p['officialCityScopeLabel'],'authoritySha256':a['sha256'],'authorityCheckedAt':a['checkedAt'],'authorityExpiresAt':a['expiresAt'],'frontendSha256':f['sha256'],'rowsAreIndependent':True,'GPVcolumn':2,'ZOVAIsExclusionNotQueue':True,'GAVNeverUsed':True}

def decode(p,geo):
    groups={};unknown=[];declined=[];blocked=set();unbound=0
    for q in p.get('quarantinedRows',[]):
        if any(v.get('field') in ['street','house'] for v in q.get('fieldIssues',[])):
            if q.get('sourceStreetSha256'):blocked.add(q['sourceStreetSha256'])
            else:unbound+=1
    if unbound:raise ValueError('unbound_quarantined_address_connection')
    for item in p['rows']:
        if not isinstance(item,list) or len(item)!=4 or not isinstance(item[3],bool):raise ValueError('projection_row_shape_changed')
        label,raw_house,gpv,excluded=item;r=road(label);digest=sha(json.dumps(item,ensure_ascii=False,separators=(',',':')).encode())
        if r is None:declined.append({'rowSha256':digest,'reason':'untyped_locality_or_landmark_scope','streetLength':len(str(label)),'houseLength':len(str(raw_house))});continue
        q=queue(gpv);house=literal_house(raw_house)
        if house is None:unknown.append({'road':r,'label':str(raw_house),'queue':q,'excluded':excluded,'rowSha256':digest});continue
        key=(r['key'],hkey(house));g=groups.setdefault(key,{'street':r['name'],'house':house,'connections':[],'sourceHashes':set()});g['sourceHashes'].add(r['sourceHash']);g['connections'].append({'queue':q,'excluded':excluded,'sourceStreet':str(label),'sourceHouse':str(raw_house),'rowSha256':digest})
    by_road={}
    for u in unknown:by_road.setdefault(u['road']['key'],[]).append(u)
    records=[];observations=[];abstentions=[]
    for (road_key,house_key),g in groups.items():
        c=g['connections'];queues={v['queue'] for v in c};reason=None
        if any(v['excluded'] for v in c):reason='explicit_ZOVA_partial_exemption'
        elif None in queues:reason='unknown_GPV_connection'
        elif len(queues)!=1:reason='conflicting_GPV_connections'
        elif g['sourceHashes']&blocked:reason='quarantined_house_connection_on_this_road'
        else:
            for u in by_road.get(road_key,[]):
                if possible_house(u['label'],g['house']) and (u['excluded'] or u['queue'] is None or u['queue'] not in queues):reason='overlapping_unsupported_house_connection';break
        observation={'regionId':'UA-23','settlement':geo['settlement'],'community':geo['community'],'street':g['street'],'house':g['house'],'checkedAt':p['checkedAt'],'expiresAt':p['expiresAt']};observations.append(observation)
        if reason:abstentions.append({**observation,'reason':reason,'connections':len(c)});continue
        q=next(iter(queues));source=c[0];quote=f"Міський сервіс Запоріжжя; вулиця: {source['sourceStreet']}; будинок: {source['sourceHouse']}; ГПВ: {q}; усі опубліковані з'єднання цього точного будинку узгоджені, позначок ЗОВА немає."
        records.append({'id':sha(('zaporizhzhia|'+road_key+'|'+house_key+'|'+q).encode())[:24],'official':True,'regionId':'UA-23','settlement':geo['settlement'],'community':geo['community'],'street':g['street'],'scope':'house','houses':[g['house']],'queue':q,'sourceUrl':p['sourceUrl'],'quote':quote,'quoteType':'structured-official-fields','checkedAt':p['checkedAt'],'expiresAt':p['expiresAt']})
    report={'literalHouseIdentities':len(groups),'positiveHouseFacts':len(records),'abstentions':abstentions,'declinedRows':declined,'unsupportedHouseRows':[{'rowSha256':u['rowSha256'],'reason':'unsupported_house_encoding_only_veto_never_positive','houseLength':len(u['label'])} for u in unknown],'quarantinedRoadHashes':sorted(blocked),'unboundQuarantinedRows':unbound,'method':'Only typed city-default roads and literal houses; no positive pipe/range expansion, no GAV substitution; unknown GPV/ZOVA/overlapping uncertainty veto whole-house assignment. No whole-city completeness claim.'}
    return records,observations,report

def main():
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--projection',required=True);a.add_argument('--output',required=True);args=a.parse_args();path=Path(args.projection);raw=path.read_bytes()
    if len(raw)>10000000:raise ValueError('projection_too_large')
    p=json.loads(raw);proof=verify_projection(p,path,int(time.time()*1000));cities=json.loads(Path(__file__).with_name('capital-geography.json').read_text())['cities'];geo=next(c for c in cities if c['regionId']=='UA-23' and c['settlement']=='Запоріжжя');rows,obs,report=decode(p,geo);now=int(time.time()*1000);out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    report.update(generatedAt=now,operatorId='zaporizhzhia',originalProjectionSha256=sha(raw),scopeProof=proof,sourceCheckedAt=p['checkedAt'],sourceExpiresAt=p['expiresAt'],sourceRows=len(p['rows']),records=len(rows));Path(str(out)+'.report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    if not rows:raise SystemExit('No unambiguous literal city-house assignments')
    packet={'schemaVersion':1,'operatorId':'zaporizhzhia','generatedAt':now,'expiresAt':p['expiresAt'],'records':rows,'observedHouses':obs};out.write_text(json.dumps(packet,ensure_ascii=False,separators=(',',':'))+'\n');print(json.dumps({'records':len(rows),'observedHouses':len(obs),'abstentions':len(report['abstentions']),'declinedRows':len(report['declinedRows']),'unsupportedHouseRows':len(report['unsupportedHouseRows'])}))
if __name__=='__main__':main()
