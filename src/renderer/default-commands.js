const CCodeDefaultCommandCategories=[
 {id:'documents',title:'Documents',commands:['prd','design','tech-spec','task-plan','test-plan','adr']},
 {id:'development',title:'Development',commands:['implement','debug','explain']},
 {id:'quality',title:'Quality',commands:['review','test','security-review']}
];
function CCodeDefaultCommandGroups(commands){
 const known=new Map();
 for(const category of CCodeDefaultCommandCategories)for(const name of category.commands)known.set(name,category.id);
 const grouped=new Map(CCodeDefaultCommandCategories.map(category=>[category.id,[]]));
 const custom=[];
 const name=value=>String(value??'').trim().replace(/^\/+/, '').replace(/\.md$/i,'').toLowerCase();
 for(const command of commands??[]){
  const direct=name(command?.name),file=name(String(command?.filePath??command?.path??'').split(/[\\/]/).pop());
  const categoryId=known.get(direct)??known.get(file);
  if(categoryId)grouped.get(categoryId).push(command);else custom.push(command);
 }
 return [
  ...CCodeDefaultCommandCategories.filter(category=>grouped.get(category.id).length).map(category=>({...category,items:grouped.get(category.id)})),
  ...(custom.length?[{id:'custom',title:'Custom',items:custom}]:[])
 ];
}
function CCodeMergeSlashCommands(slashCommands,commands){
 const name=value=>String(value??'').trim().replace(/^\/+/, '');
 const native=(slashCommands??[]).filter(item=>item?.source!=='custom');
 const names=new Set(native.map(item=>name(item?.name)).filter(Boolean));
 const custom=[];
 for(const command of commands??[]){
  if(!command?.enabled)continue;
  const commandName=name(command.name);
  if(!commandName||names.has(commandName))continue;
  names.add(commandName);
  custom.push({name:commandName,description:command.description,
   inputHint:command.argumentHint?`/${commandName} ${command.argumentHint}`:`/${commandName}`,source:'custom'});
 }
 return [...native,...custom];
}
function CCodeCommandCategoryList(commands,renderList){
 return $.jsxs(Q.Fragment,{children:CCodeDefaultCommandGroups(commands).map(group=>$.jsxs('section',{className:'space-y-4',children:[
  $.jsx(H7,{title:group.title,count:group.items.length}),
  renderList(group.items)
 ]},group.id))});
}
if(typeof module!=='undefined'&&module.exports)module.exports={CCodeDefaultCommandGroups,CCodeMergeSlashCommands};
