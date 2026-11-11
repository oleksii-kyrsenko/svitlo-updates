"""Bind dated-hint evidence to its real visible Android container, not the page."""
import re,xml.etree.ElementTree as ET

def box(node):
 m=re.fullmatch(r'\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]',node.get('bounds',''))
 value=tuple(map(int,m.groups())) if m else None
 return value if value and value[2]>value[0] and value[3]>value[1] else None

def contains(outer,inner):return bool(outer and inner and outer[0]<=inner[0]<inner[2]<=outer[2] and outer[1]<=inner[1]<inner[3]<=outer[3])
def identity(node):return node.get('resource-id','').split('/')[-1]

def visible_notice(xml,scope_id,width,height):
 root=ET.fromstring(xml);parents={child:parent for parent in root.iter() for child in parent}
 def ancestors(node):
  result=[]
  while node in parents:node=parents[node];result.append(node)
  return result
 def visible(node):return not any(n.get('displayed')=='false' or n.get('visible-to-user')=='false' for n in [node,*ancestors(node)])
 scopes=[n for n in root.iter() if identity(n)==scope_id]
 if len(scopes)!=1:return {'texts':[],'binding':'missing-or-ambiguous-historical-container'}
 scope=scopes[0];scrolls=[n for n in ancestors(scope) if identity(n)=='main-scroll']
 if len(scrolls)!=1 or not visible(scope):return {'texts':[],'binding':'historical-container-outside-main-scroll'}
 scope_box,viewport=box(scope),box(scrolls[0]);window=(0,0,width,height)
 if not scope_box or not viewport:return {'texts':[],'binding':'invalid-historical-container-bounds'}
 # Accessibility can flatten this View into an empty marker and same-parent
 # text siblings. Its exact rectangle still scopes the accepted visible text.
 group=scope if len(scope) else parents.get(scope)
 if group is None:return {'texts':[],'binding':'missing-historical-container-parent'}
 accepted=[n for n in group.iter() if n.get('text') and visible(n) and contains(scope_box,box(n)) and contains(viewport,box(n)) and contains(window,box(n))]
 return {'texts':[n.get('text') for n in accepted],
         'textBounds':[box(n) for n in accepted],
         'binding':'descendant-historical-text' if len(scope) else 'contained-historical-sibling-text',
         'scopeId':scope_id,'scopeBounds':scope_box,'viewport':viewport}
