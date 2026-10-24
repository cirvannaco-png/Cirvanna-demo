import { useState, useEffect, useRef, useCallback } from "react";

const FONTS = `@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;1,300&family=DM+Mono:wght@400;500&family=Outfit:wght@300;400;500;600&display=swap');`;

const T = {
  obsidian:"#080808", surface:"#0f0f0f", card:"#141414", elevated:"#1a1a1a",
  border:"#1e1e1e", borderHov:"#2e2e2e",
  gold:"#d4af37", goldDim:"#8a7020", goldGlow:"#d4af3712",
  cream:"#f0ebe3", muted:"#666", subtle:"#333",
  green:"#22c55e", amber:"#f59e0b", red:"#ef4444", blue:"#3b82f6",
  font:{ serif:"'Cormorant Garamond',Georgia,serif", mono:"'DM Mono','Courier New',monospace", sans:"'Outfit','Helvetica Neue',sans-serif" },
};

// ─── Sample data ──────────────────────────────────────────────────────────────

const ARCHETYPES = [
  { id:"refined_minimalist",    label:"Refined Minimalist",    desc:"Clean lines, neutral palette, quiet luxury",              icon:"◻" },
  { id:"bold_expressionist",    label:"Bold Expressionist",    desc:"Prints, colour, maximum self-expression",                  icon:"◈" },
  { id:"cultural_curator",      label:"Cultural Curator",      desc:"Heritage textiles, diaspora identity, meaning over trend", icon:"◉" },
  { id:"streetwear_architect",  label:"Streetwear Architect",  desc:"Technical construction, layering, urban edge",             icon:"◧" },
  { id:"fluid_romantique",      label:"Fluid Romantique",      desc:"Draped silhouettes, texture, movement",                    icon:"◌" },
  { id:"structured_classicist", label:"Structured Classicist", desc:"Tailoring, heritage brands, timeless investment",          icon:"◫" },
  { id:"conscious_minimalist",  label:"Conscious Minimalist",  desc:"Sustainable, considered, never wasteful",                  icon:"◷" },
  { id:"identity_explorer",     label:"Identity Explorer",     desc:"Experimental, genre-bending, fearless",                    icon:"◎" },
];

const OCCASIONS = ["Daily / Street","Professional / Office","Evening / Events","Creative / Studio","Travel / Transit","Active / Outdoor"];

const CULTURAL_FRAMES = [
  { id:"global",label:"Global Contemporary" },{ id:"west_african",label:"West African / Diaspora" },
  { id:"east_african",label:"East African / Nairobi" },{ id:"south_asian",label:"South Asian" },
  { id:"east_asian",label:"East Asian" },{ id:"middle_eastern",label:"Middle Eastern" },
  { id:"afro_caribbean",label:"Afro-Caribbean" },{ id:"european_classic",label:"European Classic" },
];

const PRODUCTS = [
  { id:"p1",name:"Obsidian Structured Blazer",brand:"Maison Ndovu",price:"KES 38,500",category:"Outerwear",color:"#1a1a1a",score:0.96,url:"https://shop.cirvanna.co/p/obsidian-blazer" },
  { id:"p2",name:"Archive Monochrome Tee",brand:"KIKO Studio",price:"KES 4,200",category:"Tops",color:"#2d2d2d",score:0.91,url:"https://shop.cirvanna.co/p/archive-tee" },
  { id:"p3",name:"Ankara Precision Blazer",brand:"Lagos Archive",price:"KES 22,000",category:"Outerwear",color:"#b5541e",score:0.88,url:"https://shop.cirvanna.co/p/ankara-blazer" },
  { id:"p4",name:"Slim Technical Chino",brand:"KIKO Studio",price:"KES 9,800",category:"Bottoms",color:"#2a2a1e",score:0.85,url:"https://shop.cirvanna.co/p/chino" },
  { id:"p5",name:"Ivory Linen Kurta",brand:"Threads Collective",price:"KES 6,500",category:"Tops",color:"#e8e0d0",score:0.79,url:"https://shop.cirvanna.co/p/kurta" },
  { id:"p6",name:"Derby Oxford — Black",brand:"Sole Theory",price:"KES 12,500",category:"Shoes",color:"#0a0a0a",score:0.94,url:"https://shop.cirvanna.co/p/derby" },
];

const MOCK_CARE_RESPONSES = {
  style_query:"Your VSI reads structured at 78% — so for this occasion, the move is precision over volume. A well-cut dark blazer anchors your archetype and travels easily across formality levels. Avoid anything fluid or draped; that's not your signal right now.",
  size_query:"For your measurements, our Maison Ndovu blazers run true to size with a slightly extended shoulder. The structured cut accommodates a broader back without excess fabric at the waist. Size up only if you prefer a more relaxed layering silhouette.",
  complaint:"I hear this, and I'm sorry the experience didn't match what Cirvanna is supposed to be for you. Let me look at exactly what happened and come back to you within the hour with a clear path forward — not a script.",
  general:"Tell me more about what you're working with — occasion, constraints, what you're trying to feel. The more specific you are, the more precise I can be.",
};

// ─── Atoms ────────────────────────────────────────────────────────────────────

function Badge({ children, color=T.gold, bg=T.goldGlow }) {
  return <span style={{ fontFamily:T.font.mono,fontSize:10,color,background:bg,border:`1px solid ${color}28`,borderRadius:3,padding:"2px 8px",letterSpacing:"0.05em",display:"inline-block" }}>{children}</span>;
}

function Sk({ w="100%", h=16 }) {
  return <div style={{ width:w,height:h,borderRadius:3,background:"linear-gradient(90deg,#141414 0%,#1e1e1e 50%,#141414 100%)",backgroundSize:"200% 100%",animation:"shimmer 1.4s ease infinite" }} />;
}

