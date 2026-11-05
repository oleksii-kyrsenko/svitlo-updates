"""One ordinary HTTPS read of the already reviewed public operator parent.

This probe never signs or publishes; different standard free runners can establish
which ordinary hosted transport can actually read the current official page.
"""
import argparse,importlib.util,json,os,platform,time
from pathlib import Path

spec=importlib.util.spec_from_file_location('capture',Path(__file__).with_name('browser-zap-app.py'))
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);args=p.parse_args();out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
 request=json.loads(Path('coverage/zap-app-request.json').read_text());report={'sourceUrl':capture.INDEX,'method':'One bounded ordinary strict HTTPS GET; no browser challenge/account/EIC/address input, no signing or publication.','hostedRunner':os.environ.get('RUNNER_OS',platform.system()),'architecture':platform.machine(),'checkedAt':int(time.time()*1000),'authorityVerified':False}
 try:
  response=capture.ordinary_parent();raw=response.body();report.update(httpStatus=response.status,responseUrl=response.url,checkedAt=response.checkedAt,sha256=capture.sha(raw),bytes=len(raw))
  (out/'official-parent-original.html').write_bytes(raw)
  if response.status!=200:raise ValueError('official_parent_not_available')
  report['activeReviewedCityLink']=capture.app_link(raw.decode('utf8'),request['reviewedPublicAppUrl']);report['authorityVerified']=True;report['expiresAt']=response.checkedAt+86400000
 except Exception as error:
  report.update(error=type(error).__name__,reason=str(error)[:250])
 (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False))
 # An unavailable route is retained as evidence; it does not create authority.

if __name__=='__main__':main()
