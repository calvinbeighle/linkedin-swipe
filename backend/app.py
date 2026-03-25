"""
Lead Swipe -- FastAPI backend + web app.

Serves the swipe web app and API for reviewing lead profiles.
"""

import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

import requests
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# --- Database ----------------------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./linkedin_swipe.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, index=True)
    linkedin_url = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    headline = Column(String)
    company = Column(String)
    location = Column(String)
    photo_url = Column(String)
    icp_score = Column(Integer, nullable=True)
    employee_count = Column(String, nullable=True)
    company_summary = Column(Text, nullable=True)
    ai_signal = Column(String, nullable=True)
    ai_signal_analysis = Column(Text, nullable=True)
    why_trace_fits = Column(Text, nullable=True)
    recommended_approach = Column(Text, nullable=True)
    score_breakdown = Column(Text, nullable=True)
    job_search_url = Column(String, nullable=True)
    status = Column(String, default="pending", index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    swiped_at = Column(DateTime, nullable=True)


Base.metadata.create_all(bind=engine)

# --- Pydantic schemas --------------------------------------------------------


class ProfileCreate(BaseModel):
    linkedin_url: str
    name: str
    headline: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    photo_url: Optional[str] = None
    icp_score: Optional[int] = None
    employee_count: Optional[str] = None
    company_summary: Optional[str] = None
    ai_signal: Optional[str] = None
    ai_signal_analysis: Optional[str] = None
    why_trace_fits: Optional[str] = None
    recommended_approach: Optional[str] = None
    score_breakdown: Optional[str] = None
    job_search_url: Optional[str] = None


class ProfileResponse(BaseModel):
    id: int
    linkedin_url: str
    name: str
    headline: Optional[str]
    company: Optional[str]
    location: Optional[str]
    photo_url: Optional[str]
    icp_score: Optional[int]
    employee_count: Optional[str]
    company_summary: Optional[str]
    ai_signal: Optional[str]
    ai_signal_analysis: Optional[str]
    why_trace_fits: Optional[str]
    recommended_approach: Optional[str]
    score_breakdown: Optional[str]
    job_search_url: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class SwipeAction(BaseModel):
    profile_id: int
    direction: str


class StatsResponse(BaseModel):
    total: int
    pending: int
    liked: int
    skipped: int


# --- App ---------------------------------------------------------------------

app = FastAPI(title="Lead Swipe")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.getenv("SWIPE_API_KEY", "")


def verify_api_key(authorization: str = Header(None), key: str = Query(None)):
    """Accept auth via header OR ?key= query param."""
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    elif key:
        token = key
    if not token or token != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Web App (served as HTML) -----------------------------------------------


@app.get("/", response_class=RedirectResponse)
def root():
    return RedirectResponse(url="/app?key=" + API_KEY)


@app.get("/app", response_class=HTMLResponse)
def serve_app(key: str = Query("")):
    """Serve the swipe web app. Auth via ?key= query param."""
    if key != API_KEY:
        return HTMLResponse("<h1>Invalid key</h1>", status_code=401)

    return HTMLResponse(WEB_APP_HTML.replace("__API_KEY__", key))


WEB_APP_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Swipe">
<meta name="robots" content="noindex, nofollow">
<title>Lead Swipe</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Crimson+Text:wght@400;600&family=Playfair+Display:ital@1&display=swap" rel="stylesheet">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
html, body { height: 100%; }
body {
  font-family: 'Crimson Text', serif;
  background: #e8e8e8;
  color: rgba(0,0,0,0.7);
  display: flex; flex-direction: column;
  padding-top: env(safe-area-inset-top, 20px);
  padding-bottom: env(safe-area-inset-bottom, 20px);
}

.header {
  background: #fff; padding: 14px 20px 12px;
  border-bottom: 1px solid rgba(0,0,0,0.08);
  display: flex; justify-content: space-between; align-items: baseline;
  flex-shrink: 0;
}
.header h1 {
  font-family: 'Playfair Display', serif;
  font-weight: 400; font-style: italic;
  font-size: 20px; color: rgba(0,0,0,0.85);
}
.header .counter { font-size: 13px; color: rgba(0,0,0,0.35); }

.card-area {
  flex: 1; display: flex; align-items: flex-start; justify-content: center;
  padding: 16px; overflow-y: auto; -webkit-overflow-scrolling: touch;
}

.card {
  background: #fff; width: 100%; max-width: 440px;
  border-radius: 3px; padding: 32px 24px 24px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.08);
  animation: fadeIn 0.2s ease-out;
}
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.card-top {
  display: flex; align-items: flex-start; gap: 16px; margin-bottom: 20px;
}
.card .avatar {
  width: 72px; height: 72px; border-radius: 50%; flex-shrink: 0;
  background: rgba(0,0,0,0.06); color: rgba(0,0,0,0.35);
  font-family: 'Playfair Display', serif; font-style: italic;
  font-size: 22px;
  overflow: hidden; display: flex; align-items: center; justify-content: center;
}
.card .avatar img {
  width: 100%; height: 100%; object-fit: cover; border-radius: 50%;
}
.card-top-info { flex: 1; min-width: 0; }

