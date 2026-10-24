import { useState, useRef, useCallback } from "react";

const C = {
  obsidian:'#0B0C10',obsidianDeep:'#07080B',obsidianPanel:'#12141A',obsidianCard:'#1A1D26',obsidianHover:'#1F2330',
  gold:'#C9A84C',goldLight:'#E2C46E',goldDim:'#8A6E30',goldGlow:'rgba(201,168,76,0.18)',goldSubtle:'rgba(201,168,76,0.08)',
  silver:'#B8BEC8',silverLight:'#D4D8E0',silverDim:'#6B7280',silverSubtle:'rgba(184,190,200,0.08)',
  magenta:'#C026D3',magentaBright:'#E040FB',magentaDim:'#7B1FA2',magentaGlow:'rgba(192,38,211,0.22)',magentaSubtle:'rgba(192,38,211,0.10)',
  success:'#22C55E',warning:'#F59E0B',error:'#EF4444',
  text:{primary:'#F0F1F3',secondary:'#9BA3AF',muted:'#4B5563',gold:'#C9A84C',magenta:'#E040FB'},
  border:{subtle:'rgba(255,255,255,0.05)',default:'rgba(255,255,255,0.09)',gold:'rgba(201,168,76,0.25)',magenta:'rgba(192,38,211,0.30)',silver:'rgba(184,190,200,0.15)'},
};

const BRAND = {name:'Maison Ndovu',category:'Luxury Streetwear',id:'brand_7f3a91',country:'Kenya',logo_initial:'MN'};

const INITIAL_PRODUCTS = [
  {id:'p1',name:'Obsidian Technical Jacket',sku:'MTJ-001',description:'Water-resistant matte shell with concealed zip pockets.',category:'Outerwear',price:42000,currency:'KES',status:'live',sizes:['XS','S','M','L','XL'],colors:['Obsidian','Slate'],images:[],stock:24,views:3241,tryons:847,saves:312,marketplace_visible:true,created_at:'2026-06-01'},
  {id:'p2',name:'Archive Print Tee — Vol.3',sku:'APT-003',description:'Limited run, 200gsm Supima cotton.',category:'Tops',price:4800,currency:'KES',status:'live',sizes:['S','M','L','XL'],colors:['Ivory','Black'],images:[],stock:68,views:1890,tryons:512,saves:201,marketplace_visible:true,created_at:'2026-06-05'},
  {id:'p3',name:'Cargo Silhouette Trousers',sku:'CST-002',description:'Six-pocket relaxed fit. Ripstop cotton.',category:'Bottoms',price:12500,currency:'KES',status:'draft',sizes:['28','30','32','34','36'],colors:['Khaki','Black','Olive'],images:[],stock:0,views:0,tryons:0,saves:0,marketplace_visible:false,created_at:'2026-06-10'},
];

const fmt = (n) => n.toLocaleString();
const fmtKES = (n) => `KES ${n.toLocaleString()}`;
const statusMeta = {
  live:{color:C.success,bg:'rgba(34,197,94,0.1)',border:'rgba(34,197,94,0.25)'},
  draft:{color:C.warning,bg:'rgba(245,158,11,0.1)',border:'rgba(245,158,11,0.25)'},
  archived:{color:C.silverDim,bg:'rgba(107,114,128,0.1)',border:'rgba(107,114,128,0.2)'},
};

function StatusPill({status}){
  const m=statusMeta[status];
  return <span style={{display:'inline-flex',alignItems:'center',gap:5,padding:'3px 10px',borderRadius:99,fontSize:11,fontWeight:600,background:m.bg,color:m.color,border:`1px solid ${m.border}`}}><span style={{width:5,height:5,borderRadius:'50%',background:m.color}}/>{status.charAt(0).toUpperCase()+status.slice(1)}</span>;
}

function GoldBtn({children,onClick,style}){
  const [hov,setHov]=useState(false);
  return <button onClick={onClick} onMouseEnter={()=>setHov(true)} onMouseLeave={()=>setHov(false)} style={{background:hov?`linear-gradient(135deg,${C.goldLight},${C.gold})`:`linear-gradient(135deg,${C.gold},${C.goldDim})`,color:'#07080B',border:'none',borderRadius:8,padding:'10px 20px',fontWeight:700,fontSize:13,cursor:'pointer',transition:'all 200ms ease',boxShadow:hov?`0 0 20px ${C.goldGlow}`:'none',...style}}>{children}</button>;
}

