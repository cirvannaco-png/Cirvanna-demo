'use client';

import { useState, useEffect, useCallback } from "react";

// ─── Design Tokens ─────────────────────────────────────────────────────────────
// Obsidian + Magenta (dominant — sovereignty) + Gold (brand tracking) + Silver (system data)
// Signature: magenta-to-gold gradient header communicating "you own all of this"
const C = {
  obsidian:      '#07080B',
  obsidianDeep:  '#050608',
  obsidianPanel: '#0E1016',
  obsidianCard:  '#161820',
  obsidianHover: '#1C1F2A',

  gold:          '#C9A84C',
  goldLight:     '#E2C46E',
  goldDim:       '#7A6130',
  goldGlow:      'rgba(201,168,76,0.20)',
  goldSubtle:    'rgba(201,168,76,0.08)',

  silver:        '#B8BEC8',
  silverLight:   '#D4D8E0',
  silverDim:     '#5A6070',
  silverSubtle:  'rgba(184,190,200,0.07)',

  magenta:       '#C026D3',
  magentaBright: '#E040FB',
  magentaLight:  '#F06AFF',
  magentaDim:    '#6B1275',
  magentaGlow:   'rgba(192,38,211,0.25)',
  magentaSubtle: 'rgba(192,38,211,0.10)',

  success:  '#22C55E',
  warning:  '#F59E0B',
  error:    '#EF4444',
  info:     '#38BDF8',

  text: {
    primary:   '#F0F1F4',
    secondary: '#8B909C',
    muted:     '#45505F',
    gold:      '#C9A84C',
    magenta:   '#E040FB',
    silver:    '#B8BEC8',
  },
  border: {
    subtle:  'rgba(255,255,255,0.045)',
    default: 'rgba(255,255,255,0.08)',
    strong:  'rgba(255,255,255,0.14)',
    gold:    'rgba(201,168,76,0.28)',
    magenta: 'rgba(192,38,211,0.35)',
    silver:  'rgba(184,190,200,0.15)',
  },
};

// ─── Types ─────────────────────────────────────────────────────────────────────
type Tab = 'command' | 'brands' | 'marketplace' | 'platform' | 'ai' | 'system';
type ProductStatus = 'draft' | 'live' | 'archived';
type BrandStatus = 'pending' | 'approved' | 'suspended';
type AutonomyLevel = 'full_auto' | 'approval_required' | 'manual_only';

interface BrandRecord {
  id: string;
  name: string;
  category: string;
  country: string;
  status: BrandStatus;
  product_count: number;
  live_count: number;
  total_revenue: number;
  joined: string;
  logo: string;
}

interface MarketplaceProduct {
  id: string;
  brand_id: string;
  brand_name: string;
  name: string;
  category: string;
  price: number;
  status: ProductStatus;
  marketplace_visible: boolean;
  founder_override_hidden: boolean;
  tryons: number;
  views: number;
  saves: number;
  flagged: boolean;
  flag_reason?: string;
  sku: string;
}

interface PAMASMMAAction {
  id: string;
  system: string;
  systemCode: string;
  action: string;
  target: string;
  score: number;
  time: string;
  requires_approval: boolean;
  approved?: boolean;
}

interface SystemAlert {
  id: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  message: string;
  component: string;
  time: string;
}

// ─── Mock Data ──────────────────────────────────────────────────────────────────
const MOCK_BRANDS: BrandRecord[] = [
  { id: 'b1', name: 'Maison Ndovu', category: 'Luxury Streetwear', country: 'Kenya', status: 'approved', product_count: 12, live_count: 9, total_revenue: 2840000, joined: '2026-05-01', logo: 'MN' },
  { id: 'b2', name: 'Savanna Studio', category: 'Sustainable Fashion', country: 'Kenya', status: 'approved', product_count: 7, live_count: 5, total_revenue: 920000, joined: '2026-05-15', logo: 'SS' },
  { id: 'b3', name: 'Urbancore KE', category: 'Streetwear', country: 'Kenya', status: 'pending', product_count: 3, live_count: 0, total_revenue: 0, joined: '2026-06-13', logo: 'UK' },
  { id: 'b4', name: 'Kente Arc', category: 'Heritage Fashion', country: 'Ghana', status: 'approved', product_count: 18, live_count: 14, total_revenue: 1650000, joined: '2026-04-10', logo: 'KA' },
  { id: 'b5', name: 'Fake Luxe Co', category: 'Accessories', country: 'Unknown', status: 'suspended', product_count: 4, live_count: 0, total_revenue: 0, joined: '2026-04-20', logo: 'FL' },
];

const MOCK_PRODUCTS: MarketplaceProduct[] = [
  { id: 'p1', brand_id: 'b1', brand_name: 'Maison Ndovu', name: 'Obsidian Technical Jacket', category: 'Outerwear', price: 42000, status: 'live', marketplace_visible: true, founder_override_hidden: false, tryons: 847, views: 3241, saves: 312, flagged: false, sku: 'MTJ-001' },
  { id: 'p2', brand_id: 'b1', brand_name: 'Maison Ndovu', name: 'Archive Print Tee Vol.3', category: 'Tops', price: 4800, status: 'live', marketplace_visible: true, founder_override_hidden: false, tryons: 512, views: 1890, saves: 201, flagged: false, sku: 'APT-003' },
  { id: 'p3', brand_id: 'b2', brand_name: 'Savanna Studio', name: 'Recycled Linen Coat', category: 'Outerwear', price: 28000, status: 'live', marketplace_visible: true, founder_override_hidden: false, tryons: 334, views: 1200, saves: 145, flagged: false, sku: 'RLC-001' },
  { id: 'p4', brand_id: 'b4', brand_name: 'Kente Arc', name: 'Silk Kente Blazer', category: 'Tops', price: 65000, status: 'live', marketplace_visible: true, founder_override_hidden: false, tryons: 621, views: 2800, saves: 388, flagged: false, sku: 'SKB-007' },
  { id: 'p5', brand_id: 'b5', brand_name: 'Fake Luxe Co', name: 'Replica Signature Belt', category: 'Accessories', price: 3200, status: 'archived', marketplace_visible: false, founder_override_hidden: true, tryons: 0, views: 94, saves: 2, flagged: true, flag_reason: 'Suspected IP violation — trademarked logo', sku: 'RSB-001' },
  { id: 'p6', brand_id: 'b3', brand_name: 'Urbancore KE', name: 'Cargo Drop Trouser', category: 'Bottoms', price: 9500, status: 'draft', marketplace_visible: false, founder_override_hidden: false, tryons: 0, views: 0, saves: 0, flagged: false, sku: 'CDT-002' },
];