.card .name {
  font-size: 22px; font-weight: 600; color: rgba(0,0,0,0.85);
  letter-spacing: 0.2px; line-height: 1.2;
}
.card .headline {
  font-size: 14px; color: rgba(0,0,0,0.55); margin-top: 4px;
  line-height: 1.3;
}
.card .meta-row {
  display: flex; gap: 12px; flex-wrap: wrap; margin-top: 6px;
  font-size: 13px; color: rgba(0,0,0,0.4);
}
.card .meta-row span { white-space: nowrap; }

.icp-badge {
  display: inline-block; padding: 2px 10px; border-radius: 2px;
  font-size: 13px; font-weight: 600; letter-spacing: 0.5px;
  margin-top: 6px;
}
.icp-high { background: rgba(0,120,0,0.1); color: rgba(0,120,0,0.8); }
.icp-mid { background: rgba(180,130,0,0.1); color: rgba(180,130,0,0.8); }
.icp-low { background: rgba(180,0,0,0.1); color: rgba(180,0,0,0.8); }

.sep { width: 40px; height: 1px; background: rgba(0,0,0,0.1); margin: 16px 0; }

.section-label {
  font-size: 11px; font-weight: 600; letter-spacing: 1.5px;
  text-transform: uppercase; color: rgba(0,0,0,0.3); margin-bottom: 6px;
}
.section-text {
  font-size: 15px; color: rgba(0,0,0,0.65); line-height: 1.5;
  margin-bottom: 16px;
}
.section-text:last-child { margin-bottom: 0; }

.insight-block {
  border-left: 2px solid rgba(0,0,0,0.1);
  background: rgba(0,0,0,0.02); padding: 10px 14px;
  margin-bottom: 16px;
}
.insight-block .section-text {
  font-family: 'Playfair Display', serif; font-style: italic;
  font-size: 14px; color: rgba(0,0,0,0.55); margin-bottom: 0;
}

.card-links {
  display: flex; gap: 10px; margin-top: 20px;
}
.card-links a {
  flex: 1; display: block; padding: 12px 16px;
  text-decoration: none; text-align: center;
  font-family: 'Crimson Text', serif; font-size: 14px; font-weight: 600;
  letter-spacing: 0.5px; border-radius: 2px;
  transition: opacity 0.15s;
}
.card-links a:active { opacity: 0.6; }
.link-linkedin { background: rgba(0,0,0,0.85); color: rgba(255,255,255,0.95); }
.link-signal { background: rgba(0,0,0,0.06); color: rgba(0,0,0,0.6); }

.actions {
  background: #fff; padding: 12px 20px 8px;
  border-top: 1px solid rgba(0,0,0,0.08);
  display: flex; gap: 14px; flex-shrink: 0;
}
.btn {
  flex: 1; padding: 16px 0; border: none; border-radius: 2px;
  font-family: 'Crimson Text', serif;
  font-size: 16px; font-weight: 600; letter-spacing: 1.5px;
  cursor: pointer; transition: opacity 0.15s;
}
.btn:active { opacity: 0.6; }
.btn-skip { background: rgba(0,0,0,0.05); color: rgba(0,0,0,0.45); }
.btn-connect { background: rgba(0,120,0,0.8); color: rgba(255,255,255,0.95); }
.btn:disabled { opacity: 0.3; }