function GoldBar({ val, animated=false }) {
  const pct = Math.min(100, Math.max(0, val*100));
  return <div style={{ height:3,background:"#1a1a1a",borderRadius:2,overflow:"hidden" }}>
    <div style={{ width:`${pct}%`,height:"100%",background:`linear-gradient(90deg,${T.goldDim},${T.gold})`,borderRadius:2,transition:animated?"width 0.9s cubic-bezier(0.4,0,0.2,1)":"none" }} />
  </div>;
}

function Btn({ children, variant="outline", onClick, disabled, style={} }) {
  const base = { fontFamily:T.font.mono,fontSize:11,letterSpacing:"0.07em",cursor:disabled?"not-allowed":"pointer",borderRadius:5,padding:"10px 18px",minHeight:44,transition:"all 0.15s",border:"none",opacity:disabled?0.45:1 };
  const variants = {
    gold:    { background:T.gold,color:T.obsidian,fontWeight:600 },
    outline: { background:"transparent",border:`1px solid ${T.border}`,color:T.cream },
    ghost:   { background:"transparent",border:"none",color:T.muted },
  };
  return <button onClick={onClick} disabled={disabled} style={{ ...base,...variants[variant],...style }}>{children}</button>;
}

// ─── Onboarding ───────────────────────────────────────────────────────────────

