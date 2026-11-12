import {local,gps} from './buffers.js';

export const DEFAULT_BOUNDARY_PADDING_M=10;
const cross=(a,b,c)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
const position=([latitude,longitude])=>({latitude,longitude});

export function boundaryInputs(map,start=null){
    if(!map)return [];
    const ref=map.geographic_reference;
    const objects=[...(map.buoys||[]),...(map.obstacles||[])];
    return [
        ...objects.flatMap(o=>{
            if(o.footprint?.length)return [o.centre,...o.footprint];
            if(o.type==='cylinder'&&o.radius_m>0){
                // Circumscribe the full physical circle, including between samples.
                const [x,y]=local(o.centre,ref),r=o.radius_m/Math.cos(Math.PI/16);
                return Array.from({length:16},(_,i)=>position(gps([x+r*Math.cos(i*Math.PI/8),y+r*Math.sin(i*Math.PI/8)],ref)));
            }
            return [o.centre];
        }),
        ...(map.stations||[]).map(s=>s.position),
        map.start_pose?.position,start
    ].filter(Boolean);
}

export function suggestBoundary(map,padding=DEFAULT_BOUNDARY_PADDING_M,start=null){
    if(!Number.isFinite(padding)||padding<=0)throw new Error('Extra room must be a finite number greater than zero.');
    const points=boundaryInputs(map,start).map(p=>local(p,map.geographic_reference));
    if(!points.length)return [];
    if(points.some(p=>!p.every(Number.isFinite)))throw new Error('Map positions must be finite to suggest a boundary.');
    const sorted=points.slice().sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
    const half=values=>{const h=[];for(const p of values){while(h.length>1&&cross(h.at(-2),h.at(-1),p)<=0)h.pop();h.push(p);}return h.slice(0,-1);};
    const hull=sorted.length===1?sorted:[...half(sorted),...half(sorted.slice().reverse())];
    let best=null;
    // An enclosing minimum-area rectangle has a side parallel to a hull edge.
    // Project every observation onto each candidate frame; cardinal alignment
    // and inferred task headings play no role in containment.
    for(let i=0;i<Math.max(1,hull.length);i++){
        const a=hull[i],b=hull[(i+1)%hull.length];
        const length=Math.hypot(b[0]-a[0],b[1]-a[1]);
        const u=length>1e-9?[(b[0]-a[0])/length,(b[1]-a[1])/length]:[1,0],v=[-u[1],u[0]];
        let xmin=Infinity,xmax=-Infinity,ymin=Infinity,ymax=-Infinity;
        for(const p of points){const x=p[0]*u[0]+p[1]*u[1],y=p[0]*v[0]+p[1]*v[1];xmin=Math.min(xmin,x);xmax=Math.max(xmax,x);ymin=Math.min(ymin,y);ymax=Math.max(ymax,y);}
        xmin-=padding;xmax+=padding;ymin-=padding;ymax+=padding;
        const area=(xmax-xmin)*(ymax-ymin);
        if(!best||area<best.area-1e-6)best={area,corners:[[xmin,ymin],[xmax,ymin],[xmax,ymax],[xmin,ymax]].map(([x,y])=>[x*u[0]+y*v[0],x*u[1]+y*v[1]])};
    }
    return best.corners.map(p=>position(gps(p,map.geographic_reference)));
}

export function boundaryProblem(points,ref){
    if(!points||points.length<3)return 'Add at least three boundary corners, or regenerate the suggested boundary.';
    const p=points.map(v=>local(v,ref));
    if(p.some(v=>!v.every(Number.isFinite)))return 'Boundary corners must have finite GPS positions.';
    const between=(a,b,c)=>Math.abs(cross(a,b,c))<1e-7&&c[0]>=Math.min(a[0],b[0])-1e-7&&c[0]<=Math.max(a[0],b[0])+1e-7&&c[1]>=Math.min(a[1],b[1])-1e-7&&c[1]<=Math.max(a[1],b[1])+1e-7;
    for(let i=0;i<p.length;i++){
        const a=p[i],b=p[(i+1)%p.length];
        if(Math.hypot(b[0]-a[0],b[1]-a[1])<.01)return 'Boundary corners overlap. Move or remove a corner.';
        for(let j=i+2;j<p.length;j++){
            if((j+1)%p.length===i)continue;
            const c=p[j],d=p[(j+1)%p.length];
            if((cross(a,b,c)*cross(a,b,d)<0&&cross(c,d,a)*cross(c,d,b)<0)||between(a,b,c)||between(a,b,d)||between(c,d,a)||between(c,d,b))return 'Boundary edges cross. Move the corners or regenerate the boundary.';
        }
    }
    const area=p.reduce((sum,a,i)=>sum+cross([0,0],a,p[(i+1)%p.length]),0);
    return Math.abs(area)<.01?'Boundary corners must enclose an area.':'';
}

export function outsideBoundary(points,boundary,ref){
    if(boundaryProblem(boundary,ref))return false;
    const polygon=boundary.map(p=>local(p,ref));
    return points.some(point=>{
        const p=local(point,ref);
        let inside=false;
        for(let i=0;i<polygon.length;i++){
            const a=polygon[i],b=polygon[(i+1)%polygon.length];
            const dx=b[0]-a[0],dy=b[1]-a[1],length=dx*dx+dy*dy;
            const t=Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length));
            if(Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)<1e-6)return false;
            if((a[1]>p[1])!==(b[1]>p[1])&&p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0])inside=!inside;
        }
        return !inside;
    });
}
