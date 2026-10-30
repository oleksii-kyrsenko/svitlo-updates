"""Inspect the signed APK's actual compiled resources, not Expo config alone."""
import pathlib,subprocess,json,re,zipfile,io,os
from PIL import Image
root=pathlib.Path('candidate');meta=json.load(open(root/'meta.json'));apk=root/meta['fileName'];out=pathlib.Path('apk-diagnostics');out.mkdir(exist_ok=True)
aapt=sorted((pathlib.Path(os.environ['ANDROID_HOME'])/'build-tools').glob('*/aapt'))[-1]
def dump(*args):return subprocess.check_output([str(aapt),'dump',*args,str(apk)],text=True)
s=subprocess.check_output([str(aapt),'dump','--values','resources',str(apk)],text=True)
pattern=r'        resource (0x[0-9a-f]+) '+re.escape(meta['packageName'])+r':([^:]+):[^\n]*\n\s*\(string8\) "([^"]+)"'
rows=re.findall(pattern,s);table={}
for id,name,path in rows:table.setdefault(name,[]).append((id,path))
required=['mipmap/ic_launcher_foreground','mipmap/ic_launcher_background','mipmap/ic_launcher_monochrome','drawable/notification_icon'];flags={};metrics={}
with zipfile.ZipFile(apk) as z:
 for name in required:
  files=table[name];assert len(files)==5,(name,files);sizes=[]
  for index,(id,path) in enumerate(files):
   im=Image.open(io.BytesIO(z.read(path))).convert('RGBA');assert im.width==im.height;px=list(im.getdata());sizes.append(im.width)
   if name.endswith('background'):assert all(a==255 for r,g,b,a in px)
   else:
    assert im.getpixel((0,0))[3]<8 and max(v[3] for v in px)>248,(name,im.size,im.getpixel((0,0)),max(v[3] for v in px))
    if name.endswith('foreground'):
     cyan=sum(b>120 and g>100 and r<g*.85 and a>128 for r,g,b,a in px);gold=sum(r>170 and g>110 and b<170 and r>b+40 and a>128 for r,g,b,a in px);assert cyan>3 and gold>2
     outside=[im.getpixel((x,y))[3] for y in range(im.height) for x in range(im.width) if (x+.5-im.width/2)**2+(y+.5-im.height/2)**2>(im.width*33/108)**2];assert max(outside)<16,(name,im.width,max(outside))
    else:assert all(min(r,g,b)>248 for r,g,b,a in px if a>16),name
   (out/(name.split('/')[-1]+'-'+str(im.width)+pathlib.Path(path).suffix)).write_bytes(z.read(path))
  metrics[name+'Sizes']=sizes
 flags['fiveDensitiesColorAndMonoAndNotification']=True;flags['foregroundInside66dpSafeCircle']=True;flags['transparentWhiteSystemGlyphs']=True
 for name in ['mipmap/ic_launcher','mipmap/ic_launcher_round']:
  files=table[name];xmls=[p for id,p in files if p.endswith('.xml')];assert len(xmls)==1
  tree=subprocess.check_output([str(aapt),'dump','xmltree',str(apk),xmls[0]],text=True)
  for kind in ['background','foreground','monochrome']:
   assert 'E: '+kind in tree and '@'+table['mipmap/ic_launcher_'+kind][0][0] in tree
  (out/(name.split('/')[-1]+'.txt')).write_text(tree)
 flags['adaptiveBackgroundForegroundAndMonochromeWired']=True
manifest=subprocess.check_output([str(aapt),'dump','xmltree',str(apk),'AndroidManifest.xml'],text=True);assert 'expo.modules.notifications.default_notification_icon' in manifest and 'com.google.firebase.messaging.default_notification_icon' in manifest and 'outages' in manifest;flags['notificationMetadataAndChannelRetained']=True
result={'apkSha256':meta['sha256'],'flags':flags,'metrics':metrics,'allPassed':len(flags)==5 and all(flags.values())};(out/'icon-resources-result.json').write_text(json.dumps(result,indent=2)+'\n');print('ICON_RESOURCES_RESULT',json.dumps(result))
