/* Spirit Pressure fight engine (port of tools/fightsim.py). Rough guide, not a rules engine. */
function mulberry(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
function mk(o){return Object.assign({buffs:[],once:new Set(),resist:0,dis:0,ac_bonus:0,ac_all:0,dealt:0,timer:3,dead:false,dupl:0,wall:0,stunned:false,shrunk:0,marked:0,persona:"brute",abil:[],tmp_done:false,bond_save:false},o)}
function cloneHero(s){const h=mk(JSON.parse(JSON.stringify(s)));h.maxhp=h.hp;h.once=new Set();h.buffs=[];return h}
function enemies(E,k,rng,persona){
  const mkE=(hp,ac,atks,name)=>{const e=mk({hp:Math.floor(hp),maxhp:Math.floor(hp),ac:ac,atks:atks,name:name});e.persona=persona&&persona!=="mixed"?persona:["brute","focus","assassin","hunter","bully"][Math.floor(rng()*5)];return e};
  const f=0.8+0.2*k, n=E.n;
  const boss=mkE(E.hp*k,E.ac,Array(n).fill([E.th,E.dm*f]),"Boss");
  const m=[0,1].map(i=>mkE(E.hp*k*0.3,E.ac-2,[[E.th-2,E.dm*0.55*f]],"Minion "+(i+1)));
  return [m[0],m[1],boss]}
function pickTarget(e,party,rng){
  const up=party.filter(p=>p.hp>0); if(!up.length) return null;
  const ps=e.persona, by=(f,dir)=>up.reduce((a,b)=>dir*f(b)<dir*f(a)?b:a);
  if(ps==="focus") return by(p=>p.hp/p.maxhp,1);
  if(ps==="assassin") return by(p=>p.ac+p.ac_bonus*1+p.maxhp/1e4,1);
  if(ps==="hunter") return by(p=>p.dealt+rng()*1e-3,-1);
  if(ps==="bully") return by(p=>p.hp,-1);
  return up[Math.floor(rng()*up.length)]}
function d20(rng,adv){const a=1+Math.floor(rng()*20),b=1+Math.floor(rng()*20);return adv>0?Math.max(a,b):adv<0?Math.min(a,b):a}
function reserve(h){const c=h.abil.filter(a=>a.kind==="act"&&a.heal!==undefined).map(a=>a.cost);return c.length?Math.min(...c):0}
function sum(h,k){return h.buffs.reduce((s,b)=>s+(b[k]||0),0)}
function fight(party,foes,rng,log,maxr){
  maxr=maxr||12; const hero=party[0], stat={dmg:0,heal:0,saved:0}; const L=(t)=>{if(log)log.push(t)};
  party.forEach(h=>h.maxrp=h.rp);
  for(let rnd=1;rnd<=maxr;rnd++){
    if(!foes.some(e=>e.hp>0)) return {win:true,rounds:rnd,stat};
    if(!party.some(p=>p.hp>0)) return {win:false,rounds:rnd,stat};
    L("— Round "+rnd+" —");
    party.forEach((h,idx)=>{
      let af=foes.filter(e=>e.hp>0); if(!af.length||h.hp<=0) return;
      if(idx>0){ let tgt=af[0];
        for(const [t,dm] of h.atks){ if(tgt.hp<=0){const r=foes.filter(e=>e.hp>0); if(!r.length)break; tgt=r[0]}
          const roll=d20(rng,tgt.marked?1:0); if(roll===20||(roll!==1&&roll+t>=tgt.ac)){const x=dm*(roll===20?2:1);tgt.hp-=x;h.dealt+=x}}
        const bs=af[af.length-1]; if(bs.marked) bs.marked=0; return}
      // hero
      for(const a of h.abil){ if(a.kind!=="buff")continue; if(h.once.has(a.i))continue;
        if(a.cost<=h.rp){ if(a.once&&rnd<2)continue; h.rp-=a.cost;h.once.add(a.i);h.buffs.push(a); if(a.cost>0||a.once)L((idx===0?"Hero":"")+" powers up (−"+a.cost+" RP)") } }
      const xd=sum(h,"xd"),xdf=sum(h,"xdfirst"),xhit=sum(h,"xhit"),crit=sum(h,"crit"),xatk=sum(h,"atk");
      const adv=h.buffs.some(b=>b.advfirst||b.adv)?1:0, tmp=sum(h,"tmp");
      h.resist=Math.min(.8,sum(h,"resist")); h.dis=Math.min(.6,sum(h,"dis")); h.ac_bonus=sum(h,"ac"); h.ac_all=sum(h,"ac_all");
      if(!h.tmp_done){h.hp+=tmp;h.maxhp+=tmp;h.tmp_done=true}
      h.hp=Math.min(h.maxhp,h.hp+sum(h,"heal_r"));
      const ha=sum(h,"heal_all"); if(ha) party.forEach(p=>{if(p.hp>0)p.hp=Math.min(p.maxhp,p.hp+ha)});
      const aura=sum(h,"aura"); if(aura) af.forEach(e=>{e.hp-=aura*.7;h.dealt+=aura*.7;stat.dmg+=aura*.7});
      const ca=sum(h,"ctrl_aura"); if(ca) af.forEach(e=>{if(rng()<ca)e.stunned=true});
      const hurt=party.filter(p=>p.hp<.5*p.maxhp);
      for(const a of h.abil.filter(a=>a.kind==="act").sort((x,y)=>((y.heal!==undefined||y.revive)?1:0)-((x.heal!==undefined||x.revive)?1:0))){
        if(a.cost>h.rp)continue; if(a.once&&h.once.has(a.i))continue;
        if(a.heal!==undefined){ if(!hurt.length)continue; const t=hurt.reduce((x,y)=>y.hp/y.maxhp<x.hp/x.maxhp?y:x);
          const amt=a.heal*(h.buffs.some(b=>b.heal_mult)?2:1); if(t.hp<=0){t.hp=0;t.timer=3}
          t.hp=Math.min(t.maxhp,t.hp+amt); stat.heal+=amt; h.rp-=a.cost; L("Hero heals "+(t===hero?"self":"an ally")+" for "+Math.round(amt)+(t.hp<=amt?" (back on their feet)":"")); break}
        if(a.revive){ const d=party.filter(p=>p.dead); if(!d.length)continue; const p=d[0];p.dead=false;p.hp=1;p.timer=3;h.once.add(a.i);h.rp-=a.cost;L("Hero revives a fallen ally");break}
        if(a.aoe!==undefined){ const m=(a.name==="cero"&&h.buffs.some(b=>b.ceromult))?1.4:1; if(a.once)h.once.add(a.i);
          af.slice(0,a.targets||3).forEach(e=>{const x=a.aoe*.7*m;e.hp-=x;h.dealt+=x;stat.dmg+=x}); h.rp-=a.cost; L("Hero unleashes an area technique ("+a.name+")"); break}
        if(a.shrink!==undefined){ const b=af[af.length-1]; if(rng()<a.shrink&&!b.shrunk){b.stunned=true;b.shrunk=2;L("Boss is shrunk into a doll!")} h.rp-=a.cost;break}
        if(a.ctrl!==undefined){ const b=af[af.length-1]; if(rng()<a.ctrl){b.stunned=true;L("Boss is bound")} h.rp-=a.cost;break}
        if(a.dupl){h.dupl=3;h.rp-=a.cost;L("Hero creates 3 duplicates");break}
        if(a.wall){h.wall=a.wall;h.rp-=a.cost;L("Hero raises a barrier ("+a.wall+" HP)");break}
        if(a.advnext){af[af.length-1].marked=1;h.rp-=a.cost;L("Hero marks the boss (next attack has advantage)");break}
        if(a.dmg!==undefined){af[0].hp-=a.dmg;h.dealt+=a.dmg;stat.dmg+=a.dmg;h.rp-=a.cost;break}
      }
      const n=h.atks.length+xatk; let tgt=af[0], first=true; const bh=h.atks[0][0]+xhit; let bd=h.atks[0][1]; if(h.buffs.some(b=>b.bigdie))bd*=1.4;
      for(let i=0;i<n;i++){ if(tgt.hp<=0){const r=foes.filter(e=>e.hp>0);if(!r.length)break;tgt=r[0]}
        let extra=xd+(first?xdf:0);
        if(h.conc&&h.rp>=h.conc&&i===0){const sp=Math.min(h.conc,Math.floor(h.rp*.4));extra+=3.5*sp;h.rp-=sp}
        let a_=first?adv:0; if(tgt.marked)a_=1; const roll=d20(rng,a_), cr=roll>=20-Math.floor(crit*20);
        if(cr||(roll!==1&&roll+bh>=tgt.ac)){const x=(bd+extra)*(cr?1.8:1);tgt.hp-=x;h.dealt+=x;stat.dmg+=x; if(h.cls==="qu")h.rp=Math.min(h.rpmax,h.rp+1)}
        first=false}
      const bs=af[af.length-1]; if(bs&&bs.marked)bs.marked=0;
    });
    // enemies
    foes.filter(e=>e.hp>0).forEach(e=>{
      if(e.stunned){e.stunned=false; if(e.shrunk){e.shrunk--; if(e.shrunk>0)e.stunned=true} return}
      for(const [t_,dm_] of e.atks){ const tgt=pickTarget(e,party,rng); if(!tgt)break;
        if(tgt.dupl>0&&rng()<.6){tgt.dupl--;continue}
        const ac=tgt.ac+tgt.ac_bonus+((tgt!==hero&&hero.hp>0)?hero.ac_all:0);
        const adv=(tgt===hero&&rng()<hero.dis)?-1:0; const roll=d20(rng,adv);
        let hit=roll===20||(roll!==1&&roll+t_>=ac);
        if(hit&&roll!==20&&hero.hp>0){
          for(const a of hero.abil){ if(a.kind==="react"&&a.ac_party!==undefined&&hero.rp-a.cost>=reserve(hero)&&roll+t_<ac+a.ac_party){hero.rp-=a.cost;hit=false;stat.saved+=dm_;L("Hero's ward turns a hit into a miss");break}}
          if(hit) for(const a of hero.abil){ if(a.kind==="react"&&a.replay&&tgt!==hero&&hero.rp-a.cost>=reserve(hero)){hero.rp-=a.cost;const r2=d20(rng,-1);hit=r2===20||(r2!==1&&r2+t_>=ac);if(!hit){stat.saved+=dm_;L("Hero forces a re-roll: miss")}break}}}
        if(!hit)continue;
        let dm=dm_;
        if(tgt===hero){dm*=(1-hero.resist); const sr=hero.abil.find(a=>a.selfred); if(sr&&hero.rp>=2){hero.rp-=2;dm=Math.max(0,dm-sr.selfred)}}
        if(tgt!==hero&&hero.wall>0&&rng()<.5){const ab=Math.min(dm,hero.wall);hero.wall-=ab;dm-=ab;stat.saved+=ab}
        if(tgt.hp>0&&tgt.hp-dm<=0&&tgt===hero&&!hero.bond_save&&hero.cls==="fb"){hero.bond_save=true;tgt.hp=1;continue}
        tgt.hp-=dm; const th=hero.buffs.reduce((s,b)=>s+(b.thorns||0)+(b.retaliate||0),0); if(th&&tgt===hero)e.hp-=th*.8;
        if(tgt.hp<=0){tgt.timer=3;L((tgt===hero?"Hero":"A party member")+" is knocked down by the "+e.name)}
      }});
    party.forEach(p=>{if(p.hp<=0&&!p.dead){p.timer--;if(p.timer<=0){p.dead=true;p.hp=-999}}});
  }
  return {win:!foes.some(e=>e.hp>0),rounds:maxr,stat}}
function simulate(spec,lvl,k,n,seed,persona){
  const rng=mulberry(seed||1); const D=SIMDATA; let w=0,r=0,dm=0,hl=0,sv=0;
  for(let i=0;i<n;i++){
    const party=[cloneHero(spec)]; for(let j=0;j<3;j++)party.push(cloneHero(D.base[lvl]));
    const res=fight(party,enemies(D.enemy[lvl],k,rng,persona),rng);
    w+=res.win?1:0;r+=res.rounds;dm+=res.stat.dmg;hl+=res.stat.heal;sv+=res.stat.saved}
  return {win:w/n,rounds:r/n,dmg:dm/n,heal:hl/n,saved:sv/n}}
