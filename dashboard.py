"""Revenue OS — 2050 Holographic Command Interface."""
from __future__ import annotations

import html
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from core.config import get_settings

st.set_page_config(page_title="Revenue OS // 2050", layout="wide", initial_sidebar_state="collapsed")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;700;900&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
    --bg:        #020510;
    --bg1:       #04081A;
    --bg2:       #060C20;
    --glass:     rgba(6, 15, 40, 0.7);
    --glass2:    rgba(10, 20, 55, 0.5);
    --cyan:      #00F5FF;
    --cyan-d:    rgba(0,245,255,0.08);
    --cyan-g:    rgba(0,245,255,0.15);
    --purple:    #BF5FFF;
    --purple-d:  rgba(191,95,255,0.08);
    --pink:      #FF2D78;
    --pink-d:    rgba(255,45,120,0.08);
    --green:     #00FF9C;
    --green-d:   rgba(0,255,156,0.08);
    --amber:     #FFB800;
    --amber-d:   rgba(255,184,0,0.08);
    --blue:      #4D9FFF;
    --text:      #E8F4FF;
    --muted:     #3A5070;
    --muted2:    #6080A0;
    --orb:       'Orbitron', sans-serif;
    --sans:      'Inter', sans-serif;
    --mono:      'JetBrains Mono', monospace;
}

html, body, .stApp {
    background: var(--bg) !important;
    font-family: var(--sans);
    color: var(--text);
    overflow-x: hidden;
}

/* Animated grid background */
.stApp::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image:
        linear-gradient(rgba(0,245,255,0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(0,245,255,0.03) 1px, transparent 1px);
    background-size: 60px 60px;
    pointer-events: none;
    z-index: 0;
}

header[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
#MainMenu, footer, .stDeployButton { display: none !important; }
section[data-testid="stSidebar"] { display: none !important; }
div.block-container { padding: 0 !important; max-width: 100% !important; }

::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: rgba(0,245,255,0.2); border-radius: 2px; }

