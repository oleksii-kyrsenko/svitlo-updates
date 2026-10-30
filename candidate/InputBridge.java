package ua.svitlo.qa.input;
import android.app.Instrumentation;
import android.app.UiAutomation;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import android.accessibilityservice.AccessibilityServiceInfo;
public class InputBridge extends Instrumentation {
 private Bundle args;
 @Override public void onCreate(Bundle arguments){super.onCreate(arguments);args=arguments;start();}
 private AccessibilityNodeInfo find(AccessibilityNodeInfo node,String id){
  if(node==null)return null;String name=node.getViewIdResourceName();
  if(node.isEditable()&&name!=null&&(name.equals(id)||name.endsWith("/"+id)))return node;
  for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo found=find(node.getChild(i),id);if(found!=null)return found;}return null;
 }
 @Override public void onStart(){
  Bundle result=new Bundle();
  try {
   UiAutomation ui=getUiAutomation();AccessibilityServiceInfo info=ui.getServiceInfo();info.flags|=AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS|AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;ui.setServiceInfo(info);
   for(int attempt=0;attempt<50;attempt++){
    AccessibilityNodeInfo node=find(ui.getRootInActiveWindow(),args.getString("resource"));
    if(node==null)for(AccessibilityWindowInfo window:ui.getWindows()){node=find(window.getRoot(),args.getString("resource"));if(node!=null)break;}
    if(node!=null){Bundle text=new Bundle();text.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,args.getString("value"));if(node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,text)){result.putString("inputResult","ok");finish(-1,result);return;}}
    SystemClock.sleep(100);
   }
   result.putString("inputResult","editable target not available");finish(1,result);
  }catch(Exception e){result.putString("inputResult",e.getClass().getSimpleName());finish(1,result);}
 }
}
