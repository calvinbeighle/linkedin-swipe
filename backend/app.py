"""
Lead Swipe -- FastAPI backend + web app.

Uses Google Sheets as the database via gws CLI.
"""

import base64
import hashlib
import json
import logging
import os
import subprocess
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import requests
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# --- Config ------------------------------------------------------------------

SHEET_ID = os.getenv("SWIPE_SHEET_ID", "1JvQrDO8To0h8WFcPNrTFLS46jze2zeTAMNc8cjj11eI")
# Tabs to read leads from, in priority order
SHEET_TABS = ["Prospect Tracker", "OpenClaw iMac"]

API_KEY = os.getenv("SWIPE_API_KEY", "")
BASIC_USER = os.getenv("SWIPE_BASIC_USER", "calvin")
BASIC_PASS = os.getenv("SWIPE_BASIC_PASS", "")

# --- Google Sheets helpers ---------------------------------------------------


import shutil

GWS_BIN = shutil.which("gws") or "/usr/local/bin/gws"


def _gws_read(tab: str, range_: str) -> dict:
    """Read from a Google Sheet tab via gws CLI."""
    full_range = f"'{tab}'!{range_}"
    result = subprocess.run(
        [GWS_BIN, "sheets", "+read", "--spreadsheet", SHEET_ID, "--range", full_range],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        log.error(f"gws read failed: {result.stderr}")
        return {"values": []}
    return json.loads(result.stdout)


def _gws_update(tab: str, range_: str, values: list) -> bool:
    """Update cells in a Google Sheet tab via gws CLI."""
    params = json.dumps(
        {
            "spreadsheetId": SHEET_ID,
            "range": f"'{tab}'!{range_}",
            "valueInputOption": "USER_ENTERED",
        }
    )
    body = json.dumps({"values": values})
    result = subprocess.run(
        [
            GWS_BIN,
            "sheets",
            "spreadsheets",
            "values",
            "update",
            "--params",
            params,
            "--json",
            body,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        log.error(f"gws update failed: {result.stderr}")
        return False
    return True


def _read_tab_as_dicts(tab: str) -> tuple:
    """Read a tab and return (headers, list_of_dicts, row_numbers).

    Each dict maps header_name -> value. row_numbers are 1-indexed sheet rows.
    """
    data = _gws_read(tab, "A1:Z1000")
    rows = data.get("values", [])
    if len(rows) < 2:
        return [], [], []
    headers = rows[0]
    results = []
    row_numbers = []
    for i, row in enumerate(rows[1:], start=2):
        d = {}
        for j, h in enumerate(headers):
            d[h] = row[j] if j < len(row) else ""
        d["_tab"] = tab
        d["_row"] = i
        results.append(d)
        row_numbers.append(i)
    return headers, results, row_numbers


def _col_letter(headers: list, col_name: str) -> str:
    """Get the spreadsheet column letter for a header name."""
    try:
        idx = headers.index(col_name)
        return chr(65 + idx) if idx < 26 else chr(64 + idx // 26) + chr(65 + idx % 26)
    except ValueError:
        return None


# --- Profile mapping ---------------------------------------------------------

# Map from sheet column names to our internal profile format.
# Both tabs have slightly different column names, so we try multiple.

FIELD_MAP = {
    "name": ["Leader Name"],
    "company": ["Company"],
    "headline": ["Title"],
    "location": ["Location"],
    "linkedin_url": ["Leader LinkedIn URL"],
    "photo_url": ["LinkedIn Photo URL", "LinkedIn Image URL"],
    "ai_signal": ["AI Job Signal"],
    "job_search_url": ["Job Search URL"],
    "icp_score": ["ICP Score"],
    "employee_count": ["Employee Count"],
    "company_summary": ["Company Summary"],
    "ai_signal_analysis": ["AI Signal Analysis"],
    "why_trace_fits": ["Why Trace Fits"],
    "recommended_approach": ["Recommended Approach"],
    "score_breakdown": ["Score Breakdown"],
    "outreach_status": ["Outreach Status", "LinkedIn Status"],
    "reviewed": ["Reviewed"],
}


def _map_row(row_dict: dict) -> dict:
    """Map a sheet row dict to our profile format."""
    profile = {"_tab": row_dict["_tab"], "_row": row_dict["_row"]}
    for field, candidates in FIELD_MAP.items():
        val = ""
        for c in candidates:
            if c in row_dict and row_dict[c]:
                val = row_dict[c]
                break
        profile[field] = val
    # Parse ICP score as int
    try:
        profile["icp_score"] = int(str(profile["icp_score"]).replace(",", ""))
    except (ValueError, TypeError):
        profile["icp_score"] = None
    # Check for locally downloaded photo
    linkedin_url = profile.get("linkedin_url", "")
    slug = linkedin_url.rstrip("/").split("/")[-1] if linkedin_url else ""
    if slug:
        photo_path = os.path.join(PHOTOS_DIR, f"{slug}.jpg")
        if os.path.exists(photo_path):
            profile["photo_url"] = f"/photos/{slug}.jpg"
    return profile


# --- In-memory cache (refresh on load) --------------------------------------

_cache = {"profiles": [], "headers_by_tab": {}}


def _refresh_cache():
    """Reload all profiles from both sheet tabs."""
    all_profiles = []
    for tab in SHEET_TABS:
        headers, rows, _ = _read_tab_as_dicts(tab)
        _cache["headers_by_tab"][tab] = headers
        for row in rows:
            p = _map_row(row)
            # Skip rows with no name or no LinkedIn URL
            if not p["name"] or p["name"] == "N/A":
                continue
            if not p["linkedin_url"] or "/search/results/" in p["linkedin_url"]:
                continue
            all_profiles.append(p)
    _cache["profiles"] = all_profiles
    log.info(
        f"Cache refreshed: {len(all_profiles)} total profiles from {len(SHEET_TABS)} tabs"
    )


# --- App ---------------------------------------------------------------------

app = FastAPI(title="Lead Swipe")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve downloaded profile photos
PHOTOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "photos")
os.makedirs(PHOTOS_DIR, exist_ok=True)
app.mount("/photos", StaticFiles(directory=PHOTOS_DIR), name="photos")


def check_basic_auth(request: Request):
    if (
        request.cookies.get("swipe_session")
        == hashlib.sha256((BASIC_PASS + API_KEY).encode()).hexdigest()[:32]
    ):
        return True
    auth = request.headers.get("authorization", "")
    if auth.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth[6:]).decode()
            user, pwd = decoded.split(":", 1)
            if user == BASIC_USER and pwd == BASIC_PASS:
                return True
        except Exception:
            pass
    return False


def verify_api_key(authorization: str = Header(None), key: str = Query(None)):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    elif key:
        token = key
    if not token or token != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


# --- Web App (served as HTML) -----------------------------------------------


@app.get("/")
def root(request: Request):
    if BASIC_PASS and not check_basic_auth(request):
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Lead Swipe"'},
            content="Unauthorized",
        )
    resp = RedirectResponse(url="/app?key=" + API_KEY)
    if BASIC_PASS:
        resp.set_cookie(
            "swipe_session",
            hashlib.sha256((BASIC_PASS + API_KEY).encode()).hexdigest()[:32],
            httponly=True,
            samesite="lax",
            max_age=86400 * 30,
        )
    return resp


@app.get("/app", response_class=HTMLResponse)
def serve_app(request: Request, key: str = Query("")):
    if key != API_KEY:
        if BASIC_PASS and check_basic_auth(request):
            return RedirectResponse(url="/app?key=" + API_KEY)
        return HTMLResponse("<h1>Invalid key</h1>", status_code=401)
    return HTMLResponse(WEB_APP_HTML.replace("__API_KEY__", key))


# --- (HTML inserted below, then API endpoints) ---

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
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent;user-select:none}
html,body{height:100%;overflow:hidden}
body{font-family:'Inter',system-ui,-apple-system,sans-serif;background:#111;color:#fff;display:flex;flex-direction:column}
.topbar{height:52px;display:flex;align-items:center;justify-content:center;flex-shrink:0;position:relative;z-index:10}
.topbar .logo{font-size:24px;font-weight:800;background:linear-gradient(135deg,#fd267a,#ff6036);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.topbar .counter{position:absolute;right:16px;font-size:12px;color:rgba(255,255,255,0.35);font-weight:600}
.stack{flex:1;position:relative;display:flex;align-items:center;justify-content:center;padding:8px;overflow:hidden}
.card{position:absolute;width:calc(100% - 16px);max-width:420px;height:calc(100% - 8px);border-radius:12px;overflow-y:auto;overflow-x:hidden;background:#222;box-shadow:0 4px 24px rgba(0,0,0,0.5);transform-origin:50% 80%;will-change:transform;cursor:grab;touch-action:pan-y;-webkit-overflow-scrolling:touch;scroll-snap-type:y proximity}
.card:active{cursor:grabbing}
.card.behind{transform:scale(0.95) translateY(8px);filter:brightness(0.7);pointer-events:none;z-index:0;overflow:hidden}
.card.top{z-index:2}
.card.exit-left{transition:transform 0.4s ease-out,opacity 0.4s;transform:translateX(-150%) rotate(-20deg)!important;opacity:0;pointer-events:none}
.card.exit-right{transition:transform 0.4s ease-out,opacity 0.4s;transform:translateX(150%) rotate(20deg)!important;opacity:0;pointer-events:none}
.card-hero{position:relative;width:100%;height:100%;flex-shrink:0;scroll-snap-align:start}
.card-photo{position:absolute;inset:0;background-size:cover;background-position:center top;background-color:#2a2a2a}
.card-photo .initials{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:72px;font-weight:800;color:rgba(255,255,255,0.15)}
.card-gradient{position:absolute;bottom:0;left:0;right:0;height:55%;background:linear-gradient(to top,rgba(0,0,0,0.85) 0%,rgba(0,0,0,0.5) 40%,transparent 100%);pointer-events:none}
.stamp{position:absolute;top:60px;padding:8px 16px;border:4px solid;border-radius:8px;font-size:36px;font-weight:800;letter-spacing:3px;opacity:0;transform:scale(0.8);pointer-events:none;z-index:5}
.stamp-nope{left:20px;border-color:#fe3c72;color:#fe3c72;transform:rotate(-15deg) scale(0.8)}
.stamp-like{right:20px;border-color:#2DF88A;color:#2DF88A;transform:rotate(15deg) scale(0.8)}
.card-info{position:absolute;bottom:0;left:0;right:0;padding:20px 20px 24px;z-index:3}
.card-name{font-size:28px;font-weight:700;line-height:1.1;text-shadow:0 2px 8px rgba(0,0,0,0.5)}
.card-name .icp{font-size:16px;font-weight:600;margin-left:8px;padding:2px 8px;border-radius:20px;vertical-align:middle}
.icp-high{background:rgba(45,248,138,0.25);color:#2DF88A}
.icp-mid{background:rgba(255,200,0,0.25);color:#ffc800}
.icp-low{background:rgba(254,60,114,0.2);color:#fe3c72}
.card-title{font-size:15px;color:rgba(255,255,255,0.85);margin-top:4px;font-weight:400}
.card-company{font-size:14px;color:rgba(255,255,255,0.6);margin-top:2px;font-weight:600}
.card-meta{font-size:13px;color:rgba(255,255,255,0.45);margin-top:4px}
.scroll-hint{text-align:center;margin-top:10px;font-size:11px;color:rgba(255,255,255,0.3);letter-spacing:1px}
.card-below{padding:24px 20px 40px;background:#1a1a1a}
.detail-section{margin-bottom:20px}
.detail-label{font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:rgba(255,255,255,0.4);margin-bottom:6px}
.detail-text{font-size:14px;color:rgba(255,255,255,0.8);line-height:1.5}
.detail-links{display:flex;gap:10px;margin-top:8px}
.detail-links a{flex:1;display:block;padding:10px;text-align:center;text-decoration:none;font-size:13px;font-weight:700;border-radius:20px;transition:opacity 0.15s}
.detail-links a:active{opacity:0.6}
.link-li{background:rgba(255,255,255,0.15);color:#fff}
.link-job{background:rgba(45,248,138,0.15);color:#2DF88A}
.email-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:100;align-items:center;justify-content:center;padding:16px}
.email-overlay.visible{display:flex}
.email-card{background:#1a1a1a;border-radius:16px;width:100%;max-width:420px;max-height:80vh;overflow-y:auto;padding:28px 24px}
.email-card h3{font-size:18px;font-weight:700;color:#2DF88A;margin-bottom:4px}
.email-card .email-to{font-size:13px;color:rgba(255,255,255,0.5);margin-bottom:16px}
.email-card .email-subject{font-size:15px;font-weight:600;color:rgba(255,255,255,0.85);margin-bottom:12px;cursor:text;border-radius:6px;padding:6px 8px;margin:-6px -8px 12px;transition:background .15s}
.email-card .email-subject:focus{outline:none;background:rgba(255,255,255,0.06)}
.email-card .email-body{font-size:14px;color:rgba(255,255,255,0.75);line-height:1.6;white-space:pre-wrap;cursor:text;border-radius:8px;padding:12px;margin:-12px;transition:background 0.15s}
.email-card .email-body:focus{outline:none;background:rgba(255,255,255,0.06)}
.email-edit-row{display:flex;gap:8px;margin-top:16px}
.email-edit-row input{flex:1;padding:12px 14px;border:1px solid rgba(255,255,255,0.15);border-radius:20px;background:rgba(255,255,255,0.08);color:#fff;font-size:14px;font-family:inherit;outline:none}
.email-edit-row input::placeholder{color:rgba(255,255,255,0.3)}
.email-edit-row input:focus{border-color:rgba(45,248,138,0.5)}
.email-edit-row button{padding:10px 18px;border:none;border-radius:20px;background:rgba(33,160,255,0.3);color:#21a0ff;font-size:13px;font-weight:700;cursor:pointer;white-space:nowrap}
.email-edit-row button:active{opacity:0.7}
.email-edit-row button:disabled{opacity:0.3}
.email-loading{font-size:12px;color:rgba(255,255,255,0.4);margin-top:8px;display:none}
.email-loading.visible{display:block}
.email-actions{display:flex;gap:12px;margin-top:24px}
.email-actions button{flex:1;padding:14px;border:none;border-radius:24px;font-size:15px;font-weight:700;cursor:pointer}
.email-send{background:linear-gradient(135deg,#2DF88A,#21d07a);color:#000}
.email-skip{background:rgba(255,255,255,0.1);color:rgba(255,255,255,0.7)}
.actions{height:90px;display:flex;align-items:center;justify-content:center;gap:24px;flex-shrink:0;z-index:10}
.action-btn{width:60px;height:60px;border-radius:50%;border:2px solid;display:flex;align-items:center;justify-content:center;cursor:pointer;transition:transform 0.15s,box-shadow 0.15s;background:transparent}
.action-btn:active{transform:scale(0.9)}
.action-btn:hover{transform:scale(1.08);box-shadow:0 0 20px rgba(255,255,255,0.1)}
.btn-nope{border-color:#fe3c72}
.btn-nope svg{width:26px;height:26px;stroke:#fe3c72;fill:none;stroke-width:3;stroke-linecap:round}
.btn-info{width:46px;height:46px;border-color:#21a0ff}
.btn-info svg{width:20px;height:20px;fill:#21a0ff}
.btn-undo{width:46px;height:46px;border-color:#f5a623}
.btn-undo svg{width:20px;height:20px;fill:none;stroke:#f5a623;stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round}
.btn-undo.disabled{opacity:0.2;pointer-events:none}
.btn-like{border-color:#2DF88A}
.btn-like svg{width:28px;height:28px;fill:#2DF88A}
.empty{display:none;flex:1;flex-direction:column;align-items:center;justify-content:center;padding:40px;text-align:center}
.empty.visible{display:flex}
.empty h2{font-size:24px;font-weight:700;color:rgba(255,255,255,0.7)}
.empty p{font-size:15px;color:rgba(255,255,255,0.35);margin-top:8px}
.empty button{margin-top:24px;padding:12px 32px;background:linear-gradient(135deg,#fd267a,#ff6036);color:#fff;border:none;border-radius:24px;font-size:15px;font-weight:700;cursor:pointer}
</style>
</head>
<body>
<div class="topbar">
  <div class="logo">lead swipe</div>
  <span class="counter" id="counter"></span>
</div>
<div class="stack" id="stack"></div>
<div class="actions" id="actions">
  <div class="action-btn btn-undo disabled" id="btnUndo"><svg viewBox="0 0 24 24"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg></div>
  <div class="action-btn btn-nope" id="btnNope"><svg viewBox="0 0 24 24"><line x1="5" y1="5" x2="19" y2="19"/><line x1="19" y1="5" x2="5" y2="19"/></svg></div>
  <div class="action-btn btn-info" id="btnInfo"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="none" stroke="#21a0ff" stroke-width="2"/><line x1="12" y1="16" x2="12" y2="12" stroke="#21a0ff" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="8" r="1"/></svg></div>
  <div class="action-btn btn-like" id="btnLike"><svg viewBox="0 0 24 24"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78L12 21.23l8.84-8.84a5.5 5.5 0 0 0 0-7.78z"/></svg></div>
</div>
<div class="email-overlay" id="emailOverlay"><div class="email-card" id="emailCard"></div></div>
<div class="empty" id="emptyState"><h2>No more leads</h2><p>You've reviewed everyone</p><button onclick="loadProfiles()">Refresh</button></div>

<script>
const API_KEY='__API_KEY__', BASE=window.location.origin, K='?key='+API_KEY;
const $=id=>document.getElementById(id);
const stackEl=$('stack');

let profiles=[], idx=0, locked=false, lastIdx=-1;

function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}
function ini(n){return n.split(' ').map(w=>w[0]).filter(Boolean).slice(0,2).join('').toUpperCase()}
function icpCls(s){return s>=75?'icp-high':s>=50?'icp-mid':'icp-low'}
function inSendWindow(){const p=new Date(new Date().toLocaleString('en-US',{timeZone:'America/Los_Angeles'}));const h=p.getHours();return h>=8&&(h<19||(h===19&&p.getMinutes()<=30))}
function api(path,body){return fetch(BASE+path,{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+API_KEY},body:JSON.stringify(body)}).catch(()=>{})}

// ── Load & Render ──

async function loadProfiles(){
  $('emptyState').classList.remove('visible');
  stackEl.style.display='';$('actions').style.display='';
  try{profiles=await(await fetch(BASE+'/profiles'+K+'&limit=200')).json();idx=0;lastIdx=-1;render()}catch(e){console.error(e)}
}

function render(){
  stackEl.innerHTML='';
  if(idx>=profiles.length){stackEl.style.display='none';$('actions').style.display='none';$('emptyState').classList.add('visible');$('counter').textContent='';return}
  if(idx+1<profiles.length) stackEl.appendChild(makeCard(profiles[idx+1],false));
  stackEl.appendChild(makeCard(profiles[idx],true));
  $('counter').textContent=(idx+1)+' / '+profiles.length;
  $('btnUndo').classList.toggle('disabled',lastIdx<0);
  locked=false;
}

function makeCard(p,isTop){
  const c=document.createElement('div');c.className='card '+(isTop?'top':'behind');
  let bg='';
  if(p.photo_url) bg='background-image:url('+p.photo_url.replace(/'/g,'%27')+')';
  else if(p.company){const d=p.company.toLowerCase().replace(/[^a-z0-9]/g,'')+'.com';bg='background-image:url(https://logo.clearbit.com/'+d+'?size=400);background-size:40%;background-repeat:no-repeat;background-position:center 30%'}

  let meta=[];if(p.location)meta.push(esc(p.location));if(p.employee_count)meta.push(esc(p.employee_count)+' employees');
  let icp='';if(p.icp_score!=null&&p.icp_score<=100)icp='<span class="icp '+icpCls(p.icp_score)+'">'+p.icp_score+'</span>';

  let det='';
  if(p.company_summary)det+='<div class="detail-section"><div class="detail-label">Company</div><div class="detail-text">'+esc(p.company_summary)+'</div></div>';
  if(p.ai_signal){let t=esc(p.ai_signal);if(p.ai_signal_analysis)t+='<br><span style="color:rgba(255,255,255,.55);font-size:13px">'+esc(p.ai_signal_analysis)+'</span>';det+='<div class="detail-section"><div class="detail-label">AI Signal</div><div class="detail-text">'+t+'</div></div>'}
  if(p.why_trace_fits)det+='<div class="detail-section"><div class="detail-label">Why Trace Fits</div><div class="detail-text">'+esc(p.why_trace_fits)+'</div></div>';
  if(p.recommended_approach)det+='<div class="detail-section"><div class="detail-label">Approach</div><div class="detail-text">'+esc(p.recommended_approach)+'</div></div>';
  det+='<div class="detail-links"><a class="link-li" href="'+esc(p.linkedin_url)+'" target="_blank">LinkedIn</a>';
  if(p.job_search_url)det+='<a class="link-job" href="'+esc(p.job_search_url)+'" target="_blank">AI Job Posting</a>';
  det+='</div>';

  c.innerHTML='<div class="card-hero"><div class="card-photo" style="'+bg+'">'+(p.photo_url?'':'<div class="initials">'+ini(p.name||'?')+'</div>')+'</div><div class="card-gradient"></div><div class="stamp stamp-nope">NOPE</div><div class="stamp stamp-like">LIKE</div><div class="card-info"><div class="card-name">'+esc(p.name||'')+' '+icp+'</div>'+(p.headline?'<div class="card-title">'+esc(p.headline)+'</div>':'')+(p.company?'<div class="card-company">'+esc(p.company)+'</div>':'')+(meta.length?'<div class="card-meta">'+meta.join(' / ')+'</div>':'')+(det?'<div class="scroll-hint">SCROLL DOWN FOR MORE</div>':'')+'</div></div>'+(det?'<div class="card-below">'+det+'</div>':'');
  return c;
}

// ── Swipe Logic (simple, no races) ──

function doSwipe(dir){
  if(locked||idx>=profiles.length) return;
  locked=true;

  // Capture who we're swiping BEFORE any idx change
  const swipedProfile=profiles[idx];
  const swipedIdx=idx;
  const card=stackEl.querySelector('.card.top');
  if(!card){locked=false;return}

  if(dir==='left'){
    card.querySelector('.stamp-nope').style.opacity='1';
    card.classList.add('exit-left');
    lastIdx=swipedIdx; idx++;
    api('/swipe',{tab:swipedProfile._tab,row:swipedProfile._row,direction:'left'});
    setTimeout(render,400);
  } else {
    card.querySelector('.stamp-like').style.opacity='1';
    card.classList.add('exit-right');
    // Show email for THIS person, don't advance idx yet
    showEmail(swipedProfile, swipedIdx);
  }
}

function doUndo(){
  if(locked||lastIdx<0) return;
  locked=true;
  const p=profiles[lastIdx];
  api('/undo',{tab:p._tab,row:p._row});
  idx=lastIdx; lastIdx=-1;
  render();
}

// ── Drag ──

stackEl.addEventListener('pointerdown',function(e){
  if(locked) return;
  const card=stackEl.querySelector('.card.top');
  if(!card||!card.contains(e.target)) return;
  if(e.target.closest('.detail-links,.card-below a')) return;

  const sx=e.clientX, sy=e.clientY;
  let dx=0, active=false;

  function onMove(ev){
    dx=ev.clientX-sx;
    const dy=ev.clientY-sy;
    if(!active){
      if(Math.abs(dx)>10&&Math.abs(dx)>Math.abs(dy)&&card.scrollTop<10){
        active=true;card.setPointerCapture(ev.pointerId);card.style.transition='none';card.style.overflow='hidden';
      } else return;
    }
    card.style.transform='translateX('+dx+'px) rotate('+(dx*0.06)+'deg)';
    const n=card.querySelector('.stamp-nope'),l=card.querySelector('.stamp-like'),t=Math.min(Math.abs(dx)/120,1);
    if(dx<-20){n.style.opacity=t;l.style.opacity=0}
    else if(dx>20){l.style.opacity=t;n.style.opacity=0}
    else{n.style.opacity=0;l.style.opacity=0}
  }
  function onUp(){
    document.removeEventListener('pointermove',onMove);
    document.removeEventListener('pointerup',onUp);
    if(!active) return;
    card.style.overflow='';
    if(Math.abs(dx)>100){doSwipe(dx>0?'right':'left')}
    else{card.style.transition='transform .3s ease-out';card.style.transform='';card.querySelector('.stamp-nope').style.opacity=0;card.querySelector('.stamp-like').style.opacity=0}
  }
  document.addEventListener('pointermove',onMove);
  document.addEventListener('pointerup',onUp);
});

// ── Email ──

const TEMPLATES=[
  (n,j,c)=>'Hi '+n+',\n\nI graduated from Harvard and have been deeply involved in AI since December \'22. I came across the '+j+' role on LinkedIn and would love to ask a few questions about the position.\n\nHave a great day!\n\nBest,\nCalvin',
];
let tplIdx=parseInt(localStorage.getItem('tplIdx')||'0');

async function showEmail(profile, swipedIdx){
  const fn=(profile.name||'').split(' ')[0];
  let job=profile.ai_signal||'AI';
  const co=profile.company||'your company';

  // Clean the job title via LLM
  try{const r=await fetch(BASE+'/clean-title'+K+'&title='+encodeURIComponent(job));const d=await r.json();if(d.title)job=d.title}catch(e){}

  const body=TEMPLATES[tplIdx%TEMPLATES.length](fn,job,co);tplIdx++;localStorage.setItem('tplIdx',tplIdx);

  $('emailCard').innerHTML=
    '<h3>Draft Email</h3>'+
    '<div class="email-to">To: '+esc(fn)+' (enrich via Apollo for email)</div>'+
    '<div class="email-subject" id="emailSubject" contenteditable="true" spellcheck="false" oninput="window._email.subject=this.textContent.replace(/^Subject: /,&quot;&quot;)">Subject: '+esc(job)+'</div>'+
    '<div class="email-body" id="emailBody" contenteditable="true" spellcheck="false">'+esc(body)+'</div>'+
    '<div class="email-edit-row"><input type="text" id="emailEditInput" placeholder="e.g. make it shorter..." onkeydown="if(event.key===\'Enter\')adjustEmail()"><button onclick="adjustEmail()" id="emailEditBtn">Adjust</button></div>'+
    '<div class="email-loading" id="emailLoading">Rewriting...</div>'+
    '<div class="email-actions"><button class="email-skip" onclick="closeEmail(false)">Skip Email</button><button class="email-send" onclick="closeEmail(true)">Send</button></div>';
  $('emailOverlay').classList.add('visible');

  // Store draft state -- profile is captured by closure, not idx
  window._email={body,subject:job,profile,swipedIdx};
}

async function adjustEmail(){
  const inp=$('emailEditInput'), v=inp.value.trim(); if(!v) return;
  const btn=$('emailEditBtn'), ld=$('emailLoading');
  btn.disabled=inp.disabled=true; ld.classList.add('visible'); ld.textContent='Rewriting...';
  try{
    const e=window._email;
    const r=await(await fetch(BASE+'/adjust-email',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+API_KEY},body:JSON.stringify({current_body:$('emailBody').innerText,subject:e.subject,instruction:v,profile_name:e.profile.name,company:e.profile.company,ai_signal:e.profile.ai_signal})})).json();
    if(r.body){window._email.body=r.body;$('emailBody').textContent=r.body}
    if(r.subject){window._email.subject=r.subject;$('emailSubject').textContent='Subject: '+r.subject}
    inp.value='';
  }catch(err){ld.textContent='Failed -- try again'}
  btn.disabled=inp.disabled=false;
  setTimeout(()=>ld.classList.remove('visible'),1500);
}

function closeEmail(send){
  $('emailOverlay').classList.remove('visible');
  const e=window._email;
  lastIdx=e.swipedIdx; idx=e.swipedIdx+1;
  api('/swipe',{tab:e.profile._tab,row:e.profile._row,direction:'right'});
  if(send){
    fetch(BASE+'/send-email',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+API_KEY},body:JSON.stringify({
      linkedin_url:e.profile.linkedin_url,name:e.profile.name,company:e.profile.company,
      ai_signal:e.profile.ai_signal,subject:e.subject,body:$('emailBody').innerText,
      tab:e.profile._tab,row:e.profile._row
    })}).then(r=>r.json()).then(d=>{
      if(d.status==='no_email') showToast('No email found for '+d.name,'red');
      else if(d.status==='name_mismatch') showToast('BLOCKED: LinkedIn URL is for '+d.enriched_name+', not '+d.name,'red');
      else if(d.email) showToast('Sending to '+d.email,'green');
    }).catch(()=>{});
  }
  setTimeout(render,300);
}
function showToast(msg,color){
  const t=document.createElement('div');
  t.style.cssText='position:fixed;top:60px;left:50%;transform:translateX(-50%);padding:12px 24px;border-radius:20px;font-size:14px;font-weight:600;z-index:200;pointer-events:none;opacity:0;transition:opacity .3s;background:'+(color==='red'?'rgba(254,60,114,.9)':'rgba(45,248,138,.9)')+';color:'+(color==='red'?'#fff':'#000');
  t.textContent=msg;document.body.appendChild(t);
  requestAnimationFrame(()=>{t.style.opacity='1'});
  setTimeout(()=>{t.style.opacity='0';setTimeout(()=>t.remove(),300)},3000);
}

// ── Buttons ──

$('btnNope').onclick=()=>doSwipe('left');
$('btnLike').onclick=()=>doSwipe('right');
$('btnUndo').onclick=()=>doUndo();
$('btnInfo').onclick=()=>{const c=stackEl.querySelector('.card.top');if(c)c.scrollTo({top:c.querySelector('.card-hero').offsetHeight,behavior:'smooth'})};

document.addEventListener('keydown',e=>{
  if($('emailOverlay').classList.contains('visible')) return;
  if(e.key==='ArrowLeft') doSwipe('left');
  if(e.key==='ArrowRight') doSwipe('right');
  if(e.key==='ArrowUp'||e.key==='ArrowDown') $('btnInfo').click();
  if(e.key==='z'&&(e.metaKey||e.ctrlKey)) doUndo();
});

loadProfiles();
</script>
</body>
</html>"""


# --- API endpoints (Google Sheets backed) ------------------------------------


@app.get("/profiles")
def get_pending_profiles(
    limit: int = 200,
    _auth: None = Depends(verify_api_key),
):
    """Return profiles that haven't been reviewed or reached out to."""
    _refresh_cache()
    pending = [
        p for p in _cache["profiles"] if not p["reviewed"] and not p["outreach_status"]
    ]
    # Sort by ICP score descending (nulls last)
    pending.sort(
        key=lambda p: (p["icp_score"] is not None, p["icp_score"] or 0), reverse=True
    )
    return pending[:limit]


class SwipeRequest(BaseModel):
    tab: str
    row: int
    direction: str


@app.post("/swipe")
def record_swipe(
    swipe: SwipeRequest,
    _auth: None = Depends(verify_api_key),
):
    """Write swipe result to the Reviewed column in the sheet."""
    tab = swipe.tab
    row = swipe.row
    headers = _cache["headers_by_tab"].get(tab)
    if not headers:
        raise HTTPException(status_code=400, detail=f"Unknown tab: {tab}")

    # Find the Reviewed column dynamically
    reviewed_col = _col_letter(headers, "Reviewed")
    if not reviewed_col:
        raise HTTPException(status_code=500, detail="No Reviewed column found in sheet")

    status_value = "Liked" if swipe.direction == "right" else "Skipped"
    ok = _gws_update(tab, f"{reviewed_col}{row}", [[status_value]])
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to update sheet")

    return {"status": "ok", "tab": tab, "row": row, "direction": swipe.direction}


class UndoRequest(BaseModel):
    tab: str
    row: int


@app.post("/undo")
def undo_swipe(
    req: UndoRequest,
    _auth: None = Depends(verify_api_key),
):
    """Clear the Reviewed column for a profile (undo last swipe)."""
    headers = _cache["headers_by_tab"].get(req.tab)
    if not headers:
        raise HTTPException(status_code=400, detail=f"Unknown tab: {req.tab}")
    reviewed_col = _col_letter(headers, "Reviewed")
    if not reviewed_col:
        raise HTTPException(status_code=500, detail="No Reviewed column found")
    ok = _gws_update(req.tab, f"{reviewed_col}{req.row}", [[""]])
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to update sheet")
    return {"status": "ok", "tab": req.tab, "row": req.row}


@app.get("/stats")
def get_stats(_auth: None = Depends(verify_api_key)):
    if not _cache["profiles"]:
        _refresh_cache()
    total = len(_cache["profiles"])
    pending = sum(
        1 for p in _cache["profiles"] if not p["reviewed"] and not p["outreach_status"]
    )
    liked = sum(1 for p in _cache["profiles"] if p["reviewed"].lower() == "liked")
    skipped = sum(1 for p in _cache["profiles"] if p["reviewed"].lower() == "skipped")
    reached_out = sum(1 for p in _cache["profiles"] if p["outreach_status"])
    return {
        "total": total,
        "pending": pending,
        "liked": liked,
        "skipped": skipped,
        "reached_out": reached_out,
    }


@app.get("/clean-title")
def clean_title(
    title: str = Query(""),
    _auth: None = Depends(verify_api_key),
):
    """Use Claude to clean a LinkedIn job title for use in an email."""
    if not title:
        return {"title": title}
    env = os.environ.copy()
    env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    config_env = os.path.expanduser("~/BridgeIntelligence/GTM/config.env")
    if os.path.exists(config_env):
        with open(config_env) as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    env.setdefault(k, v)
    try:
        r = subprocess.run(
            [
                "/usr/local/bin/claude",
                "--print",
                "-p",
                f'Clean this LinkedIn job title for use in a cold email. Remove location info like "(USA - Remote)", remove parenthetical notes, replace dashes between title parts with natural language. Return ONLY the cleaned title, nothing else. Title: {title}',
            ],
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
        cleaned = r.stdout.strip()
        if cleaned and len(cleaned) < 200:
            return {"title": cleaned}
    except Exception:
        pass
    return {"title": title}


class EmailAdjustRequest(BaseModel):
    current_body: str
    subject: str
    instruction: str
    profile_name: Optional[str] = None
    company: Optional[str] = None
    ai_signal: Optional[str] = None


@app.post("/adjust-email")
def adjust_email(
    req: EmailAdjustRequest,
    _auth: None = Depends(verify_api_key),
):
    """Use Claude CLI to adjust the email draft based on user instruction."""
    prompt = (
        f"You are rewriting a cold outreach email. The current draft is:\n\n"
        f"Subject: {req.subject}\n\n{req.current_body}\n\n"
        f"Context: This email is to {req.profile_name or 'a lead'} at {req.company or 'their company'}."
        f"{(' AI signal: ' + req.ai_signal) if req.ai_signal else ''}\n\n"
        f"User instruction: {req.instruction}\n\n"
        f"Return the result in exactly this format (two lines then the body):\n"
        f"SUBJECT: <the subject line>\n"
        f"BODY:\n<the email body>\n\n"
        f"Keep the same signature (Best, Calvin). Keep it concise. No markdown."
    )
    try:
        env = os.environ.copy()
        env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
        config_env = os.path.expanduser("~/BridgeIntelligence/GTM/config.env")
        if os.path.exists(config_env):
            with open(config_env) as f:
                for line in f:
                    if "=" in line and not line.startswith("#"):
                        k, v = line.strip().split("=", 1)
                        env[k] = v
        result = subprocess.run(
            ["/usr/local/bin/claude", "--print", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
            stdin=subprocess.DEVNULL,
        )
        output = result.stdout.strip()
        if not output:
            raise ValueError("Empty response")
        # Parse SUBJECT: and BODY: format
        new_subject = req.subject
        new_body = output
        if "SUBJECT:" in output and "BODY:" in output:
            parts = output.split("BODY:", 1)
            subject_line = parts[0].strip()
            if subject_line.startswith("SUBJECT:"):
                new_subject = subject_line[8:].strip()
            new_body = parts[1].strip()
        return {"body": new_body, "subject": new_subject}
    except Exception as e:
        log.error(f"Email adjust failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to adjust email")


class SendEmailRequest(BaseModel):
    linkedin_url: str
    name: str
    company: Optional[str] = None
    ai_signal: Optional[str] = None
    subject: str
    body: str
    tab: Optional[str] = None
    row: Optional[int] = None


@app.post("/send-email")
def send_email(
    req: SendEmailRequest,
    _auth: None = Depends(verify_api_key),
):
    """Enrich via Apollo (sync), then fire-and-forget Claude Code to send."""
    import sys as _sys
    import uuid

    html_body = req.body.replace("\n", "<br>")
    first_name = req.name.split()[0] if req.name else ""
    last_name = " ".join(req.name.split()[1:]) if req.name else ""

    # Load API keys
    config_env = os.path.expanduser("~/BridgeIntelligence/GTM/config.env")
    if os.path.exists(config_env):
        with open(config_env) as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ.setdefault(k, v)

    # Step 1: Apollo enrichment (synchronous)
    _sys.path.insert(
        0, os.path.expanduser("~/.claude/skills/apollo-enrichment/scripts")
    )
    email = None
    try:
        from apollo_client import ApolloClient

        apollo = ApolloClient()
        r = apollo.enrich_by_linkedin(req.linkedin_url)
        email = r.get("email")
        enriched_name = r.get("name", "")
        # Safety check: verify enriched person matches intended recipient
        if email and enriched_name:
            expected = req.name.lower().split()[0]
            actual = enriched_name.lower().split()[0]
            if expected != actual:
                log.warning(
                    f"NAME MISMATCH: expected {req.name} but Apollo returned {enriched_name} ({email}). Blocking send."
                )
                return {
                    "status": "name_mismatch",
                    "name": req.name,
                    "enriched_name": enriched_name,
                    "note": f"LinkedIn URL returned {enriched_name}, not {req.name}. Check sheet data.",
                }
        if not email:
            r = apollo.enrich_by_name(first_name, last_name, req.company)
            email = r.get("email")
    except Exception as e:
        log.error(f"Apollo enrichment failed: {e}")

    if not email:
        log.warning(f"No email found for {req.name}")
        return {"status": "no_email", "name": req.name}

    # Step 2: Fire-and-forget Claude Code to send
    prompt = (
        f"Read the skill at ~/.claude/skills/ai-job-scrape-email-writer/SKILL.md.\n\n"
        f"Send an email to {email} ({req.name} at {req.company or 'unknown'}).\n"
        f"The email address is already known. Skip Apollo enrichment. Go directly to Step 3 (send).\n\n"
        f"Use this EXACT email body (already approved by user):\n"
        f"Subject: {req.subject}\n"
        f"Body: {html_body}\n\n"
        f"Do NOT modify the email body.\n"
        f"After sending, update Google Sheet {SHEET_ID} tab '{req.tab or 'Prospect Tracker'}' "
        f"row {req.row or 'find by name'}: set Date Sent column to today's date."
    )

    env = os.environ.copy()
    env["PATH"] = "/usr/local/bin:/usr/bin:/bin"

    try:
        proc = subprocess.Popen(
            [
                "/usr/local/bin/claude",
                "--print",
                "--allowedTools",
                "Bash,Read",
                "-p",
                prompt,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )
        log.info(f"Email sending to {email} for {req.name} (pid {proc.pid})")
        return {"status": "sending", "name": req.name, "email": email}
    except Exception as e:
        log.error(f"Failed to start email send: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- HeyReach integration ---------------------------------------------------

HEYREACH_BASE = "https://api.heyreach.io/api/public"


def _add_to_heyreach(name: str, linkedin_url: str, company: str, headline: str) -> bool:
    api_key = os.getenv("HEYREACH_API_KEY", "")
    campaign_id = os.getenv("HEYREACH_SWIPE_CAMPAIGN_ID", "")
    if not api_key or not campaign_id:
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
        return False
    parts = name.split(" ", 1)
    lead = {
        "profileUrl": linkedin_url,
        "firstName": parts[0] if parts else "",
        "lastName": parts[1] if len(parts) > 1 else "",
        "companyName": company,
        "position": headline,
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
        return True
    except Exception as e:
        log.error(f"HeyReach AddLeads failed: {e}")
        return False