.empty {
  display: none; flex: 1;
  flex-direction: column; justify-content: center; align-items: center;
  padding: 40px; text-align: center;
}
.empty.visible { display: flex; }
.empty h2 {
  font-family: 'Playfair Display', serif;
  font-weight: 400; font-style: italic;
  font-size: 24px; color: rgba(0,0,0,0.7);
}
.empty p { font-size: 15px; color: rgba(0,0,0,0.4); margin-top: 8px; }
.empty .refresh-btn {
  margin-top: 24px; padding: 12px 32px;
  background: rgba(0,0,0,0.85); color: rgba(255,255,255,0.95);
  border: none; border-radius: 2px; font-family: 'Crimson Text', serif;
  font-size: 15px; font-weight: 600; cursor: pointer;
}

.kbd-hint {
  text-align: center; font-size: 12px; color: rgba(0,0,0,0.25);
  padding: 4px 0 0; background: #fff;
}
</style>
</head>
<body>

<div class="header">
  <h1>Lead Swipe</h1>
  <span class="counter" id="counter">--</span>
</div>

<div class="card-area" id="cardArea">
  <div class="card" id="card">
    <div class="card-top">
      <div class="avatar" id="avatar">--</div>
      <div class="card-top-info">
        <div class="name" id="profileName">Loading...</div>
        <div class="headline" id="profileHeadline"></div>
        <div class="meta-row" id="profileMeta"></div>
        <div id="icpBadge"></div>
      </div>
    </div>
    <div id="enrichmentArea"></div>
    <div class="card-links" id="cardLinks">
      <a class="link-linkedin" id="viewLink" href="#" target="_blank" rel="noopener">LinkedIn Profile</a>
    </div>
  </div>
</div>

<div class="actions" id="actions">
  <button class="btn btn-skip" id="btnSkip" onclick="doSwipe('left')">SKIP</button>
  <button class="btn btn-connect" id="btnConnect" onclick="doSwipe('right')">CONNECT</button>
</div>
<div class="kbd-hint" id="kbdHint"></div>

<div class="empty" id="emptyState">
  <h2>All caught up</h2>
  <p>No pending leads to review</p>
  <button class="refresh-btn" onclick="loadProfiles()">Refresh</button>
</div>

<script>
const API_KEY = '__API_KEY__';
const BASE = window.location.origin;
const K = '?key=' + API_KEY;

let profiles = [];
let idx = 0;
let busy = false;

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function getInitials(name) {
  return name.split(' ').map(w => w[0]).filter(Boolean).slice(0,2).join('').toUpperCase();
}

function icpClass(score) {
  if (score >= 75) return 'icp-high';
  if (score >= 50) return 'icp-mid';
  return 'icp-low';
}

async function loadProfiles() {
  document.getElementById('emptyState').classList.remove('visible');
  document.getElementById('cardArea').style.display = 'flex';
  document.getElementById('actions').style.display = 'flex';
  document.getElementById('kbdHint').style.display = '';
  document.getElementById('profileName').textContent = 'Loading...';
  document.getElementById('profileHeadline').textContent = '';
  document.getElementById('enrichmentArea').innerHTML = '';
  try {
    const r = await fetch(BASE + '/profiles' + K + '&limit=200');
    profiles = await r.json();
    idx = 0;
    showCurrent();
  } catch(e) {
    document.getElementById('profileName').textContent = 'Error: ' + e.message;
  }
}

