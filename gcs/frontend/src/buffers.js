// Display geometry only. Backend validation remains authoritative.
const METRES = 111319.49079327357;
export function local(p, ref) {
    return [(p.longitude-ref.longitude)*METRES*Math.cos((p.latitude+ref.latitude)*Math.PI/360), (p.latitude-ref.latitude)*METRES];
}
export function gps([x,y], ref) {
    const latitude=ref.latitude+y/METRES;
    return [latitude,ref.longitude+x/(METRES*Math.cos((latitude+ref.latitude)*Math.PI/360))];
}
const cross=(a,b,c)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
export function expandedFootprint(points, buffer, ref) {
    // Convex physical footprints: hull of circumscribed vertex circles.
    const radius=buffer/Math.cos(Math.PI/32);
    const samples=points.flatMap(p=>{const [x,y]=local(p,ref);return Array.from({length:32},(_,i)=>[x+radius*Math.cos(i*Math.PI/16),y+radius*Math.sin(i*Math.PI/16)]);}).sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
    const half=list=>{const h=[];for(const p of list){while(h.length>1&&cross(h.at(-2),h.at(-1),p)<=0)h.pop();h.push(p);}return h.slice(0,-1);};
    return [...half(samples),...half([...samples].reverse())].map(p=>gps(p,ref));
}
export function insetBoundary(points, buffer, ref) {
    const poly=points.map(p=>local(p,ref));
    if(poly.length<3)return null;
    const area=poly.reduce((sum,p,i)=>sum+p[0]*poly[(i+1)%poly.length][1]-p[1]*poly[(i+1)%poly.length][0],0);
    const sign=Math.sign(area);
    if(!sign||poly.some((p,i)=>sign*cross(p,poly[(i+1)%poly.length],poly[(i+2)%poly.length]) < -1e-7))return null;
    let result=poly;
    for(let i=0;i<poly.length;i++){
        const a=poly[i],b=poly[(i+1)%poly.length],length=Math.hypot(b[0]-a[0],b[1]-a[1]);
        if(length<1e-7)return null;
        const distance=p=>sign*cross(a,b,p)/length-buffer;
        const clipped=[];
        for(let j=0;j<result.length;j++){
            const p=result[j],q=result[(j+1)%result.length],dp=distance(p),dq=distance(q);
            if(dp>=0)clipped.push(p);
            if((dp>=0)!==(dq>=0)){const t=dp/(dp-dq);clipped.push([p[0]+t*(q[0]-p[0]),p[1]+t*(q[1]-p[1])]);}
        }
        result=clipped;
    }
    return result.map(p=>gps(p,ref));
}
export function crossingWindow(draft, key, ref) {
    const [dx,dy]=draft.direction||[0,0],length=Math.hypot(dx,dy);
    if(!draft[key]||!length)return [];
    const [x,y]=local(draft[key],ref),r=draft[`${key}_radius_m`]??1;
    return [-1,1].map(s=>gps([x-s*dy/length*r,y+s*dx/length*r],ref));
}

// Edge capsules illustrate the exclusion band for concave as well as convex
// boundaries. Exact inset topology and segment validation belong to the backend.
export function boundaryBands(points, buffer, ref) {
    if(points.length<3||buffer<=0)return [];
    const poly=points.map(p=>local(p,ref));
    return poly.map((a,i)=>{
        const b=poly[(i+1)%poly.length],length=Math.hypot(b[0]-a[0],b[1]-a[1]);
        if(length<1e-7)return [];
        const n=[-(b[1]-a[1])/length*buffer,(b[0]-a[0])/length*buffer];
        return [[a[0]+n[0],a[1]+n[1]],[b[0]+n[0],b[1]+n[1]],[b[0]-n[0],b[1]-n[1]],[a[0]-n[0],a[1]-n[1]]].map(p=>gps(p,ref));
    }).filter(p=>p.length);
}
