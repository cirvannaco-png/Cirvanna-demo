'use client';

/**
 * Cirvanna Brand Partner Portal
 * UX Classification: Utility UX with Identity framing
 * Emotional target: Pride of association, confidence of control, trust of discretion
 *
 * Three primary zones:
 * 1. Products — upload, manage visibility, track processing
 * 2. Analytics — views, saves, try-ons scoped to this brand only
 * 3. Assets — GCS upload manager with signed URLs
 *
 * Security: brand_id NEVER in client state as ground truth.
 * All reads are scoped by the API via JWT.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';

// ─── Types ─────────────────────────────────────────────────────────────────────

type Tab = 'products' | 'analytics' | 'assets' | 'communications';
type ProductStatus = 'draft' | 'live' | 'archived';

interface Product {
  product_id: string;
  name: string;
  description: string;
  category: string;
  price: number;
  currency: string;
  status: ProductStatus;
  images: string[];
  created_at: string;
  tryons?: number;
  views?: number;
}

interface AnalyticsSummary {
  total_views: number;
  total_saves: number;
  total_tryons: number;
  conversion_rate: number;
  top_products: { product_id: string; name: string; views: number }[];
}

interface BrandMeta {
  brand_name: string;
  brand_id: string;
  category: string;
}

// ─── Mock Data (replace with API calls in production) ──────────────────────────

const MOCK_BRAND: BrandMeta = {
  brand_name: 'Maison Ndovu',
  brand_id: 'brand_7f3a91',
  category: 'Luxury Streetwear',
};

const MOCK_PRODUCTS: Product[] = [
  {
    product_id: 'p1', name: 'Obsidian Technical Jacket', description: 'Water-resistant matte shell',
    category: 'Outerwear', price: 42000, currency: 'KES', status: 'live',
    images: [], created_at: '2026-06-01', tryons: 847, views: 3241,
  },
  {
    product_id: 'p2', name: 'Archive Print Tee — Vol.3', description: 'Limited run, 200gsm cotton',
    category: 'Tops', price: 4800, currency: 'KES', status: 'live',
    images: [], created_at: '2026-06-05', tryons: 512, views: 1890,
  },
  {
    product_id: 'p3', name: 'Cargo Silhouette Trousers', description: 'Six-pocket relaxed fit',
    category: 'Bottoms', price: 12500, currency: 'KES', status: 'draft',
    images: [], created_at: '2026-06-10', tryons: 0, views: 0,
  },
];

const MOCK_ANALYTICS: AnalyticsSummary = {
  total_views: 5131,
  total_saves: 734,
  total_tryons: 1359,
  conversion_rate: 0.034,
  top_products: MOCK_PRODUCTS.filter(p => p.status === 'live').map(p => ({
    product_id: p.product_id,
    name: p.name,
    views: p.views ?? 0,
  })),
};

// ─── Utility ───────────────────────────────────────────────────────────────────

const fmt = (n: number) => n.toLocaleString();
const fmtKES = (n: number) => `KES ${n.toLocaleString()}`;
const statusColor: Record<ProductStatus, string> = {
  live: '#2ECC71',
  draft: '#F39C12',
  archived: '#6B7280',
};

// ─── Sub-components ────────────────────────────────────────────────────────────

function StatCard({ label, value, delta }: { label: string; value: string; delta?: string }) {
  return (
    <div style={{
      background: '#111318',
      border: '1px solid rgba(255,255,255,0.08)',
      borderRadius: 12,
      padding: '20px 24px',
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
    }}>
      <span style={{ fontSize: 12, color: '#6B7280', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
        {label}
      </span>
      <span style={{ fontSize: 28, fontWeight: 600, color: '#F0F0F0', fontFamily: '"Inter", sans-serif', lineHeight: 1 }}>
        {value}
      </span>
      {delta && (
        <span style={{ fontSize: 12, color: '#2ECC71' }}>{delta}</span>
      )}
    </div>
  );
}

function ProductRow({ product, onStatusChange }: {
  product: Product;
  onStatusChange: (id: string, status: ProductStatus) => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '1fr 100px 120px 100px 80px 40px',
      alignItems: 'center',
      gap: 16,
      padding: '14px 20px',
      borderBottom: '1px solid rgba(255,255,255,0.05)',
      transition: 'background 150ms ease',
    }}
      onMouseEnter={e => (e.currentTarget.style.background = '#1A1D26')}
      onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
    >
      {/* Name + category */}
      <div>
        <div style={{ color: '#F0F0F0', fontWeight: 500, fontSize: 14 }}>{product.name}</div>
        <div style={{ color: '#6B7280', fontSize: 12, marginTop: 2 }}>{product.category}</div>
      </div>

      {/* Price */}
      <div style={{ color: '#9BA3AF', fontSize: 13, fontFamily: 'monospace' }}>
        {fmtKES(product.price)}
      </div>

      {/* Status pill */}
      <div>
        <span style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          padding: '3px 10px',
          borderRadius: 99,
          fontSize: 11,
          fontWeight: 500,
          background: `${statusColor[product.status]}18`,
          color: statusColor[product.status],
          border: `1px solid ${statusColor[product.status]}40`,
        }}>
          <span style={{
            width: 6, height: 6, borderRadius: '50%',
            background: statusColor[product.status],
          }} />
          {product.status.charAt(0).toUpperCase() + product.status.slice(1)}
        </span>
      </div>

      {/* Try-ons */}
      <div style={{ color: '#C9A84C', fontSize: 13, fontFamily: 'monospace' }}>
        {product.tryons != null ? fmt(product.tryons) : '—'}
      </div>

      {/* Views */}
      <div style={{ color: '#9BA3AF', fontSize: 13, fontFamily: 'monospace' }}>
        {product.views != null ? fmt(product.views) : '—'}
      </div>

      {/* Actions */}
      <div style={{ position: 'relative' }}>
        <button
          onClick={() => setMenuOpen(v => !v)}
          aria-label="Product actions"
          style={{
            background: 'none', border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: 6, padding: '4px 8px', cursor: 'pointer',
            color: '#9BA3AF', fontSize: 16,
          }}
        >
          ⋯
        </button>
        {menuOpen && (
          <div style={{
            position: 'absolute', right: 0, top: '100%', zIndex: 50,
            background: '#222535', border: '1px solid rgba(255,255,255,0.12)',
            borderRadius: 8, overflow: 'hidden', minWidth: 140,
            boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
          }}>
            {product.status !== 'live' && (
              <button onClick={() => { onStatusChange(product.product_id, 'live'); setMenuOpen(false); }}
                style={menuItemStyle}>
                Set Live
              </button>
            )}
            {product.status !== 'draft' && (
              <button onClick={() => { onStatusChange(product.product_id, 'draft'); setMenuOpen(false); }}
                style={menuItemStyle}>
                Move to Draft
              </button>
            )}
            {product.status !== 'archived' && (
              <button onClick={() => { onStatusChange(product.product_id, 'archived'); setMenuOpen(false); }}
                style={{ ...menuItemStyle, color: '#E74C3C' }}>
                Archive
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

const menuItemStyle: React.CSSProperties = {
  display: 'block', width: '100%', padding: '10px 16px',
  background: 'none', border: 'none', cursor: 'pointer',
  textAlign: 'left', fontSize: 13, color: '#F0F0F0',
  transition: 'background 100ms ease',
};

function UploadDropzone({ onUpload }: { onUpload: (file: File) => void }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) onUpload(file);
  }, [onUpload]);

  return (
    <div
      onDragOver={e => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      role="button"
      tabIndex={0}
      aria-label="Upload product image — click or drag and drop"
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click(); }}
      style={{
        border: `2px dashed ${dragging ? '#C9A84C' : 'rgba(255,255,255,0.15)'}`,
        borderRadius: 12,
        padding: '48px 24px',
        textAlign: 'center',
        cursor: 'pointer',
        transition: 'all 200ms ease',
        background: dragging ? 'rgba(201,168,76,0.04)' : 'transparent',
        outline: 'none',
      }}
    >
      <div style={{ fontSize: 32, marginBottom: 12 }}>⬆</div>
      <div style={{ color: '#F0F0F0', fontSize: 15, fontWeight: 500, marginBottom: 6 }}>
        Drop product image here
      </div>
      <div style={{ color: '#6B7280', fontSize: 13 }}>
        PNG, JPG, WebP — max 50MB · Signed upload, never proxied
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        style={{ display: 'none' }}
        onChange={e => { const f = e.target.files?.[0]; if (f) onUpload(f); }}
      />
    </div>
  );
}

