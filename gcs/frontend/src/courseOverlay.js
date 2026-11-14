import {local,gps} from './buffers.js';

// Leaflet coordinates are arrays; observation coordinates are GPS objects.
// Keep conversion at this boundary so preview geometry cannot mix the two.
export function courseOverlay(map,tasks){
    const observations=Object.fromEntries([...map.buoys,...(map.obstacles||[])].map(o=>[o.id,o.centre]));
    const ref=map.geographic_reference,lines=[],labels=[];
    const ll=p=>[p.latitude,p.longitude];
    const observation=p=>({latitude:p[0],longitude:p[1]});
    const centre=(a,b)=>observation(gps(local(a,ref).map((v,i)=>(v+local(b,ref)[i])/2),ref));
    function arrow(from,to,task){
        const a=local(from,ref),b=local(to,ref),length=Math.hypot(b[0]-a[0],b[1]-a[1]);
        if(length<.001)return;
        const d=[(b[0]-a[0])/length,(b[1]-a[1])/length],mid=[(a[0]+b[0])/2,(a[1]+b[1])/2];
        const at=(f,s=0)=>gps([mid[0]+f*d[0]-s*d[1],mid[1]+f*d[1]+s*d[0]],ref);
        lines.push({task,kind:'travel',points:[ll(from),ll(to)]},{task,kind:'arrow',points:[at(-1,1),at(1),at(-1,-1)]});
    }
    for(const [task,roles] of Object.entries(tasks||{})){
        function pair(red,green,label){
            const a=observations[roles[red]],b=observations[roles[green]];
            if(!a||!b)return null;
            lines.push({task,kind:'gate',points:[ll(a),ll(b)],label});
            return centre(a,b);
        }
        const anchors=[];
        if(task==='channel'){
            for(const colour of ['red','green'])lines.push({task,kind:'chain',points:[1,2,3].map(i=>ll(observations[roles[`channel.${colour}.${i}`]]))});
            for(let i=1;i<=3;i++)anchors.push(pair(`channel.red.${i}`,`channel.green.${i}`,`Channel ${i}`));
        }else{
            if(task==='slalom'){
                for(let i=1;i<=4;i++){
                    const p=observations[roles[`slalom.turn.${i}`]];anchors.push(p);
                    labels.push({task,position:ll(p),text:String(i)});
                }
                anchors.push(pair('slalom.exit.red','slalom.exit.green','Slalom exit'));
            }else{
                anchors.push(pair('slalom.entrance.red','slalom.entrance.green','Starting gate'));
                if(!anchors[0])continue;
                const a=local(observations[roles['slalom.entrance.red']],ref),b=local(observations[roles['slalom.entrance.green']],ref),m=local(anchors[0],ref),length=Math.hypot(b[0]-a[0],b[1]-a[1]),d=[(b[1]-a[1])/length,-(b[0]-a[0])/length];
                arrow(observation(gps(m.map((v,i)=>v-3*d[i]),ref)),observation(gps(m.map((v,i)=>v+3*d[i]),ref)),task);
            }
        }
        for(let i=1;i<anchors.length;i++)if(anchors[i-1]&&anchors[i])arrow(anchors[i-1],anchors[i],task);
    }
    return {lines,labels};
}
