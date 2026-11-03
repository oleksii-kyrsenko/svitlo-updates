export const GROUPS={
 asd:['lviv'],
 a:['cherkasy','mykolaiv','chernivtsi','zhytomyr','sumy'],
 b:['vinnytsia','volyn','prykarpattia','ternopil','zakarpattia','kirovohrad','khmelnytskyi'],
 c:['dtek-kyiv','dtek-dnipro','cek','dtek-kyiv-region','dtek-odesa','dtek-donetsk','dtek-pem','dtek-vvm'],
 remainder:['poltava','rivne','zaporizhzhia','kharkiv','kherson','chernihiv','atomservice','naftogaz-teplo','ukrzaliznytsia','luhansk','regional-networks'],
};
export function collectorCommand(operatorId,{budget=20,streetBudget=8,targetCity=null,fullCity=false,requestLimit=400}={}){
 const output=`coverage/staging/${operatorId}.json`,group=Object.keys(GROUPS).find(k=>GROUPS[k].includes(operatorId));
 if(!group)throw Error('unknown_collector_operator');
 const scripts={asd:'collect-asd.py',a:'batch-a.py',b:'collect-batch-b.py',c:'collect-batch-c.py',remainder:'collect-remainder.py'};
 const script=targetCity&&operatorId==='cherkasy'?'collect-cherkasy-documents.py':targetCity&&['ternopil','zhytomyr','sumy'].includes(operatorId)?'collect-official-bulk.py':targetCity&&['kirovohrad','volyn'].includes(operatorId)?'collect-city-forms.py':scripts[group];
 const args=[`coverage/${script}`,'--output',output];
 if(group==='asd')args.push('--street-limit',String(streetBudget),'--state','coverage/crawl-state.json');
 else{
  args.push('--operator',operatorId,'--state',`coverage/cursors/${operatorId}.json`);
  if(group==='b')args.push('--street-limit',String(streetBudget),'--city-limit','1');
  else if(script!=='collect-cherkasy-documents.py')args.push('--budget',String(group==='a'?Math.max(80,budget*4):budget));
 }
 const targeted=targetCity&&group!=='remainder';
 if(targeted){
  if(typeof targetCity!=='string'||!targetCity.trim()||targetCity.length>250||!Number.isInteger(requestLimit)||requestLimit<1||requestLimit>2000)throw Error('invalid_city_request');
  args.push('--target-city',targetCity,'--request-limit',String(requestLimit));if(fullCity)args.push('--full-city');
 }
 return {operatorId,output,args,group,targetCity:targeted?targetCity:null,fullCity:Boolean(targeted&&fullCity)};
}
// Cities are sourced metadata, not a list of addresses/queues. Other regions
// remain monitored and their existing collectors continue to run.
export function collectionPlan(operators,cities,selected,options={}){
 const ids=selected||operators.map(o=>o.id),commands=ids.map(id=>{
  const operator=operators.find(o=>o.id===id);if(!operator)throw Error('unknown_requested_operator');
  const targets=options.capitalPriority===false?[]:cities.filter(c=>operator.regionIds.includes(c.regionId));
  // Ambiguous multi-city regions must receive explicit scheduled tasks rather
  // than silently picking one locality. The current capital directory has one.
  const target=targets.length===1?targets[0]:null;
  return collectorCommand(id,{...options,...(target?{targetCity:target.settlement,fullCity:true}:{})});
 });
 return commands.sort((a,b)=>Number(Boolean(b.targetCity))-Number(Boolean(a.targetCity)));
}