const MOCK_ACTIONS: PAMASMMAAction[] = [
  { id: 'a1', system: 'Relationship Management', systemCode: 'S3', action: 'draft_support_response', target: 'user_7f3a', score: 8.4, time: '09:11', requires_approval: false },
  { id: 'a2', system: 'Marketing Intelligence', systemCode: 'S2', action: 'generate_brand_narrative', target: 'Maison Ndovu', score: 9.1, time: '08:55', requires_approval: false },
  { id: 'a3', system: 'Executive Operations', systemCode: 'S1', action: 'suspend_brand', target: 'Fake Luxe Co', score: 9.4, time: '08:30', requires_approval: true, approved: undefined },
  { id: 'a4', system: 'Persuasion Governance', systemCode: 'S8', action: 'ethics_audit', target: 'campaign_c12', score: 9.3, time: '07:00', requires_approval: false },
  { id: 'a5', system: 'Strategic Narrative', systemCode: 'S10', action: 'weekly_review', target: 'platform', score: 9.5, time: '06:00', requires_approval: true, approved: undefined },
];

const MOCK_ALERTS: SystemAlert[] = [
  { id: 'al1', severity: 'medium', message: 'USI index stale — oldest embedding 26.1h', component: 'pgvector', time: '07:00' },
  { id: 'al2', severity: 'low', message: 'IDM-VTON queue latency: 8.2s avg (target <5s)', component: 'replicate', time: '08:45' },
];

// ─── Helpers ───────────────────────────────────────────────────────────────────
const fmt = (n: number) => n.toLocaleString();
const fmtKES = (n: number) => `KES ${n.toLocaleString()}`;

const brandStatusMeta: Record<BrandStatus, { color: string; bg: string; border: string; label: string }> = {
  approved:  { color: C.success,   bg: 'rgba(34,197,94,0.1)',   border: 'rgba(34,197,94,0.25)',   label: 'Approved' },
  pending:   { color: C.warning,   bg: 'rgba(245,158,11,0.1)',  border: 'rgba(245,158,11,0.25)',  label: 'Pending' },
  suspended: { color: C.error,     bg: 'rgba(239,68,68,0.1)',   border: 'rgba(239,68,68,0.25)',   label: 'Suspended' },
};

const alertColor: Record<string, string> = {
  critical: C.error, high: '#F97316', medium: C.warning, low: C.info,
};

// ─── Shared UI ─────────────────────────────────────────────────────────────────

function StatusPill({ status }: { status: BrandStatus }) {
  const m = brandStatusMeta[status];
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '3px 10px', borderRadius: 99, fontSize: 10, fontWeight: 700,
      letterSpacing: '0.06em', textTransform: 'uppercase',
      background: m.bg, color: m.color, border: `1px solid ${m.border}`,
    }}>
      <span style={{ width: 5, height: 5, borderRadius: '50%', background: m.color }} />
      {m.label}
    </span>
  );
}

function MagentaBtn({ children, onClick, small, style }: any) {
  const [hov, setHov] = useState(false);
  return (
    <button onClick={onClick}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
      style={{
        background: hov
          ? `linear-gradient(135deg, ${C.magentaBright}, ${C.magenta})`
          : `linear-gradient(135deg, ${C.magenta}, ${C.magentaDim})`,
        color: '#fff', border: 'none', borderRadius: small ? 6 : 8,
        padding: small ? '6px 12px' : '9px 18px',
        fontWeight: 700, fontSize: small ? 11 : 13,
        cursor: 'pointer', transition: 'all 180ms ease',
        boxShadow: hov ? `0 0 20px ${C.magentaGlow}` : 'none',
        ...style,
      }}>
      {children}
    </button>
  );
}

function GoldBtn({ children, onClick, small, style }: any) {
  const [hov, setHov] = useState(false);
  return (
    <button onClick={onClick}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
      style={{
        background: hov
          ? `linear-gradient(135deg, ${C.goldLight}, ${C.gold})`
          : `linear-gradient(135deg, ${C.gold}, ${C.goldDim})`,
        color: '#07080B', border: 'none', borderRadius: small ? 6 : 8,
        padding: small ? '6px 12px' : '9px 18px',
        fontWeight: 700, fontSize: small ? 11 : 13,
        cursor: 'pointer', transition: 'all 180ms ease',
        boxShadow: hov ? `0 0 18px ${C.goldGlow}` : 'none',
        ...style,
      }}>
      {children}
    </button>
  );
}

function GhostBtn({ children, onClick, small }: any) {
  return (
    <button onClick={onClick} style={{
      background: 'none', border: `1px solid ${C.border.default}`,
      borderRadius: small ? 6 : 8,
      padding: small ? '5px 11px' : '8px 16px',
      color: C.text.secondary, fontSize: small ? 11 : 13,
      cursor: 'pointer', transition: 'all 150ms',
    }}
      onMouseEnter={e => { (e.currentTarget as any).style.borderColor = C.border.silver; (e.currentTarget as any).style.color = C.silver; }}
      onMouseLeave={e => { (e.currentTarget as any).style.borderColor = C.border.default; (e.currentTarget as any).style.color = C.text.secondary; }}
    >
      {children}
    </button>
  );
}

function MetricCard({ label, value, sub, topColor, icon }: { label: string; value: string; sub?: string; topColor: string; icon?: string }) {
  return (
    <div style={{
      background: C.obsidianPanel, borderRadius: 12,
      border: `1px solid ${C.border.subtle}`,
      borderTop: `2px solid ${topColor}`,
      padding: '18px 20px',
      boxShadow: `0 2px 16px rgba(0,0,0,0.3)`,
    }}>
      {icon && <div style={{ fontSize: 18, marginBottom: 8, color: topColor }}>{icon}</div>}
      <div style={{ fontSize: 10, color: C.text.muted, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 8, fontWeight: 700 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 800, color: C.text.primary, fontVariantNumeric: 'tabular-nums' }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: topColor, marginTop: 5 }}>{sub}</div>}
    </div>
  );
}

function SectionHeading({ children, accent }: { children: React.ReactNode; accent?: string }) {
  return (
    <div style={{
      fontSize: 10, fontWeight: 800, letterSpacing: '0.14em',
      textTransform: 'uppercase', color: accent || C.text.muted,
      marginBottom: 14,
    }}>
      {children}
    </div>
  );
}

// ─── Toggle ────────────────────────────────────────────────────────────────────
function Toggle({ value, onChange, onColor }: { value: boolean; onChange: (v: boolean) => void; onColor?: string }) {
  return (
    <button
      onClick={() => onChange(!value)}
      aria-label="Toggle"
      style={{
        width: 44, height: 24, borderRadius: 12, border: 'none',
        background: value
          ? (onColor || `linear-gradient(90deg, ${C.magenta}, ${C.gold})`)
          : C.obsidianCard,
        cursor: 'pointer', position: 'relative',
        transition: 'background 250ms ease',
        boxShadow: value ? `0 0 10px ${C.magentaGlow}` : 'none',
        flexShrink: 0,
      }}
    >
      <span style={{
        position: 'absolute', top: 2, left: value ? 21 : 2,
        width: 20, height: 20, borderRadius: '50%', background: '#fff',
        transition: 'left 250ms ease',
        boxShadow: '0 1px 4px rgba(0,0,0,0.4)',
      }} />
    </button>
  );
}

