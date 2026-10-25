const fs=require('fs'), vm=require('vm'), assert=require('assert');
const file=process.argv[2], content=fs.readFileSync(file,'utf8');
const blocks=[...content.matchAll(/<script(?:[^>]*)>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
const data=JSON.parse(blocks[1]), elements={};
class Element{
 constructor(id){this.id=id;this.value='';this.listeners={};this.options=[];this.textContent=id==='report-data'?blocks[1]:'';}
 set innerHTML(value){this._html=value;if(value.includes('<option')){this.options=[...value.matchAll(/<option(?: value="([^"]*)")?>(.*?)<\/option>/g)].map(m=>({value:m[1]??m[2]}));this.value=this.options[0]?.value||'';}}
 get innerHTML(){return this._html;}
 addEventListener(type,fn){this.listeners[type]=fn;}
}
const get=id=>elements[id]??=new Element(id);
for(const [id,value] of [['view','revised'],['quality','all']])get(id).value=value;
const charts={};const context=vm.createContext({document:{getElementById:get},Plotly:{react:(id,traces,layout)=>{charts[id]={traces,layout}}},console,URL,Blob});
vm.runInContext(blocks[2],context);
assert.equal(vm.runInContext('current.length',context),data.weekly.filter(r=>r.view==='revised').length);
assert.equal(Object.keys(charts).length,9);
assert.equal(vm.runInContext('new Set(current.map(r=>r.view)).size',context),1);
get('tenant').value=data.weekly[0].tenant_id;get('tenant').listeners.change();
assert(vm.runInContext('current.every(r=>r.tenant_id===$("tenant").value)',context));
get('vehicle').value=vm.runInContext('current[0].vehicle_id',context);get('vehicle').listeners.change();
assert(vm.runInContext('current.every(r=>r.vehicle_id===$("vehicle").value)',context));
get('view').value='initial';get('view').listeners.change();
assert(vm.runInContext('current.every(r=>r.view==="initial")',context));
get('from').value='2099-01-01';get('from').listeners.change();
assert.equal(vm.runInContext('current.length',context),0);
get('reset').onclick();
assert.equal(vm.runInContext('current.length',context),data.weekly.filter(r=>r.view==='revised').length);
assert(!content.includes('src="https://cdn.plot.ly'));
console.log(JSON.stringify({status:'passed',checks:['strict embedded JSON','default revised view','nine charts rendered','single-view isolation','tenant filter','vehicle filter','view filter','empty selection','reset','no external Plotly CDN'],weekly_rows:data.weekly.length,panels:Object.keys(charts)},null,2));