function Onboarding({ onDone }) {
  const [step,setStep]=useState(0);
  const [arch,setArch]=useState(null);
  const [occs,setOccs]=useState([]);
  const [cult,setCult]=useState("global");
  const [isc,setIsc]=useState({ coverage:"none",transparency:"any" });
  const [fading,setFading]=useState(false);

  const ok=[!!arch,occs.length>0,true];

  const next=()=>{
    if(!ok[step])return;
    if(step<2){ setFading(true); setTimeout(()=>{ setStep(s=>s+1);setFading(false); },160); }
    else onDone({ archetype:arch,occasions:occs,culturalFrame:cult,isc });
  };

  const steps=[
    { label:"Your Style Identity",   sub:"Which archetype resonates most?" },
    { label:"How You Dress",         sub:"Select the occasions you dress for" },
    { label:"Your Cultural Frame",   sub:"Heritage, context, and aesthetic constraints" },
  ];

  return (
    <div style={{ minHeight:"100vh",background:T.obsidian,display:"flex",alignItems:"center",justifyContent:"center",padding:20 }}>
      <div style={{ width:"100%",maxWidth:680,opacity:fading?0:1,transition:"opacity 0.16s" }}>
        <div style={{ marginBottom:28 }}>
          <div style={{ fontFamily:T.font.mono,fontSize:10,color:T.goldDim,letterSpacing:"0.18em",textTransform:"uppercase",marginBottom:8 }}>Building your style identity — {step+1} of 3</div>
          <div style={{ display:"flex",gap:5 }}>{[0,1,2].map(i=><div key={i} style={{ flex:1,height:2,borderRadius:1,background:i<=step?T.gold:"#1a1a1a",transition:"background 0.4s" }} />)}</div>
        </div>

        <h2 style={{ fontFamily:T.font.serif,fontSize:30,fontWeight:300,color:T.cream,margin:"0 0 4px" }}>{steps[step].label}</h2>
        <p style={{ fontFamily:T.font.sans,fontSize:14,color:T.muted,margin:"0 0 22px" }}>{steps[step].sub}</p>

        {step===0 && <div style={{ display:"grid",gridTemplateColumns:"1fr 1fr",gap:8 }}>
          {ARCHETYPES.map(a=>(
            <button key={a.id} onClick={()=>setArch(a.id)} aria-pressed={arch===a.id}
              style={{ background:arch===a.id?T.goldGlow:T.card,border:`1px solid ${arch===a.id?T.gold:T.border}`,borderRadius:7,padding:"12px 14px",cursor:"pointer",textAlign:"left",transition:"all 0.15s" }}>
              <div style={{ fontFamily:T.font.mono,fontSize:20,color:arch===a.id?T.gold:"#444",marginBottom:4 }}>{a.icon}</div>
              <div style={{ fontFamily:T.font.sans,fontSize:13,fontWeight:500,color:arch===a.id?T.gold:T.cream,marginBottom:2 }}>{a.label}</div>
              <div style={{ fontFamily:T.font.sans,fontSize:11,color:T.muted,lineHeight:1.4 }}>{a.desc}</div>
            </button>
          ))}
        </div>}

        {step===1 && <div style={{ display:"flex",flexWrap:"wrap",gap:8 }}>
          {OCCASIONS.map(o=>{ const s=occs.includes(o); return (
            <button key={o} onClick={()=>setOccs(s?occs.filter(x=>x!==o):[...occs,o])} aria-pressed={s}
              style={{ background:s?T.goldGlow:T.card,border:`1px solid ${s?T.gold:T.border}`,borderRadius:20,padding:"9px 18px",cursor:"pointer",fontFamily:T.font.sans,fontSize:13,color:s?T.gold:T.cream,transition:"all 0.15s" }}>
              {o}
            </button>
          ); })}
        </div>}

        {step===2 && <>
          <div style={{ display:"grid",gridTemplateColumns:"1fr 1fr",gap:7,marginBottom:18 }}>
            {CULTURAL_FRAMES.map(cf=>(
              <button key={cf.id} onClick={()=>setCult(cf.id)} aria-pressed={cult===cf.id}
                style={{ background:cult===cf.id?T.goldGlow:T.card,border:`1px solid ${cult===cf.id?T.gold:T.border}`,borderRadius:6,padding:"9px 12px",cursor:"pointer",fontFamily:T.font.sans,fontSize:12,color:cult===cf.id?T.gold:T.cream,textAlign:"left",transition:"all 0.15s" }}>
                {cf.label}
              </button>
            ))}
          </div>
          <div style={{ background:T.surface,border:`1px solid ${T.border}`,borderRadius:8,padding:14 }}>
            <div style={{ fontFamily:T.font.sans,fontSize:12,color:T.muted,marginBottom:10 }}>Style constraints — sets your NPL veto layer</div>
            {[{ key:"coverage",label:"Coverage",opts:["none","modest","full_coverage"] },{ key:"transparency",label:"Transparency",opts:["any","avoid_sheer"] }].map(f=>(
              <div key={f.key} style={{ marginBottom:10 }}>
                <div style={{ fontFamily:T.font.mono,fontSize:9,color:T.muted,letterSpacing:"0.07em",textTransform:"uppercase",marginBottom:6 }}>{f.label}</div>
                <div style={{ display:"flex",gap:6 }}>
                  {f.opts.map(o=>(
                    <button key={o} onClick={()=>setIsc({...isc,[f.key]:o})} aria-pressed={isc[f.key]===o}
                      style={{ background:isc[f.key]===o?T.goldGlow:"transparent",border:`1px solid ${isc[f.key]===o?T.gold:T.border}`,borderRadius:4,padding:"4px 10px",cursor:"pointer",fontFamily:T.font.mono,fontSize:10,color:isc[f.key]===o?T.gold:T.muted }}>
                      {o.replace(/_/g," ")}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </>}

        <div style={{ display:"flex",justifyContent:"space-between",alignItems:"center",marginTop:26 }}>
          {step>0
            ? <Btn variant="outline" onClick={()=>setStep(s=>s-1)}>← Back</Btn>
            : <div/>}
          <Btn variant="gold" onClick={next} disabled={!ok[step]}>
            {step===2?"Enter Cirvanna →":"Continue →"}
          </Btn>
        </div>
      </div>
    </div>
  );
}

// ─── Waitlist Panel ───────────────────────────────────────────────────────────

function WaitlistPanel({ twin }) {
  const [form,setForm]=useState({ full_name:"",email:"",country:"",style_description:"",item_never_wear:"",cultural_background:"",excitement:"" });
  const [status,setStatus]=useState("idle"); // idle|loading|success|error
  const [result,setResult]=useState(null);
  const [error,setError]=useState("");

  const handleSubmit = async () => {
    if (!form.email) { setError("Email is required."); return; }
    setStatus("loading"); setError("");
    try {
      const payload = {
        ...form,
        source:"demo_waitlist",
        submitted_at:new Date().toISOString(),
        style_archetype: twin?.archetype || null,
        culture_frame: twin?.culturalFrame || null,
      };

      // Demo mode: call Anthropic API to simulate position
      const resp = await fetch("https://api.anthropic.com/v1/messages", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({
          model:"claude-sonnet-4-6",
          max_tokens:200,
          system:"You are simulating a waitlist API response. Return ONLY valid JSON with keys: status (always 'joined'), position (a number between 40 and 200), message (a warm Cirvanna brand voice confirmation sentence, max 20 words). No explanation, no markdown.",
          messages:[{ role:"user", content:`Waitlist submission from: ${form.email} archetype: ${twin?.archetype||'unknown'}` }],
        }),
      });
      const data = await resp.json();
      let parsed = { status:"joined", position:47, message:"You're on the list — Xyra is preparing your style identity." };
      try { parsed = JSON.parse(data.content[0].text); } catch {}
      setResult(parsed);
      setStatus("success");
    } catch(e) {
      setError("Connection interrupted — try again in a moment.");
      setStatus("error");
    }
  };

  if (status==="success" && result) return (
    <div style={{ background:T.goldGlow,border:`1px solid ${T.gold}28`,borderRadius:10,padding:"28px 24px",textAlign:"center" }}>
      <div style={{ fontFamily:T.font.mono,fontSize:10,color:T.goldDim,letterSpacing:"0.18em",textTransform:"uppercase",marginBottom:12 }}>Secured</div>
      <div style={{ fontFamily:T.font.serif,fontSize:48,fontWeight:300,color:T.gold,marginBottom:4 }}>#{result.position}</div>
      <div style={{ fontFamily:T.font.sans,fontSize:15,color:T.cream,marginBottom:8,lineHeight:1.6 }}>{result.message}</div>
      <div style={{ fontFamily:T.font.sans,fontSize:13,color:T.muted }}>Check your inbox — Xyra has begun building your identity model.</div>
      <div style={{ marginTop:16,padding:"10px 14px",background:T.card,border:`1px solid ${T.border}`,borderRadius:6,display:"inline-block" }}>
        <span style={{ fontFamily:T.font.mono,fontSize:10,color:T.green }}>✓ PAMASMMA profiling active</span>
      </div>
    </div>
  );

  return (
    <div>
      <div style={{ fontFamily:T.font.mono,fontSize:10,color:T.goldDim,letterSpacing:"0.16em",textTransform:"uppercase",marginBottom:6 }}>Join the waitlist</div>
      <h2 style={{ fontFamily:T.font.serif,fontSize:26,fontWeight:300,color:T.cream,margin:"0 0 20px" }}>Reserve your place</h2>

      <div style={{ display:"grid",gap:10 }}>
        {[
          { key:"full_name",label:"Full name",placeholder:"Your name" },
          { key:"email",    label:"Email address",placeholder:"you@example.com",type:"email" },
          { key:"country",  label:"Country",placeholder:"Where you're based" },
        ].map(f=>(
          <div key={f.key}>
            <label style={{ fontFamily:T.font.mono,fontSize:9,color:T.muted,letterSpacing:"0.1em",textTransform:"uppercase",display:"block",marginBottom:5 }}>{f.label}</label>
            <input type={f.type||"text"} value={form[f.key]} placeholder={f.placeholder}
              onChange={e=>setForm({...form,[f.key]:e.target.value})}
              style={{ width:"100%",background:T.card,border:`1px solid ${T.border}`,borderRadius:5,padding:"10px 12px",fontFamily:T.font.sans,fontSize:13,color:T.cream,outline:"none",minHeight:44 }} />
          </div>
        ))}
        <div>
          <label style={{ fontFamily:T.font.mono,fontSize:9,color:T.muted,letterSpacing:"0.1em",textTransform:"uppercase",display:"block",marginBottom:5 }}>Describe your style</label>
          <textarea value={form.style_description} placeholder="In your own words — how do you dress?" rows={3}
            onChange={e=>setForm({...form,style_description:e.target.value})}
            style={{ width:"100%",background:T.card,border:`1px solid ${T.border}`,borderRadius:5,padding:"10px 12px",fontFamily:T.font.sans,fontSize:13,color:T.cream,outline:"none",resize:"vertical" }} />
        </div>
        <div>
          <label style={{ fontFamily:T.font.mono,fontSize:9,color:T.muted,letterSpacing:"0.1em",textTransform:"uppercase",display:"block",marginBottom:5 }}>One item you'd never wear</label>
          <input type="text" value={form.item_never_wear} placeholder="e.g. skinny jeans, crop tops..."
            onChange={e=>setForm({...form,item_never_wear:e.target.value})}
            style={{ width:"100%",background:T.card,border:`1px solid ${T.border}`,borderRadius:5,padding:"10px 12px",fontFamily:T.font.sans,fontSize:13,color:T.cream,outline:"none",minHeight:44 }} />
        </div>
        {error && <div style={{ fontFamily:T.font.sans,fontSize:12,color:T.red,padding:"8px 12px",background:"#1a0000",border:`1px solid ${T.red}30`,borderRadius:5 }}>{error}</div>}
        <Btn variant="gold" onClick={handleSubmit} disabled={status==="loading"} style={{ width:"100%" }}>
          {status==="loading"?"Securing your place...":"Secure My Place →"}
        </Btn>
        <p style={{ fontFamily:T.font.sans,fontSize:11,color:T.muted,textAlign:"center",margin:0 }}>
          Your profile is built from what you share. No spam. Ever.
        </p>
      </div>
    </div>
  );
}

// ─── PAMASMMA Care Panel ──────────────────────────────────────────────────────

function CarePanel({ twin }) {
  const [topic,setTopic]=useState("style_query");
  const [message,setMessage]=useState("");
  const [loading,setLoading]=useState(false);
  const [response,setResponse]=useState(null);
  const [history,setHistory]=useState([]);

  const TOPICS=[
    { id:"style_query",  label:"Style Advice",   icon:"◈" },
    { id:"size_query",   label:"Size & Fit",     icon:"◎" },
    { id:"complaint",    label:"Issue / Concern",icon:"◉" },
    { id:"general",      label:"General",        icon:"◌" },
  ];

  const ask = async () => {
    if (!message.trim()||loading) return;
    const userMsg = message;
    setMessage("");
    setLoading(true);

    // Demo: simulate PAMASMMA pipeline via Anthropic
    try {
      const archData = ARCHETYPES.find(a=>a.id===(twin?.archetype||"structured_classicist"));
      const resp = await fetch("https://api.anthropic.com/v1/messages", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({
          model:"claude-sonnet-4-6",
          max_tokens:300,
          system:`You are PAMASMMA — Cirvanna's cognitive care engine. You are not a chatbot.

User archetype: ${archData?.label||"Structured Classicist"}
Cultural frame: ${twin?.culturalFrame||"global"}
Topic type: ${topic}

PAMASMMA cognitive systems active: Perception → ${topic==="complaint"?"Mediation":"Analysis"} → Synthesis

Voice: Warm, intelligent, specific to this user's style identity. Never corporate. Never generic.
For style queries: editorial and precise. For complaints: empathetic and direct.
Max 80 words. Never start with 'I'.`,
          messages:[{ role:"user",content:userMsg }],
        }),
      });
      const data = await resp.json();
      const reply = data?.content?.[0]?.text || MOCK_CARE_RESPONSES[topic];
      const entry = { id:Date.now(), userMsg, reply, topic, tier:topic==="complaint"?"TIER_2":"TIER_1", ts:new Date().toLocaleTimeString() };
      setHistory(h=>[entry,...h]);
      setResponse(entry);
    } catch {
      const reply = MOCK_CARE_RESPONSES[topic]||"Connection interrupted — try again.";
      const entry = { id:Date.now(), userMsg, reply, topic, tier:"TIER_1", ts:new Date().toLocaleTimeString() };
      setHistory(h=>[entry,...h]);
      setResponse(entry);
    }
    setLoading(false);
  };

  return (
    <div>
      <div style={{ fontFamily:T.font.mono,fontSize:10,color:T.goldDim,letterSpacing:"0.16em",textTransform:"uppercase",marginBottom:6 }}>Cognitive care engine</div>
      <h2 style={{ fontFamily:T.font.serif,fontSize:26,fontWeight:300,color:T.cream,margin:"0 0 4px" }}>PAMASMMA Care</h2>
      <p style={{ fontFamily:T.font.sans,fontSize:13,color:T.muted,margin:"0 0 20px",lineHeight:1.5 }}>
        8-system cognitive AI — Perception · Analysis · Mediation · Action · Synthesis · Memory · Metacognition · Alignment
      </p>

      {/* Topic selector */}
      <div style={{ display:"flex",gap:6,marginBottom:16,flexWrap:"wrap" }}>
        {TOPICS.map(t=>(
          <button key={t.id} onClick={()=>setTopic(t.id)} aria-pressed={topic===t.id}
            style={{ background:topic===t.id?T.goldGlow:T.card,border:`1px solid ${topic===t.id?T.gold:T.border}`,borderRadius:6,padding:"7px 14px",cursor:"pointer",fontFamily:T.font.sans,fontSize:12,color:topic===t.id?T.gold:T.cream,transition:"all 0.15s",display:"flex",alignItems:"center",gap:6 }}>
            <span style={{ fontFamily:T.font.mono,fontSize:14 }}>{t.icon}</span>{t.label}
          </button>
        ))}
      </div>

      {/* Conversation history */}
      {history.length>0 && (
        <div style={{ marginBottom:14,display:"flex",flexDirection:"column",gap:10,maxHeight:320,overflowY:"auto" }}>
          {[...history].reverse().map(entry=>(
            <div key={entry.id}>
              <div style={{ display:"flex",justifyContent:"flex-end",marginBottom:6 }}>
                <div style={{ background:T.goldGlow,border:`1px solid ${T.gold}28`,borderRadius:"12px 12px 3px 12px",padding:"9px 13px",maxWidth:"80%",fontFamily:T.font.sans,fontSize:13,color:T.gold,lineHeight:1.6 }}>{entry.userMsg}</div>
              </div>
              <div style={{ display:"flex",justifyContent:"flex-start" }}>
                <div style={{ background:T.card,border:`1px solid ${T.border}`,borderRadius:"12px 12px 12px 3px",padding:"9px 13px",maxWidth:"88%",fontFamily:T.font.sans,fontSize:13,color:T.cream,lineHeight:1.7 }}>
                  {entry.reply}
                  <div style={{ display:"flex",gap:6,marginTop:6 }}>
                    <Badge color={entry.tier==="TIER_1"?T.green:T.amber}>{entry.tier}</Badge>
                    <Badge color={T.muted} bg="transparent">{entry.ts}</Badge>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Loading indicator */}
      {loading && (
        <div style={{ display:"flex",gap:5,alignItems:"center",padding:"8px 0" }}>
          {[0,1,2].map(i=>(
            <div key={i} style={{ width:5,height:5,borderRadius:"50%",background:T.gold,opacity:0.6,animation:`xyra-dot 1s ${i*0.18}s ease-in-out infinite alternate` }} />
          ))}
          <span style={{ fontFamily:T.font.mono,fontSize:9,color:T.muted,marginLeft:4 }}>PAMASMMA processing...</span>
        </div>
      )}

      {/* Input */}
      <div style={{ display:"flex",gap:8,marginTop:4 }}>
        <textarea value={message} onChange={e=>setMessage(e.target.value)}
          onKeyDown={e=>{ if(e.key==="Enter"&&!e.shiftKey){ e.preventDefault(); ask(); } }}
          placeholder={`Ask PAMASMMA about ${topic==="style_query"?"your style...":topic==="size_query"?"sizing and fit...":topic==="complaint"?"an issue...":"anything..."}`}
          rows={2}
          style={{ flex:1,background:T.card,border:`1px solid ${T.border}`,borderRadius:5,padding:"9px 12px",fontFamily:T.font.sans,fontSize:13,color:T.cream,outline:"none",resize:"none" }} />
        <Btn variant="gold" onClick={ask} disabled={loading||!message.trim()} style={{ alignSelf:"flex-end" }}>→</Btn>
      </div>

      {/* PAMASMMA info bar */}
      <div style={{ marginTop:14,padding:"10px 14px",background:T.surface,border:`1px solid ${T.border}`,borderRadius:6,display:"flex",alignItems:"center",gap:10 }}>
        <div style={{ width:6,height:6,borderRadius:"50%",background:T.green,boxShadow:`0 0 6px ${T.green}` }} />
        <span style={{ fontFamily:T.font.mono,fontSize:10,color:T.muted }}>PAMASMMA operational — 8 cognitive systems active — Tier 1/2 autonomous, Tier 3 requires founder approval</span>
      </div>
    </div>
  );
}

// ─── Identity Mirror ──────────────────────────────────────────────────────────

function IdentityMirror({ twin }) {
  const [anim,setAnim]=useState({});
  useEffect(()=>{ const keys=["structured","minimal","cultural_expressivity","bold","monochrome"]; keys.forEach((k,i)=>setTimeout(()=>setAnim(p=>({...p,[k]:true})),i*90)); },[]);

  const archData=ARCHETYPES.find(a=>a.id===(twin?.archetype||"structured_classicist"))||ARCHETYPES[5];
  const signals={ structured:0.78,minimal:0.65,cultural_expressivity:0.42,bold:0.35,monochrome:0.71,classic:0.68 };
  const labels={ structured:"Structural precision",minimal:"Minimal sensibility",cultural_expressivity:"Cultural expressivity",bold:"Boldness threshold",monochrome:"Tonal discipline",classic:"Timeless sensibility" };
  const descs={ structured:"Tailoring and construction matter deeply",minimal:"Restraint is your natural register",cultural_expressivity:"Heritage aesthetics emerging",bold:"Considered risk-taking",monochrome:"Colour used as accent",classic:"Investment over impulse" };

  return (
    <div>
      <div style={{ background:T.goldGlow,border:`1px solid ${T.gold}28`,borderRadius:10,padding:"18px 20px",marginBottom:14 }}>
        <div style={{ fontFamily:T.font.mono,fontSize:9,color:T.goldDim,letterSpacing:"0.14em",textTransform:"uppercase",marginBottom:10 }}>Your Style Identity</div>
        <div style={{ display:"flex",alignItems:"center",gap:14,marginBottom:12 }}>
          <div style={{ fontFamily:T.font.mono,fontSize:28,color:T.gold }}>{archData.icon}</div>
          <div>
            <div style={{ fontFamily:T.font.serif,fontSize:22,color:T.gold,fontWeight:300 }}>{archData.label}</div>
            <div style={{ fontFamily:T.font.sans,fontSize:12,color:T.muted,marginTop:2 }}>{archData.desc}</div>
          </div>
        </div>
        <p style={{ fontFamily:T.font.sans,fontSize:13,color:T.cream,lineHeight:1.65,fontStyle:"italic",margin:0 }}>
          "Deeply consistent style identity — precision and restraint as signature."
        </p>
      </div>
      <div style={{ background:T.card,border:`1px solid ${T.border}`,borderRadius:10,padding:"16px 18px",marginBottom:14 }}>
        <div style={{ fontFamily:T.font.mono,fontSize:9,color:T.muted,letterSpacing:"0.14em",textTransform:"uppercase",marginBottom:14 }}>What defines your style</div>
        {Object.entries(signals).map(([k,v])=>(
          <div key={k} style={{ marginBottom:13 }}>
            <div style={{ display:"flex",justifyContent:"space-between",marginBottom:4 }}>
              <span style={{ fontFamily:T.font.sans,fontSize:13,color:T.cream }}>{labels[k]}</span>
              <span style={{ fontFamily:T.font.mono,fontSize:11,color:T.gold }}>{Math.round(v*100)}%</span>
            </div>
            <GoldBar val={v} animated={!!anim[k]} />
            <div style={{ fontFamily:T.font.sans,fontSize:11,color:T.muted,marginTop:3 }}>{descs[k]}</div>
          </div>
        ))}
      </div>
      <div style={{ background:T.surface,border:`1px solid ${T.border}`,borderRadius:10,padding:"12px 16px" }}>
        <div style={{ fontFamily:T.font.mono,fontSize:9,color:T.muted,letterSpacing:"0.14em",textTransform:"uppercase",marginBottom:8 }}>NPL Active Constraints</div>
        <div style={{ display:"flex",flexWrap:"wrap",gap:6,marginBottom:8 }}>
          <Badge color={T.blue}>Coverage: {twin?.isc?.coverage||"none"}</Badge>
          <Badge color={T.muted} bg="transparent">Transparency: {twin?.isc?.transparency||"any"}</Badge>
          <Badge color={T.green}>Frame: {twin?.culturalFrame||"global"}</Badge>
        </div>
        <p style={{ fontFamily:T.font.sans,fontSize:12,color:T.muted,lineHeight:1.55,margin:0 }}>Items conflicting with these constraints are filtered, not hidden. Always explainable.</p>
      </div>
    </div>
  );
}

// ─── Product Card ─────────────────────────────────────────────────────────────

function ProductCard({ p, onTryOn }) {
  const [hov,setHov]=useState(false);
  return (
    <div onMouseEnter={()=>setHov(true)} onMouseLeave={()=>setHov(false)}
      style={{ background:T.card,border:`1px solid ${hov?T.borderHov:T.border}`,borderRadius:8,overflow:"hidden",transition:"all 0.18s",transform:hov?"translateY(-2px)":"none" }}>
      <div style={{ height:170,background:`${p.color}18`,display:"flex",alignItems:"center",justifyContent:"center",position:"relative",borderBottom:`1px solid ${T.border}` }}>
        <div style={{ width:55,height:85,background:p.color,borderRadius:4,opacity:0.65 }} />
        <div style={{ position:"absolute",top:8,right:8 }}><Badge>{Math.round(p.score*100)}% match</Badge></div>
      </div>
      <div style={{ padding:"12px 12px 14px" }}>
        <div style={{ fontFamily:T.font.mono,fontSize:9,color:T.muted,letterSpacing:"0.08em",marginBottom:3 }}>{p.brand}</div>
        <div style={{ fontFamily:T.font.serif,fontSize:15,color:T.cream,marginBottom:6,lineHeight:1.3 }}>{p.name}</div>
        <div style={{ display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:10 }}>
          <span style={{ fontFamily:T.font.sans,fontSize:13,color:T.gold,fontWeight:500 }}>{p.price}</span>
          <Badge color={T.muted} bg="transparent">{p.category}</Badge>
        </div>
        <div style={{ display:"grid",gridTemplateColumns:"1fr 1fr",gap:6 }}>
          <button onClick={()=>onTryOn(p)} style={{ background:"transparent",border:`1px solid ${T.border}`,borderRadius:4,padding:"9px 0",fontFamily:T.font.mono,fontSize:10,color:T.cream,cursor:"pointer",minHeight:44 }}>Try On</button>
          <a href={p.url} target="_blank" rel="noopener noreferrer" style={{ background:T.gold,borderRadius:4,padding:"9px 0",fontFamily:T.font.mono,fontSize:10,color:T.obsidian,cursor:"pointer",minHeight:44,display:"flex",alignItems:"center",justifyContent:"center",textDecoration:"none",fontWeight:600 }}>Find This →</a>
        </div>
      </div>
    </div>
  );
}

// ─── Try-On Modal ─────────────────────────────────────────────────────────────

function TryOnModal({ product, onClose }) {
  const [status,setStatus]=useState("idle");
  const [prog,setProg]=useState(0);
  const ref=useRef(null);

  const start=()=>{
    setStatus("queued"); setProg(10);
    let p=10;
    ref.current=setInterval(()=>{ p=Math.min(p+14,95); setProg(p); if(p>=95){ clearInterval(ref.current); setStatus("done"); setProg(100); } },600);
  };
  useEffect(()=>()=>clearInterval(ref.current),[]);

  return (
    <div style={{ position:"fixed",inset:0,background:"#000000cc",zIndex:1000,display:"flex",alignItems:"center",justifyContent:"center",backdropFilter:"blur(5px)",padding:20 }}
      role="dialog" aria-modal="true">
      <div style={{ background:T.surface,border:`1px solid ${T.border}`,borderRadius:12,padding:28,width:"100%",maxWidth:420,position:"relative" }}>
        <button onClick={onClose} style={{ position:"absolute",top:14,right:14,background:"none",border:"none",color:T.muted,cursor:"pointer",fontSize:20,minWidth:44,minHeight:44,display:"flex",alignItems:"center",justifyContent:"center" }}>✕</button>
        <div style={{ fontFamily:T.font.serif,fontSize:22,color:T.cream,marginBottom:4 }}>Virtual Try-On</div>
        <div style={{ fontFamily:T.font.sans,fontSize:13,color:T.muted,marginBottom:20 }}>{product.name}</div>
        {status==="idle" && <div style={{ display:"grid",gap:8 }}>
          <Btn variant="gold" onClick={start} style={{ width:"100%" }}>Try on with archetype silhouette</Btn>
          <Btn variant="outline" style={{ width:"100%" }}>Upload your photo (PATH A)</Btn>
        </div>}
        {(status==="queued"||status==="processing") && <div style={{ textAlign:"center",padding:"20px 0" }}>
          <div style={{ fontFamily:T.font.mono,fontSize:12,color:T.gold,marginBottom:14 }}>Compositing...</div>
          <div style={{ height:4,background:T.border,borderRadius:2,overflow:"hidden",marginBottom:6 }}>
            <div style={{ width:`${prog}%`,height:"100%",background:`linear-gradient(90deg,${T.goldDim},${T.gold})`,borderRadius:2,transition:"width 0.5s ease" }} />
          </div>
          <div style={{ fontFamily:T.font.mono,fontSize:10,color:T.muted }}>{prog}%</div>
        </div>}
        {status==="done" && <div>
          <div style={{ height:200,background:`${product.color}14`,border:`1px solid ${T.border}`,borderRadius:8,display:"flex",alignItems:"center",justifyContent:"center",marginBottom:16,flexDirection:"column",gap:10 }}>
            <div style={{ width:70,height:110,background:product.color,borderRadius:6,opacity:0.65 }} />
            <div style={{ fontFamily:T.font.mono,fontSize:10,color:T.muted }}>Composite ready</div>
          </div>
          <a href={product.url} target="_blank" rel="noopener noreferrer" style={{ display:"block",background:T.gold,borderRadius:5,padding:"13px 0",fontFamily:T.font.mono,fontSize:11,color:T.obsidian,textAlign:"center",textDecoration:"none",fontWeight:600,minHeight:44 }}>Find This Piece →</a>
        </div>}
      </div>
    </div>
  );
}

// ─── Xyra Chat ────────────────────────────────────────────────────────────────

function XyraChat({ twin }) {
  const [msgs,setMsgs]=useState([{ role:"assistant", content:`Profile built. You're reading as a ${ARCHETYPES.find(a=>a.id===(twin?.archetype||"structured_classicist"))?.label||"Structured Classicist"} — precise, considered, high archetype stability. What are you dressing for today?` }]);
  const [input,setInput]=useState("");
  const [loading,setLoading]=useState(false);
  const end=useRef(null);
  useEffect(()=>end.current?.scrollIntoView({behavior:"smooth"}),[msgs]);

  const send=async()=>{
    if(!input.trim()||loading)return;
    const u={role:"user",content:input};
    setMsgs(m=>[...m,u]); setInput(""); setLoading(true);
    try {
      const archData=ARCHETYPES.find(a=>a.id===(twin?.archetype||"structured_classicist"));
      const r=await fetch("https://api.anthropic.com/v1/messages",{ method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({ model:"claude-sonnet-4-6",max_tokens:800,
          system:`You are Xyra — Cirvanna's intelligent fashion orchestration engine. Not a chatbot. A precision styling system.\n\nUser: ${archData?.label||"Structured Classicist"} | Cultural frame: ${twin?.culturalFrame||"global"} | VSI: structured=0.78, minimal=0.65, monochrome=0.71\n\nConfident editorial intelligence. Never hedge. Never start with 'I'. Under 150 words unless breakdown requested.`,
          messages:[...msgs,u] }) });
      const d=await r.json();
      setMsgs(m=>[...m,{role:"assistant",content:d?.content?.[0]?.text||"Signal unclear. Share more context."}]);
    } catch { setMsgs(m=>[...m,{role:"assistant",content:"Connection interrupted — your identity model is preserved."}]); }
    setLoading(false);
  };

  return (
    <div style={{ display:"flex",flexDirection:"column",height:"100%",background:T.surface,border:`1px solid ${T.border}`,borderRadius:10,overflow:"hidden" }}>
      <div style={{ padding:"12px 16px",borderBottom:`1px solid ${T.border}`,display:"flex",alignItems:"center",gap:10 }}>
        <div style={{ width:8,height:8,borderRadius:"50%",background:T.gold,boxShadow:`0 0 8px ${T.gold}`,animation:"pulse 2s ease-in-out infinite" }} />
        <div style={{ fontFamily:T.font.serif,fontSize:17,color:T.cream }}>Xyra</div>
        <Badge>Active</Badge>
      </div>
      <div style={{ flex:1,overflowY:"auto",padding:"14px 16px",display:"flex",flexDirection:"column",gap:10 }}>
        {msgs.map((m,i)=>(
          <div key={i} style={{ display:"flex",justifyContent:m.role==="user"?"flex-end":"flex-start" }}>
            <div style={{ maxWidth:"84%",background:m.role==="user"?T.goldGlow:T.card,border:`1px solid ${m.role==="user"?T.gold+"28":T.border}`,borderRadius:m.role==="user"?"12px 12px 3px 12px":"12px 12px 12px 3px",padding:"10px 13px",fontFamily:T.font.sans,fontSize:13,lineHeight:1.65,color:m.role==="user"?T.gold:T.cream }}>{m.content}</div>
          </div>
        ))}
        {loading && <div style={{ display:"flex",gap:5,alignItems:"center" }}>
          {[0,1,2].map(i=><div key={i} style={{ width:5,height:5,borderRadius:"50%",background:T.gold,opacity:0.6,animation:`xyra-dot 1s ${i*0.18}s ease-in-out infinite alternate` }} />)}
          <span style={{ fontFamily:T.font.mono,fontSize:9,color:T.muted,marginLeft:4 }}>Reading your signals...</span>
        </div>}
        <div ref={end} />
      </div>
      <div style={{ padding:"10px 12px",borderTop:`1px solid ${T.border}`,display:"flex",gap:8 }}>
        <input value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>e.key==="Enter"&&!e.shiftKey&&send()} placeholder="Ask Xyra to style you..."
          style={{ flex:1,background:T.card,border:`1px solid ${T.border}`,borderRadius:5,padding:"9px 12px",fontFamily:T.font.sans,fontSize:13,color:T.cream,outline:"none",minHeight:44 }} />
        <Btn variant="gold" onClick={send} disabled={loading||!input.trim()}>→</Btn>
      </div>
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function CirvannaApp() {
  const [screen,setScreen]=useState("onboarding");
  const [twin,setTwin]=useState(null);
  const [tab,setTab]=useState("discover");
  const [tryOn,setTryOn]=useState(null);

  const TABS=[
    { id:"discover",  label:"Discover" },
    { id:"identity",  label:"Identity" },
    { id:"xyra",      label:"Xyra" },
    { id:"care",      label:"PAMASMMA" },
    { id:"waitlist",  label:"Waitlist" },
  ];

  if(screen==="onboarding") return (
    <>
      <style>{FONTS+CSS}</style>
      <Onboarding onDone={profile=>{ setTwin(profile); setScreen("app"); }} />
    </>
  );

  return (
    <>
      <style>{FONTS+CSS}</style>
      <div style={{ background:T.obsidian,minHeight:"100vh" }}>
        {/* Header */}
        <header style={{ position:"sticky",top:0,zIndex:100,background:T.obsidian,borderBottom:`1px solid ${T.border}`,padding:"0 20px",height:52,display:"flex",alignItems:"center",justifyContent:"space-between" }}>
          <div style={{ display:"flex",alignItems:"center",gap:10 }}>
            <div style={{ fontFamily:T.font.serif,fontSize:19,color:T.gold,letterSpacing:"0.06em" }}>CIRVANNA</div>
            <Badge>Beta</Badge>
          </div>
          <nav style={{ display:"flex",gap:2 }}>
            {TABS.map(t=>(
              <button key={t.id} onClick={()=>setTab(t.id)} aria-current={tab===t.id?"page":undefined}
                style={{ background:"none",border:"none",fontFamily:T.font.mono,fontSize:10,letterSpacing:"0.08em",textTransform:"uppercase",padding:"6px 10px",cursor:"pointer",color:tab===t.id?T.gold:T.muted,borderBottom:tab===t.id?`2px solid ${T.gold}`:"2px solid transparent",minHeight:44,transition:"color 0.15s" }}>
                {t.label}
              </button>
            ))}
          </nav>
          <div style={{ display:"flex",alignItems:"center",gap:6 }}>
            <div style={{ width:7,height:7,borderRadius:"50%",background:T.gold,animation:"pulse 2s ease-in-out infinite" }} />
            <span style={{ fontFamily:T.font.mono,fontSize:9,color:T.muted }}>{ARCHETYPES.find(a=>a.id===twin?.archetype)?.label||""}</span>
          </div>
        </header>

        <main style={{ padding:"24px 20px",maxWidth:1200,margin:"0 auto" }}>

          {/* Discover */}
          {tab==="discover" && <>
            <div style={{ marginBottom:20 }}>
              <div style={{ fontFamily:T.font.mono,fontSize:9,color:T.goldDim,letterSpacing:"0.16em",textTransform:"uppercase",marginBottom:6 }}>Curated for your identity</div>
              <h1 style={{ fontFamily:T.font.serif,fontSize:26,fontWeight:300,color:T.cream,margin:0 }}>Today's Recommendations</h1>
            </div>
            <div style={{ display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(200px,1fr))",gap:14 }}>
              {PRODUCTS.map(p=><ProductCard key={p.id} p={p} onTryOn={setTryOn} />)}
            </div>
          </>}

          {/* Identity Mirror */}
          {tab==="identity" && <>
            <div style={{ marginBottom:20 }}>
              <div style={{ fontFamily:T.font.mono,fontSize:9,color:T.goldDim,letterSpacing:"0.16em",textTransform:"uppercase",marginBottom:6 }}>Your living style portrait</div>
              <h1 style={{ fontFamily:T.font.serif,fontSize:26,fontWeight:300,color:T.cream,margin:0 }}>Identity Mirror</h1>
            </div>
            <IdentityMirror twin={twin} />
          </>}

          {/* Xyra */}
          {tab==="xyra" && (
            <div style={{ height:"calc(100vh - 130px)" }}>
              <div style={{ marginBottom:14 }}>
                <div style={{ fontFamily:T.font.mono,fontSize:9,color:T.goldDim,letterSpacing:"0.16em",textTransform:"uppercase",marginBottom:4 }}>Intelligence engine</div>
                <h1 style={{ fontFamily:T.font.serif,fontSize:26,fontWeight:300,color:T.cream,margin:0 }}>Xyra</h1>
              </div>
              <div style={{ height:"calc(100% - 60px)" }}><XyraChat twin={twin} /></div>
            </div>
          )}

          {/* PAMASMMA Care */}
          {tab==="care" && <CarePanel twin={twin} />}

          {/* Waitlist */}
          {tab==="waitlist" && <WaitlistPanel twin={twin} />}
        </main>
      </div>

      {tryOn && <TryOnModal product={tryOn} onClose={()=>setTryOn(null)} />}
    </>
  );
}

const CSS=`
* { box-sizing:border-box; margin:0; padding:0; }
:root { color-scheme:dark; }
body { background:#080808; color:#f0ebe3; -webkit-font-smoothing:antialiased; }
::-webkit-scrollbar { width:3px; }
::-webkit-scrollbar-thumb { background:#2a2a2a; border-radius:2px; }
:focus-visible { outline:2px solid #d4af37 !important; outline-offset:2px !important; }
@keyframes shimmer { 0%{background-position:200% 0}100%{background-position:-200% 0} }
@keyframes pulse { 0%,100%{opacity:1}50%{opacity:0.5} }
@keyframes xyra-dot { from{opacity:0.3;transform:translateY(0)}to{opacity:1;transform:translateY(-3px)} }
@media(prefers-reduced-motion:reduce){ *,*::before,*::after{animation-duration:0.01ms!important;transition-duration:0.01ms!important} }
`;