// ─── Add Product (Founder) Form ────────────────────────────────────────────────
function FounderAddProduct({ brands, onAdd, onCancel }: {
  brands: BrandRecord[];
  onAdd: (p: MarketplaceProduct) => void;
  onCancel: () => void;
}) {
  const approvedBrands = brands.filter(b => b.status === 'approved');
  const [form, setForm] = useState({
    brand_id: approvedBrands[0]?.id || '',
    name: '', sku: '', category: 'Outerwear', price: '',
    description: '', marketplace_visible: true,
  });
  const [saving, setSaving] = useState(false);
  const set = (k: string) => (v: any) => setForm(f => ({ ...f, [k]: v }));

  const handleSubmit = async () => {
    if (!form.name || !form.sku || !form.price) return;
    setSaving(true);
    await new Promise(r => setTimeout(r, 700));
    const brand = brands.find(b => b.id === form.brand_id);
    onAdd({
      id: 'p_' + Date.now(),
      brand_id: form.brand_id,
      brand_name: brand?.name || '',
      name: form.name,
      sku: form.sku,
      category: form.category,
      price: Number(form.price),
      status: 'live',
      marketplace_visible: form.marketplace_visible,
      founder_override_hidden: false,
      tryons: 0, views: 0, saves: 0,
      flagged: false,
    });
    setSaving(false);
  };

  const inputStyle: React.CSSProperties = {
    width: '100%', background: C.obsidianDeep,
    border: `1px solid ${C.border.default}`,
    borderRadius: 8, padding: '10px 14px',
    fontSize: 14, color: C.text.primary,
    outline: 'none', boxSizing: 'border-box', fontFamily: 'inherit',
  };
  const labelStyle: React.CSSProperties = {
    fontSize: 10, fontWeight: 700, color: C.silver,
    letterSpacing: '0.1em', textTransform: 'uppercase',
    display: 'block', marginBottom: 6,
  };

  return (
    <div style={{ maxWidth: 660 }}>
      <div style={{ marginBottom: 28 }}>
        <h2 style={{
          fontSize: 26, fontWeight: 800, margin: 0,
          background: `linear-gradient(135deg, ${C.magentaBright}, ${C.gold})`,
          WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
        }}>
          Add Product to Marketplace
        </h2>
        <p style={{ color: C.text.secondary, fontSize: 13, margin: '8px 0 0' }}>
          As founder, you can add products on behalf of any approved brand and set their marketplace visibility immediately.
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Brand selector */}
        <div style={{ background: C.obsidianPanel, border: `1px solid ${C.border.magenta}`, borderRadius: 12, padding: 20 }}>
          <SectionHeading accent={C.magenta}>Assign to Brand</SectionHeading>
          <label style={labelStyle}>Brand</label>
          <select value={form.brand_id} onChange={e => set('brand_id')(e.target.value)}
            style={{ ...inputStyle, cursor: 'pointer' }}>
            {approvedBrands.map(b => <option key={b.id} value={b.id}>{b.name} — {b.category}</option>)}
          </select>
        </div>

        {/* Product info */}
        <div style={{ background: C.obsidianPanel, border: `1px solid ${C.border.gold}`, borderRadius: 12, padding: 20 }}>
          <SectionHeading accent={C.gold}>Product Details</SectionHeading>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={labelStyle}>Product Name <span style={{ color: C.magenta }}>*</span></label>
              <input value={form.name} onChange={e => set('name')(e.target.value)} placeholder="e.g. Heritage Silk Kaftan" style={inputStyle}
                onFocus={e => { e.target.style.borderColor = C.gold; }} onBlur={e => { e.target.style.borderColor = C.border.default; }} />
            </div>
            <div>
              <label style={labelStyle}>SKU <span style={{ color: C.magenta }}>*</span></label>
              <input value={form.sku} onChange={e => set('sku')(e.target.value)} placeholder="e.g. HSK-001" style={inputStyle}
                onFocus={e => { e.target.style.borderColor = C.gold; }} onBlur={e => { e.target.style.borderColor = C.border.default; }} />
            </div>
            <div>
              <label style={labelStyle}>Category</label>
              <select value={form.category} onChange={e => set('category')(e.target.value)} style={{ ...inputStyle, cursor: 'pointer' }}>
                {['Outerwear','Tops','Bottoms','Dresses','Sets','Footwear','Accessories'].map(c =>
                  <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Price (KES) <span style={{ color: C.magenta }}>*</span></label>
              <input type="number" value={form.price} onChange={e => set('price')(e.target.value)} placeholder="0.00" style={inputStyle}
                onFocus={e => { e.target.style.borderColor = C.gold; }} onBlur={e => { e.target.style.borderColor = C.border.default; }} />
            </div>
          </div>
        </div>

        {/* Visibility — founder controls this directly */}
        <div style={{
          background: C.obsidianPanel,
          border: `1px solid ${form.marketplace_visible ? C.border.magenta : C.border.subtle}`,
          borderRadius: 12, padding: '16px 20px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          transition: 'border-color 200ms',
        }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: C.text.primary }}>Publish to Marketplace Immediately</div>
            <div style={{ fontSize: 12, color: C.text.secondary, marginTop: 3 }}>
              {form.marketplace_visible
                ? 'Listing goes live as soon as you save — no brand action required'
                : 'Product created but hidden — brand can publish from their dashboard'}
            </div>
          </div>
          <Toggle value={form.marketplace_visible} onChange={set('marketplace_visible')} />
        </div>

        <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
          <GhostBtn onClick={onCancel}>Cancel</GhostBtn>
          <MagentaBtn onClick={handleSubmit} style={{ opacity: saving ? 0.7 : 1 }}>
            {saving ? 'Publishing…' : form.marketplace_visible ? 'Publish to Marketplace' : 'Save as Draft'}
          </MagentaBtn>
        </div>
      </div>
    </div>
  );
}