function MagentaBtn({children,onClick,style}){
  const [hov,setHov]=useState(false);
  return <button onClick={onClick} onMouseEnter={()=>setHov(true)} onMouseLeave={()=>setHov(false)} style={{background:hov?`linear-gradient(135deg,${C.magentaBright},${C.magenta})`:`linear-gradient(135deg,${C.magenta},${C.magentaDim})`,color:'#fff',border:'none',borderRadius:8,padding:'10px 20px',fontWeight:700,fontSize:13,cursor:'pointer',transition:'all 200ms ease',boxShadow:hov?`0 0 24px ${C.magentaGlow}`:'none',...style}}>{children}</button>;
}

function TagInput({label,values,onChange,suggestions}){
  const [input,setInput]=useState('');
  const add=(val)=>{const v=val.trim();if(v&&!values.includes(v))onChange([...values,v]);setInput('');};
  return(
    <div style={{display:'flex',flexDirection:'column',gap:6}}>
      <label style={{fontSize:11,fontWeight:600,color:C.silver,letterSpacing:'0.08em',textTransform:'uppercase'}}>{label}</label>
      <div style={{display:'flex',flexWrap:'wrap',gap:6,background:C.obsidianDeep,border:`1px solid ${C.border.default}`,borderRadius:8,padding:'8px 10px',minHeight:44}}>
        {values.map(v=><span key={v} style={{display:'inline-flex',alignItems:'center',gap:4,background:C.goldSubtle,color:C.gold,border:`1px solid ${C.border.gold}`,borderRadius:6,padding:'3px 8px',fontSize:12,fontWeight:500}}>{v}<button onClick={()=>onChange(values.filter(x=>x!==v))} style={{background:'none',border:'none',color:C.goldDim,cursor:'pointer',fontSize:14,lineHeight:1,padding:0}}>×</button></span>)}
        <input value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'||e.key===','){e.preventDefault();add(input);}}} placeholder="Type + Enter" style={{background:'none',border:'none',outline:'none',color:C.text.primary,fontSize:13,minWidth:80,flex:1,fontFamily:'inherit'}}/>
      </div>
      {suggestions&&<div style={{display:'flex',flexWrap:'wrap',gap:4}}>{suggestions.filter(s=>!values.includes(s)).map(s=><button key={s} onClick={()=>add(s)} style={{background:C.silverSubtle,border:`1px solid ${C.border.silver}`,borderRadius:5,padding:'2px 8px',fontSize:11,color:C.silver,cursor:'pointer'}}>{s}</button>)}</div>}
    </div>
  );
}

function StatCard({label,value,sub,accent}){
  return(
    <div style={{background:C.obsidianPanel,border:`1px solid ${C.border.default}`,borderTop:`2px solid ${accent}`,borderRadius:12,padding:'20px 22px'}}>
      <div style={{fontSize:11,color:C.text.muted,letterSpacing:'0.1em',textTransform:'uppercase',marginBottom:10}}>{label}</div>
      <div style={{fontSize:26,fontWeight:700,color:C.text.primary}}>{value}</div>
      {sub&&<div style={{fontSize:11,color:accent,marginTop:5}}>{sub}</div>}
    </div>
  );
}