function showCurrent() {
  if (idx >= profiles.length) {
    document.getElementById('cardArea').style.display = 'none';
    document.getElementById('actions').style.display = 'none';
    document.getElementById('kbdHint').style.display = 'none';
    document.getElementById('emptyState').classList.add('visible');
    return;
  }
  const p = profiles[idx];

  document.getElementById('profileName').textContent = p.name || 'Profile';
  document.getElementById('profileHeadline').textContent = p.headline || '';

  // Meta row: company, location, employees
  let meta = [];
  if (p.company) meta.push(esc(p.company));
  if (p.location) meta.push(esc(p.location));
  if (p.employee_count) meta.push(esc(p.employee_count) + ' employees');
  document.getElementById('profileMeta').innerHTML = meta.map(m => '<span>' + m + '</span>').join('');

  // ICP badge
  const badge = document.getElementById('icpBadge');
  if (p.icp_score != null) {
    badge.innerHTML = '<span class="icp-badge ' + icpClass(p.icp_score) + '">ICP ' + p.icp_score + '</span>';
  } else {
    badge.innerHTML = '';
  }

  // Avatar
  const av = document.getElementById('avatar');
  const initials = getInitials(p.name || '?');
  if (p.photo_url) {
    av.innerHTML = '<img src="' + esc(p.photo_url) + '" onerror="this.parentNode.textContent=\'' + initials + '\'">';
  } else if (p.company) {
    const domain = p.company.toLowerCase().replace(/[^a-z0-9]/g,'') + '.com';
    av.innerHTML = '<img src="https://logo.clearbit.com/' + domain + '?size=192" onerror="this.parentNode.textContent=\'' + initials + '\'" style="border-radius:0;padding:12px;">';
  } else {
    av.innerHTML = ''; av.textContent = initials;
  }

  // Enrichment sections
  let html = '';

  if (p.company_summary) {
    html += '<div class="sep"></div>';
    html += '<div class="section-label">Company</div>';
    html += '<div class="section-text">' + esc(p.company_summary) + '</div>';
  }

  if (p.ai_signal) {
    html += '<div class="sep"></div>';
    html += '<div class="section-label">AI Signal</div>';
    html += '<div class="section-text">' + esc(p.ai_signal) + '</div>';
    if (p.ai_signal_analysis) {
      html += '<div class="insight-block"><div class="section-text">' + esc(p.ai_signal_analysis) + '</div></div>';
    }
  }

  if (p.why_trace_fits) {
    html += '<div class="sep"></div>';
    html += '<div class="section-label">Why Trace Fits</div>';
    html += '<div class="section-text">' + esc(p.why_trace_fits) + '</div>';
  }

  if (p.recommended_approach) {
    html += '<div class="sep"></div>';
    html += '<div class="section-label">Recommended Approach</div>';
    html += '<div class="section-text">' + esc(p.recommended_approach) + '</div>';
  }

  document.getElementById('enrichmentArea').innerHTML = html;

  // Links
  let links = '<a class="link-linkedin" href="' + esc(p.linkedin_url) + '" target="_blank" rel="noopener">LinkedIn Profile</a>';
  if (p.job_search_url) {
    links += '<a class="link-signal" href="' + esc(p.job_search_url) + '" target="_blank" rel="noopener">AI Job Posting</a>';
  }
  document.getElementById('cardLinks').innerHTML = links;

  document.getElementById('counter').textContent = (idx + 1) + ' / ' + profiles.length;
  document.getElementById('card').style.animation = 'none';
  void document.getElementById('card').offsetHeight;
  document.getElementById('card').style.animation = 'fadeIn 0.2s ease-out';
  document.getElementById('cardArea').scrollTop = 0;
}

async function doSwipe(direction) {
  if (busy || idx >= profiles.length) return;
  busy = true;
  document.querySelectorAll('.btn').forEach(b => b.disabled = true);
  try {
    await fetch(BASE + '/swipe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + API_KEY },
      body: JSON.stringify({ profile_id: profiles[idx].id, direction })
    });
  } catch(e) {}
  idx++;
  showCurrent();
  busy = false;
  document.querySelectorAll('.btn').forEach(b => b.disabled = false);
}

// Keyboard shortcuts
document.addEventListener('keydown', function(e) {
  if (e.key === 'ArrowLeft' || e.key === '1') doSwipe('left');
  if (e.key === 'ArrowRight' || e.key === '2') doSwipe('right');
});

if (window.matchMedia('(pointer: fine)').matches) {
  document.getElementById('kbdHint').textContent = 'Keyboard: left arrow = skip, right arrow = connect';
}

