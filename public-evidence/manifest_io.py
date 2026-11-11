"""Complete public manifests share one byte budget across all reader types."""
import json,os,pathlib,tempfile

MAX_BYTES=2_000_000
MAX_RECORDS=10_000

def serialize_manifest(value):
 if value.get('schemaVersion')!=2 or not isinstance(value.get('records'),list):raise ValueError('Unsupported public manifest')
 body=json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n'
 if len(value['records'])>MAX_RECORDS:raise ValueError('Complete public manifest record budget exceeded; previous manifest retained')
 if len(body.encode('utf-8'))>MAX_BYTES:raise ValueError('Complete public manifest byte budget exceeded; previous manifest retained')
 return body

def write_manifest(path,value):
 path=pathlib.Path(path);body=serialize_manifest(value);temporary=None
 try:
  with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,prefix=path.name+'.',suffix='.tmp',delete=False) as stream:
   temporary=pathlib.Path(stream.name);stream.write(body)
  os.replace(temporary,path)
 finally:
  if temporary is not None:temporary.unlink(missing_ok=True)
