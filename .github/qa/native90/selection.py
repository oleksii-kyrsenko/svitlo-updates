"""Strict acceptance selection; source metadata is supplied only after a real build."""
import json,os

def selection(suite='all',api='all',theme='all'):
 if suite not in ['all','native','live','historical'] or api not in ['all','30','35','36'] or theme not in ['all','aurora','moss']:raise ValueError('Invalid acceptance suite/API/theme selection')
 apis=[30,35,36] if api=='all' else [int(api)];themes=['aurora','moss'] if theme=='all' else [theme]
 return {'runNative':suite in ['all','native'],'runLive':suite in ['all','live'],'runHistorical':suite in ['all','historical'],
         'nativeMatrix':{'api':apis,'theme':themes},'liveMatrix':{'api':apis},'historicalMatrix':{'api':apis}}

if __name__=='__main__':
 result=selection(os.environ.get('INPUT_SUITE') or 'all',os.environ.get('INPUT_API') or 'all',os.environ.get('INPUT_THEME') or 'all')
 with open(os.environ['GITHUB_OUTPUT'],'a') as output:
  for key,value in result.items():output.write(key+'='+json.dumps(value,separators=(',',':'))+'\n')
 print(json.dumps(result))