function AddProductForm({onAdd,onCancel}){
  const [form,setForm]=useState({name:'',sku:'',description:'',category:'Tops',price:'',currency:'KES',sizes:[],colors:[],stock:'',marketplace_visible:true});
  const [errors,setErrors]=useState({});
  const [submitting,setSubmitting]=useState(false);
  const set=(k)=>(v)=>setForm(f=>({...f,[k]:v}));

  const validate=()=>{
    const e={};
    if(!form.name.trim())e.name='Required';
    if(!form.sku.trim())e.sku='Required';
    if(!form.description.trim())e.description='Required';
    if(!form.price||isNaN(Number(form.price))||Number(form.price)<=0)e.price='Valid price required';
    if(!form.stock||isNaN(Number(form.stock)))e.stock='Required';
    return e;
  };

  const handleSubmit=async()=>{
    const e=validate();
    if(Object.keys(e).length){setErrors(e);return;}
    setSubmitting(true);
    await new Promise(r=>setTimeout(r,800));
    onAdd({id:'p_'+Date.now(),name:form.name,sku:form.sku,description:form.description,category:form.category,price:Number(form.price),currency:form.currency,status:'draft',sizes:form.sizes,colors:form.colors,images:[],stock:Number(form.stock),views:0,tryons:0,saves:0,marketplace_visible:form.marketplace_visible,created_at:new Date().toISOString().slice(0,10)});
    setSubmitting(false);
  };

  const cats=['Outerwear','Tops','Bottoms','Footwear','Accessories','Dresses','Sets'];
  const sel={width:'100%',marginTop:6,background:C.obsidianDeep,border:`1px solid ${C.border.default}`,borderRadius:8,padding:'10px 14px',fontSize:14,color:C.text.primary,outline:'none',cursor:'pointer',fontFamily:'inherit'};
  const inp={background:C.obsidianDeep,border:`1px solid ${C.border.default}`,borderRadius:8,padding:'10px 14px',fontSize:14,color:C.text.primary,outline:'none',width:'100%',boxSizing:'border-box',fontFamily:'inherit'};
  const lbl={fontSize:11,fontWeight:600,color:C.silver,letterSpacing:'0.08em',textTransform:'uppercase',display:'block',marginBottom:6};

  return(
    <div style={{maxWidth:700}}>
      <div style={{marginBottom:28}}>
        <h2 style={{fontSize:28,fontWeight:700,margin:0,background:`linear-gradient(135deg,${C.gold},${C.magentaBright})`,WebkitBackgroundClip:'text',WebkitTextFillColor:'transparent'}}>Add New Product</h2>
        <p style={{color:C.text.secondary,fontSize:14,margin:'8px 0 0'}}>Products are saved as Draft until you publish them to the marketplace.</p>
      </div>
      <div style={{display:'flex',flexDirection:'column',gap:16}}>
        {/* Identity */}
        <div style={{background:C.obsidianPanel,border:`1px solid ${C.border.gold}`,borderRadius:12,padding:22}}>
          <div style={{fontSize:11,fontWeight:700,color:C.gold,letterSpacing:'0.12em',textTransform:'uppercase',marginBottom:18}}>Product Identity</div>
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:14}}>
            <div style={{gridColumn:'1/-1'}}>
              <label style={lbl}>Product Name <span style={{color:C.magenta}}>*</span></label>
              <input value={form.name} onChange={e=>set('name')(e.target.value)} placeholder="e.g. Obsidian Technical Jacket" style={inp} onFocus={e=>{e.target.style.borderColor=C.gold;}} onBlur={e=>{e.target.style.borderColor=C.border.default;}}/>
              {errors.name&&<div style={{fontSize:11,color:C.error,marginTop:4}}>{errors.name}</div>}
            </div>
            <div>
              <label style={lbl}>SKU <span style={{color:C.magenta}}>*</span></label>
              <input value={form.sku} onChange={e=>set('sku')(e.target.value)} placeholder="MTJ-001" style={inp} onFocus={e=>{e.target.style.borderColor=C.gold;}} onBlur={e=>{e.target.style.borderColor=C.border.default;}}/>
              {errors.sku&&<div style={{fontSize:11,color:C.error,marginTop:4}}>{errors.sku}</div>}
            </div>
            <div>
              <label style={lbl}>Category</label>
              <select value={form.category} onChange={e=>set('category')(e.target.value)} style={sel}>{cats.map(c=><option key={c} value={c}>{c}</option>)}</select>
            </div>
            <div style={{gridColumn:'1/-1'}}>
              <label style={lbl}>Description <span style={{color:C.magenta}}>*</span></label>
              <textarea value={form.description} onChange={e=>set('description')(e.target.value)} placeholder="Describe material, cut, and feel…" rows={3} style={{...inp,resize:'vertical'}} onFocus={e=>{e.target.style.borderColor=C.gold;}} onBlur={e=>{e.target.style.borderColor=C.border.default;}}/>
              {errors.description&&<div style={{fontSize:11,color:C.error,marginTop:4}}>{errors.description}</div>}
            </div>
          </div>
        </div>

        {/* Pricing */}
        <div style={{background:C.obsidianPanel,border:`1px solid ${C.border.magenta}`,borderRadius:12,padding:22}}>
          <div style={{fontSize:11,fontWeight:700,color:C.magenta,letterSpacing:'0.12em',textTransform:'uppercase',marginBottom:18}}>Pricing & Inventory</div>
          <div style={{display:'grid',gridTemplateColumns:'1fr 100px 1fr',gap:14}}>
            <div>
              <label style={lbl}>Price <span style={{color:C.magenta}}>*</span></label>
              <input type="number" value={form.price} onChange={e=>set('price')(e.target.value)} placeholder="0.00" style={inp} onFocus={e=>{e.target.style.borderColor=C.magenta;}} onBlur={e=>{e.target.style.borderColor=C.border.default;}}/>
              {errors.price&&<div style={{fontSize:11,color:C.error,marginTop:4}}>{errors.price}</div>}
            </div>
            <div>
              <label style={lbl}>Currency</label>
              <select value={form.currency} onChange={e=>set('currency')(e.target.value)} style={sel}><option>KES</option><option>USD</option><option>EUR</option></select>
            </div>
            <div>
              <label style={lbl}>Stock <span style={{color:C.magenta}}>*</span></label>
              <input type="number" value={form.stock} onChange={e=>set('stock')(e.target.value)} placeholder="0" style={inp} onFocus={e=>{e.target.style.borderColor=C.magenta;}} onBlur={e=>{e.target.style.borderColor=C.border.default;}}/>
              {errors.stock&&<div style={{fontSize:11,color:C.error,marginTop:4}}>{errors.stock}</div>}
            </div>
          </div>
        </div>

        {/* Variants */}
        <div style={{background:C.obsidianPanel,border:`1px solid ${C.border.silver}`,borderRadius:12,padding:22}}>
          <div style={{fontSize:11,fontWeight:700,color:C.silver,letterSpacing:'0.12em',textTransform:'uppercase',marginBottom:18}}>Variants</div>
          <div style={{display:'flex',flexDirection:'column',gap:14}}>
            <TagInput label="Sizes" values={form.sizes} onChange={set('sizes')} suggestions={['XS','S','M','L','XL','XXL','28','30','32','34','36','One Size']}/>
            <TagInput label="Colours" values={form.colors} onChange={set('colors')} suggestions={['Black','White','Ivory','Obsidian','Slate','Khaki','Olive','Navy','Cream']}/>
          </div>
        </div>

        {/* Visibility toggle */}
        <div style={{background:C.obsidianPanel,border:`1px solid ${form.marketplace_visible?C.border.gold:C.border.default}`,borderRadius:12,padding:'18px 22px',display:'flex',alignItems:'center',justifyContent:'space-between',transition:'border-color 200ms'}}>
          <div>
            <div style={{fontWeight:600,fontSize:14,color:C.text.primary}}>List on Marketplace</div>
            <div style={{fontSize:12,color:C.text.secondary,marginTop:3}}>{form.marketplace_visible?'Visible to Cirvanna shoppers once published':'Stays private to your brand dashboard'}</div>
          </div>
          <button onClick={()=>set('marketplace_visible')(!form.marketplace_visible)} style={{width:48,height:26,borderRadius:13,border:'none',background:form.marketplace_visible?`linear-gradient(90deg,${C.gold},${C.magenta})`:C.obsidianCard,cursor:'pointer',position:'relative',transition:'all 250ms',boxShadow:form.marketplace_visible?`0 0 12px ${C.goldGlow}`:'none'}} aria-label="Toggle">
            <span style={{position:'absolute',top:3,borderRadius:'50%',width:20,height:20,background:'#fff',transition:'left 250ms',left:form.marketplace_visible?25:3,boxShadow:'0 1px 3px rgba(0,0,0,0.4)'}}/>
          </button>
        </div>

        <div style={{display:'flex',gap:12,justifyContent:'flex-end'}}>
          <button onClick={onCancel} style={{background:'none',border:`1px solid ${C.border.default}`,borderRadius:8,padding:'10px 20px',color:C.text.secondary,fontSize:13,cursor:'pointer'}}>Cancel</button>
          <GoldBtn onClick={handleSubmit} style={{opacity:submitting?0.7:1}}>{submitting?'Saving…':'Save as Draft'}</GoldBtn>
        </div>
      </div>
    </div>
  );
}

