"""
LinkedIn Swipe -- FastAPI backend + web app.

Serves the swipe web app and API for reviewing LinkedIn profiles.
"""

import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

import requests
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# --- Database ----------------------------------------------------------------

DATABASE_URL = "sqlite:///./linkedin_swipe.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
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


class ProfileResponse(BaseModel):
    id: int
    linkedin_url: str
    name: str
    headline: Optional[str]
    company: Optional[str]
    location: Optional[str]
    photo_url: Optional[str]
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

app = FastAPI(title="LinkedIn Swipe")

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


@app.get("/app", response_class=HTMLResponse)
def serve_app(key: str = Query("")):
    """Serve the swipe web app. Auth via ?key= query param."""
    if key != API_KEY:
        return HTMLResponse("<h1>Invalid key</h1>", status_code=401)

    return HTMLResponse(WEB_APP_HTML.replace("__API_KEY__", key))


WEB_APP_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Swipe">
<meta name="robots" content="noindex, nofollow">
<title>LinkedIn Swipe</title>
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
  padding-top: env(safe-area-inset-top, 44px);
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
  flex: 1; display: flex; align-items: center; justify-content: center;
  padding: 20px; overflow: hidden;
}

.card {
  background: #fff; width: 100%; max-width: 400px;
  border-radius: 3px; padding: 40px 28px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.08);
  text-align: center;
  animation: fadeIn 0.2s ease-out;
}
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.card .avatar {
  width: 96px; height: 96px; border-radius: 50%;
  background: rgba(0,0,0,0.06); color: rgba(0,0,0,0.35);
  font-family: 'Playfair Display', serif; font-style: italic;
  font-size: 28px; line-height: 96px;
  margin: 0 auto 20px; object-fit: cover;
  overflow: hidden; display: flex; align-items: center; justify-content: center;
}
.card .avatar img {
  width: 100%; height: 100%; object-fit: cover; border-radius: 50%;
}

.card .name {
  font-size: 24px; font-weight: 600; color: rgba(0,0,0,0.85);
  letter-spacing: 0.2px;
}
.card .headline {
  font-size: 15px; color: rgba(0,0,0,0.55); margin-top: 8px;
  line-height: 1.4;
}
.card .company {
  font-size: 14px; color: rgba(0,0,0,0.6); margin-top: 6px;
  font-weight: 600;
}
.card .location {
  font-size: 13px; color: rgba(0,0,0,0.35); margin-top: 4px;
}
.card .view-link {
  display: block; margin-top: 28px;
  padding: 16px 28px; background: rgba(0,0,0,0.85);
  color: rgba(255,255,255,0.95); text-decoration: none;
  font-family: 'Crimson Text', serif; font-size: 16px; font-weight: 600;
  letter-spacing: 0.5px; border-radius: 2px;
  text-align: center; transition: opacity 0.15s;
}
.card .view-link:active { opacity: 0.6; }
.card .view-hint {
  font-size: 12px; color: rgba(0,0,0,0.3); margin-top: 10px;
}

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
</style>
</head>
<body>

<div class="header">
  <h1>LinkedIn Swipe</h1>
  <span class="counter" id="counter">--</span>
</div>

<div class="card-area" id="cardArea">
  <div class="card" id="card">
    <div class="avatar" id="avatar">--</div>
    <div class="name" id="profileName">Loading...</div>
    <div class="headline" id="profileHeadline"></div>
    <div class="company" id="profileCompany"></div>
    <div class="location" id="profileLocation"></div>
    <a class="view-link" id="viewLink" href="#" target="_blank" rel="noopener">View Full Profile</a>
    <div class="view-hint">Opens in LinkedIn app</div>
  </div>
</div>

<div class="actions" id="actions">
  <button class="btn btn-skip" onclick="doSwipe('left')">SKIP</button>
  <button class="btn btn-connect" onclick="doSwipe('right')">CONNECT</button>
</div>

<div class="empty" id="emptyState">
  <h2>All caught up</h2>
  <p>New profiles arrive each morning</p>
  <button class="refresh-btn" onclick="loadProfiles()">Refresh</button>
</div>

<script>
const API_KEY = '__API_KEY__';
const BASE = window.location.origin;
const K = '?key=' + API_KEY;

let profiles = [];
let idx = 0;
let busy = false;

function getInitials(name) {
  return name.split(' ').map(w => w[0]).filter(Boolean).slice(0,2).join('').toUpperCase();
}

async function loadProfiles() {
  document.getElementById('emptyState').classList.remove('visible');
  document.getElementById('cardArea').style.display = 'flex';
  document.getElementById('actions').style.display = 'flex';
  document.getElementById('profileName').textContent = 'Loading...';
  document.getElementById('profileHeadline').textContent = '';
  try {
    const r = await fetch(BASE + '/profiles' + K + '&limit=60');
    profiles = await r.json();
    idx = 0;
    showCurrent();
  } catch(e) {
    document.getElementById('profileName').textContent = 'Error: ' + e.message;
    console.error('Load failed:', e);
  }
}

function showCurrent() {
  if (idx >= profiles.length) {
    document.getElementById('cardArea').style.display = 'none';
    document.getElementById('actions').style.display = 'none';
    document.getElementById('emptyState').classList.add('visible');
    return;
  }
  const p = profiles[idx];
  document.getElementById('profileName').textContent = p.name || 'Profile';
  document.getElementById('profileHeadline').textContent = p.headline || '';
  document.getElementById('profileCompany').textContent = p.company ? p.company : '';
  document.getElementById('profileLocation').textContent = p.location ? p.location : '';
  const av = document.getElementById('avatar');
  if (p.photo_url) {
    av.innerHTML = '<img src="' + p.photo_url + '" onerror="this.parentNode.textContent=\'' + getInitials(p.name || '?') + '\'">';
  } else if (p.company) {
    // Use Clearbit company logo as visual
    const domain = p.company.toLowerCase().replace(/[^a-z0-9]/g,'') + '.com';
    av.innerHTML = '<img src="https://logo.clearbit.com/' + domain + '?size=192" onerror="this.parentNode.textContent=\'' + getInitials(p.name || '?') + '\'" style="border-radius:0;padding:16px;">';
  } else {
    av.innerHTML = ''; av.textContent = getInitials(p.name || '?');
  }
  document.getElementById('viewLink').href = p.linkedin_url;
  document.getElementById('counter').textContent = (idx + 1) + ' / ' + profiles.length;
  document.getElementById('card').style.animation = 'none';
  void document.getElementById('card').offsetHeight;
  document.getElementById('card').style.animation = 'fadeIn 0.2s ease-out';
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
        .order_by(Profile.created_at.desc())
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
    for key in ("photo_url", "headline", "company", "location", "linkedin_url"):
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