loadProfiles();
</script>
</body>
</html>"""


# --- API endpoints -----------------------------------------------------------


@app.get("/profiles", response_model=List[ProfileResponse])
def get_pending_profiles(
    limit: int = 50,
    db: Session = Depends(get_db),
    _auth: None = Depends(verify_api_key),
):
    return (
        db.query(Profile)
        .filter(Profile.status == "pending")
        .order_by(Profile.icp_score.desc().nullslast(), Profile.created_at.desc())
        .limit(limit)
        .all()
    )


@app.post("/profiles", status_code=201)
def upload_profiles(
    profiles: List[ProfileCreate],
    db: Session = Depends(get_db),
    _auth: None = Depends(verify_api_key),
):
    created = 0
    duplicates = 0
    for p in profiles:
        existing = (
            db.query(Profile).filter(Profile.linkedin_url == p.linkedin_url).first()
        )
        if existing:
            duplicates += 1
            continue
        db.add(Profile(**p.model_dump()))
        created += 1
    db.commit()
    log.info(f"Uploaded {created} new profiles ({duplicates} duplicates)")
    return {"created": created, "duplicates": duplicates}


@app.post("/swipe")
def record_swipe(
    swipe: SwipeAction,
    db: Session = Depends(get_db),
    _auth: None = Depends(verify_api_key),
):
    profile = db.query(Profile).filter(Profile.id == swipe.profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    if swipe.direction not in ("right", "left"):
        raise HTTPException(
            status_code=400, detail="direction must be 'right' or 'left'"
        )
    if swipe.direction == "right":
        profile.status = "liked"
        heyreach_ok = _add_to_heyreach(profile)
        if not heyreach_ok:
            log.warning(f"HeyReach push failed for {profile.linkedin_url}")
    else:
        profile.status = "skipped"
    profile.swiped_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "status": "ok",
        "profile_id": profile.id,
        "direction": swipe.direction,
        "heyreach": swipe.direction == "right",
    }


@app.get("/liked", response_model=List[ProfileResponse])
def get_liked_profiles(
    limit: int = 200,
    db: Session = Depends(get_db),
    _auth: None = Depends(verify_api_key),
):
    return (
        db.query(Profile)
        .filter(Profile.status == "liked")
        .order_by(Profile.swiped_at.desc())
        .limit(limit)
        .all()
    )


@app.patch("/profiles/{profile_id}")
def update_profile(
    profile_id: int,
    updates: dict,
    db: Session = Depends(get_db),
    _auth: None = Depends(verify_api_key),
):
    """Update a profile (used for photo enrichment)."""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    for key in (
        "photo_url",
        "headline",
        "company",
        "location",
        "linkedin_url",
        "icp_score",
        "employee_count",
        "company_summary",
        "ai_signal",
        "ai_signal_analysis",
        "why_trace_fits",
        "recommended_approach",
        "score_breakdown",
        "job_search_url",
    ):
        if key in updates:
            setattr(profile, key, updates[key])
    db.commit()
    return {"status": "ok", "profile_id": profile_id}


@app.get("/stats", response_model=StatsResponse)
def get_stats(
    db: Session = Depends(get_db),
    _auth: None = Depends(verify_api_key),
):
    total = db.query(Profile).count()
    pending = db.query(Profile).filter(Profile.status == "pending").count()
    liked = db.query(Profile).filter(Profile.status == "liked").count()
    skipped = db.query(Profile).filter(Profile.status == "skipped").count()
    return {"total": total, "pending": pending, "liked": liked, "skipped": skipped}


# --- HeyReach integration ---------------------------------------------------

HEYREACH_BASE = "https://api.heyreach.io/api/public"


def _add_to_heyreach(profile: Profile) -> bool:
    api_key = os.getenv("HEYREACH_API_KEY", "")
    campaign_id = os.getenv("HEYREACH_SWIPE_CAMPAIGN_ID", "")
    if not api_key or not campaign_id:
        log.warning("HeyReach not configured (missing API key or campaign ID)")
        return False
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        resp = requests.get(
            f"{HEYREACH_BASE}/campaign/GetById?campaignId={campaign_id}",
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        campaign = resp.json()
    except Exception as e:
        log.error(f"Failed to fetch HeyReach campaign: {e}")
        return False
    account_ids = campaign.get("campaignAccountIds", [])
    if not account_ids:
        log.error(f"Campaign {campaign_id} has no linked LinkedIn accounts")
        return False
    parts = profile.name.split(" ", 1)
    first_name = parts[0] if parts else ""
    last_name = parts[1] if len(parts) > 1 else ""
    lead = {
        "profileUrl": profile.linkedin_url,
        "firstName": first_name,
        "lastName": last_name,
        "companyName": profile.company or "",
        "position": profile.headline or "",
        "emailAddress": "",
    }
    body = {
        "campaignId": campaign_id,
        "accountLeadPairs": [{"accountId": account_ids[0], "lead": lead}],
    }
    try:
        resp = requests.post(
            f"{HEYREACH_BASE}/campaign/AddLeadsToCampaignV2",
            headers=headers,
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        log.info(f"Added {profile.linkedin_url} to HeyReach campaign {campaign_id}")
        return True
    except Exception as e:
        log.error(f"HeyReach AddLeads failed: {e}")
        return False
