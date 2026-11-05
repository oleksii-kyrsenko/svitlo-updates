"""Persist only an actually reread active official authority, never renew a cache."""
import argparse, importlib.util, json, sys, time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
spec=importlib.util.spec_from_file_location('decoder',Path(__file__).with_name('collect-rivne-zap-app.py'))
decoder=importlib.util.module_from_spec(spec);spec.loader.exec_module(decoder)

def cache_plan(projection, projection_path, request, now):
    decoder.verify_projection(projection,projection_path,now)
    if projection['sourceUrl']!=request['reviewedPublicAppUrl']:
        raise ValueError('unreviewed_public_app_deployment')
    authority=projection['authority']
    method=authority['method']
    if method=='previously-reviewed-official-parent-during-temporary-unavailability':
        return None
    if method!='current-live-official-parent':
        raise ValueError('unknown_authority_observation_method')
    original=Path(projection_path).parent/'official-parent-attempt.html'
    raw=original.read_bytes()
    # verify_projection has checked original hash, active city-specific link,
    # exact original clock/expiry and the independent public frontend semantics.
    return raw,{key:authority[key] for key in ['sourceUrl','checkedAt','expiresAt','sha256']}

def main():
    a=argparse.ArgumentParser();a.add_argument('--projection',required=True);a.add_argument('--request',required=True);args=a.parse_args()
    projection=json.loads(Path(args.projection).read_text());request=json.loads(Path(args.request).read_text())
    plan=cache_plan(projection,args.projection,request,int(time.time()*1000))
    if plan is None:
        print(json.dumps({'cacheUpdated':False,'reason':'Fallback authority retains its original observation and expiry.'}));return
    meta_path=Path(request['reviewedAuthorityMetadata']);previous=json.loads(meta_path.read_text());raw,meta=plan
    original=Path(previous['originalFile']);root=Path.cwd().resolve()
    if not original.resolve().is_relative_to(root) or not meta_path.resolve().is_relative_to(root):
        raise ValueError('authority_cache_path_escape')
    meta['originalFile']=previous['originalFile'];meta['review']='Fresh ordinary HTTPS read; exact previously reviewed deployment remains actively linked by the city-specific official label.'
    original.write_bytes(raw);meta_path.write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'cacheUpdated':True,'originalCheckedAt':meta['checkedAt'],'expiresAt':meta['expiresAt']}))

if __name__=='__main__':main()