// ─── Main Control Panel ────────────────────────────────────────────────────────
export default function FounderControlPanel() {
  const [tab, setTab] = useState<Tab>('command');
  const [brands, setBrands] = useState<BrandRecord[]>(MOCK_BRANDS);
  const [products, setProducts] = useState<MarketplaceProduct[]>(MOCK_PRODUCTS);
  const [actions, setActions] = useState<PAMASMMAAction[]>(MOCK_ACTIONS);
  const [autonomy, setAutonomy] = useState<AutonomyLevel>('full_auto');
  const [clock, setClock] = useState(new Date());
  const [toast, setToast] = useState<{ msg: string; type: 'gold' | 'magenta' | 'error' } | null>(null);
  const [showAddProduct, setShowAddProduct] = useState(false);
  const [selectedBrand, setSelectedBrand] = useState<BrandRecord | null>(null);
  const [circuitBreakers, setCircuitBreakers] = useState({ qdrant: true, replicate: true, anthropic: true, gcs: true });

  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const showToast = useCallback((msg: string, type: 'gold' | 'magenta' | 'error' = 'magenta') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3200);
  }, []);

  // Brand actions
  const handleBrandDecision = (id: string, decision: 'approve' | 'suspend' | 'reinstate') => {
    const newStatus: BrandStatus = decision === 'approve' || decision === 'reinstate' ? 'approved' : 'suspended';
    setBrands(prev => prev.map(b => b.id === id ? { ...b, status: newStatus } : b));
    const brand = brands.find(b => b.id === id);
    showToast(`${brand?.name} ${decision}d`, decision === 'suspend' ? 'error' : 'gold');
  };

  // Marketplace: founder override toggle
  const handleProductVisibility = (id: string, visible: boolean) => {
    setProducts(prev => prev.map(p => p.id === id
      ? { ...p, marketplace_visible: visible, founder_override_hidden: !visible }
      : p));
    const p = products.find(x => x.id === id);
    showToast(`"${p?.name}" ${visible ? 'shown on' : 'hidden from'} marketplace`, visible ? 'gold' : 'magenta');
  };

  // PAMASMMA override decisions
  const handleActionDecision = (id: string, approved: boolean) => {
    setActions(prev => prev.map(a => a.id === id ? { ...a, approved } : a));
    showToast(`Action ${approved ? 'approved' : 'rejected'}`, approved ? 'gold' : 'error');
  };

  const handleAddProduct = (p: MarketplaceProduct) => {
    setProducts(prev => [p, ...prev]);
    setShowAddProduct(false);
    showToast(`"${p.name}" added to marketplace`, 'magenta');
  };

  // Stats
  const approvedBrands = brands.filter(b => b.status === 'approved').length;
  const pendingBrands = brands.filter(b => b.status === 'pending').length;
  const liveProducts = products.filter(p => p.status === 'live' && p.marketplace_visible && !p.founder_override_hidden).length;
  const totalRevenue = brands.reduce((a, b) => a + b.total_revenue, 0);
  const pendingActions = actions.filter(a => a.requires_approval && a.approved === undefined).length;

  const navItems: { id: Tab; label: string; icon: string; badge?: number }[] = [
    { id: 'command', label: 'PAMASMMA', icon: '◈', badge: pendingActions },
    { id: 'brands', label: 'Brands', icon: '⬡', badge: pendingBrands },
    { id: 'marketplace', label: 'Marketplace', icon: '◉' },
    { id: 'platform', label: 'Platform', icon: '⬢' },
    { id: 'ai', label: 'AI Systems', icon: '◇', badge: MOCK_ALERTS.length },
    { id: 'system', label: 'Controls', icon: '⊞' },
  ];

  const toastColors: Record<string, string> = {
    gold: C.gold, magenta: C.magenta, error: C.error,
  };

  return (
    <div style={{
      minHeight: '100vh', background: C.obsidian,
      fontFamily: '"Inter", -apple-system, sans-serif',
      color: C.text.primary, display: 'flex', flexDirection: 'column',
    }}>

      {/* Toast */}
      {toast && (
        <div style={{
          position: 'fixed', bottom: 28, right: 28, zIndex: 500,
          background: C.obsidianCard,
          border: `1px solid ${toastColors[toast.type]}60`,
          borderRadius: 10, padding: '12px 20px', fontSize: 13,
          color: toastColors[toast.type],
          boxShadow: `0 0 24px ${toastColors[toast.type]}30`,
        }}>
          {toast.type === 'error' ? '✕' : '✓'} {toast.msg}
        </div>
      )}

      {/* Brand detail modal */}
      {selectedBrand && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 200,
          background: 'rgba(5,6,8,0.88)', backdropFilter: 'blur(10px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24,
        }} onClick={() => setSelectedBrand(null)}>
          <div onClick={e => e.stopPropagation()} style={{
            background: C.obsidianPanel,
            border: `1px solid ${C.border.magenta}`,
            borderRadius: 16, padding: 32, width: '100%', maxWidth: 520,
            boxShadow: `0 0 60px ${C.magentaGlow}`,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                <div style={{
                  width: 48, height: 48, borderRadius: 10,
                  background: `linear-gradient(135deg, ${C.magenta}, ${C.gold})`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontWeight: 800, fontSize: 15, color: '#07080B',
                }}>
                  {selectedBrand.logo}
                </div>
                <div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: C.text.primary }}>{selectedBrand.name}</div>
                  <div style={{ fontSize: 12, color: C.text.muted }}>{selectedBrand.category} · {selectedBrand.country}</div>
                </div>
              </div>
              <button onClick={() => setSelectedBrand(null)} style={{ background: 'none', border: 'none', color: C.text.secondary, fontSize: 20, cursor: 'pointer' }}>✕</button>
            </div>

            {/* Stats */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 24 }}>
              {[
                { label: 'Products', value: String(selectedBrand.product_count), color: C.silver },
                { label: 'Live SKUs', value: String(selectedBrand.live_count), color: C.gold },
                { label: 'Revenue', value: `KES ${(selectedBrand.total_revenue / 1000).toFixed(0)}K`, color: C.magenta },
              ].map(s => (
                <div key={s.label} style={{ textAlign: 'center', background: C.obsidianCard, borderRadius: 10, padding: '14px 8px' }}>
                  <div style={{ fontSize: 20, fontWeight: 700, color: s.color }}>{s.value}</div>
                  <div style={{ fontSize: 10, color: C.text.muted }}>{s.label}</div>
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', gap: 8 }}>
              {selectedBrand.status === 'pending' && (
                <MagentaBtn onClick={() => { handleBrandDecision(selectedBrand.id, 'approve'); setSelectedBrand(null); }}>
                  Approve Brand
                </MagentaBtn>
              )}
              {selectedBrand.status === 'approved' && (
                <button onClick={() => { handleBrandDecision(selectedBrand.id, 'suspend'); setSelectedBrand(null); }}
                  style={{
                    flex: 1, padding: '10px', borderRadius: 8, border: `1px solid ${C.border.default}`,
                    background: 'rgba(239,68,68,0.08)', color: C.error, fontSize: 13, cursor: 'pointer', fontWeight: 600,
                  }}>
                  Suspend Brand
                </button>
              )}
              {selectedBrand.status === 'suspended' && (
                <GoldBtn onClick={() => { handleBrandDecision(selectedBrand.id, 'reinstate'); setSelectedBrand(null); }} style={{ flex: 1 }}>
                  Reinstate Brand
                </GoldBtn>
              )}
              <GhostBtn onClick={() => setSelectedBrand(null)}>Close</GhostBtn>
            </div>
          </div>
        </div>
      )}

      {/* ── Sovereign Header ──────────────────────────────────────────────────── */}
      <header style={{
        height: 56, flexShrink: 0,
        background: `linear-gradient(90deg, ${C.obsidianDeep} 0%, #1A0A2E 50%, ${C.obsidianDeep} 100%)`,
        borderBottom: `1px solid ${C.border.subtle}`,
        display: 'flex', alignItems: 'center', padding: '0 28px', gap: 20,
        position: 'sticky', top: 0, zIndex: 100,
        boxShadow: `0 1px 0 ${C.border.magenta}`,
      }}>
        {/* Identity */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 28, height: 28, borderRadius: 6,
            background: `linear-gradient(135deg, ${C.magenta}, ${C.gold})`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: `0 0 14px ${C.magentaGlow}`,
          }}>
            <span style={{ fontSize: 12, fontWeight: 900, color: '#fff' }}>C</span>
          </div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 800, color: C.text.primary, letterSpacing: '0.05em' }}>CIRVANNA CONTROL</div>
            <div style={{ fontSize: 9, color: C.text.muted, letterSpacing: '0.1em' }}>SOVEREIGN ACCESS</div>
          </div>
          <div style={{
            fontSize: 9, padding: '2px 7px', borderRadius: 3,
            background: C.magentaSubtle, color: C.magenta,
            fontWeight: 800, letterSpacing: '0.12em', textTransform: 'uppercase',
            border: `1px solid ${C.border.magenta}`,
          }}>
            FOUNDER
          </div>
        </div>

        {/* Tabs */}
        <nav style={{ display: 'flex', gap: 1, flex: 1 }}>
          {navItems.map(item => (
            <button key={item.id} onClick={() => { setTab(item.id); setShowAddProduct(false); }}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '7px 14px', borderRadius: 7, border: 'none',
                background: tab === item.id
                  ? `linear-gradient(135deg, ${C.magentaSubtle}, ${C.goldSubtle})`
                  : 'transparent',
                color: tab === item.id ? C.text.primary : C.text.secondary,
                fontSize: 12, fontWeight: tab === item.id ? 700 : 400,
                cursor: 'pointer', transition: 'all 150ms ease',
                borderBottom: tab === item.id ? `2px solid ${C.magenta}` : '2px solid transparent',
              }}>
              <span style={{ fontSize: 11 }}>{item.icon}</span>
              {item.label}
              {item.badge != null && item.badge > 0 && (
                <span style={{
                  minWidth: 16, height: 16, borderRadius: 8,
                  background: `linear-gradient(135deg, ${C.magenta}, ${C.gold})`,
                  color: '#fff', fontSize: 9, fontWeight: 800,
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: '0 4px',
                }}>
                  {item.badge}
                </span>
              )}
            </button>
          ))}
        </nav>

        {/* Status bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 11 }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 5, color: C.success }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: C.success, boxShadow: `0 0 6px ${C.success}` }} />
            PAMASMMA online
          </span>
          <span style={{ color: C.text.muted, fontFamily: 'monospace' }}>
            {clock.toISOString().slice(11, 19)} UTC
          </span>
          <span style={{
            fontSize: 11, fontWeight: 700,
            background: `linear-gradient(90deg, ${C.magenta}, ${C.gold})`,
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
          }}>
            kelson@cirvanna
          </span>
        </div>
      </header>

      {/* ── Main Content ──────────────────────────────────────────────────────── */}
      <div style={{ flex: 1, padding: '32px 36px', maxWidth: 1360, margin: '0 auto', width: '100%' }}>

        {/* ══ PAMASMMA Command Tab ══ */}
        {tab === 'command' && !showAddProduct && (
          <div>
            {/* Metrics */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 14, marginBottom: 28 }}>
              <MetricCard label="Brands Active" value={String(approvedBrands)} sub={`${pendingBrands} awaiting approval`} topColor={C.magenta} />
              <MetricCard label="Live Products" value={String(liveProducts)} sub="On marketplace" topColor={C.gold} />
              <MetricCard label="Platform Revenue" value={`KES ${(totalRevenue / 1000000).toFixed(1)}M`} topColor={C.silver} />
              <MetricCard label="Pending Actions" value={String(pendingActions)} sub="Require your approval" topColor={C.warning} />
              <MetricCard label="PAMASMMA Score" value="9.2" sub="Average MALI v7" topColor={C.success} />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: 20 }}>
              {/* Action log */}
              <div>
                <SectionHeading accent={C.magenta}>PAMASMMA Autonomous Actions — Today</SectionHeading>
                <div style={{ background: C.obsidianPanel, border: `1px solid ${C.border.subtle}`, borderRadius: 12, overflow: 'hidden' }}>
                  {actions.map((action, i) => (
                    <div key={action.id} style={{
                      padding: '16px 20px',
                      borderBottom: i < actions.length - 1 ? `1px solid ${C.border.subtle}` : 'none',
                      background: action.requires_approval && action.approved === undefined
                        ? 'rgba(192,38,211,0.04)' : 'transparent',
                    }}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, justifyContent: 'space-between' }}>
                        <div style={{ display: 'flex', gap: 10, flex: 1 }}>
                          <span style={{
                            fontSize: 9, padding: '3px 7px', borderRadius: 4,
                            background: C.magentaSubtle, color: C.magenta, fontWeight: 800,
                            letterSpacing: '0.06em', flexShrink: 0, height: 'fit-content',
                          }}>
                            {action.systemCode}
                          </span>
                          <div>
                            <div style={{ fontSize: 13, fontWeight: 600, color: C.text.primary, marginBottom: 2 }}>
                              {action.action.replace(/_/g, ' ')}
                            </div>
                            <div style={{ fontSize: 11, color: C.text.secondary }}>
                              → {action.target} · {action.system}
                            </div>
                          </div>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                          <span style={{ fontSize: 10, color: C.text.muted, fontFamily: 'monospace' }}>{action.time}</span>
                          <span style={{
                            fontSize: 10, fontFamily: 'monospace', fontWeight: 700,
                            color: action.score >= 9 ? C.gold : C.silver,
                          }}>
                            {action.score.toFixed(1)}
                          </span>
                          {action.requires_approval && action.approved === undefined && (
                            <div style={{ display: 'flex', gap: 6 }}>
                              <button onClick={() => handleActionDecision(action.id, true)}
                                style={{
                                  padding: '4px 10px', borderRadius: 5, border: 'none',
                                  background: 'rgba(34,197,94,0.15)', color: C.success,
                                  fontSize: 11, fontWeight: 700, cursor: 'pointer',
                                }}>
                                Approve
                              </button>
                              <button onClick={() => handleActionDecision(action.id, false)}
                                style={{
                                  padding: '4px 10px', borderRadius: 5, border: 'none',
                                  background: 'rgba(239,68,68,0.12)', color: C.error,
                                  fontSize: 11, cursor: 'pointer',
                                }}>
                                Reject
                              </button>
                            </div>
                          )}
                          {action.approved === true && <span style={{ fontSize: 10, color: C.success, fontWeight: 700 }}>✓ APPROVED</span>}
                          {action.approved === false && <span style={{ fontSize: 10, color: C.error, fontWeight: 700 }}>✕ REJECTED</span>}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Right column — autonomy + quick controls */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                {/* Autonomy */}
                <div style={{ background: C.obsidianPanel, border: `1px solid ${C.border.default}`, borderRadius: 12, padding: '18px 20px' }}>
                  <SectionHeading accent={C.gold}>PAMASMMA Autonomy</SectionHeading>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4, background: C.obsidianCard, borderRadius: 8, padding: 4 }}>
                    {([
                      { id: 'full_auto', label: 'Full Auto', color: C.success },
                      { id: 'approval_required', label: 'Needs Approval', color: C.warning },
                      { id: 'manual_only', label: 'Manual Only', color: C.error },
                    ] as const).map(l => (
                      <button key={l.id} onClick={() => setAutonomy(l.id)} style={{
                        padding: '10px 14px', borderRadius: 6, border: 'none',
                        background: autonomy === l.id
                          ? `linear-gradient(135deg, ${C.magentaSubtle}, ${C.goldSubtle})`
                          : 'transparent',
                        color: autonomy === l.id ? l.color : C.text.secondary,
                        fontSize: 12, fontWeight: autonomy === l.id ? 700 : 400,
                        cursor: 'pointer', textAlign: 'left',
                        borderLeft: autonomy === l.id ? `3px solid ${l.color}` : '3px solid transparent',
                        transition: 'all 150ms',
                      }}>
                        {l.label}
                      </button>
                    ))}
                  </div>
                  <div style={{ marginTop: 12, fontSize: 11, color: C.text.muted, lineHeight: 1.6 }}>
                    {autonomy === 'full_auto' && 'PAMASMMA acts immediately. Critical-impact actions still queue for approval.'}
                    {autonomy === 'approval_required' && 'Every action waits in the queue. Check it daily.'}
                    {autonomy === 'manual_only' && 'PAMASMMA advises. You execute everything.'}
                  </div>
                </div>

                {/* Quick brand actions */}
                <div style={{ background: C.obsidianPanel, border: `1px solid ${C.border.default}`, borderRadius: 12, padding: '18px 20px' }}>
                  <SectionHeading accent={C.silver}>Quick Actions</SectionHeading>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <MagentaBtn onClick={() => { setTab('marketplace'); setShowAddProduct(true); }} style={{ width: '100%' }}>
                      + Add Product to Marketplace
                    </MagentaBtn>
                    <GoldBtn onClick={() => setTab('brands')} style={{ width: '100%' }}>
                      Review Brand Queue ({pendingBrands})
                    </GoldBtn>
                    <GhostBtn onClick={() => setTab('ai')} style={{ width: '100%' }}>View AI System Health</GhostBtn>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ══ Brands Tab ══ */}
        {tab === 'brands' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 24 }}>
              <div>
                <h1 style={{ fontSize: 26, fontWeight: 800, margin: 0 }}>All Brands — God View</h1>
                <p style={{ color: C.text.secondary, fontSize: 13, margin: '6px 0 0' }}>
                  {brands.length} brands total · {approvedBrands} approved · {pendingBrands} awaiting your review
                </p>
              </div>
            </div>

            {/* Pending approvals first */}
            {brands.filter(b => b.status === 'pending').length > 0 && (
              <div style={{ marginBottom: 24 }}>
                <SectionHeading accent={C.warning}>⚠ Awaiting Approval</SectionHeading>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {brands.filter(b => b.status === 'pending').map(brand => (
                    <div key={brand.id} style={{
                      display: 'grid', gridTemplateColumns: '44px 1fr 140px auto',
                      alignItems: 'center', gap: 16, padding: '16px 20px',
                      background: 'rgba(245,158,11,0.05)',
                      border: `1px solid rgba(245,158,11,0.25)`,
                      borderRadius: 10, cursor: 'pointer',
                    }} onClick={() => setSelectedBrand(brand)}>
                      <div style={{
                        width: 44, height: 44, borderRadius: 8,
                        background: `linear-gradient(135deg, ${C.warning}, rgba(245,158,11,0.4))`,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontWeight: 800, fontSize: 13, color: '#07080B',
                      }}>{brand.logo}</div>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 14, color: C.text.primary }}>{brand.name}</div>
                        <div style={{ fontSize: 12, color: C.text.muted }}>{brand.category} · {brand.country} · Joined {brand.joined}</div>
                      </div>
                      <StatusPill status={brand.status} />
                      <div style={{ display: 'flex', gap: 8 }}>
                        <MagentaBtn small onClick={(e: any) => { e.stopPropagation(); handleBrandDecision(brand.id, 'approve'); }}>
                          Approve
                        </MagentaBtn>
                        <GhostBtn small onClick={(e: any) => { e.stopPropagation(); handleBrandDecision(brand.id, 'suspend'); }}>Decline</GhostBtn>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* All brands table */}
            <SectionHeading>All Brands</SectionHeading>
            <div style={{ background: C.obsidianPanel, border: `1px solid ${C.border.default}`, borderRadius: 12, overflow: 'hidden' }}>
              <div style={{
                display: 'grid', gridTemplateColumns: '44px 1fr 120px 80px 80px 110px 120px auto',
                gap: 12, padding: '10px 20px', background: C.obsidianCard,
                borderBottom: `1px solid ${C.border.subtle}`,
              }}>
                {['', 'Brand', 'Category', 'SKUs', 'Live', 'Revenue', 'Status', 'Actions'].map(h => (
                  <span key={h} style={{ fontSize: 9, fontWeight: 800, color: C.text.muted, letterSpacing: '0.12em', textTransform: 'uppercase' }}>{h}</span>
                ))}
              </div>
              {brands.map((brand, i) => (
                <div key={brand.id}
                  onClick={() => setSelectedBrand(brand)}
                  style={{
                    display: 'grid', gridTemplateColumns: '44px 1fr 120px 80px 80px 110px 120px auto',
                    gap: 12, padding: '14px 20px', cursor: 'pointer',
                    borderBottom: i < brands.length - 1 ? `1px solid ${C.border.subtle}` : 'none',
                    transition: 'background 150ms', alignItems: 'center',
                  }}
                  onMouseEnter={e => { (e.currentTarget as any).style.background = C.obsidianHover; }}
                  onMouseLeave={e => { (e.currentTarget as any).style.background = 'transparent'; }}
                >
                  <div style={{
                    width: 36, height: 36, borderRadius: 7,
                    background: brand.status === 'suspended'
                      ? 'rgba(239,68,68,0.2)'
                      : brand.status === 'pending'
                        ? 'rgba(245,158,11,0.2)'
                        : `linear-gradient(135deg, ${C.magentaSubtle}, ${C.goldSubtle})`,
                    border: `1px solid ${C.border.subtle}`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontWeight: 800, fontSize: 11, color: brand.status === 'suspended' ? C.error : C.gold,
                  }}>{brand.logo}</div>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: C.text.primary }}>{brand.name}</div>
                    <div style={{ fontSize: 11, color: C.text.muted }}>{brand.country}</div>
                  </div>
                  <div style={{ fontSize: 12, color: C.text.secondary }}>{brand.category}</div>
                  <div style={{ fontSize: 13, color: C.silver, fontFamily: 'monospace' }}>{brand.product_count}</div>
                  <div style={{ fontSize: 13, color: C.gold, fontFamily: 'monospace', fontWeight: 600 }}>{brand.live_count}</div>
                  <div style={{ fontSize: 12, color: C.text.secondary, fontFamily: 'monospace' }}>
                    {brand.total_revenue > 0 ? `KES ${(brand.total_revenue / 1000).toFixed(0)}K` : '—'}
                  </div>
                  <StatusPill status={brand.status} />
                  <div style={{ display: 'flex', gap: 6 }} onClick={e => e.stopPropagation()}>
                    {brand.status === 'pending' && (
                      <MagentaBtn small onClick={() => handleBrandDecision(brand.id, 'approve')}>Approve</MagentaBtn>
                    )}
                    {brand.status === 'approved' && (
                      <button onClick={() => handleBrandDecision(brand.id, 'suspend')}
                        style={{
                          padding: '5px 10px', borderRadius: 5, border: `1px solid ${C.border.subtle}`,
                          background: 'rgba(239,68,68,0.08)', color: C.error, fontSize: 10, cursor: 'pointer',
                        }}>Suspend</button>
                    )}
                    {brand.status === 'suspended' && (
                      <GoldBtn small onClick={() => handleBrandDecision(brand.id, 'reinstate')}>Reinstate</GoldBtn>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ══ Marketplace Tab ══ */}
        {tab === 'marketplace' && !showAddProduct && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 24 }}>
              <div>
                <h1 style={{ fontSize: 26, fontWeight: 800, margin: 0 }}>Marketplace — Full Control</h1>
                <p style={{ color: C.text.secondary, fontSize: 13, margin: '6px 0 0' }}>
                  {liveProducts} live listings · You control visibility for every product across every brand.
                </p>
              </div>
              <MagentaBtn onClick={() => setShowAddProduct(true)}>+ Add Product</MagentaBtn>
            </div>

            {/* Flagged products */}
            {products.filter(p => p.flagged).length > 0 && (
              <div style={{ marginBottom: 24 }}>
                <SectionHeading accent={C.error}>⚑ Flagged for Review</SectionHeading>
                {products.filter(p => p.flagged).map(p => (
                  <div key={p.id} style={{
                    display: 'flex', alignItems: 'center', gap: 16, padding: '14px 18px',
                    background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.25)',
                    borderRadius: 10, marginBottom: 8,
                  }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: C.error }}>{p.name}</div>
                      <div style={{ fontSize: 11, color: C.text.muted }}>{p.brand_name} · {p.flag_reason}</div>
                    </div>
                    <GhostBtn small onClick={() => handleProductVisibility(p.id, false)}>Hide from Market</GhostBtn>
                  </div>
                ))}
              </div>
            )}

            {/* All products */}
            <div style={{ background: C.obsidianPanel, border: `1px solid ${C.border.default}`, borderRadius: 12, overflow: 'hidden' }}>
              <div style={{
                display: 'grid', gridTemplateColumns: '1fr 130px 120px 80px 80px 80px 90px 90px',
                gap: 12, padding: '10px 20px', background: C.obsidianCard,
                borderBottom: `1px solid ${C.border.subtle}`,
              }}>
                {['Product', 'Brand', 'Category', 'Price', 'Try-ons', 'Views', 'Status', 'Visibility'].map(h => (
                  <span key={h} style={{ fontSize: 9, fontWeight: 800, color: C.text.muted, letterSpacing: '0.12em', textTransform: 'uppercase' }}>{h}</span>
                ))}
              </div>

              {products.map((p, i) => {
                const effectivelyVisible = p.marketplace_visible && !p.founder_override_hidden;
                return (
                  <div key={p.id} style={{
                    display: 'grid', gridTemplateColumns: '1fr 130px 120px 80px 80px 80px 90px 90px',
                    gap: 12, padding: '13px 20px', alignItems: 'center',
                    borderBottom: i < products.length - 1 ? `1px solid ${C.border.subtle}` : 'none',
                    background: p.flagged ? 'rgba(239,68,68,0.03)' : 'transparent',
                    transition: 'background 150ms',
                  }}
                    onMouseEnter={e => { if (!p.flagged) (e.currentTarget as any).style.background = C.obsidianHover; }}
                    onMouseLeave={e => { (e.currentTarget as any).style.background = p.flagged ? 'rgba(239,68,68,0.03)' : 'transparent'; }}
                  >
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 500, color: C.text.primary }}>{p.name}</div>
                      <div style={{ fontSize: 10, color: C.text.muted, fontFamily: 'monospace' }}>{p.sku}</div>
                    </div>
                    <div style={{ fontSize: 11, color: C.text.secondary }}>{p.brand_name}</div>
                    <div style={{ fontSize: 11, color: C.text.secondary }}>{p.category}</div>
                    <div style={{ fontSize: 12, color: C.silver, fontFamily: 'monospace' }}>
                      KES {(p.price / 1000).toFixed(0)}K
                    </div>
                    <div style={{ fontSize: 13, color: C.gold, fontFamily: 'monospace', fontWeight: 600 }}>{fmt(p.tryons)}</div>
                    <div style={{ fontSize: 12, color: C.text.secondary, fontFamily: 'monospace' }}>{fmt(p.views)}</div>
                    {/* Status */}
                    <div>
                      <span style={{
                        fontSize: 10, padding: '2px 8px', borderRadius: 5, fontWeight: 700,
                        background: p.status === 'live' ? 'rgba(34,197,94,0.1)' : p.status === 'draft' ? 'rgba(245,158,11,0.1)' : 'rgba(107,114,128,0.1)',
                        color: p.status === 'live' ? C.success : p.status === 'draft' ? C.warning : C.silverDim,
                      }}>
                        {p.status}
                      </span>
                    </div>
                    {/* Founder visibility override */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Toggle
                        value={effectivelyVisible}
                        onChange={v => handleProductVisibility(p.id, v)}
                        onColor={`linear-gradient(90deg, ${C.magenta}, ${C.gold})`}
                      />
                      {p.founder_override_hidden && (
                        <span style={{ fontSize: 9, color: C.error, fontWeight: 700 }}>HIDDEN</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            <div style={{ marginTop: 12, fontSize: 11, color: C.text.muted, textAlign: 'right' }}>
              Visibility toggles apply founder-level override — supersedes brand settings
            </div>
          </div>
        )}

        {/* Add product form (marketplace tab) */}
        {tab === 'marketplace' && showAddProduct && (
          <FounderAddProduct
            brands={brands}
            onAdd={handleAddProduct}
            onCancel={() => setShowAddProduct(false)}
          />
        )}

        {/* ══ Platform Health Tab ══ */}
        {tab === 'platform' && (
          <div>
            <h1 style={{ fontSize: 26, fontWeight: 800, margin: '0 0 24px' }}>Platform Health</h1>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 28 }}>
              <MetricCard label="API P95 Latency" value="187ms" sub="Target < 300ms ✓" topColor={C.success} />
              <MetricCard label="Error Rate" value="0.04%" sub="Target < 0.1% ✓" topColor={C.success} />
              <MetricCard label="VTON Queue" value="3 jobs" sub="< 20 target ✓" topColor={C.gold} />
              <MetricCard label="DB Connections" value="14 / 100" sub="Healthy" topColor={C.silver} />
            </div>

            <SectionHeading accent={C.gold}>Circuit Breakers</SectionHeading>
            <div style={{ background: C.obsidianPanel, border: `1px solid ${C.border.default}`, borderRadius: 12, padding: '20px 24px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
                {Object.entries(circuitBreakers).map(([svc, open]) => (
                  <div key={svc} style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '12px 0', borderBottom: `1px solid ${C.border.subtle}`,
                  }}>
                    <span style={{ fontSize: 13, color: C.text.primary, fontFamily: 'monospace' }}>{svc}</span>
                    <button
                      onClick={() => setCircuitBreakers(prev => ({ ...prev, [svc]: !prev[svc as keyof typeof prev] }))}
                      style={{
                        padding: '5px 12px', borderRadius: 6, border: 'none', cursor: 'pointer',
                        background: open ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                        color: open ? C.success : C.error, fontSize: 11, fontWeight: 700,
                      }}>
                      {open ? 'OPEN' : 'TRIPPED'}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ══ AI Systems Tab ══ */}
        {tab === 'ai' && (
          <div>
            <h1 style={{ fontSize: 26, fontWeight: 800, margin: '0 0 24px' }}>AI Infrastructure</h1>

            {MOCK_ALERTS.length > 0 && (
              <div style={{ marginBottom: 24 }}>
                {MOCK_ALERTS.map(a => (
                  <div key={a.id} style={{
                    display: 'flex', alignItems: 'center', gap: 14,
                    padding: '12px 18px', borderRadius: 9, marginBottom: 8,
                    background: `${alertColor[a.severity]}0D`,
                    border: `1px solid ${alertColor[a.severity]}35`,
                  }}>
                    <span style={{
                      fontSize: 9, padding: '2px 7px', borderRadius: 4, fontWeight: 800,
                      background: `${alertColor[a.severity]}20`, color: alertColor[a.severity],
                      textTransform: 'uppercase', letterSpacing: '0.08em',
                    }}>{a.severity}</span>
                    <span style={{ flex: 1, fontSize: 13, color: C.text.primary }}>{a.message}</span>
                    <span style={{ fontSize: 11, color: C.text.muted, fontFamily: 'monospace' }}>{a.component}</span>
                    <span style={{ fontSize: 10, color: C.text.muted }}>{a.time}</span>
                  </div>
                ))}
              </div>
            )}

            <SectionHeading accent={C.magenta}>Vector Index Health</SectionHeading>
            <div style={{ background: C.obsidianPanel, border: `1px solid ${C.border.default}`, borderRadius: 12, overflow: 'hidden' }}>
              {[
                { name: 'cirvanna_products', vectors: 12450, age: 8.3, freshness: 0.91 },
                { name: 'cirvanna_users_usi', vectors: 3210, age: 26.1, freshness: 0.62 },
                { name: 'cirvanna_xyra_memory', vectors: 890, age: 4.2, freshness: 0.97 },
              ].map((idx, i, arr) => {
                const stale = idx.age > 24;
                const color = idx.freshness > 0.85 ? C.success : idx.freshness > 0.65 ? C.warning : C.error;
                return (
                  <div key={idx.name} style={{
                    display: 'flex', alignItems: 'center', gap: 16, padding: '16px 22px',
                    borderBottom: i < arr.length - 1 ? `1px solid ${C.border.subtle}` : 'none',
                  }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0 }} />
                    <span style={{ fontFamily: 'monospace', fontSize: 13, color: C.text.primary, flex: 1 }}>{idx.name}</span>
                    <span style={{ fontSize: 11, color: C.text.secondary, fontFamily: 'monospace' }}>{idx.vectors.toLocaleString()} vectors</span>
                    <span style={{ fontSize: 11, color: stale ? C.warning : C.text.muted, fontFamily: 'monospace' }}>{idx.age.toFixed(1)}h old</span>
                    {/* Freshness bar */}
                    <div style={{ width: 100, height: 4, background: C.obsidianCard, borderRadius: 2, overflow: 'hidden' }}>
                      <div style={{
                        height: '100%', borderRadius: 2,
                        background: `linear-gradient(90deg, ${color}, ${color}80)`,
                        width: `${idx.freshness * 100}%`,
                        transition: 'width 400ms ease',
                      }} />
                    </div>
                    <span style={{ fontSize: 11, color, fontFamily: 'monospace', fontWeight: 700, width: 48 }}>
                      {(idx.freshness * 100).toFixed(0)}%
                    </span>
                    {stale && (
                      <MagentaBtn small onClick={() => showToast(`Refresh queued for ${idx.name}`, 'magenta')}>Refresh</MagentaBtn>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ══ System Controls Tab ══ */}
        {tab === 'system' && (
          <div>
            <h1 style={{ fontSize: 26, fontWeight: 800, margin: '0 0 24px' }}>System Controls</h1>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
              {/* Feature flags */}
              <div style={{ background: C.obsidianPanel, border: `1px solid ${C.border.default}`, borderRadius: 12, padding: '20px 22px' }}>
                <SectionHeading accent={C.magenta}>Feature Flags</SectionHeading>
                {[
                  { label: 'Virtual Try-On (IDM-VTON)', on: true, color: C.magenta },
                  { label: 'Xyra AI Assistant', on: true, color: C.gold },
                  { label: 'Brand Portal', on: true, color: C.silver },
                  { label: 'Semantic Search', on: true, color: C.magenta },
                  { label: 'PAMASMMA Auto-Support', on: true, color: C.gold },
                  { label: 'New Brand Applications', on: true, color: C.silver },
                ].map((f, i, arr) => (
                  <div key={f.label} style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '12px 0',
                    borderBottom: i < arr.length - 1 ? `1px solid ${C.border.subtle}` : 'none',
                  }}>
                    <span style={{ fontSize: 13, color: C.text.primary }}>{f.label}</span>
                    <span style={{
                      fontSize: 10, padding: '3px 9px', borderRadius: 5, fontWeight: 800,
                      background: f.on ? `${f.color}18` : 'rgba(107,114,128,0.1)',
                      color: f.on ? f.color : C.silverDim,
                      border: `1px solid ${f.on ? f.color + '40' : C.border.subtle}`,
                    }}>
                      {f.on ? 'ON' : 'OFF'}
                    </span>
                  </div>
                ))}
              </div>

              {/* Platform identity */}
              <div style={{ background: C.obsidianPanel, border: `1px solid ${C.border.default}`, borderRadius: 12, padding: '20px 22px' }}>
                <SectionHeading accent={C.gold}>Platform Identity</SectionHeading>
                <div style={{ fontSize: 11, color: C.text.muted, lineHeight: 1.9 }}>
                  {[
                    ['Platform', 'Cirvanna'],
                    ['Positioning', 'Infrastructure of Identity'],
                    ['Region', 'Nairobi, Kenya'],
                    ['Environment', 'Production'],
                    ['Founder', 'Kelson'],
                    ['PAMASMMA Build', 'v1.0 — 48/49 checks'],
                    ['Cirvanna Score', '8.77 / 10'],
                  ].map(([k, v]) => (
                    <div key={k} style={{ display: 'flex', gap: 12 }}>
                      <span style={{ color: C.text.muted, width: 120, flexShrink: 0 }}>{k}</span>
                      <span style={{ color: C.text.primary, fontFamily: k === 'PAMASMMA Build' || k === 'Cirvanna Score' ? 'monospace' : 'inherit' }}>{v}</span>
                    </div>
                  ))}
                </div>

                <div style={{ marginTop: 20, padding: '12px 16px', background: C.obsidianCard, borderRadius: 8, borderLeft: `3px solid ${C.magenta}` }}>
                  <div style={{ fontSize: 11, color: C.magenta, fontWeight: 700, marginBottom: 4 }}>Sovereign Principle</div>
                  <div style={{ fontSize: 11, color: C.text.secondary, lineHeight: 1.6 }}>
                    This panel is accessible to one human and one AI. Kelson reigns supreme — PAMASMMA executes within approved autonomy bounds. All brand visibility is subject to founder override at any time.
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