function ProductModal({product,onClose,onUpdate}){
  const [localStatus,setLocalStatus]=useState(product.status);
  const [localVisible,setLocalVisible]=useState(product.marketplace_visible);
  const save=()=>{onUpdate({...product,status:localStatus,marketplace_visible:localVisible});onClose();};
  return(
    <div style={{position:'fixed',inset:0,zIndex:200,background:'rgba(7,8,11,0.88)',backdropFilter:'blur(8px)',display:'flex',alignItems:'center',justifyContent:'center',padding:24}} onClick={onClose}>
      <div onClick={e=>e.stopPropagation()} style={{background:C.obsidianPanel,border:`1px solid ${C.border.gold}`,borderRadius:16,padding:32,width:'100%',maxWidth:520,boxShadow:`0 0 60px ${C.goldGlow}`}}>
        <div style={{display:'flex',justifyContent:'space-between',marginBottom:20}}>
          <div><div style={{fontSize:18,fontWeight:700,color:C.text.primary}}>{product.name}</div><div style={{fontSize:11,color:C.text.muted,fontFamily:'monospace',marginTop:3}}>{product.sku}</div></div>
          <button onClick={onClose} style={{background:'none',border:'none',color:C.text.secondary,fontSize:20,cursor:'pointer'}}>✕</button>
        </div>
        <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:12,marginBottom:20,background:C.obsidianCard,borderRadius:10,padding:16}}>
          {[{l:'Views',v:fmt(product.views),c:C.silver},{l:'Try-ons',v:fmt(product.tryons),c:C.gold},{l:'Saves',v:fmt(product.saves),c:C.magenta}].map(s=>(
            <div key={s.l} style={{textAlign:'center'}}><div style={{fontSize:20,fontWeight:700,color:s.c}}>{s.v}</div><div style={{fontSize:11,color:C.text.muted}}>{s.l}</div></div>
          ))}
        </div>
        <div style={{display:'flex',gap:8,marginBottom:16}}>
          {['draft','live','archived'].map(s=>{const m=statusMeta[s];return(
            <button key={s} onClick={()=>setLocalStatus(s)} style={{flex:1,padding:'8px',borderRadius:8,border:`1px solid ${localStatus===s?m.border:C.border.subtle}`,background:localStatus===s?m.bg:'transparent',color:localStatus===s?m.color:C.text.secondary,fontSize:12,fontWeight:localStatus===s?700:400,cursor:'pointer'}}>{s.charAt(0).toUpperCase()+s.slice(1)}</button>
          );})}
        </div>
        <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',padding:'12px 16px',background:C.obsidianCard,borderRadius:10,marginBottom:16}}>
          <span style={{fontSize:13,color:C.text.primary}}>Marketplace Visibility</span>
          <button onClick={()=>setLocalVisible(v=>!v)} style={{width:44,height:24,borderRadius:12,border:'none',background:localVisible?`linear-gradient(90deg,${C.gold},${C.magenta})`:C.obsidianCard,cursor:'pointer',position:'relative',transition:'all 250ms'}}>
            <span style={{position:'absolute',top:2,borderRadius:'50%',width:20,height:20,background:'#fff',left:localVisible?21:2,transition:'left 250ms'}}/>
          </button>
        </div>
        <div style={{display:'flex',gap:10}}>
          <button onClick={onClose} style={{flex:1,padding:'10px',borderRadius:8,border:`1px solid ${C.border.default}`,background:'none',color:C.text.secondary,fontSize:13,cursor:'pointer'}}>Discard</button>
          <GoldBtn onClick={save} style={{flex:1}}>Save Changes</GoldBtn>
        </div>
      </div>
    </div>
  );
}