// ─── Main Dashboard ─────────────────────────────────────────────────────────────

export default function BrandDashboard() {
  const [activeTab, setActiveTab] = useState<Tab>('products');
  const [products, setProducts] = useState<Product[]>(MOCK_PRODUCTS);
  const [analytics] = useState<AnalyticsSummary>(MOCK_ANALYTICS);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const brand = MOCK_BRAND;

  const handleStatusChange = useCallback((id: string, status: ProductStatus) => {
    setProducts(prev => prev.map(p => p.product_id === id ? { ...p, status } : p));
  }, []);

  const handleUpload = useCallback(async (file: File) => {
    setUploadStatus('Requesting upload URL…');
    try {
      // In production: call productsAPI.requestUploadUrl(), then PUT directly to GCS
      await new Promise(r => setTimeout(r, 1200));
      setUploadStatus(`✓ ${file.name} uploaded successfully`);
      setTimeout(() => setUploadStatus(null), 3000);
    } catch {
      setUploadStatus('Upload failed — please retry');
    }
  }, []);

  const tabs: { id: Tab; label: string }[] = [
    { id: 'products', label: 'Products' },
    { id: 'analytics', label: 'Analytics' },
    { id: 'assets', label: 'Assets' },
    { id: 'communications', label: 'Messages' },
  ];

  return (
    <div style={{
      minHeight: '100vh',
      background: '#0A0B0F',
      fontFamily: '"Inter", -apple-system, sans-serif',
      color: '#F0F0F0',
      display: 'flex',
    }}>

      {/* ── Sidebar ── */}
      <aside style={{
        width: 240,
        flexShrink: 0,
        background: '#0D0E13',
        borderRight: '1px solid rgba(255,255,255,0.07)',
        display: 'flex',
        flexDirection: 'column',
        padding: '28px 0',
        position: 'fixed',
        top: 0,
        bottom: 0,
        left: 0,
      }}>
        {/* Brand identity */}
        <div style={{ padding: '0 24px 28px', borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
          <div style={{
            width: 40, height: 40, borderRadius: 10,
            background: 'linear-gradient(135deg, #C9A84C 0%, #8A6E30 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 16, fontWeight: 700, color: '#0A0B0F', marginBottom: 12,
          }}>
            {brand.brand_name.charAt(0)}
          </div>
          <div style={{ fontWeight: 600, fontSize: 14, color: '#F0F0F0', lineHeight: 1.2 }}>
            {brand.brand_name}
          </div>
          <div style={{ fontSize: 11, color: '#6B7280', marginTop: 4 }}>{brand.category}</div>
        </div>

        {/* Navigation */}
        <nav style={{ flex: 1, padding: '20px 12px' }}>
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                display: 'flex',
                width: '100%',
                alignItems: 'center',
                gap: 10,
                padding: '10px 12px',
                borderRadius: 8,
                border: 'none',
                background: activeTab === tab.id ? 'rgba(201,168,76,0.1)' : 'transparent',
                color: activeTab === tab.id ? '#C9A84C' : '#9BA3AF',
                fontSize: 13,
                fontWeight: activeTab === tab.id ? 500 : 400,
                cursor: 'pointer',
                textAlign: 'left',
                transition: 'all 150ms ease',
                marginBottom: 2,
              }}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        {/* Footer */}
        <div style={{ padding: '16px 24px', borderTop: '1px solid rgba(255,255,255,0.07)' }}>
          <div style={{ fontSize: 11, color: '#6B7280' }}>Cirvanna Brand Portal</div>
          <div style={{ fontSize: 10, color: '#374151', marginTop: 2 }}>Private · {brand.brand_id}</div>
        </div>
      </aside>

      {/* ── Main Content ── */}
      <main style={{ marginLeft: 240, flex: 1, padding: '40px 48px', maxWidth: 1200 }}>

        {/* Header */}
        <div style={{ marginBottom: 36, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <h1 style={{
              fontFamily: '"Cormorant Garamond", Georgia, serif',
              fontSize: 32, fontWeight: 600, color: '#F0F0F0', margin: 0, lineHeight: 1.1,
            }}>
              {activeTab === 'products' && 'Your Collection'}
              {activeTab === 'analytics' && 'Performance'}
              {activeTab === 'assets' && 'Asset Library'}
              {activeTab === 'communications' && 'Messages'}
            </h1>
            <p style={{ color: '#6B7280', fontSize: 13, marginTop: 6, marginBottom: 0 }}>
              {activeTab === 'products' && 'Manage your product catalog and visibility'}
              {activeTab === 'analytics' && 'Engagement data — your brand only'}
              {activeTab === 'assets' && 'Product images and brand kit — private storage'}
              {activeTab === 'communications' && 'Messages from Cirvanna platform'}
            </p>
          </div>

          {activeTab === 'products' && (
            <button style={{
              background: '#C9A84C',
              color: '#0A0B0F',
              border: 'none',
              borderRadius: 8,
              padding: '10px 20px',
              fontWeight: 600,
              fontSize: 13,
              cursor: 'pointer',
            }}>
              + Add Product
            </button>
          )}
        </div>

        {/* ── Products Tab ── */}
        {activeTab === 'products' && (
          <div>
            {/* Stats row */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 32 }}>
              <StatCard label="Total Products" value={fmt(products.length)} />
              <StatCard label="Live" value={fmt(products.filter(p => p.status === 'live').length)} delta="↑ 2 this month" />
              <StatCard label="Total Try-Ons" value={fmt(products.reduce((a, p) => a + (p.tryons ?? 0), 0))} />
              <StatCard label="Total Views" value={fmt(products.reduce((a, p) => a + (p.views ?? 0), 0))} />
            </div>

            {/* Table */}
            <div style={{
              background: '#111318',
              border: '1px solid rgba(255,255,255,0.07)',
              borderRadius: 12,
              overflow: 'hidden',
            }}>
              {/* Table header */}
              <div style={{
                display: 'grid',
                gridTemplateColumns: '1fr 100px 120px 100px 80px 40px',
                gap: 16,
                padding: '12px 20px',
                borderBottom: '1px solid rgba(255,255,255,0.07)',
              }}>
                {['Product', 'Price', 'Status', 'Try-ons', 'Views', ''].map((h, i) => (
                  <span key={i} style={{
                    fontSize: 11, fontWeight: 500, color: '#6B7280',
                    letterSpacing: '0.08em', textTransform: 'uppercase',
                  }}>{h}</span>
                ))}
              </div>
              {products.map(p => (
                <ProductRow key={p.product_id} product={p} onStatusChange={handleStatusChange} />
              ))}
            </div>
          </div>
        )}

        {/* ── Analytics Tab ── */}
        {activeTab === 'analytics' && (
          <div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 32 }}>
              <StatCard label="Total Views" value={fmt(analytics.total_views)} delta="Last 30 days" />
              <StatCard label="Saves" value={fmt(analytics.total_saves)} />
              <StatCard label="Virtual Try-Ons" value={fmt(analytics.total_tryons)} />
              <StatCard label="Conversion" value={`${(analytics.conversion_rate * 100).toFixed(1)}%`} />
            </div>

            <div style={{
              background: '#111318',
              border: '1px solid rgba(255,255,255,0.07)',
              borderRadius: 12,
              padding: '24px',
            }}>
              <div style={{ fontSize: 13, fontWeight: 500, color: '#9BA3AF', marginBottom: 20, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Top Products by Views
              </div>
              {analytics.top_products.map((p, i) => (
                <div key={p.product_id} style={{
                  display: 'flex', alignItems: 'center', gap: 16,
                  padding: '12px 0',
                  borderBottom: i < analytics.top_products.length - 1 ? '1px solid rgba(255,255,255,0.05)' : 'none',
                }}>
                  <span style={{ color: '#374151', fontSize: 12, width: 20 }}>{String(i + 1).padStart(2, '0')}</span>
                  <span style={{ flex: 1, fontSize: 14, color: '#F0F0F0' }}>{p.name}</span>
                  <span style={{ fontSize: 13, color: '#C9A84C', fontFamily: 'monospace' }}>{fmt(p.views)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Assets Tab ── */}
        {activeTab === 'assets' && (
          <div>
            <div style={{ marginBottom: 24 }}>
              {uploadStatus && (
                <div style={{
                  background: uploadStatus.startsWith('✓') ? 'rgba(46,204,113,0.1)' : 'rgba(231,76,60,0.1)',
                  border: `1px solid ${uploadStatus.startsWith('✓') ? '#2ECC7140' : '#E74C3C40'}`,
                  borderRadius: 8, padding: '12px 16px',
                  fontSize: 13, color: uploadStatus.startsWith('✓') ? '#2ECC71' : '#E74C3C',
                  marginBottom: 16,
                }}>
                  {uploadStatus}
                </div>
              )}
              <UploadDropzone onUpload={handleUpload} />
            </div>

            <div style={{
              background: '#111318',
              border: '1px solid rgba(255,255,255,0.07)',
              borderRadius: 12,
              padding: '20px 24px',
            }}>
              <div style={{ fontSize: 12, color: '#6B7280', marginBottom: 8 }}>Storage Usage</div>
              <div style={{ fontSize: 22, color: '#F0F0F0', fontFamily: 'monospace' }}>12.4 MB</div>
              <div style={{ fontSize: 11, color: '#374151', marginTop: 4 }}>
                Private · gs://cirvanna-brand-assets/{brand.brand_id}/
              </div>
            </div>
          </div>
        )}

        {/* ── Communications Tab ── */}
        {activeTab === 'communications' && (
          <div style={{
            background: '#111318',
            border: '1px solid rgba(255,255,255,0.07)',
            borderRadius: 12,
            padding: '40px 24px',
            textAlign: 'center',
          }}>
            <div style={{ fontSize: 24, marginBottom: 12 }}>✉</div>
            <div style={{ color: '#F0F0F0', fontWeight: 500, marginBottom: 8 }}>No messages</div>
            <div style={{ color: '#6B7280', fontSize: 13 }}>
              Platform notifications and onboarding updates appear here
            </div>
          </div>
        )}

      </main>
    </div>
  );
}
