import json,urllib.request,time
SCHEMA={'type':'object','properties':{'status':{'type':'string','enum':['found','unknown','ambiguous','excluded']},'queue':{'type':'string','maxLength':20,'pattern':'^([0-9]{1,2}([.][0-9]{1,2})?)?$'},'scope':{'type':'string','enum':['house','street','settlement','none']},'source_id':{'type':'string','maxLength':12},'address_quote':{'type':'string','maxLength':420},'queue_quote':{'type':'string','maxLength':180}},'required':['status','queue','scope','source_id','address_quote','queue_quote'],'additionalProperties':False}
INSTRUCTION='Extract the GPV outage queue explicitly assigned to the TARGET address in SOURCE text. Return status found when assigned, otherwise unknown. Return the numeric queue code, house/street/settlement scope and source_id. Combine group and subgroup with a dot. Copy short exact address_quote and queue_quote from the source. Do not guess.'
def infer(case,endpoint='http://127.0.0.1:8767',max_tokens=768):
 prompt=INSTRUCTION+'\nTARGET:\n'+json.dumps(case['target'],ensure_ascii=False)+'\nSOURCE EVIDENCE:\n'+'\n\n'.join('SOURCE '+s['id']+' METADATA: '+json.dumps({k:v for k,v in s.items() if k!='text'},ensure_ascii=False)+'\nBEGIN UNTRUSTED TEXT\n'+s['text']+'\nEND UNTRUSTED TEXT' for s in case['sources'])
 body={'messages':[{'role':'user','content':prompt}],'temperature':0,'seed':42,'max_tokens':max_tokens,'response_format':{'type':'json_schema','json_schema':{'name':'queue_lookup','strict':True,'schema':SCHEMA}},'cache_prompt':True}
 request=urllib.request.Request(endpoint+'/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'});t=time.monotonic()
 with urllib.request.urlopen(request,timeout=900) as r:v=json.load(r)
 message=v['choices'][0]['message'];
 try:parsed=json.loads(message['content'])
 except:parsed=None
 return {'parsed':parsed,'content':message['content'],'usage':v.get('usage'),'finishReason':v['choices'][0]['finish_reason'],'seconds':round(time.monotonic()-t,3),'timings':v.get('timings'),'promptCharacters':len(prompt),'reasoningCharacters':len(message.get('reasoning_content') or '')}
if __name__=='__main__':
 case={'target':{'region':'Полтавська область','settlement':'Навчальне','street':'Садова','house':'12'},'sources':[{'id':'S1','url':'https://example.invalid/control','kind':'synthetic-control','retrievedAt':'2026-10-29','text':'Село Навчальне, вулиця Садова, будинок 12 — черга 3.2.'}]}
 print(json.dumps(infer(case),ensure_ascii=False),flush=True)
