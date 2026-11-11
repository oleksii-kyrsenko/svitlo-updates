"""External QA action selection. Never chooses an obscured editor delete button."""
import re,xml.etree.ElementTree as E

def box(node):
 m=re.fullmatch(r'\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]',node.get('bounds',''))
 value=tuple(map(int,m.groups())) if m else None
 return value if value and value[0]>=0 and value[1]>=0 and value[2]>value[0] and value[3]>value[1] else None

def inside(outer,inner,margin=0):return bool(outer and inner and outer[0]+margin<=inner[0]<inner[2]<=outer[2]-margin and outer[1]+margin<=inner[1]<inner[3]<=outer[3]-margin)
def identifier(node):return node.get('resource-id','').split('/')[-1]
def dialog_open(tree):return any(identifier(n)=='delete-place-dialog' for n in tree.iter())

def delete_target(tree):
 if dialog_open(tree):return None
 parents={child:parent for parent in tree.iter() for child in parent}
 candidates=[n for n in tree.iter() if identifier(n)=='delete-place' or n.get('class')=='android.widget.Button' and n.get('content-desc')=='Видалити адресу']
 if len(candidates)!=1:return None
 node=candidates[0];ancestors=[];parent=node
 while parent in parents:parent=parents[parent];ancestors.append(parent)
 if any(n.get('displayed')=='false' or n.get('visible-to-user')=='false' or n.get('enabled')=='false' for n in [node,*ancestors]):return None
 scroll=next((n for n in ancestors if n.get('scrollable')=='true'),None)
 if scroll is None:return None
 bounds,viewport=box(node),box(scroll)
 if not inside(viewport,bounds,8):return None
 footers=[box(n) for n in tree.iter() if identifier(n)=='save-place']
 if len(footers)!=1 or not footers[0] or bounds[3]>footers[0][1]-8:return None
 texts=[n for n in node.iter() if n.get('text')=='Видалити адресу']
 if texts and not all(inside(bounds,box(n)) for n in texts):return None
 return {'resourceId':node.get('resource-id'),'label':'Видалити адресу','bounds':list(bounds),'viewport':list(viewport),'saveFooter':list(footers[0])}

def activate_delete(read_xml,click,scroll,retain,settle):
 # At most2 guarded clicks. Every click gets a new tree after its screenshot;
 # a prior successfully opened dialog is always detected before any retap.
 for click_attempt in range(2):
  clicked=False
  for probe in range(8):
   xml=read_xml();tree=E.fromstring(xml)
   if dialog_open(tree):return
   selected=delete_target(tree)
   if selected is None:scroll(tree);continue
   retain('candidate',xml,selected,click_attempt,probe)
   confirmed_xml=read_xml();confirmed_tree=E.fromstring(confirmed_xml)
   if dialog_open(confirmed_tree):return
   confirmed=delete_target(confirmed_tree)
   if confirmed!=selected:continue
   retain('confirmed',confirmed_xml,confirmed,click_attempt,probe)
   # Re-read after screenshot collection; never use its stale coordinate.
   final_xml=read_xml();final_tree=E.fromstring(final_xml)
   if dialog_open(final_tree):return
   final=delete_target(final_tree)
   if final!=confirmed:continue
   retain('tap',final_xml,final,click_attempt,probe)
   x1,y1,x2,y2=final['bounds'];click((x1+x2)//2,(y1+y2)//2);clicked=True;break
  if not clicked:raise AssertionError('Delete action did not become fully visible above the save footer')
  for _ in range(4):
   if dialog_open(E.fromstring(read_xml())):return
   settle(.5)
 raise AssertionError('Delete dialog did not open after2 fresh, fully visible guarded clicks')