/* ── TOP NAV ── */
.topnav {
    position: sticky; top: 0; z-index: 1000;
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 2rem; height: 56px;
    background: rgba(2,5,16,0.92);
    border-bottom: 1px solid rgba(0,245,255,0.12);
    backdrop-filter: blur(20px);
}
.nav-brand {
    font-family: var(--orb);
    font-size: 0.9rem;
    font-weight: 900;
    letter-spacing: 0.15em;
    background: linear-gradient(90deg, var(--cyan), var(--purple));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.nav-right {
    display: flex; align-items: center; gap: 1.5rem;
    font-family: var(--mono); font-size: 0.7rem; color: var(--muted2);
}
.nav-right strong { color: var(--cyan); }
.nav-badge {
    padding: 0.2rem 0.65rem; border-radius: 20px;
    font-family: var(--orb); font-size: 0.6rem;
    font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase;
}
.badge-live { background: var(--green-d); color: var(--green); border: 1px solid rgba(0,255,156,0.25); }
.badge-err  { background: var(--pink-d);  color: var(--pink);  border: 1px solid rgba(255,45,120,0.25); }

.pulse-dot {
    display: inline-block; width: 8px; height: 8px;
    border-radius: 50%; background: var(--green);
    box-shadow: 0 0 0 0 rgba(0,255,156,0.6);
    animation: sonar 1.8s infinite;
}
@keyframes sonar {
    0%   { box-shadow: 0 0 0 0 rgba(0,255,156,0.6); }
    70%  { box-shadow: 0 0 0 8px rgba(0,255,156,0); }
    100% { box-shadow: 0 0 0 0 rgba(0,255,156,0); }
}

/* ── HERO ── */
.hero {
    padding: 2rem 2rem 1.5rem 2rem;
    position: relative; overflow: hidden;
}
.hero::after {
    content: '';
    position: absolute; top: -60px; right: -60px;
    width: 400px; height: 400px; border-radius: 50%;
    background: radial-gradient(circle, rgba(191,95,255,0.08) 0%, transparent 70%);
    pointer-events: none;
}
.hero-label {
    font-family: var(--orb); font-size: 0.6rem;
    letter-spacing: 0.3em; text-transform: uppercase;
    color: var(--cyan); margin-bottom: 0.5rem;
    display: flex; align-items: center; gap: 0.5rem;
}
.hero-title {
    font-family: var(--orb);
    font-size: clamp(1.8rem, 3vw, 2.8rem);
    font-weight: 900;
    line-height: 1.05;
    letter-spacing: -0.01em;
    background: linear-gradient(135deg, #E8F4FF 0%, var(--cyan) 40%, var(--purple) 80%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 0.4rem;
}
.hero-sub {
    font-size: 0.85rem; color: var(--muted2);
    font-weight: 300; letter-spacing: 0.02em;
}
.hero-meta {
    margin-top: 1rem;
    display: flex; gap: 0.5rem; flex-wrap: wrap;
}
.holo-chip {
    padding: 0.3rem 0.75rem; border-radius: 20px;
    font-family: var(--mono); font-size: 0.68rem;
    background: var(--glass); border: 1px solid rgba(0,245,255,0.15);
    color: var(--muted2); backdrop-filter: blur(10px);
}
.holo-chip .val { color: var(--cyan); font-weight: 600; }

/* ── STAT GRID ── */
.stat-grid {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 1px; background: rgba(0,245,255,0.06);
    border-top: 1px solid rgba(0,245,255,0.08);
    border-bottom: 1px solid rgba(0,245,255,0.08);
}
.stat-tile {
    background: var(--bg1);
    padding: 1.1rem 1.2rem 0.9rem;
    position: relative; overflow: hidden;
    transition: background 0.2s;
}
.stat-tile:hover { background: var(--bg2); }
.stat-tile::before {
    content: ''; position: absolute;
    top: 0; left: 0; right: 0; height: 2px;
    background: var(--line-color, var(--cyan));
    opacity: 0.5;
}
.stat-lbl {
    font-family: var(--orb); font-size: 0.56rem;
    letter-spacing: 0.18em; text-transform: uppercase;
    color: var(--muted2); margin-bottom: 0.55rem;
}
.stat-num {
    font-family: var(--orb); font-size: 2rem;
    font-weight: 700; line-height: 1;
    color: var(--cyan);
    text-shadow: 0 0 20px rgba(0,245,255,0.35);
}
.stat-num.purple { color: var(--purple); text-shadow: 0 0 20px rgba(191,95,255,0.35); }
.stat-num.green  { color: var(--green);  text-shadow: 0 0 20px rgba(0,255,156,0.35); }
.stat-num.amber  { color: var(--amber);  text-shadow: 0 0 20px rgba(255,184,0,0.35); }
.stat-num.pink   { color: var(--pink);   text-shadow: 0 0 20px rgba(255,45,120,0.35); }
.stat-num.white  { color: var(--text);   text-shadow: none; }
.stat-sub { font-size: 0.68rem; color: var(--muted); margin-top: 0.35rem; }

/* ── ACTION BAR ── */
.action-strip {
    padding: 0.7rem 2rem;
    display: flex; align-items: center; gap: 0.8rem;
    font-family: var(--mono); font-size: 0.78rem;
    border-bottom: 1px solid rgba(0,245,255,0.07);
    background: var(--bg1);
}
.action-strip.cyan   { border-left: 3px solid var(--cyan);   background: rgba(0,245,255,0.04); }
.action-strip.green  { border-left: 3px solid var(--green);  background: rgba(0,255,156,0.04); }
.action-strip.amber  { border-left: 3px solid var(--amber);  background: rgba(255,184,0,0.05); }
.action-strip.pink   { border-left: 3px solid var(--pink);   background: rgba(255,45,120,0.05); }
.action-strip .icon  { font-size: 1rem; }
.action-strip .msg   { color: var(--text); flex: 1; }
.action-strip code {
    font-family: var(--mono); font-size: 0.72rem;
    background: rgba(255,255,255,0.07); padding: 0.1rem 0.4rem;
    border-radius: 4px; color: var(--cyan);
}

/* ── FUNNEL ── */
.funnel-bar {
    display: flex; align-items: stretch;
    padding: 0.6rem 2rem; gap: 0;
    background: var(--bg1); border-bottom: 1px solid rgba(0,245,255,0.07);
}
.f-stage {
    display: flex; flex-direction: column; align-items: center;
    padding: 0.4rem 1.5rem; gap: 0.2rem;
}
.f-n {
    font-family: var(--orb); font-size: 1.3rem;
    font-weight: 700;
}
.f-label {
    font-size: 0.6rem; font-family: var(--orb);
    text-transform: uppercase; letter-spacing: 0.12em; color: var(--muted2);
}
.f-pct { font-size: 0.62rem; color: var(--muted); font-family: var(--mono); }
.f-arrow { display: flex; align-items: center; color: var(--muted); font-size: 1.2rem; padding: 0 0.3rem; }

/* ── GLASS PANEL ── */
.glass-panel {
    background: var(--glass);
    border: 1px solid rgba(0,245,255,0.1);
    border-radius: 16px;
    backdrop-filter: blur(20px);
    overflow: hidden;
    margin: 0 0 1rem 0;
}
.panel-head {
    display: flex; align-items: center; justify-content: space-between;
    padding: 0.6rem 1rem;
    border-bottom: 1px solid rgba(0,245,255,0.08);
    background: rgba(0,245,255,0.04);
}
.panel-head-title {
    font-family: var(--orb); font-size: 0.62rem;
    letter-spacing: 0.18em; text-transform: uppercase;
    color: var(--cyan);
}
.panel-head-count { font-family: var(--mono); font-size: 0.65rem; color: var(--muted2); }

/* ── HOLO TABLE ── */
.htbl { width: 100%; border-collapse: collapse; }
.htbl th {
    font-family: var(--orb); font-size: 0.56rem;
    letter-spacing: 0.15em; text-transform: uppercase;
    color: var(--muted2); padding: 0.5rem 1rem;
    border-bottom: 1px solid rgba(0,245,255,0.08);
    text-align: left; white-space: nowrap;
    background: rgba(0,0,0,0.2);
}
.htbl td {
    font-family: var(--mono); font-size: 0.75rem;
    padding: 0.55rem 1rem; color: var(--text);
    border-bottom: 1px solid rgba(0,245,255,0.05);
    white-space: nowrap; overflow: hidden;
    text-overflow: ellipsis; max-width: 220px;
}
.htbl tr:hover td { background: rgba(0,245,255,0.04); }
.s-hi  { color: var(--green);  font-weight: 600; text-shadow: 0 0 10px rgba(0,255,156,0.4); }
.s-mid { color: var(--amber); }
.s-lo  { color: var(--muted2); }

/* ── HOLO TAG ── */
.htag {
    display: inline-block;
    font-family: var(--orb); font-size: 0.55rem;
    font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
    padding: 0.14rem 0.5rem; border-radius: 20px;
}
.htag-qualified  { background:rgba(0,255,156,0.1);  color:var(--green);  border:1px solid rgba(0,255,156,0.25); }
.htag-reviewed   { background:rgba(255,184,0,0.1);  color:var(--amber);  border:1px solid rgba(255,184,0,0.25); }
.htag-new        { background:rgba(77,159,255,0.1); color:var(--blue);   border:1px solid rgba(77,159,255,0.25); }
.htag-stub       { background:rgba(58,80,112,0.15); color:var(--muted2); border:1px solid rgba(58,80,112,0.3); }
.htag-emailed,.htag-audit_ready { background:rgba(0,245,255,0.1); color:var(--cyan); border:1px solid rgba(0,245,255,0.25); }
.htag-sendable   { background:rgba(0,255,156,0.1);  color:var(--green);  border:1px solid rgba(0,255,156,0.25); }
.htag-needs_edit { background:rgba(255,184,0,0.1);  color:var(--amber);  border:1px solid rgba(255,184,0,0.25); }
.htag-do_not_send{ background:rgba(255,45,120,0.1); color:var(--pink);   border:1px solid rgba(255,45,120,0.25); }
.htag-replied,.htag-interested,.htag-closed_won { background:rgba(0,255,156,0.1); color:var(--green); border:1px solid rgba(0,255,156,0.25); }
.htag-closed_lost { background:rgba(255,45,120,0.1); color:var(--pink); border:1px solid rgba(255,45,120,0.25); }

/* ── FEED ── */
.feed-item {
    display: grid; grid-template-columns: 4.5rem 7rem 1fr;
    gap: 0.6rem; align-items: baseline;
    padding: 0.55rem 1rem;
    border-bottom: 1px solid rgba(0,245,255,0.05);
    font-family: var(--mono); font-size: 0.72rem;
    transition: background 0.15s;
}
.feed-item:hover { background: rgba(0,245,255,0.03); }
.f-time  { color: var(--muted2); font-size: 0.62rem; }
.f-agent { font-weight: 600; font-size: 0.68rem; }
.f-text  { color: var(--text); }
.f-meta  { color: var(--muted2); font-size: 0.65rem; }
.f-err   { color: var(--pink); }

/* ── CARD ITEM ── */
.card-item {
    padding: 0.85rem 1rem;
    border-bottom: 1px solid rgba(0,245,255,0.06);
    transition: background 0.15s;
}
.card-item:hover { background: rgba(0,245,255,0.03); }
.card-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem; margin-bottom: 0.3rem; }
.card-name { font-weight: 600; font-size: 0.85rem; color: var(--text); }
.card-meta { font-family: var(--mono); font-size: 0.68rem; color: var(--muted2); margin-bottom: 0.3rem; }
.card-body { font-size: 0.75rem; color: var(--muted2); line-height: 1.5; }

/* ── TAB OVERRIDES ── */
.stTabs [data-baseweb="tab-list"] {
    background: var(--bg1) !important;
    border-bottom: 1px solid rgba(0,245,255,0.1) !important;
    gap: 0; padding: 0 2rem;
}
.stTabs [data-baseweb="tab"] {
    font-family: var(--orb) !important;
    font-size: 0.6rem !important;
    letter-spacing: 0.15em !important;
    text-transform: uppercase !important;
    color: var(--muted2) !important;
    padding: 0.6rem 1rem !important;
    border: none !important; border-radius: 0 !important;
    background: transparent !important;
}
.stTabs [aria-selected="true"] {
    color: var(--cyan) !important;
    border-bottom: 2px solid var(--cyan) !important;
    text-shadow: 0 0 12px rgba(0,245,255,0.5);
}

/* ── WIDGET OVERRIDES ── */
[data-baseweb="select"] > div {
    background: var(--glass) !important;
    border: 1px solid rgba(0,245,255,0.15) !important;
    border-radius: 8px !important;
    backdrop-filter: blur(10px) !important;
    min-height: 36px !important;
}
[data-baseweb="select"] * {
    color: var(--text) !important;
    font-family: var(--mono) !important;
    font-size: 0.73rem !important;
}
.stMultiSelect label, .stToggle label {
    font-family: var(--orb) !important;
    font-size: 0.58rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.15em !important;
    color: var(--muted2) !important;
}
div[data-testid="stExpander"] {
    border: 1px solid rgba(0,245,255,0.12) !important;
    border-radius: 10px !important;
    background: var(--glass) !important;
    backdrop-filter: blur(10px) !important;
}
div[data-testid="stExpander"] summary {
    font-family: var(--mono) !important;
    font-size: 0.68rem !important;
    color: var(--cyan) !important;
}

/* section wrapper */
.section-wrap { padding: 1.5rem 2rem 0 2rem; }
</style>
"""

# ── helpers ────────────────────────────────────────────────────────────────

def _db_path() -> Path:
    return get_settings().db_path

@st.cache_data(ttl=8)
def _q(query: str) -> pd.DataFrame:
    db = _db_path()
    if not db.exists(): return pd.DataFrame()
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        return pd.read_sql_query(query, conn)

def _leads():  return _q("SELECT * FROM leads ORDER BY score DESC, updated_at DESC")
def _emails(): return _q("""
    SELECT e.id, e.lead_id, l.name AS lead_name, l.city, l.category,
           l.status AS lead_status, l.score,
           e.subject, e.body, e.sendability, e.notes, e.created_at
    FROM emails e JOIN leads l ON l.id = e.lead_id ORDER BY e.created_at DESC
""")
def _audits(): return _q("""
    SELECT a.id, a.lead_id, l.name AS lead_name, l.city, l.category,
           l.status AS lead_status, a.summary, a.offer_angle, a.file_path, a.created_at
    FROM audits a JOIN leads l ON l.id = a.lead_id ORDER BY a.created_at DESC
""")
def _logs():   return _q("SELECT * FROM logs ORDER BY timestamp DESC LIMIT 200")

def _ts(v, t=False):
    if not v: return "—"
    s = str(v).replace("T"," ")
    return s[11:16] if t else s[:16]

def _now(): return datetime.now(timezone.utc).strftime("%Y-%m-%d  %H:%M:%S  UTC")

def _tag(label):
    k = (label or "").lower().replace(" ","_")
    return f'<span class="htag htag-{k}">{html.escape(label.upper())}</span>'

def _sc(v):
    return "s-hi" if v>=7 else ("s-mid" if v>=5 else "s-lo")

def _clean(text):
    if not text: return ""
    text = text.strip()
    if text.startswith("```") or (text.startswith("{") and '"body"' in text[:60]):
        c = re.sub(r"^```[a-z]*\n?","",text); c=re.sub(r"\n?```$","",c).strip()
        try:
            d=json.loads(c); return d.get("body") or d.get("summary") or c
        except: return c
    return text

def _e(v):
    if v is None or (isinstance(v,float) and pd.isna(v)): return "—"
    return html.escape(str(v))

# ── sections ───────────────────────────────────────────────────────────────

def _topnav(last: str, has_err: bool):
    badge = f'<span class="nav-badge badge-err">⚠ ERRORS</span>' if has_err else f'<span class="nav-badge badge-live"><span class="pulse-dot"></span> LIVE</span>'
    st.markdown(f"""
    <div class="topnav">
        <div class="nav-brand">REVENUE OS // NEURAL COMMAND</div>
        <div class="nav-right">
            <span>LAST SYNC <strong>{html.escape(last)}</strong></span>
            <span>{_now()}</span>
            {badge}
        </div>
    </div>""", unsafe_allow_html=True)

def _hero(leads_n, emails_n, audits_n, last):
    st.markdown(f"""
    <div class="hero">
        <div class="hero-label"><span class="pulse-dot"></span> AGENT INTELLIGENCE LAYER · REVENUE OPERATIONS</div>
        <div class="hero-title">Pipeline Command<br>Center</div>
        <div class="hero-sub">Real-time revenue intelligence for local home-service lead generation</div>
        <div class="hero-meta">
            <span class="holo-chip">LEADS <span class="val">{leads_n}</span></span>
            <span class="holo-chip">DRAFTS <span class="val">{emails_n}</span></span>
            <span class="holo-chip">AUDITS <span class="val">{audits_n}</span></span>
            <span class="holo-chip">LAST SCRAPE <span class="val">{html.escape(last)}</span></span>
        </div>
    </div>""", unsafe_allow_html=True)

def _stats(leads, emails, audits):
    real  = leads[leads["source"]!="fallback_stub"] if not leads.empty else pd.DataFrame()
    n     = len(real)
    qual  = int(real["status"].isin(["qualified","reviewed"]).sum()) if not real.empty else 0
    cont  = int(real["status"].isin(["emailed","replied","interested","audit_ready","closed_won"]).sum()) if not real.empty else 0
    send  = int((emails["sendability"]=="sendable").sum()) if not emails.empty else 0
    edit  = int((emails["sendability"]=="needs_edit").sum()) if not emails.empty else 0
    an    = len(audits)
    avg   = f"{real['score'].mean():.1f}" if not real.empty else "—"
    st.markdown(f"""
    <div class="stat-grid">
        <div class="stat-tile" style="--line-color:var(--cyan)">
            <div class="stat-lbl">Real Leads</div>
            <div class="stat-num white">{n}</div>
            <div class="stat-sub">avg score {avg}</div>
        </div>
        <div class="stat-tile" style="--line-color:var(--purple)">
            <div class="stat-lbl">Qualified+</div>
            <div class="stat-num purple">{qual}</div>
            <div class="stat-sub">reviewed or above</div>
        </div>
        <div class="stat-tile" style="--line-color:var(--cyan)">
            <div class="stat-lbl">In Contact</div>
            <div class="stat-num">{cont}</div>
            <div class="stat-sub">emailed or beyond</div>
        </div>
        <div class="stat-tile" style="--line-color:var(--green)">
            <div class="stat-lbl">Sendable</div>
            <div class="stat-num green">{send}</div>
            <div class="stat-sub">ready to deploy</div>
        </div>
        <div class="stat-tile" style="--line-color:var(--amber)">
            <div class="stat-lbl">Needs Edit</div>
            <div class="stat-num amber">{edit}</div>
            <div class="stat-sub">review before send</div>
        </div>
        <div class="stat-tile" style="--line-color:var(--purple)">
            <div class="stat-lbl">Audit Memos</div>
            <div class="stat-num purple">{an}</div>
            <div class="stat-sub">opportunity files</div>
        </div>
    </div>""", unsafe_allow_html=True)

def _funnel(leads):
    real = leads[leads["source"]!="fallback_stub"] if not leads.empty else pd.DataFrame()
    s = len(real)
    r = int(real["status"].isin(["qualified","reviewed","emailed","replied","interested","audit_ready","closed_won"]).sum()) if not real.empty else 0
    e = int(real["status"].isin(["emailed","replied","interested","audit_ready","closed_won"]).sum()) if not real.empty else 0
    w = int(real["status"].isin(["closed_won"]).sum()) if not real.empty else 0
    def pct(a,b): return f"{int(a/max(b,1)*100)}%" if b else "—"
    st.markdown(f"""
    <div class="funnel-bar">
        <div class="f-stage"><div class="f-n" style="color:var(--blue)">{s}</div><div class="f-label">Scraped</div><div class="f-pct">100%</div></div>
        <div class="f-arrow">›</div>
        <div class="f-stage"><div class="f-n" style="color:var(--purple)">{r}</div><div class="f-label">Reviewed</div><div class="f-pct">{pct(r,s)}</div></div>
        <div class="f-arrow">›</div>
        <div class="f-stage"><div class="f-n" style="color:var(--cyan)">{e}</div><div class="f-label">Emailed</div><div class="f-pct">{pct(e,s)}</div></div>
        <div class="f-arrow">›</div>
        <div class="f-stage"><div class="f-n" style="color:var(--green)">{w}</div><div class="f-label">Won</div><div class="f-pct">{pct(w,s)}</div></div>
    </div>""", unsafe_allow_html=True)

def _action_bar(leads, emails, has_err):
    real = leads[leads["source"]!="fallback_stub"] if not leads.empty else pd.DataFrame()
    send = int((emails["sendability"]=="sendable").sum()) if not emails.empty else 0
    edit = int((emails["sendability"]=="needs_edit").sum()) if not emails.empty else 0
    qual = int(real["status"].isin(["qualified","reviewed"]).sum()) if not real.empty else 0
    if has_err:
        tone,icon,msg = "pink","⚠","Scheduler error detected. Inspect activity feed — resolve before next automated run."
    elif send>0:
        tone,icon,msg = "green","✦",f"{send} draft{'s' if send>1 else ''} ready to transmit · <code>python cli.py export-emails</code>"
    elif edit>0:
        tone,icon,msg = "amber","◈",f"{edit} draft{'s' if edit>1 else ''} flagged NEEDS_EDIT · review before sending · <code>python cli.py export-emails</code>"
    elif qual>0:
        tone,icon,msg = "cyan","→",f"{qual} lead{'s' if qual>1 else ''} awaiting outreach · <code>python cli.py generate-emails --limit 20</code>"
    else:
        tone,icon,msg = "green","✓","All systems nominal · pipeline is healthy · next scrape on schedule"
    st.markdown(f'<div class="action-strip {tone}"><span class="icon">{icon}</span><span class="msg">{msg}</span></div>',unsafe_allow_html=True)

def _lead_table(df):
    real = df[df["source"]!="fallback_stub"] if not df.empty else df
    if real.empty:
        st.markdown('<div style="padding:2rem;text-align:center;color:var(--muted2);font-family:var(--orb);font-size:0.7rem;letter-spacing:0.15em;">NO LEAD DATA — RUN SCRAPE</div>',unsafe_allow_html=True)
        return
    rows = real.sort_values("score",ascending=False).head(30)
    trs=""
    for _,r in rows.iterrows():
        sc=float(r.get("score") or 0)
        trs+=(f"<tr>"
              f"<td style='color:var(--muted2);font-size:0.62rem;'>{_e(r.get('id'))}</td>"
              f"<td title='{_e(r.get('name'))}'>{_e(str(r.get('name') or '')[:30])}</td>"
              f"<td>{_tag(str(r.get('status','new')))}</td>"
              f"<td class='{_sc(sc)}'>{sc:.1f}</td>"
              f"<td style='color:var(--muted2)'>{_e(r.get('city'))}</td>"
              f"<td style='color:var(--muted2)'>{_e(r.get('phone'))}</td>"
              f"<td style='color:{'var(--green)' if r.get('website') else 'var(--muted)'}'>"
              f"{'✦' if r.get('website') else '○'}</td>"
              f"<td style='color:var(--muted2);font-size:0.62rem;'>{_ts(r.get('updated_at'))}</td>"
              f"</tr>")
    st.markdown(
        f'<div class="panel-head"><div class="panel-head-title">Lead Intelligence Matrix</div><div class="panel-head-count">{len(rows)} nodes</div></div>'
        f'<div style="overflow-x:auto;">'
        f'<table class="htbl"><thead><tr>'
        f'<th>ID</th><th>ENTITY</th><th>STATUS</th><th>SCORE</th><th>SECTOR</th><th>COMM</th><th>WEB</th><th>UPDATED</th>'
        f'</tr></thead><tbody>{trs}</tbody></table></div>',
        unsafe_allow_html=True)

def _feed(logs):
    st.markdown(f'<div class="panel-head"><div class="panel-head-title">Neural Activity Log</div><div class="panel-head-count">{len(logs)} events</div></div>',unsafe_allow_html=True)
    if logs.empty:
        st.markdown('<div style="padding:1.5rem;color:var(--muted2);font-family:var(--mono);font-size:0.72rem;">awaiting agent events...</div>',unsafe_allow_html=True)
        return
    C={"lead_hunter":"var(--blue)","outreach":"var(--amber)","audit_offer":"var(--cyan)","scheduler":"var(--green)"}
    out=""
    for _,r in logs.head(40).iterrows():
        ag=str(r.get("agent") or ""); ac=str(r.get("action") or "")
        col=C.get(ag,"var(--muted2)"); err="error" in ac.lower()
        try:
            m=json.loads(r.get("metadata") or "{}"); ms="  ".join(f"{k}={v}" for k,v in list(m.items())[:3] if k!="trace")
        except: ms=str(r.get("metadata") or "")[:80]
        acls="f-err" if err else "f-text"
        out+=(f'<div class="feed-item">'
              f'<span class="f-time">{_ts(r.get("timestamp"),t=True)}</span>'
              f'<span class="f-agent" style="color:{col}">[{html.escape(ag)}]</span>'
              f'<div><span class="{acls}">{html.escape(ac)}</span>'
              f'<span class="f-meta">&nbsp;{html.escape(ms[:100])}</span></div>'
              f'</div>')
    st.markdown(out,unsafe_allow_html=True)

def _drafts(df):
    st.markdown(f'<div class="panel-head"><div class="panel-head-title">Outreach Transmissions</div><div class="panel-head-count">{len(df)} drafts</div></div>',unsafe_allow_html=True)
    if df.empty:
        st.markdown('<div style="padding:1.5rem;color:var(--muted2);font-family:var(--mono);font-size:0.72rem;">no transmissions queued</div>',unsafe_allow_html=True)
        return
    for _,r in df.head(10).iterrows():
        body=_clean(str(r.get("body") or ""))
        st.markdown(
            f'<div class="card-item">'
            f'<div class="card-top"><span class="card-name">{_e(r.get("lead_name"))}</span>{_tag(str(r.get("sendability","needs_edit")))}</div>'
            f'<div class="card-meta">SUBJ: {_e(r.get("subject"))} · {_ts(r.get("created_at"))}</div>'
            f'<div class="card-body">{html.escape(body[:180]+("…" if len(body)>180 else ""))}</div>'
            f'</div>',unsafe_allow_html=True)
        if len(body)>180:
            with st.expander("▶ full transmission"): st.code(body,language=None)

def _audit_cards(df):
    st.markdown(f'<div class="panel-head"><div class="panel-head-title">Opportunity Intelligence Files</div><div class="panel-head-count">{len(df)} memos</div></div>',unsafe_allow_html=True)
    if df.empty:
        st.markdown('<div style="padding:1.5rem;color:var(--muted2);font-family:var(--mono);font-size:0.72rem;">no intelligence files generated</div>',unsafe_allow_html=True)
        return
    for _,r in df.head(10).iterrows():
        summary=_clean(str(r.get("summary") or "")); angle=str(r.get("offer_angle") or "")
        st.markdown(
            f'<div class="card-item">'
            f'<div class="card-top"><span class="card-name">{_e(r.get("lead_name"))}</span>{_tag(str(r.get("lead_status","audit_ready")))}</div>'
            f'<div class="card-meta">{_e(r.get("city"))} · {_ts(r.get("created_at"))}</div>'
            f'<div class="card-body">{html.escape(summary[:200]+("…" if len(summary)>200 else ""))}</div>'
            f'</div>',unsafe_allow_html=True)
        if angle:
            with st.expander("▶ full intelligence file"):
                st.write(f"**Angle:** {angle}")
                fp=r.get("file_path")
                if fp and Path(fp).exists(): st.markdown(Path(fp).read_text())

# ── main ───────────────────────────────────────────────────────────────────

def main():
    st.markdown(CSS, unsafe_allow_html=True)
    if not _db_path().exists():
        st.error("Database offline — run `python cli.py init-db`"); st.stop()

    leads=_leads(); emails=_emails(); audits=_audits(); logs=_logs()
    real = leads[leads["source"]!="fallback_stub"] if not leads.empty else pd.DataFrame()

    last = "never"
    if not logs.empty:
        sr=logs[logs["action"]=="scrape"]
        if not sr.empty: last=_ts(sr.iloc[0]["timestamp"])

    has_err = not logs.empty and (logs["action"]=="job_error").any()

    _topnav(last, has_err)
    _hero(len(real), len(emails), len(audits), last)

    # filters
    st.markdown('<div style="padding:0.6rem 2rem;background:rgba(4,8,26,0.8);border-bottom:1px solid rgba(0,245,255,0.08);backdrop-filter:blur(10px);">',unsafe_allow_html=True)
    fc=st.columns([1,1,1,0.5])
    ss=sorted(leads["status"].dropna().unique()) if not leads.empty else []
    sc=sorted(leads["city"].dropna().unique()) if not leads.empty else []
    sn=sorted(leads["category"].dropna().unique()) if not leads.empty else []
    with fc[0]: sel_s=st.multiselect("STATUS",ss,placeholder="all statuses",label_visibility="collapsed")
    with fc[1]: sel_c=st.multiselect("CITY",sc,placeholder="all sectors",label_visibility="collapsed")
    with fc[2]: sel_n=st.multiselect("NICHE",sn,placeholder="all niches",label_visibility="collapsed")
    with fc[3]: stubs=st.toggle("STUBS",value=False)
    st.markdown('</div>',unsafe_allow_html=True)

    def _f(df):
        if df.empty: return df
        f=df.copy()
        if sel_s and "status" in f: f=f[f["status"].isin(sel_s)]
        if sel_c and "city" in f: f=f[f["city"].isin(sel_c)]
        if sel_n and "category" in f: f=f[f["category"].isin(sel_n)]
        if not stubs and "source" in f: f=f[f["source"]!="fallback_stub"]
        return f

    fl=_f(leads); ids=set(fl["id"].tolist()) if not fl.empty else set()
    fe=emails[emails["lead_id"].isin(ids)] if not emails.empty and ids else emails.iloc[0:0]
    fa=audits[audits["lead_id"].isin(ids)] if not audits.empty and ids else audits.iloc[0:0]

    _stats(fl,fe,fa)
    _funnel(fl)
    _action_bar(fl,fe,has_err)

    tabs=st.tabs(["LEADS","ACTIVITY","DRAFTS","AUDITS","RAW"])
    with tabs[0]: _lead_table(fl)
    with tabs[1]: _feed(logs)
    with tabs[2]: _drafts(fe)
    with tabs[3]: _audit_cards(fa)
    with tabs[4]:
        sub=st.tabs(["leads","emails","audits","logs"])
        with sub[0]: st.dataframe(fl.head(60),hide_index=True)
        with sub[1]: st.dataframe(fe.head(60),hide_index=True)
        with sub[2]: st.dataframe(fa.head(30),hide_index=True)
        with sub[3]: st.dataframe(logs.head(80),hide_index=True)

if __name__=="__main__":
    main()