export default function BrandDashboard(){
  const [tab,setTab]=useState('overview');
  const [products,setProducts]=useState(INITIAL_PRODUCTS);
  const [selected,setSelected]=useState(null);
  const [toast,setToast]=useState(null);

  const showToast=(msg)=>{setToast(msg);setTimeout(()=>setToast(null),3000);};
  const handleAdd=(p)=>{setProducts(prev=>[p,...prev]);setTab('products');showToast(`"${p.name}" saved as draft`);};
  const handleUpdate=(p)=>{setProducts(prev=>prev.map(x=>x.id===p.id?p:x));showToast(`"${p.name}" updated`);};

  const liveCount=products.filter(p=>p.status==='live').length;
  const totalViews=products.reduce((a,p)=>a+p.views,0);
  const totalTryons=products.reduce((a,p)=>a+p.tryons,0);
  const totalSaves=products.reduce((a,p)=>a+p.saves,0);

  const nav=[{id:'overview',label:'Overview',icon:'◈'},{id:'products',label:'Collection',icon:'⬡'},{id:'add-product',label:'Add Product',icon:'+'},{id:'analytics',label:'Analytics',icon:'◉'},{id:'assets',label:'Assets',icon:'⬢'}];

  return(
    <div style={{minHeight:'100vh',background:C.obsidian,fontFamily:'"Inter",-apple-system,sans-serif',color:C.text.primary,display:'flex'}}>
      {selected&&<ProductModal product={selected} onClose={()=>setSelected(null)} onUpdate={p=>{handleUpdate(p);setSelected(null);}}/>}
      {toast&&<div style={{position:'fixed',bottom:24,right:24,zIndex:300,background:C.obsidianCard,border:`1px solid ${C.border.gold}`,borderRadius:10,padding:'12px 20px',fontSize:13,color:C.gold,boxShadow:`0 0 20px ${C.goldGlow}`}}>✓ {toast}</div>}

      {/* Sidebar */}
      <aside style={{width:210,flexShrink:0,background:C.obsidianDeep,borderRight:`1px solid ${C.border.subtle}`,display:'flex',flexDirection:'column',position:'fixed',top:0,bottom:0,left:0}}>
        <div style={{height:3,background:`linear-gradient(90deg,${C.gold},${C.magenta},${C.gold})`}}/>
        <div style={{padding:'22px 18px 18px',borderBottom:`1px solid ${C.border.subtle}`}}>
          <div style={{width:44,height:44,borderRadius:10,background:`linear-gradient(135deg,${C.gold},${C.magenta})`,display:'flex',alignItems:'center',justifyContent:'center',fontWeight:800,fontSize:15,color:'#07080B',marginBottom:10,boxShadow:`0 0 16px ${C.goldGlow}`}}>{BRAND.logo_initial}</div>
          <div style={{fontWeight:700,fontSize:14,color:C.text.primary}}>{BRAND.name}</div>
          <div style={{fontSize:11,color:C.text.muted,marginTop:2}}>{BRAND.category}</div>
          <div style={{marginTop:8,display:'inline-flex',alignItems:'center',gap:5}}><span style={{width:6,height:6,borderRadius:'50%',background:C.success}}/><span style={{fontSize:10,color:C.success,fontWeight:600}}>APPROVED</span></div>
        </div>
        <nav style={{flex:1,padding:'14px 10px',display:'flex',flexDirection:'column',gap:2}}>
          {nav.map(item=>{const active=tab===item.id;const isAdd=item.id==='add-product';return(
            <button key={item.id} onClick={()=>setTab(item.id)} style={{display:'flex',alignItems:'center',gap:10,padding:'9px 12px',borderRadius:8,border:'none',background:active?(isAdd?C.magentaSubtle:C.goldSubtle):'transparent',color:active?(isAdd?C.magenta:C.gold):C.text.secondary,fontSize:13,fontWeight:active?600:400,cursor:'pointer',textAlign:'left',transition:'all 150ms',borderLeft:active?`2px solid ${isAdd?C.magenta:C.gold}`:'2px solid transparent'}}>
              <span style={{fontSize:13,opacity:0.8}}>{item.icon}</span>{item.label}
            </button>
          );})}
        </nav>
        <div style={{padding:'14px 18px',borderTop:`1px solid ${C.border.subtle}`}}>
          <div style={{fontSize:10,color:C.text.muted,fontFamily:'monospace'}}>{BRAND.id}</div>
          <div style={{fontSize:10,color:C.text.muted,marginTop:2}}>Brand Portal · {BRAND.country}</div>
        </div>
      </aside>

      <main style={{marginLeft:210,flex:1,padding:'36px 44px',minWidth:0}}>

        {/* Overview */}
        {tab==='overview'&&(
          <div>
            <div style={{marginBottom:32}}>
              <h1 style={{fontSize:30,fontWeight:800,margin:0,letterSpacing:'-0.02em'}}>
                <span style={{color:C.text.primary}}>Welcome back, </span>
                <span style={{background:`linear-gradient(135deg,${C.gold},${C.magentaBright})`,WebkitBackgroundClip:'text',WebkitTextFillColor:'transparent'}}>{BRAND.name}</span>
              </h1>
              <p style={{color:C.text.secondary,fontSize:14,margin:'8px 0 0'}}>Your private atelier dashboard. All data is exclusive to your brand.</p>
            </div>
            <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:14,marginBottom:28}}>
              <StatCard label="Products Live" value={String(liveCount)} sub={`of ${products.length} total`} accent={C.success}/>
              <StatCard label="Total Views" value={fmt(totalViews)} sub="Last 30 days" accent={C.silver}/>
              <StatCard label="Virtual Try-Ons" value={fmt(totalTryons)} sub="↑ 18% this week" accent={C.gold}/>
              <StatCard label="Saves" value={fmt(totalSaves)} sub="Wishlisted" accent={C.magenta}/>
            </div>
            <div style={{display:'flex',gap:12,marginBottom:36}}>
              <MagentaBtn onClick={()=>setTab('add-product')}>+ Add New Product</MagentaBtn>
              <GoldBtn onClick={()=>setTab('products')}>Manage Collection</GoldBtn>
            </div>
            <div style={{fontSize:11,fontWeight:700,color:C.text.muted,letterSpacing:'0.1em',textTransform:'uppercase',marginBottom:14}}>Recent Products</div>
            <div style={{display:'flex',flexDirection:'column',gap:8}}>
              {products.slice(0,3).map(p=>(
                <div key={p.id} onClick={()=>setSelected(p)} style={{display:'flex',alignItems:'center',gap:14,background:C.obsidianPanel,border:`1px solid ${C.border.subtle}`,borderRadius:10,padding:'13px 16px',cursor:'pointer',transition:'all 150ms'}} onMouseEnter={e=>{e.currentTarget.style.borderColor=C.border.gold;}} onMouseLeave={e=>{e.currentTarget.style.borderColor=C.border.subtle;}}>
                  <div style={{width:38,height:38,borderRadius:8,background:`linear-gradient(135deg,${C.obsidianCard},${C.obsidianHover})`,border:`1px solid ${C.border.default}`,flexShrink:0,display:'flex',alignItems:'center',justifyContent:'center',fontSize:15}}>⬡</div>
                  <div style={{flex:1}}><div style={{fontSize:13,fontWeight:600,color:C.text.primary}}>{p.name}</div><div style={{fontSize:11,color:C.text.muted}}>{p.category} · {fmtKES(p.price)}</div></div>
                  <StatusPill status={p.status}/>
                  <div style={{fontSize:12,color:C.gold,fontFamily:'monospace'}}>{fmt(p.tryons)} try-ons</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Collection */}
        {tab==='products'&&(
          <div>
            <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:24}}>
              <div><h1 style={{fontSize:26,fontWeight:800,margin:0}}>Your Collection</h1><p style={{color:C.text.secondary,fontSize:13,margin:'6px 0 0'}}>{products.length} products · {liveCount} live</p></div>
              <MagentaBtn onClick={()=>setTab('add-product')}>+ Add Product</MagentaBtn>
            </div>
            <div style={{background:C.obsidianPanel,border:`1px solid ${C.border.default}`,borderRadius:12,overflow:'hidden'}}>
              <div style={{display:'grid',gridTemplateColumns:'2fr 110px 100px 90px 80px 90px 80px',gap:10,padding:'10px 18px',borderBottom:`1px solid ${C.border.subtle}`,background:C.obsidianCard}}>
                {['Product','Category','Price','Try-ons','Views','Status','Market'].map(h=><span key={h} style={{fontSize:9,fontWeight:800,color:C.text.muted,letterSpacing:'0.12em',textTransform:'uppercase'}}>{h}</span>)}
              </div>
              {products.map((p,i)=>(
                <div key={p.id} onClick={()=>setSelected(p)} style={{display:'grid',gridTemplateColumns:'2fr 110px 100px 90px 80px 90px 80px',gap:10,padding:'13px 18px',cursor:'pointer',borderBottom:i<products.length-1?`1px solid ${C.border.subtle}`:'none',transition:'background 150ms',alignItems:'center'}} onMouseEnter={e=>{e.currentTarget.style.background=C.obsidianHover;}} onMouseLeave={e=>{e.currentTarget.style.background='transparent';}}>
                  <div><div style={{fontSize:13,fontWeight:600,color:C.text.primary}}>{p.name}</div><div style={{fontSize:10,color:C.text.muted,fontFamily:'monospace'}}>{p.sku}</div></div>
                  <div style={{fontSize:12,color:C.text.secondary}}>{p.category}</div>
                  <div style={{fontSize:12,color:C.silver,fontFamily:'monospace'}}>{fmtKES(p.price)}</div>
                  <div style={{fontSize:13,color:C.gold,fontFamily:'monospace',fontWeight:600}}>{fmt(p.tryons)}</div>
                  <div style={{fontSize:12,color:C.text.secondary,fontFamily:'monospace'}}>{fmt(p.views)}</div>
                  <StatusPill status={p.status}/>
                  <span style={{fontSize:10,padding:'3px 7px',borderRadius:5,fontWeight:700,background:p.marketplace_visible?C.magentaSubtle:C.silverSubtle,color:p.marketplace_visible?C.magenta:C.text.muted,border:`1px solid ${p.marketplace_visible?C.border.magenta:C.border.subtle}`}}>{p.marketplace_visible?'Listed':'Hidden'}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Add Product */}
        {tab==='add-product'&&<AddProductForm onAdd={handleAdd} onCancel={()=>setTab('products')}/>}

        {/* Analytics */}
        {tab==='analytics'&&(
          <div>
            <h1 style={{fontSize:26,fontWeight:800,margin:'0 0 6px'}}>Analytics</h1>
            <p style={{color:C.text.secondary,fontSize:13,margin:'0 0 28px'}}>Your brand performance — visible only to you.</p>
            <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:14,marginBottom:28}}>
              <StatCard label="Conversion Rate" value="3.4%" sub="Views → Purchase" accent={C.success}/>
              <StatCard label="Avg. Session" value="4m 22s" sub="On brand products" accent={C.silver}/>
              <StatCard label="Return Visitors" value="61%" sub="Last 30 days" accent={C.magenta}/>
            </div>
            <div style={{background:C.obsidianPanel,border:`1px solid ${C.border.default}`,borderRadius:12,padding:22}}>
              <div style={{fontSize:11,fontWeight:700,color:C.text.muted,letterSpacing:'0.1em',textTransform:'uppercase',marginBottom:18}}>Top Products by Try-ons</div>
              {products.filter(p=>p.tryons>0).sort((a,b)=>b.tryons-a.tryons).map((p,i)=>(
                <div key={p.id} style={{display:'flex',alignItems:'center',gap:14,padding:'11px 0',borderBottom:`1px solid ${C.border.subtle}`}}>
                  <span style={{fontSize:11,color:C.text.muted,width:22,flexShrink:0}}>{String(i+1).padStart(2,'0')}</span>
                  <span style={{flex:1,fontSize:13,color:C.text.primary}}>{p.name}</span>
                  <div style={{width:120,height:4,background:C.obsidianCard,borderRadius:2,overflow:'hidden'}}><div style={{height:'100%',borderRadius:2,background:`linear-gradient(90deg,${C.gold},${C.magenta})`,width:`${(p.tryons/Math.max(...products.map(x=>x.tryons)))*100}%`}}/></div>
                  <span style={{fontSize:13,color:C.gold,fontFamily:'monospace',fontWeight:600,width:56,textAlign:'right'}}>{fmt(p.tryons)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Assets */}
        {tab==='assets'&&(
          <div>
            <h1 style={{fontSize:26,fontWeight:800,margin:'0 0 6px'}}>Asset Library</h1>
            <p style={{color:C.text.secondary,fontSize:13,margin:'0 0 28px'}}>Private storage — only your brand can access these files.</p>
            <div style={{border:`2px dashed ${C.border.gold}`,borderRadius:14,padding:'56px 28px',textAlign:'center',background:C.goldSubtle,cursor:'pointer'}}>
              <div style={{fontSize:36,marginBottom:14}}>⬆</div>
              <div style={{fontSize:16,fontWeight:600,color:C.text.primary,marginBottom:6}}>Drop product images here</div>
              <div style={{fontSize:13,color:C.text.secondary}}>PNG · JPG · WebP — max 50 MB · Signed upload, stored privately</div>
              <GoldBtn style={{marginTop:18}} onClick={()=>{}}>Choose Files</GoldBtn>
            </div>
            <div style={{marginTop:16,background:C.obsidianPanel,border:`1px solid ${C.border.default}`,borderRadius:10,padding:'14px 18px'}}>
              <div style={{fontSize:11,color:C.text.muted,marginBottom:4}}>Storage Path</div>
              <div style={{fontSize:12,color:C.gold,fontFamily:'monospace'}}>gs://cirvanna-brand-assets/{BRAND.id}/</div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
