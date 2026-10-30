export const ORIGINS = ['a', 'b', 'other', 'invalid', 'abstention'];
export const DESTINATIONS = ['a', 'b', 'invalid', 'abstention'];
export const LABELS = {a:'Lula', b:'Flávio Bolsonaro', other:'Other candidates', invalid:'Blank / null', abstention:'Abstention'};

export function graphFromMatrix(matrix) {
  if(!Array.isArray(matrix)||matrix.length!==5||matrix.some(r=>!Array.isArray(r)||r.length!==4)) throw Error('Expected a 5 × 4 flow matrix');
  if(matrix.some(r=>r.some(v=>!Number.isFinite(v)||v<0))) throw Error('Flow values must be finite and nonnegative');
  const sources=ORIGINS.map((key,i)=>({key,index:i,value:matrix[i].reduce((a,b)=>a+b,0)}));
  const targets=DESTINATIONS.map((key,j)=>({key,index:j,value:matrix.reduce((s,r)=>s+r[j],0)}));
  const links=[];
  sources.forEach((source,i)=>targets.forEach((target,j)=>{
    if(matrix[i][j]>0) links.push({id:`${i}-${j}`,i,j,source:source.key,target:target.key,value:matrix[i][j],retained:source.key===target.key});
  }));
  return {sources,targets,links,total:sources.reduce((s,n)=>s+n.value,0)};
}

export function sankeyLayout(matrix,{width=1100,height=640,padding=40,gap=24}={}) {
  const graph=graphFromMatrix(matrix);
  const unit=(height-2*padding-4*gap)/Math.max(1,graph.total),nodeWidth=17;
  const positions=(nodes,x)=>{
    const used=nodes.reduce((s,n)=>s+n.value*unit,0)+(nodes.length-1)*gap;
    let y=(height-used)/2;
    return nodes.map(n=>{const p={...n,x,y,width:nodeWidth,height:n.value*unit};y+=p.height+gap;return p;});
  };
  const sources=positions(graph.sources,230),targets=positions(graph.targets,width-230-nodeWidth);
  const outgoing=Array(5).fill(0),incoming=Array(4).fill(0);
  const links=graph.links.map(link=>{
    const source=sources[link.i],target=targets[link.j];
    const thickness=link.value*unit;
    const p={...link,x0:source.x+nodeWidth,x1:target.x,y0:source.y+outgoing[link.i],y1:target.y+incoming[link.j],thickness};
    outgoing[link.i]+=thickness;incoming[link.j]+=thickness;
    return p;
  });
  return {...graph,sources,targets,links,unit,width,height};
}

export function ribbonPath(link) {
  const {x0,x1,y0,y1,thickness:t}=link,m=(x0+x1)/2;
  return `M${x0},${y0}C${m},${y0} ${m},${y1} ${x1},${y1}L${x1},${y1+t}C${m},${y1+t} ${m},${y0+t} ${x0},${y0+t}Z`;
}

export function schematicLayout(matrix,{width=1100,height=640}={}) {
  const graph=graphFromMatrix(matrix),boxWidth=200,boxHeight=68;
  const leftY=[28,148,268,388,508],rightY=[28,148,388,508];
  const sources=graph.sources.map((n,i)=>({...n,x:28,y:leftY[i],width:boxWidth,height:boxHeight}));
  const targets=graph.targets.map((n,i)=>({...n,x:width-28-boxWidth,y:rightY[i],width:boxWidth,height:boxHeight}));
  const links=graph.links.map(link=>{
    const s=sources[link.i],t=targets[link.j];
    const y0=s.y+s.height/2+(link.j-1.5)*8,y1=t.y+t.height/2+(link.i-2)*7;
    return {...link,x0:s.x+s.width,x1:t.x,y0,y1,thickness:2.5};
  });
  return {...graph,sources,targets,links,width,height};
}

export function linePath(link) {
  const m=(link.x0+link.x1)/2;
  return `M${link.x0},${link.y0}C${m},${link.y0} ${m},${link.y1} ${link.x1},${link.y1}`;
}

export function curvePoint(link,t) {
  const m=(link.x0+link.x1)/2,u=1-t;
  return {x:u*u*u*link.x0+3*u*u*t*m+3*u*t*t*m+t*t*t*link.x1,
          y:u*u*u*link.y0+3*u*u*t*link.y0+3*u*t*t*link.y1+t*t*t*link.y1};
}

export function gainBreakdown(matrix) {
  const graph=graphFromMatrix(matrix);
  return ['a','b'].map((key,i)=>{
    const other=i===0?1:0;
    const parts=[{key:'other',label:'Other candidates',value:matrix[2][i]},
      {key:'invalid',label:'Previous blank / null',value:matrix[3][i]},
      {key:'abstention',label:'Previous abstainers',value:matrix[4][i]},
      {key:'switch',label:'Net finalist switching',value:matrix[other][i]-matrix[i][other]},
      {key:'loss',label:'Lost to blank / null or abstention',value:-matrix[i][2]-matrix[i][3]}];
    return {key,parts,gain:graph.targets[i].value-graph.sources[i].value};
  });
}
