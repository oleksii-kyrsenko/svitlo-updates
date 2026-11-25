"""UI evidence bindings for real Android dump shapes, with no app imports."""
import re,xml.etree.ElementTree as E

def load_helpers(path):
 # The historical helper may also carry a top-level scenario after this marker.
 # Its actions must never run merely to acquire adb/XML helper functions.
 source=path.read_text().split('\nflags={}')[0]
 namespace={'__name__':'native_helpers'};exec(compile(source,str(path),'exec'),namespace);return namespace

def bounds(node):
 m=re.fullmatch(r'\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]',node.get('bounds',''))
 value=tuple(map(int,m.groups())) if m else None
 return value if value and value[2]>value[0] and value[3]>value[1] else None

def contains(outer,inner):return bool(outer and inner and outer[0]<=inner[0]<inner[2]<=outer[2] and outer[1]<=inner[1]<inner[3]<=outer[3])
def graph_context(xml):
 root=E.fromstring(xml);parents={child:parent for parent in root.iter() for child in parent}
 def visible(node):
  return not any(n.get('displayed')=='false' or n.get('visible-to-user')=='false' for n in [node,*ancestors(node)])
 def ancestors(node):
  result=[]
  while node in parents:node=parents[node];result.append(node)
  return result
 graphs=[n for n in root.iter() if n.get('resource-id','').split('/')[-1]=='schedule-graph']
 scrolls=[n for n in root.iter() if n.get('resource-id','').split('/')[-1]=='main-scroll']
 if len(graphs)!=1 or len(scrolls)!=1:return None
 graph,scroll=graphs[0],scrolls[0];graph_box,viewport=bounds(graph),bounds(scroll)
 if not graph_box or not viewport or scroll not in ancestors(graph) or not visible(graph):return None
 # Some Android trees flatten the testID View to an empty marker alongside its
 # text siblings. In that case keep the same real parent AND graph rectangle.
 group=graph if len(graph) else parents.get(graph)
 if group is None:return None
 nodes=[n for n in group.iter() if visible(n) and contains(graph_box,bounds(n)) and contains(viewport,bounds(n))]
 return graph,graph_box,viewport,nodes

def graph_evidence(xml,interval=None):
 context=graph_context(xml)
 if context is None:return None
 graph,graph_box,viewport,nodes=context
 labels=[n.get('text') for n in nodes if n.get('text')]
 if interval is None:
  return {'binding':'visible-graph-heading','text':'Графік на добу','graphBounds':graph_box,'viewport':viewport} if 'Графік на добу' in labels else None
 start,end=interval;clock=lambda x:f'{x//60:02d}:{x%60:02d}'
 pattern=re.compile(r'(?<!\d)'+clock(start)+r'\s*[–—-]\s*'+clock(end)+r'(?!\d)')
 # Require both endpoints in one actually visible graph range label. A system
 # clock or a source-card timestamp cannot satisfy the assertion.
 matching=[n for n in nodes if n.get('text') and pattern.search(n.get('text'))]
 if not matching:return None
 return {'binding':'contained-graph-range-text' if not len(graph) else 'descendant-graph-range-text','interval':[start,end],'texts':[n.get('text') for n in matching],'textBounds':[bounds(n) for n in matching],'graphBounds':graph_box,'viewport':viewport}

def graph_failure_evidence(xml):
 if 'android:id/alertTitle' in xml or 'app-message-dialog' in xml:return None
 context=graph_context(xml)
 if context is None:return None
 graph,graph_box,viewport,nodes=context
 states=[n for n in nodes if n.get('resource-id','').split('/')[-1]=='schedule-state']
 if len(states)!=1:return None
 state_box=bounds(states[0]);labels={n.get('text') for n in nodes if contains(state_box,bounds(n))}
 required={'Не вдалося отримати графік','Спробуйте оновити. Збережену адресу повторно вводити не потрібно.'}
 if not required<=labels or 'Графік на добу' not in {n.get('text') for n in nodes}:return None
 return {'binding':'visible-graph-failure-title-and-detail','texts':sorted(required),'stateBounds':state_box,'graphBounds':graph_box,'viewport':viewport}
