"""Strict acceptance selection; source metadata is supplied only after a real build."""
import json,os

def selection(suite='all',api='all',theme='all'):
 if suite not in ['all','native','live','historical','street'] or api not in ['all','30','35','36'] or theme not in ['all','aurora','moss']:raise ValueError('Invalid acceptance suite/API/theme selection')
 apis=[30,35,36] if api=='all' else [int(api)];themes=['aurora','moss'] if theme=='all' else [theme]
 street_cases=[{'api':30,'caseId':'UA-46-capital-2'},{'api':35,'caseId':'UA-61-capital-1'},{'api':36,'caseId':'UA-21-capital-1'}]
 return {'runNative':suite in ['all','native'],'runLive':suite in ['all','live'],'runHistorical':suite in ['all','historical'],'runStreet':suite=='street',
         'nativeMatrix':{'api':apis,'theme':themes},'liveMatrix':{'api':apis},'historicalMatrix':{'api':apis},'streetMatrix':{'include':[case for case in street_cases if case['api'] in apis]}}

if __name__=='__main__':
 result=selection(os.environ.get('INPUT_SUITE') or 'all',os.environ.get('INPUT_API') or 'all',os.environ.get('INPUT_THEME') or 'all')
 with open(os.environ['GITHUB_OUTPUT'],'a') as output:
  for key,value in result.items():output.write(key+'='+json.dumps(value,separators=(',',':'))+'\n')
 print(json.dumps(result))
