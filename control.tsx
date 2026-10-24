'use client';

/**
 * Cirvanna Founder Control Panel
 * Principals: Kelson (WebAuthn) + PAMASMMA (service token)
 * Access: control.cirvanna.co — completely isolated subdomain
 *
 * UX Classification: Utility UX — information density, command velocity, zero ceremony
 * Emotional target: Control, clarity, sovereignty over the system
 * Design language: Dense, terminal-adjacent, dark command surface.
 *                  No decorative chrome. Data is the interface.
 *
 * Five command zones:
 * 1. PAMASMMA Command Interface — live cognitive feeds, action log, override queue
 * 2. Platform Health — SLOs, queue depths, GCE metrics
 * 3. AI Infrastructure — embedding freshness, retrieval quality, drift alerts
 * 4. Brand Management — god view of all brands, approval queue
 * 5. System Controls — autonomy level, circuit breakers, feature flags
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';

// ─── Types ─────────────────────────────────────────────────────────────────────

type ControlTab = 'pamasmma' | 'platform' | 'ai-infra' | 'brands' | 'system';
type AutonomyLevel = 'full_auto' | 'approval_required' | 'manual_only';
type AlertSeverity = 'critical' | 'high' | 'medium' | 'low';

interface OverrideItem {
  override_id: string;
  cognitive_system: string;
  action: string;
  rationale: string;
  estimated_impact: string;
  mali_score: number;
  requested_at: string;
}

interface ActionLogItem {
  action_id: string;
  cognitive_system: string;
  action_taken: string;
  target?: string;
  autonomy_level: string;
  mali_score: number;
  executed_at: string;
}

interface Alert {
  alert_id: string;
  type: string;
  message: string;
  severity: AlertSeverity;
  triggered_at: string;
}

interface IndexHealth {
  index_name: string;
  vector_count: number;
  oldest_embedding_hours: number;
  freshness_score: number;
  is_stale: boolean;
  recommended_action?: string;
}

interface BrandRecord {
  brand_id: string;
  brand_name: string;
  category: string;
  status: 'pending_approval' | 'approved' | 'suspended';
  product_count: number;
  created_at: string;
}

// ─── Mock Data ─────────────────────────────────────────────────────────────────

const MOCK_OVERRIDES: OverrideItem[] = [
  {
    override_id: 'ov_001',
    cognitive_system: 'executive_operations',
    action: 'suspend_brand',
    rationale: 'S1 detected repeated policy violations. Brand "Fake Luxe Co" uploaded trademarked imagery 3x.',
    estimated_impact: 'HIGH — removes brand from marketplace',
    mali_score: 9.1,
    requested_at: '2026-06-14T08:22:00Z',
  },
  {
    override_id: 'ov_002',
    cognitive_system: 'strategic_narrative',
    action: 'pivot_positioning',
    rationale: 'S10 weekly review: identity-first messaging underperforming vs commerce-first. Recommends A/B test.',
    estimated_impact: 'MEDIUM — homepage narrative change',
    mali_score: 8.7,
    requested_at: '2026-06-14T06:00:00Z',
  },
];

const MOCK_ACTION_LOG: ActionLogItem[] = [
  { action_id: 'a1', cognitive_system: 'relationship_management', action_taken: 'draft_support_response', target: 'user_7f3a', autonomy_level: 'full_auto', mali_score: 8.4, executed_at: '2026-06-14T09:11:00Z' },
  { action_id: 'a2', cognitive_system: 'marketing_intelligence', action_taken: 'generate_brand_narrative', target: 'brand_ndovu', autonomy_level: 'full_auto', mali_score: 9.1, executed_at: '2026-06-14T08:55:00Z' },
  { action_id: 'a3', cognitive_system: 'narrative_governance', action_taken: 'enforce_brand_voice', target: 'product_p7f2', autonomy_level: 'full_auto', mali_score: 9.0, executed_at: '2026-06-14T08:30:00Z' },
  { action_id: 'a4', cognitive_system: 'persuasion_governance', action_taken: 'ethics_audit', target: 'campaign_c12', autonomy_level: 'full_auto', mali_score: 9.3, executed_at: '2026-06-14T07:00:00Z' },
];

const MOCK_INDEXES: IndexHealth[] = [
  { index_name: 'cirvanna_products', vector_count: 12450, oldest_embedding_hours: 8.3, freshness_score: 0.91, is_stale: false },
  { index_name: 'cirvanna_users_usi', vector_count: 3210, oldest_embedding_hours: 26.1, freshness_score: 0.62, is_stale: true, recommended_action: 'Schedule USI re-embedding — staleness exceeds 24h threshold' },
  { index_name: 'cirvanna_xyra_memory', vector_count: 890, oldest_embedding_hours: 4.2, freshness_score: 0.97, is_stale: false },
];

const MOCK_ALERTS: Alert[] = [
  { alert_id: 'al1', type: 'embedding_staleness', message: 'USI index stale — oldest embedding 26.1h', severity: 'medium', triggered_at: '2026-06-14T07:00:00Z' },
];

const MOCK_BRANDS: BrandRecord[] = [
  { brand_id: 'b1', brand_name: 'Maison Ndovu', category: 'Luxury Streetwear', status: 'approved', product_count: 12, created_at: '2026-05-01' },
  { brand_id: 'b2', brand_name: 'Savanna Studio', category: 'Sustainable Fashion', status: 'approved', product_count: 7, created_at: '2026-05-15' },
  { brand_id: 'b3', brand_name: 'Urbancore KE', category: 'Streetwear', status: 'pending_approval', product_count: 0, created_at: '2026-06-13' },
  { brand_id: 'b4', brand_name: 'Fake Luxe Co', category: 'Accessories', status: 'suspended', product_count: 4, created_at: '2026-04-20' },
];

// ─── Design Tokens ─────────────────────────────────────────────────────────────

const T = {
  bg: '#070809',
  panel: '#0D0E12',
  surface: '#131519',
  overlay: '#1C1F28',
  border: 'rgba(255,255,255,0.07)',
  borderStrong: 'rgba(255,255,255,0.13)',
  text: { primary: '#E8E8EA', secondary: '#8B909C', tertiary: '#4B5060' },
  accent: {
    pamasmma: '#7C6FD4',      // PAMASMMA cognitive purple
    gold: '#C9A84C',           // Cirvanna brand gold
    success: '#27AE60',
    warning: '#E67E22',
    critical: '#E74C3C',
    info: '#2980B9',
  },
};

// ─── Sub-components ────────────────────────────────────────────────────────────

function PanelCard({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{
      background: T.panel,
      border: `1px solid ${T.border}`,
      borderRadius: 10,
      ...style,
    }}>
      {children}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 10, fontWeight: 600, letterSpacing: '0.12em',
      textTransform: 'uppercase', color: T.text.tertiary,
      marginBottom: 14,
    }}>
      {children}
    </div>
  );
}

function SeverityBadge({ severity }: { severity: AlertSeverity }) {
  const colors: Record<AlertSeverity, string> = {
    critical: T.accent.critical,
    high: T.accent.warning,
    medium: '#F39C12',
    low: T.accent.info,
  };
  return (
    <span style={{
      fontSize: 10, fontWeight: 600, padding: '2px 8px',
      borderRadius: 4, background: `${colors[severity]}20`,
      color: colors[severity], textTransform: 'uppercase', letterSpacing: '0.06em',
    }}>
      {severity}
    </span>
  );
}

function SystemBadge({ system }: { system: string }) {
  return (
    <span style={{
      fontSize: 10, padding: '2px 8px', borderRadius: 4,
      background: `${T.accent.pamasmma}15`,
      color: T.accent.pamasmma,
      fontFamily: 'monospace',
    }}>
      {system.replace(/_/g, ' ')}
    </span>
  );
}

function AutonomyToggle({ current, onChange }: { current: AutonomyLevel; onChange: (l: AutonomyLevel) => void }) {
  const levels: { id: AutonomyLevel; label: string; color: string }[] = [
    { id: 'full_auto', label: 'Full Auto', color: T.accent.success },
    { id: 'approval_required', label: 'Approval Required', color: T.accent.warning },
    { id: 'manual_only', label: 'Manual Only', color: T.accent.critical },
  ];
  return (
    <div style={{ display: 'flex', gap: 4, background: T.surface, borderRadius: 8, padding: 4 }}>
      {levels.map(l => (
        <button
          key={l.id}
          onClick={() => onChange(l.id)}
          style={{
            flex: 1, padding: '8px 12px', borderRadius: 6, border: 'none',
            background: current === l.id ? T.overlay : 'transparent',
            color: current === l.id ? l.color : T.text.secondary,
            fontSize: 12, fontWeight: current === l.id ? 600 : 400,
            cursor: 'pointer', transition: 'all 150ms ease',
          }}
        >
          {l.label}
        </button>
      ))}
    </div>
  );
}

// ─── Main Panel ─────────────────────────────────────────────────────────────────

export default function FounderControlPanel() {
  const [activeTab, setActiveTab] = useState<ControlTab>('pamasmma');
  const [autonomyLevel, setAutonomyLevel] = useState<AutonomyLevel>('full_auto');
  const [overrides, setOverrides] = useState<OverrideItem[]>(MOCK_OVERRIDES);
  const [actionLog] = useState<ActionLogItem[]>(MOCK_ACTION_LOG);
  const [brands, setBrands] = useState<BrandRecord[]>(MOCK_BRANDS);
  const [liveTime, setLiveTime] = useState(new Date());
  const [circuitBreakers, setCircuitBreakers] = useState({
    qdrant: true, replicate: true, anthropic: true, gcs: true,
  });

  useEffect(() => {
    const t = setInterval(() => setLiveTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const handleOverrideDecision = useCallback((id: string, decision: 'approve' | 'reject') => {
    setOverrides(prev => prev.filter(o => o.override_id !== id));
  }, []);

  const handleBrandAction = useCallback((brandId: string, action: 'approve' | 'suspend') => {
    setBrands(prev => prev.map(b =>
      b.brand_id === brandId
        ? { ...b, status: action === 'approve' ? 'approved' : 'suspended' }
        : b
    ));
  }, []);

  const tabs: { id: ControlTab; label: string; badge?: number }[] = [
    { id: 'pamasmma', label: 'PAMASMMA', badge: overrides.length },
    { id: 'platform', label: 'Platform Health' },
    { id: 'ai-infra', label: 'AI Infrastructure', badge: MOCK_ALERTS.length },
    { id: 'brands', label: 'Brands', badge: brands.filter(b => b.status === 'pending_approval').length },
    { id: 'system', label: 'System Controls' },
  ];

  return (
    <div style={{
      minHeight: '100vh', background: T.bg,
      fontFamily: '"Inter", -apple-system, sans-serif',
      color: T.text.primary,
      display: 'flex', flexDirection: 'column',
    }}>

      {/* ── Top Bar ── */}
      <header style={{
        height: 52, background: T.panel,
        borderBottom: `1px solid ${T.border}`,
        display: 'flex', alignItems: 'center',
        padding: '0 24px', gap: 24,
        position: 'sticky', top: 0, zIndex: 100,
      }}>
        {/* Identity mark */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 20, height: 20, borderRadius: 4,
            background: `linear-gradient(135deg, ${T.accent.gold}, ${T.accent.pamasmma})`,
          }} />
          <span style={{ fontSize: 12, fontWeight: 600, color: T.text.secondary, letterSpacing: '0.1em', textTransform: 'uppercase' }}>
            Cirvanna Control
          </span>
          <span style={{
            fontSize: 9, padding: '2px 6px', borderRadius: 3,
            background: 'rgba(231,76,60,0.2)', color: T.accent.critical,
            fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase',
          }}>
            Restricted
          </span>
        </div>

        {/* Tabs */}
        <nav style={{ display: 'flex', gap: 2, flex: 1 }}>
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '6px 14px', borderRadius: 6, border: 'none',
                background: activeTab === tab.id ? T.surface : 'transparent',
                color: activeTab === tab.id ? T.text.primary : T.text.secondary,
                fontSize: 12, fontWeight: activeTab === tab.id ? 500 : 400,
                cursor: 'pointer', transition: 'all 150ms ease',
              }}
            >
              {tab.label}
              {tab.badge != null && tab.badge > 0 && (
                <span style={{
                  minWidth: 16, height: 16, borderRadius: 8,
                  background: T.accent.critical, color: '#fff',
                  fontSize: 9, fontWeight: 700,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  padding: '0 4px',
                }}>
                  {tab.badge}
                </span>
              )}
            </button>
          ))}
        </nav>

        {/* Status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 11, color: T.text.tertiary }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: T.accent.success }} />
            PAMASMMA online
          </span>
          <span style={{ fontFamily: 'monospace' }}>{liveTime.toISOString().slice(11, 19)} UTC</span>
          <span style={{ color: T.accent.gold, fontSize: 10, fontWeight: 600 }}>kelson@cirvanna</span>
        </div>
      </header>

      {/* ── Content ── */}
      <div style={{ flex: 1, padding: '28px 32px', maxWidth: 1400, margin: '0 auto', width: '100%' }}>

        {/* ══ PAMASMMA Tab ══ */}
        {activeTab === 'pamasmma' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: 20 }}>

            {/* Left: Action log */}
            <div>
              <SectionLabel>Recent Autonomous Actions</SectionLabel>
              <PanelCard>
                {actionLog.map((item, i) => (
                  <div key={item.action_id} style={{
                    padding: '14px 18px',
                    borderBottom: i < actionLog.length - 1 ? `1px solid ${T.border}` : 'none',
                    display: 'flex', flexDirection: 'column', gap: 6,
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, justifyContent: 'space-between' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <SystemBadge system={item.cognitive_system} />
                        <span style={{ fontSize: 13, color: T.text.primary, fontFamily: 'monospace' }}>
                          {item.action_taken}
                        </span>
                      </div>
                      <span style={{ fontSize: 10, color: T.text.tertiary, fontFamily: 'monospace' }}>
                        MALI {item.mali_score.toFixed(1)}
                      </span>
                    </div>
                    <div style={{ display: 'flex', gap: 16, fontSize: 11, color: T.text.tertiary }}>
                      {item.target && <span>→ {item.target}</span>}
                      <span>{item.autonomy_level.replace(/_/g, ' ')}</span>
                      <span style={{ marginLeft: 'auto' }}>
                        {new Date(item.executed_at).toISOString().slice(11, 16)} UTC
                      </span>
                    </div>
                  </div>
                ))}
              </PanelCard>
            </div>

            {/* Right: Override queue */}
            <div>
              <SectionLabel>Pending Approval Queue ({overrides.length})</SectionLabel>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {overrides.length === 0 ? (
                  <PanelCard style={{ padding: '24px', textAlign: 'center' }}>
                    <div style={{ color: T.text.tertiary, fontSize: 13 }}>No actions pending approval</div>
                  </PanelCard>
                ) : overrides.map(item => (
                  <PanelCard key={item.override_id} style={{ padding: '16px 18px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                      <SystemBadge system={item.cognitive_system} />
                      <span style={{ fontSize: 10, color: T.text.tertiary, fontFamily: 'monospace' }}>
                        {item.mali_score.toFixed(1)} / 10
                      </span>
                    </div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: T.text.primary, marginBottom: 6 }}>
                      {item.action.replace(/_/g, ' ')}
                    </div>
                    <div style={{ fontSize: 12, color: T.text.secondary, lineHeight: 1.5, marginBottom: 10 }}>
                      {item.rationale}
                    </div>
                    <div style={{
                      fontSize: 11, padding: '6px 10px', borderRadius: 6,
                      background: 'rgba(231,76,60,0.08)',
                      color: '#E74C3C', marginBottom: 14,
                    }}>
                      Impact: {item.estimated_impact}
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button
                        onClick={() => handleOverrideDecision(item.override_id, 'approve')}
                        style={{
                          flex: 1, padding: '8px', borderRadius: 6, border: 'none',
                          background: `${T.accent.success}20`, color: T.accent.success,
                          fontSize: 12, fontWeight: 600, cursor: 'pointer',
                        }}>
                        Approve
                      </button>
                      <button
                        onClick={() => handleOverrideDecision(item.override_id, 'reject')}
                        style={{
                          flex: 1, padding: '8px', borderRadius: 6, border: 'none',
                          background: `${T.accent.critical}15`, color: T.accent.critical,
                          fontSize: 12, fontWeight: 600, cursor: 'pointer',
                        }}>
                        Reject
                      </button>
                    </div>
                  </PanelCard>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ══ Platform Health Tab ══ */}
        {activeTab === 'platform' && (
          <div>
            <SectionLabel>System SLOs</SectionLabel>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 24 }}>
              {[
                { label: 'API P95 Latency', value: '187ms', target: '<300ms', ok: true },
                { label: 'Error Rate', value: '0.04%', target: '<0.1%', ok: true },
                { label: 'IDM-VTON Queue', value: '3 jobs', target: '<20', ok: true },
                { label: 'DB Connections', value: '14/100', target: '<80', ok: true },
              ].map(m => (
                <PanelCard key={m.label} style={{ padding: '16px 18px' }}>
                  <div style={{ fontSize: 11, color: T.text.tertiary, marginBottom: 6 }}>{m.label}</div>
                  <div style={{ fontSize: 22, fontFamily: 'monospace', fontWeight: 600, color: m.ok ? T.accent.success : T.accent.critical }}>
                    {m.value}
                  </div>
                  <div style={{ fontSize: 10, color: T.text.tertiary, marginTop: 4 }}>target {m.target}</div>
                </PanelCard>
              ))}
            </div>

            <SectionLabel>Service Circuit Breakers</SectionLabel>
            <PanelCard style={{ padding: '20px 24px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
                {Object.entries(circuitBreakers).map(([service, active]) => (
                  <div key={service} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 0', borderBottom: `1px solid ${T.border}` }}>
                    <span style={{ fontSize: 13, color: T.text.primary, fontFamily: 'monospace' }}>{service}</span>
                    <button
                      onClick={() => setCircuitBreakers(prev => ({ ...prev, [service]: !prev[service as keyof typeof prev] }))}
                      style={{
                        padding: '4px 12px', borderRadius: 6, border: 'none',
                        background: active ? `${T.accent.success}20` : `${T.accent.critical}20`,
                        color: active ? T.accent.success : T.accent.critical,
                        fontSize: 11, fontWeight: 600, cursor: 'pointer',
                      }}
                    >
                      {active ? 'OPEN' : 'TRIPPED'}
                    </button>
                  </div>
                ))}
              </div>
            </PanelCard>
          </div>
        )}

        {/* ══ AI Infrastructure Tab ══ */}
        {activeTab === 'ai-infra' && (
          <div>
            {MOCK_ALERTS.length > 0 && (
              <div style={{ marginBottom: 20 }}>
                {MOCK_ALERTS.map(alert => (
                  <div key={alert.alert_id} style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    padding: '12px 16px', borderRadius: 8, marginBottom: 8,
                    background: 'rgba(243,156,18,0.08)',
                    border: '1px solid rgba(243,156,18,0.2)',
                  }}>
                    <SeverityBadge severity={alert.severity} />
                    <span style={{ fontSize: 13, color: T.text.primary }}>{alert.message}</span>
                    <span style={{ marginLeft: 'auto', fontSize: 11, color: T.text.tertiary, fontFamily: 'monospace' }}>
                      {new Date(alert.triggered_at).toISOString().slice(11, 16)} UTC
                    </span>
                  </div>
                ))}
              </div>
            )}

            <SectionLabel>Vector Index Health</SectionLabel>
            <PanelCard>
              {MOCK_INDEXES.map((idx, i) => (
                <div key={idx.index_name} style={{
                  padding: '16px 20px',
                  borderBottom: i < MOCK_INDEXES.length - 1 ? `1px solid ${T.border}` : 'none',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: idx.recommended_action ? 8 : 0 }}>
                    <span style={{
                      width: 8, height: 8, borderRadius: '50%',
                      background: idx.is_stale ? T.accent.warning : T.accent.success,
                      flexShrink: 0,
                    }} />
                    <span style={{ fontFamily: 'monospace', fontSize: 13, color: T.text.primary, flex: 1 }}>
                      {idx.index_name}
                    </span>
                    <span style={{ fontSize: 11, color: T.text.tertiary, fontFamily: 'monospace' }}>
                      {idx.vector_count.toLocaleString()} vectors
                    </span>
                    <span style={{ fontSize: 11, color: T.text.tertiary, fontFamily: 'monospace' }}>
                      {idx.oldest_embedding_hours.toFixed(1)}h old
                    </span>
                    <span style={{
                      fontSize: 11, fontFamily: 'monospace', fontWeight: 600,
                      color: idx.freshness_score > 0.8 ? T.accent.success : idx.freshness_score > 0.6 ? T.accent.warning : T.accent.critical,
                    }}>
                      {(idx.freshness_score * 100).toFixed(0)}% fresh
                    </span>
                    {idx.is_stale && (
                      <button style={{
                        padding: '4px 10px', borderRadius: 5, border: 'none',
                        background: `${T.accent.gold}20`, color: T.accent.gold,
                        fontSize: 11, cursor: 'pointer', fontWeight: 500,
                      }}>
                        Refresh
                      </button>
                    )}
                  </div>
                  {idx.recommended_action && (
                    <div style={{ fontSize: 11, color: T.accent.warning, marginLeft: 20, fontStyle: 'italic' }}>
                      → {idx.recommended_action}
                    </div>
                  )}
                </div>
              ))}
            </PanelCard>
          </div>
        )}

        {/* ══ Brands Tab ══ */}
        {activeTab === 'brands' && (
          <div>
            <SectionLabel>All Brand Partners — God View</SectionLabel>
            <PanelCard>
              {brands.map((brand, i) => (
                <div key={brand.brand_id} style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 140px 80px 80px auto',
                  alignItems: 'center',
                  gap: 16,
                  padding: '14px 20px',
                  borderBottom: i < brands.length - 1 ? `1px solid ${T.border}` : 'none',
                }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 500, color: T.text.primary }}>{brand.brand_name}</div>
                    <div style={{ fontSize: 11, color: T.text.tertiary, marginTop: 2 }}>{brand.category} · {brand.brand_id}</div>
                  </div>
                  <span style={{
                    fontSize: 11, padding: '3px 8px', borderRadius: 4, fontWeight: 500,
                    background: brand.status === 'approved' ? `${T.accent.success}18`
                      : brand.status === 'pending_approval' ? `${T.accent.warning}18`
                        : `${T.accent.critical}18`,
                    color: brand.status === 'approved' ? T.accent.success
                      : brand.status === 'pending_approval' ? T.accent.warning
                        : T.accent.critical,
                  }}>
                    {brand.status.replace(/_/g, ' ')}
                  </span>
                  <span style={{ fontSize: 12, color: T.text.secondary, fontFamily: 'monospace' }}>
                    {brand.product_count} SKUs
                  </span>
                  <span style={{ fontSize: 11, color: T.text.tertiary, fontFamily: 'monospace' }}>
                    {brand.created_at}
                  </span>
                  <div style={{ display: 'flex', gap: 6 }}>
                    {brand.status === 'pending_approval' && (
                      <button
                        onClick={() => handleBrandAction(brand.brand_id, 'approve')}
                        style={{
                          padding: '5px 12px', borderRadius: 5, border: 'none',
                          background: `${T.accent.success}20`, color: T.accent.success,
                          fontSize: 11, fontWeight: 600, cursor: 'pointer',
                        }}>
                        Approve
                      </button>
                    )}
                    {brand.status === 'approved' && (
                      <button
                        onClick={() => handleBrandAction(brand.brand_id, 'suspend')}
                        style={{
                          padding: '5px 12px', borderRadius: 5, border: 'none',
                          background: `${T.accent.critical}15`, color: T.accent.critical,
                          fontSize: 11, cursor: 'pointer',
                        }}>
                        Suspend
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </PanelCard>
          </div>
        )}

        {/* ══ System Controls Tab ══ */}
        {activeTab === 'system' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
            <div>
              <SectionLabel>PAMASMMA Autonomy Level</SectionLabel>
              <PanelCard style={{ padding: '20px' }}>
                <AutonomyToggle current={autonomyLevel} onChange={setAutonomyLevel} />
                <div style={{ marginTop: 14, fontSize: 12, color: T.text.tertiary, lineHeight: 1.6 }}>
                  {autonomyLevel === 'full_auto' && 'PAMASMMA acts immediately on all non-critical events. Critical impact actions still require approval.'}
                  {autonomyLevel === 'approval_required' && 'Every PAMASMMA action is queued for your review before execution. Override queue must be checked daily.'}
                  {autonomyLevel === 'manual_only' && 'PAMASMMA advises only. No autonomous action. You execute everything manually.'}
                </div>
              </PanelCard>
            </div>

            <div>
              <SectionLabel>Feature Flags</SectionLabel>
              <PanelCard style={{ padding: '16px 20px' }}>
                {[
                  { label: 'Virtual Try-On (IDM-VTON)', enabled: true },
                  { label: 'Xyra AI Assistant', enabled: true },
                  { label: 'Brand Portal', enabled: true },
                  { label: 'Semantic Search', enabled: true },
                  { label: 'PAMASMMA Auto-Support', enabled: true },
                ].map(flag => (
                  <div key={flag.label} style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '10px 0', borderBottom: `1px solid ${T.border}`,
                  }}>
                    <span style={{ fontSize: 13, color: T.text.primary }}>{flag.label}</span>
                    <span style={{
                      fontSize: 11, padding: '2px 8px', borderRadius: 4,
                      background: flag.enabled ? `${T.accent.success}20` : `${T.accent.critical}20`,
                      color: flag.enabled ? T.accent.success : T.accent.critical,
                      fontWeight: 600,
                    }}>
                      {flag.enabled ? 'ON' : 'OFF'}
                    </span>
                  </div>
                ))}
              </PanelCard>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
