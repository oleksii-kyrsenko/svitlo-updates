export const GROUPS={
 asd:['lviv'],
 a:['cherkasy','mykolaiv','chernivtsi','zhytomyr','sumy'],
 b:['vinnytsia','volyn','prykarpattia','ternopil','zakarpattia','kirovohrad','khmelnytskyi'],
 c:['dtek-kyiv','dtek-dnipro','cek','dtek-kyiv-region','dtek-odesa','dtek-donetsk','dtek-pem','dtek-vvm'],
 remainder:['poltava','rivne','zaporizhzhia','kharkiv','kherson','chernihiv','atomservice','naftogaz-teplo','ukrzaliznytsia','luhansk','regional-networks'],
};
export function collectorCommand(operatorId,{budget=20,streetBudget=8}={}){
 const output=`coverage/staging/${operatorId}.json`,group=Object.keys(GROUPS).find(k=>GROUPS[k].includes(operatorId));
 if(!group)throw Error('unknown_collector_operator');
 const scripts={asd:'collect-asd.py',a:'batch-a.py',b:'collect-batch-b.py',c:'collect-batch-c.py',remainder:'collect-remainder.py'};
 const args=[`coverage/${scripts[group]}`,'--output',output];
 if(group==='asd')args.push('--street-limit',String(streetBudget),'--state','coverage/crawl-state.json');
 else{
  args.push('--operator',operatorId,'--state',`coverage/cursors/${operatorId}.json`);
  if(group==='b')args.push('--street-limit',String(streetBudget),'--city-limit','1');
  else args.push('--budget',String(group==='a'?Math.max(80,budget*4):budget));
 }
 return {operatorId,output,args,group};
}
