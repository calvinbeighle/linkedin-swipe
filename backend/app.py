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
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent;user-select:none}
html,body{height:100%;overflow:hidden}
body{font-family:'Inter',system-ui,-apple-system,sans-serif;background:#111;color:#fff;display:flex;flex-direction:column}

/* ── Top bar ── */
.topbar{height:52px;display:flex;align-items:center;justify-content:center;flex-shrink:0;position:relative;z-index:10}
.topbar .logo{font-size:24px;font-weight:800;background:linear-gradient(135deg,#fd267a,#ff6036);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.topbar .counter{position:absolute;right:16px;font-size:12px;color:rgba(255,255,255,0.35);font-weight:600}

/* ── Card stack ── */
.stack{flex:1;position:relative;display:flex;align-items:center;justify-content:center;padding:8px;overflow:hidden}
.card{position:absolute;width:calc(100% - 16px);max-width:420px;height:calc(100% - 8px);border-radius:12px;overflow-y:auto;overflow-x:hidden;background:#222;box-shadow:0 4px 24px rgba(0,0,0,0.5);transform-origin:50% 80%;will-change:transform;cursor:grab;touch-action:pan-y;-webkit-overflow-scrolling:touch;scroll-snap-type:y proximity}
.card:active{cursor:grabbing}
.card.behind{transform:scale(0.95) translateY(8px);filter:brightness(0.7);pointer-events:none;z-index:0;overflow:hidden}
.card.top{z-index:2}
.card.exit-left{transition:transform 0.4s ease-out,opacity 0.4s;transform:translateX(-150%) rotate(-20deg)!important;opacity:0;pointer-events:none}
.card.exit-right{transition:transform 0.4s ease-out,opacity 0.4s;transform:translateX(150%) rotate(20deg)!important;opacity:0;pointer-events:none}

/* Photo section -- takes full card height as first "page" */
.card-hero{position:relative;width:100%;height:100%;flex-shrink:0;scroll-snap-align:start}
.card-photo{position:absolute;inset:0;background-size:cover;background-position:center top;background-color:#2a2a2a}
.card-photo .initials{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:72px;font-weight:800;color:rgba(255,255,255,0.15)}

/* Gradient overlay */
.card-gradient{position:absolute;bottom:0;left:0;right:0;height:55%;background:linear-gradient(to top,rgba(0,0,0,0.85) 0%,rgba(0,0,0,0.5) 40%,transparent 100%);pointer-events:none}

/* NOPE / LIKE stamps */
.stamp{position:absolute;top:60px;padding:8px 16px;border:4px solid;border-radius:8px;font-size:36px;font-weight:800;letter-spacing:3px;opacity:0;transform:scale(0.8);pointer-events:none;z-index:5}
.stamp-nope{left:20px;border-color:#fe3c72;color:#fe3c72;transform:rotate(-15deg) scale(0.8)}
.stamp-like{right:20px;border-color:#2DF88A;color:#2DF88A;transform:rotate(15deg) scale(0.8)}

/* Card info overlay on photo */
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

/* Below-photo detail area (scroll down to see) */
.card-below{padding:24px 20px 40px;background:#1a1a1a}
.detail-section{margin-bottom:20px}
.detail-label{font-size:11px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:rgba(255,255,255,0.4);margin-bottom:6px}
.detail-text{font-size:14px;color:rgba(255,255,255,0.8);line-height:1.5}
.detail-links{display:flex;gap:10px;margin-top:8px}
.detail-links a{flex:1;display:block;padding:10px;text-align:center;text-decoration:none;font-size:13px;font-weight:700;border-radius:20px;transition:opacity 0.15s}
.detail-links a:active{opacity:0.6}
.link-li{background:rgba(255,255,255,0.15);color:#fff}
.link-job{background:rgba(45,248,138,0.15);color:#2DF88A}

/* ── Email draft modal ── */
.email-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:100;align-items:center;justify-content:center;padding:16px}
.email-overlay.visible{display:flex}
.email-card{background:#1a1a1a;border-radius:16px;width:100%;max-width:420px;max-height:80vh;overflow-y:auto;padding:28px 24px}
.email-card h3{font-size:18px;font-weight:700;color:#2DF88A;margin-bottom:4px}
.email-card .email-to{font-size:13px;color:rgba(255,255,255,0.5);margin-bottom:16px}
.email-card .email-subject{font-size:15px;font-weight:600;color:rgba(255,255,255,0.85);margin-bottom:12px}
.email-card .email-body{font-size:14px;color:rgba(255,255,255,0.75);line-height:1.6;white-space:pre-wrap}
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

/* ── Action buttons ── */
.actions{height:90px;display:flex;align-items:center;justify-content:center;gap:24px;flex-shrink:0;z-index:10}
.action-btn{width:60px;height:60px;border-radius:50%;border:2px solid;display:flex;align-items:center;justify-content:center;cursor:pointer;transition:transform 0.15s,box-shadow 0.15s;background:transparent}
.action-btn:active{transform:scale(0.9)}
.action-btn:hover{transform:scale(1.08);box-shadow:0 0 20px rgba(255,255,255,0.1)}
.btn-nope{border-color:#fe3c72}
.btn-nope svg{width:26px;height:26px;stroke:#fe3c72;fill:none;stroke-width:3;stroke-linecap:round}
.btn-info{width:46px;height:46px;border-color:#21a0ff}
.btn-info svg{width:20px;height:20px;fill:#21a0ff}
.btn-like{border-color:#2DF88A}
.btn-like svg{width:28px;height:28px;fill:#2DF88A}

/* ── Empty state ── */
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
  <div class="counter" id="counter"></div>
</div>

<div class="stack" id="stack"></div>

<div class="actions" id="actions">
  <div class="action-btn btn-nope" id="btnNope">
    <svg viewBox="0 0 24 24"><line x1="5" y1="5" x2="19" y2="19"/><line x1="19" y1="5" x2="5" y2="19"/></svg>
  </div>
  <div class="action-btn btn-info" id="btnInfo">
    <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="none" stroke="#21a0ff" stroke-width="2"/><line x1="12" y1="16" x2="12" y2="12" stroke="#21a0ff" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="8" r="1"/></svg>
  </div>
  <div class="action-btn btn-like" id="btnLike">
    <svg viewBox="0 0 24 24"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78L12 21.23l8.84-8.84a5.5 5.5 0 0 0 0-7.78z"/></svg>
  </div>
</div>

<div class="email-overlay" id="emailOverlay">
  <div class="email-card" id="emailCard"></div>
</div>

<div class="empty" id="emptyState">
  <h2>No more leads</h2>
  <p>You've reviewed everyone</p>
  <button onclick="loadProfiles()">Refresh</button>
</div>

<script>
const API_KEY='__API_KEY__',BASE=window.location.origin,K='?key='+API_KEY;
let profiles=[],idx=0,busy=false,dragCard=null,startX=0,startY=0,currentX=0,detailOpen=false;

function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}
function initials(n){return n.split(' ').map(w=>w[0]).filter(Boolean).slice(0,2).join('').toUpperCase()}
function icpCls(s){return s>=75?'icp-high':s>=50?'icp-mid':'icp-low'}

async function loadProfiles(){
  document.getElementById('emptyState').classList.remove('visible');
  document.getElementById('stack').style.display='';
  document.getElementById('actions').style.display='';
  try{
    const r=await fetch(BASE+'/profiles'+K+'&limit=200');
    profiles=await r.json();idx=0;renderCards();
  }catch(e){console.error(e)}
}

function renderCards(){
  const stack=document.getElementById('stack');
  stack.innerHTML='';
  if(idx>=profiles.length){
    stack.style.display='none';
    document.getElementById('actions').style.display='none';
    document.getElementById('emptyState').classList.add('visible');
    document.getElementById('counter').textContent='';
    return;
  }
  // Render up to 2 cards (current + next behind)
  for(let i=Math.min(idx+1,profiles.length-1);i>=idx;i--){
    stack.appendChild(createCard(profiles[i],i===idx));
  }
  document.getElementById('counter').textContent=(idx+1)+' / '+profiles.length;
  setupDrag();
}

function createCard(p,isTop){
  const card=document.createElement('div');
  card.className='card '+(isTop?'top':'behind');
  card.dataset.id=p.id;

  let photoStyle='';
  if(p.photo_url){
    photoStyle='background-image:url('+p.photo_url.replace(/'/g,'%27')+')';
  }else if(p.company){
    const d=p.company.toLowerCase().replace(/[^a-z0-9]/g,'')+ '.com';
    photoStyle='background-image:url(https://logo.clearbit.com/'+d+'?size=400);background-size:40%;background-repeat:no-repeat;background-position:center 30%';
  }

  let meta=[];
  if(p.location) meta.push(esc(p.location));
  if(p.employee_count) meta.push(esc(p.employee_count)+' employees');

  let icpHtml='';
  if(p.icp_score!=null&&p.icp_score<=100) icpHtml='<span class="icp '+icpCls(p.icp_score)+'">'+p.icp_score+'</span>';

  // Below-photo detail sections
  let below='';
  if(p.company_summary) below+='<div class="detail-section"><div class="detail-label">Company</div><div class="detail-text">'+esc(p.company_summary)+'</div></div>';
  if(p.ai_signal){
    let txt=esc(p.ai_signal);
    if(p.ai_signal_analysis) txt+='<br><span style="color:rgba(255,255,255,0.55);font-size:13px">'+esc(p.ai_signal_analysis)+'</span>';
    below+='<div class="detail-section"><div class="detail-label">AI Signal</div><div class="detail-text">'+txt+'</div></div>';
  }
  if(p.why_trace_fits) below+='<div class="detail-section"><div class="detail-label">Why Trace Fits</div><div class="detail-text">'+esc(p.why_trace_fits)+'</div></div>';
  if(p.recommended_approach) below+='<div class="detail-section"><div class="detail-label">Approach</div><div class="detail-text">'+esc(p.recommended_approach)+'</div></div>';
  below+='<div class="detail-links"><a class="link-li" href="'+esc(p.linkedin_url)+'" target="_blank">LinkedIn</a>';
  if(p.job_search_url) below+='<a class="link-job" href="'+esc(p.job_search_url)+'" target="_blank">AI Job Posting</a>';
  below+='</div>';

  card.innerHTML=
    '<div class="card-hero">'+
      '<div class="card-photo" style="'+photoStyle+'">'+(p.photo_url?'':'<div class="initials">'+initials(p.name||'?')+'</div>')+'</div>'+
      '<div class="card-gradient"></div>'+
      '<div class="stamp stamp-nope">NOPE</div>'+
      '<div class="stamp stamp-like">LIKE</div>'+
      '<div class="card-info">'+
        '<div class="card-name">'+esc(p.name||'Profile')+' '+icpHtml+'</div>'+
        (p.headline?'<div class="card-title">'+esc(p.headline)+'</div>':'')+
        (p.company?'<div class="card-company">'+esc(p.company)+'</div>':'')+
        (meta.length?'<div class="card-meta">'+meta.join(' / ')+'</div>':'')+
        (below?'<div class="scroll-hint">SCROLL DOWN FOR MORE</div>':'')+
      '</div>'+
    '</div>'+
    (below?'<div class="card-below">'+below+'</div>':'');

  return card;
}

// ── Drag / swipe ──
function setupDrag(){
  const card=document.querySelector('.card.top');
  if(!card) return;
  dragCard=card;
  card.addEventListener('pointerdown',onStart,{passive:false});
}

let dragging=false;
function onStart(e){
  if(e.target.closest('.detail-links,.card-below a')) return;
  startX=e.clientX;startY=e.clientY;currentX=0;dragging=false;
  document.addEventListener('pointermove',onMove);
  document.addEventListener('pointerup',onEnd);
}

function onMove(e){
  const dx=e.clientX-startX,dy=e.clientY-startY;
  // Only start horizontal drag if at scroll top and mostly horizontal movement
  if(!dragging){
    if(Math.abs(dx)>10&&Math.abs(dx)>Math.abs(dy)&&dragCard.scrollTop<10){
      dragging=true;dragCard.setPointerCapture(e.pointerId);dragCard.style.transition='none';dragCard.style.overflow='hidden';
    }else return;
  }
  currentX=dx;
  const rotate=currentX*0.08;
  dragCard.style.transform='translateX('+currentX+'px) rotate('+rotate+'deg)';
  const nope=dragCard.querySelector('.stamp-nope');
  const like=dragCard.querySelector('.stamp-like');
  const t=Math.min(Math.abs(currentX)/120,1);
  if(currentX<-20){nope.style.opacity=t;nope.style.transform='rotate(-15deg) scale('+(0.8+t*0.2)+')';like.style.opacity=0}
  else if(currentX>20){like.style.opacity=t;like.style.transform='rotate(15deg) scale('+(0.8+t*0.2)+')';nope.style.opacity=0}
  else{nope.style.opacity=0;like.style.opacity=0}
}

function onEnd(){
  document.removeEventListener('pointermove',onMove);
  document.removeEventListener('pointerup',onEnd);
  if(!dragging) return;
  dragCard.style.overflow='';
  if(Math.abs(currentX)>100){
    animateOut(currentX>0?'right':'left');
  }else{
    dragCard.style.transition='transform 0.3s ease-out';
    dragCard.style.transform='';
    dragCard.querySelector('.stamp-nope').style.opacity=0;
    dragCard.querySelector('.stamp-like').style.opacity=0;
  }
  dragging=false;
}

function animateOut(dir){
  const card=dragCard;
  card.classList.add(dir==='left'?'exit-left':'exit-right');
  if(dir==='left'){
    doSwipe('left');
    setTimeout(()=>renderCards(),400);
  }else{
    // Right swipe: show email draft
    showEmailDraft(profiles[idx]);
  }
}

// Email draft templates (rotate for same-company variety)
const EMAIL_TEMPLATES=[
  (n,job,co)=>'Hi '+n+',\n\nI graduated from Harvard and have been deeply involved in AI since December \'22. I came across the '+job+' role on LinkedIn and would love to ask a few questions about the position and learn more about what '+co+' has planned on the AI front.\n\nHave a great day!\n\nBest,\nCalvin',
  (n,job,co)=>'Hi '+n+',\n\nI\'m a recent Harvard grad and have been working in the AI space since December \'22. I came across the '+job+' role on LinkedIn and would love to learn more about the position and what '+co+' has planned on the AI front.\n\nHave a great day!\n\nBest,\nCalvin',
  (n,job,co)=>'Hi '+n+',\n\nI graduated from Harvard and have been deeply involved in AI since December \'22. I came across the '+job+' role on LinkedIn and would love to ask a few questions about the position and learn more about what '+co+' has planned on the agents front.\n\nHave a great day!\n\nBest,\nCalvin',
];
let templateIdx=0;

function showEmailDraft(p){
  const firstName=(p.name||'').split(' ')[0];
  const job=p.ai_signal||'AI';
  const co=p.company||'your company';
  const body=EMAIL_TEMPLATES[templateIdx%EMAIL_TEMPLATES.length](firstName,job,co);
  templateIdx++;
  const subject=p.ai_signal||'AI Role';

  document.getElementById('emailCard').innerHTML=
    '<h3>Draft Email</h3>'+
    '<div class="email-to">To: '+esc(firstName)+' (enrich via Apollo for email)</div>'+
    '<div class="email-subject">Subject: '+esc(subject)+'</div>'+
    '<div class="email-body" id="emailBody">'+esc(body)+'</div>'+
    '<div class="email-edit-row">'+
      '<input type="text" id="emailEditInput" placeholder="e.g. make it shorter, mention their CTO role..." onkeydown="if(event.key===\'Enter\')adjustEmail()">'+
      '<button onclick="adjustEmail()" id="emailEditBtn">Adjust</button>'+
    '</div>'+
    '<div class="email-loading" id="emailLoading">Rewriting...</div>'+
    '<div class="email-actions">'+
      '<button class="email-skip" onclick="dismissEmail(false)">Skip Email</button>'+
      '<button class="email-send" onclick="dismissEmail(true)">Send</button>'+
    '</div>';
  document.getElementById('emailOverlay').classList.add('visible');
  // Store current draft for adjustment
  window._currentDraft={body:body,subject:subject,profile:p};
}

async function adjustEmail(){
  const input=document.getElementById('emailEditInput');
  const instruction=input.value.trim();
  if(!instruction) return;
  const btn=document.getElementById('emailEditBtn');
  const loading=document.getElementById('emailLoading');
  btn.disabled=true;input.disabled=true;
  loading.classList.add('visible');loading.textContent='Rewriting...';
  try{
    const r=await fetch(BASE+'/adjust-email',{
      method:'POST',
      headers:{'Content-Type':'application/json','Authorization':'Bearer '+API_KEY},
      body:JSON.stringify({
        current_body:window._currentDraft.body,
        subject:window._currentDraft.subject,
        instruction:instruction,
        profile_name:window._currentDraft.profile.name,
        company:window._currentDraft.profile.company,
        ai_signal:window._currentDraft.profile.ai_signal
      })
    });
    const data=await r.json();
    if(data.body){
      window._currentDraft.body=data.body;
      document.getElementById('emailBody').textContent=data.body;
      if(data.subject) window._currentDraft.subject=data.subject;
    }
    input.value='';
  }catch(e){
    loading.textContent='Failed -- try again';
  }
  btn.disabled=false;input.disabled=false;
  setTimeout(()=>loading.classList.remove('visible'),1500);
}

function dismissEmail(send){
  document.getElementById('emailOverlay').classList.remove('visible');
  if(send){
    // TODO: trigger actual send via backend -> ai-job-scrape-email-writer
    console.log('Would send email for profile',profiles[idx].id);
  }
  doSwipe('right');
  setTimeout(()=>renderCards(),300);
}

async function doSwipe(direction){
  if(busy||idx>=profiles.length) return;
  busy=true;
  const pid=profiles[idx].id;
  try{
    await fetch(BASE+'/swipe',{
      method:'POST',
      headers:{'Content-Type':'application/json','Authorization':'Bearer '+API_KEY},
      body:JSON.stringify({profile_id:pid,direction:direction==='right'?'right':'left'})
    });
  }catch(e){}
  idx++;busy=false;
}

// Button triggers
document.getElementById('btnNope').addEventListener('click',()=>{
  if(!dragCard||busy) return;
  dragCard.classList.add('exit-left');
  doSwipe('left');
  setTimeout(()=>renderCards(),400);
});
document.getElementById('btnLike').addEventListener('click',()=>{
  if(!dragCard||busy) return;
  dragCard.querySelector('.stamp-like').style.opacity=1;
  dragCard.querySelector('.stamp-like').style.transform='rotate(15deg) scale(1)';
  dragCard.classList.add('exit-right');
  showEmailDraft(profiles[idx]);
});
document.getElementById('btnInfo').addEventListener('click',()=>{
  if(!dragCard) return;
  dragCard.scrollTo({top:dragCard.querySelector('.card-hero').offsetHeight,behavior:'smooth'});
});

// Keyboard
document.addEventListener('keydown',e=>{
  if(document.getElementById('emailOverlay').classList.contains('visible')) return;
  if(e.key==='ArrowLeft')document.getElementById('btnNope').click();
  if(e.key==='ArrowRight')document.getElementById('btnLike').click();
  if(e.key==='ArrowUp'||e.key==='ArrowDown')document.getElementById('btnInfo').click();
});

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
    """Use Claude API to adjust the email draft based on user instruction."""
    import subprocess

    prompt = (
        f"You are rewriting a cold outreach email. The current draft is:\n\n"
        f"Subject: {req.subject}\n\n{req.current_body}\n\n"
        f"Context: This email is to {req.profile_name or 'a lead'} at {req.company or 'their company'}."
        f"{(' AI signal: ' + req.ai_signal) if req.ai_signal else ''}\n\n"
        f"User instruction: {req.instruction}\n\n"
        f"Return ONLY the rewritten email body. No subject line, no explanation, "
        f"no markdown. Keep the same signature (Best, Calvin). Keep it concise."
    )
    try:
        result = subprocess.run(
            ["claude", "--print", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=30,
        )
        new_body = result.stdout.strip()
        if not new_body:
            raise ValueError("Empty response")
        return {"body": new_body, "subject": req.subject}
    except Exception as e:
        log.error(f"Email adjust failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to adjust email")


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
