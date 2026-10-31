import asyncio
import base64
import csv
import hashlib
import hmac
import io
import json
import os
import secrets
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from . import store
from .data import locations
from .risk import model, predict

ROOT=Path(__file__).resolve().parent
SECRET=os.getenv('SESSION_SECRET') or secrets.token_hex(32)
DEMO=os.getenv('DEMO_MODE','true').lower()=='true'
MAX_BODY=8*1024*1024
RATE=defaultdict(deque)
WEATHER_CACHE={}

def now(): return datetime.now(timezone.utc).isoformat()
def ident(prefix): return prefix+'-'+uuid.uuid4().hex[:10]
def audit(actor,action,target):
    i=ident('AUD'); store.put('audit',i,dict(id=i,actor=actor,action=action,target=target,time=now()))

def token(role,email):
    payload=base64.urlsafe_b64encode(json.dumps(dict(role=role,email=email,exp=time.time()+28800)).encode()).decode()
    return payload+'.'+hmac.new(SECRET.encode(),payload.encode(),hashlib.sha256).hexdigest()

def current(request: Request):
    raw=request.cookies.get('sg_session','')
    try:
        p,s=raw.split('.')
        if not hmac.compare_digest(s,hmac.new(SECRET.encode(),p.encode(),hashlib.sha256).hexdigest()): raise ValueError()
        data=json.loads(base64.urlsafe_b64decode(p))
        if data['exp'] < time.time(): raise ValueError()
        return data
    except Exception: raise HTTPException(401,'Please sign in to continue')

def roles(*allowed):
    def check(user=Depends(current)):
        if user['role'] not in allowed: raise HTTPException(403,'This action requires an authority role')
        return user
    return check

def site_list():
    data=locations()
    overrides={r['id']:r for r in store.all_records('reading')}
    roads={r['id']:r['status'] for r in store.all_records('road')}
    for s in data:
        if s['id'] in overrides:
            r=overrides[s['id']]; s['features']=r['features']; s['risk']=predict(r['features'])
            s['source']=r['source']; s['updated_at']=r['time']
        if s['id'] in roads: s['road_status']=roads[s['id']]
    return data

@asynccontextmanager
async def lifespan(app):
    store.init(); model()
    for s in locations():
        if s['risk']['level'] in ['Critical','High']:
            a=dict(id='ALT-'+s['id'],site_id=s['id'],location=s['name'],state=s['state'],
                   level=s['risk']['level'],score=s['risk']['score'],status='Open',created_at=now(),
                   message=s['risk']['action'],assignee='District control room',source='Seeded demonstration alert')
            store.insert_once('alert',a['id'],a)
    for i,typ,note in [('01','Cracks','New cracks visible along the uphill road shoulder.'),('07','Blocked road','Debris observed on the approach. Field verification requested.'),('03','Slope movement','Fresh soil movement visible after prolonged rainfall.')]:
        s=next(z for z in locations() if z['id']=='SG-'+i)
        r=dict(id='REP-DEMO-'+i,client_id='seed-'+i,site_id=s['id'],type=typ,note=note,
               lat=s['lat'],lon=s['lon'],status='Pending',created_at=now(),reporter='Demo field team',
               evidence=None,source='Illustrative field report')
        store.insert_once('report',r['id'],r)
    yield

app=FastAPI(title='SlopeGuard NER API',version='1.0.0',lifespan=lifespan)

@app.middleware('http')
async def controls(request,call_next):
    if request.method not in ['GET','HEAD','OPTIONS']:
        host=request.headers.get('host','')
        origin=request.headers.get('origin')
        if origin and origin not in ['https://'+host,'http://'+host]:
            return JSONResponse({'detail':'Cross-origin writes are not permitted'},403)
        if int(request.headers.get('content-length','0') or 0)>MAX_BODY:
            return JSONResponse({'detail':'Maximum request size is 8 MB'},413)
        chunks=[]; total=0
        async for chunk in request.stream():
            total+=len(chunk)
            if total>MAX_BODY: return JSONResponse({'detail':'Maximum request size is 8 MB'},413)
            chunks.append(chunk)
        request._body=b''.join(chunks)
        key=(request.client.host if request.client else 'unknown',request.url.path)
        q=RATE[key]; t=time.monotonic()
        while q and q[0]<t-60:q.popleft()
        if len(q)>=30:return JSONResponse({'detail':'Too many requests. Please wait one minute.'},429)
        q.append(t)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://*.tile.openstreetmap.org https://server.arcgisonline.com; connect-src 'self'; media-src 'self' blob: data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    if request.url.path in ['/docs','/redoc']:
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
    if request.url.path.startswith('/api'):response.headers['Cache-Control']='no-store'
    return response

class Login(BaseModel):
    email: str=Field(max_length=150)
    password: str=Field(max_length=200)

@app.post('/api/auth/login')
def login(body:Login,request:Request):
    email=body.email.lower().strip()
    role=None
    if DEMO and hmac.compare_digest(body.password,'Demo@SlopeGuard26'):
        role={'official@demo.slopeguard.app':'official','field@demo.slopeguard.app':'field','citizen@demo.slopeguard.app':'citizen'}.get(email)
    if email==os.getenv('ADMIN_EMAIL','admin@slopeguard.app') and os.getenv('ADMIN_PASSWORD') and hmac.compare_digest(body.password,os.environ['ADMIN_PASSWORD']):role='admin'
    if not role:raise HTTPException(401,'Email or password is incorrect')
    response=JSONResponse(dict(email=email,role=role))
    response.set_cookie('sg_session',token(role,email),httponly=True,secure=request.url.scheme=='https' or request.headers.get('x-forwarded-proto')=='https',samesite='lax',max_age=28800)
    audit(email,'Signed in',role)
    return response

@app.post('/api/auth/logout')
def logout():
    r=JSONResponse({'ok':True});r.delete_cookie('sg_session');return r

@app.get('/api/auth/me')
def me(user=Depends(current)):return {'email':user['email'],'role':user['role']}

@app.get('/api/health')
def health():
    with store.db() as c:store.run(c,'SELECT 1')
    return dict(status='ok',database='postgresql' if store.URL else 'sqlite',mode='demonstration' if DEMO else 'pilot',time=now())

@app.get('/api/dashboard')
def dashboard():
    data=site_list();alerts=store.all_records('alert');reports=store.all_records('report')
    counts={k:sum(s['risk']['level']==k for s in data) for k in ['Low','Moderate','High','Critical']}
    return dict(sites=data,counts=counts,alerts=alerts,reports=[{k:v for k,v in r.items() if k!='evidence'} for r in reports],
                summary=dict(sites=len(data),states=len(set(s['state'] for s in data)),
                             active_alerts=sum(a['status']!='Closed' for a in alerts),
                             restricted_roads=sum(s['road_status']=='Restricted' for s in data),
                             people_in_priority_zones=sum(s['population'] for s in data if s['risk']['level'] in ['High','Critical'])),
                mode='Demonstration',server_time=now())

class Features(BaseModel):
    rainfall_24h:float=Field(ge=0,le=600)
    rainfall_72h:float=Field(ge=0,le=1800)
    soil_moisture:float=Field(ge=0,le=100)
    slope:float=Field(ge=0,le=80)
    past_incidents:int=Field(ge=0,le=50)
    vegetation_loss:float=Field(ge=0,le=100)
    @model_validator(mode='after')
    def cumulative(self):
        if self.rainfall_72h < self.rainfall_24h:raise ValueError('72-hour rainfall must be at least 24-hour rainfall')
        return self

@app.post('/api/predict')
def prediction(body:Features):return predict(body.model_dump())

@app.get('/api/model')
def model_info():return model()[1]

class Report(BaseModel):
    client_id:str=Field(min_length=8,max_length=100,pattern=r'^[a-zA-Z0-9_-]+$')
    site_id:str=Field(max_length=20)
    type:Literal['Cracks','Slope movement','Blocked road','Waterlogging','Other']
    note:str=Field(min_length=10,max_length=1500)
    lat:float=Field(ge=22,le=30)
    lon:float=Field(ge=88,le=98)
    evidence:str|None=Field(default=None,max_length=7000000)
    @model_validator(mode='after')
    def valid_media(self):
        if self.evidence:
            try:
                head,raw=self.evidence.split(',',1)
                data=base64.b64decode(raw,validate=True)
                allowed=(head=='data:image/jpeg;base64' and data.startswith(b'\xff\xd8\xff')) or (head=='data:image/png;base64' and data.startswith(b'\x89PNG\r\n\x1a\n')) or (head=='data:video/mp4;base64' and len(data)>12 and data[4:8]==b'ftyp') or (head=='data:video/webm;base64' and data.startswith(b'\x1aE\xdf\xa3'))
                if not allowed or len(data)>5*1024*1024:raise ValueError()
            except Exception:raise ValueError('Use a valid JPEG, PNG, MP4 or WebM file up to 5 MB')
        return self

@app.post('/api/reports',status_code=201)
def report(body:Report,user=Depends(current)):
    if body.site_id not in [s['id'] for s in locations()]:raise HTTPException(404,'Unknown pilot location')
    rid='REP-'+hashlib.sha256((user['email']+body.client_id).encode()).hexdigest()[:18]
    r=dict(**body.model_dump(),id=rid,status='Pending',created_at=now(),reporter=user['email'],source='User submitted demonstration report')
    created=store.insert_once('report',rid,r)
    if created:audit(user['email'],'Submitted field report',rid)
    return {'id':rid,'status':(store.get('report',rid) or r)['status'],'duplicate':not created}

@app.get('/api/reports/{rid}/evidence')
def evidence(rid:str,user=Depends(current)):
    r=store.get('report',rid)
    if not r or not r.get('evidence'):raise HTTPException(404,'No evidence attached')
    if user['role']=='citizen' and r['reporter']!=user['email']:raise HTTPException(403,'Evidence access restricted')
    head,data=r['evidence'].split(',',1)
    return Response(base64.b64decode(data),media_type=head[5:].split(';')[0],headers={'Cache-Control':'private, no-store'})

class Review(BaseModel):
    status:Literal['Verified','Rejected']
    note:str=Field(min_length=5,max_length=500)

@app.patch('/api/reports/{rid}')
def review(rid:str,body:Review,user=Depends(roles('official','admin'))):
    with store.LOCK:
        r=store.get('report',rid)
        if not r:raise HTTPException(404,'Report not found')
        r.update(status=body.status,review_note=body.note,reviewer=user['email'],reviewed_at=now())
        store.put('report',rid,r);audit(user['email'],body.status+' field report',rid)
        return {'id':rid,'status':r['status']}

class AlertBody(BaseModel):
    site_id:str
    message:str=Field(min_length=10,max_length=1000)
    language:Literal['en','hi','as']='en'

@app.post('/api/alerts',status_code=201)
def create_alert(body:AlertBody,user=Depends(roles('official','admin'))):
    s=next((z for z in site_list() if z['id']==body.site_id),None)
    if not s:raise HTTPException(404,'Location not found')
    # One active alert per site prevents repeated ingestion from spamming the queue.
    with store.LOCK:
        existing=next((a for a in store.all_records('alert') if a['site_id']==s['id'] and a['status']!='Closed'),None)
        if existing:return dict(**existing,duplicate=True)
        a=dict(id=ident('ALT'),site_id=s['id'],location=s['name'],state=s['state'],level=s['risk']['level'],
               score=s['risk']['score'],status='Open',message=body.message,language=body.language,created_at=now(),
               assignee='District control room',source='In-app demonstration advisory',delivery='In-app published; SMS not configured')
        store.put('alert',a['id'],a);audit(user['email'],'Created in-app advisory',a['id']);return a

class AlertUpdate(BaseModel):
    status:Literal['Acknowledged','Dispatched','Closed']
    note:str=Field(min_length=5,max_length=500)
    assignee:str=Field(default='District response team',min_length=3,max_length=100)

@app.patch('/api/alerts/{aid}')
def alert_update(aid:str,body:AlertUpdate,user=Depends(roles('official','admin'))):
    with store.LOCK:
        a=store.get('alert',aid)
        if not a:raise HTTPException(404,'Alert not found')
        allowed={'Open':['Acknowledged'],'Acknowledged':['Dispatched','Closed'],'Dispatched':['Closed'],'Closed':[]}
        if body.status not in allowed[a['status']]:raise HTTPException(409,'Follow the alert workflow: acknowledge, dispatch, then close')
        a.update(status=body.status,note=body.note,assignee=body.assignee,updated_at=now())
        store.put('alert',aid,a);audit(user['email'],body.status+' advisory',aid);return a

class Road(BaseModel):
    status:Literal['Open','Caution','Restricted']
    note:str=Field(min_length=5,max_length=500)

@app.patch('/api/roads/{sid}')
def road_update(sid:str,body:Road,user=Depends(roles('official','admin'))):
    if sid not in [s['id'] for s in locations()]:raise HTTPException(404,'Location not found')
    store.put('road',sid,dict(id=sid,**body.model_dump(),updated_at=now(),actor=user['email']))
    audit(user['email'],'Updated road status to '+body.status,sid);return {'ok':True}

class Reading(BaseModel):
    site_id:str
    features:Features
    source:Literal['sensor','satellite-derived','manual']='manual'

@app.post('/api/ingest')
def ingest(body:Reading,user=Depends(roles('admin'))):
    if body.site_id not in [s['id'] for s in locations()]:raise HTTPException(404,'Location not found')
    store.put('reading',body.site_id,dict(id=body.site_id,features=body.features.model_dump(),source=body.source,time=now()))
    audit(user['email'],'Ingested validated observation',body.site_id)
    result=predict(body.features.model_dump())
    if result['level'] in ['High','Critical']:
        create_alert(AlertBody(site_id=body.site_id,message=result['action']),user)
    return result

@app.get('/api/weather/{sid}')
async def weather(sid:str):
    s=next((z for z in locations() if z['id']==sid),None)
    if not s:raise HTTPException(404,'Unknown location')
    cached=WEATHER_CACHE.get(sid)
    if cached and time.time()-cached[0]<900:return cached[1]
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r=await client.get('https://api.open-meteo.com/v1/forecast',params=dict(latitude=s['lat'],longitude=s['lon'],hourly='precipitation,soil_moisture_0_to_1cm',past_days=3,forecast_days=3,timezone='UTC'))
            r.raise_for_status();data=r.json()
        hours=data['hourly']; t=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:00')
        index=max((i for i,v in enumerate(hours['time']) if v<=t),default=0)
        past24=hours['precipitation'][max(0,index-23):index+1]
        past72=hours['precipitation'][max(0,index-71):index+1]
        if len(past24)!=24 or len(past72)!=72 or any(v is None for v in past72):raise ValueError('Incomplete weather coverage')
        data=dict(source='Open-Meteo numerical weather model',observed=False,retrieved_at=now(),
                  rainfall_24h=round(sum(past24),1),rainfall_72h=round(sum(past72),1),
                  forecast=[dict(time=tm,precipitation=pr) for tm,pr in zip(hours['time'][index+1:index+25],hours['precipitation'][index+1:index+25])],
                  soil_moisture_m3_m3=hours['soil_moisture_0_to_1cm'][index],
                  note='Modelled precipitation and shallow volumetric moisture; not an IMD observation or a calibrated slope-saturation measurement.')
        WEATHER_CACHE[sid]=(time.time(),data);return data
    except (httpx.HTTPError,ValueError,KeyError,TypeError):
        if cached:return dict(**cached[1],stale=True)
        raise HTTPException(503,'Weather provider is unavailable. The demonstration scenario remains available; no live values were substituted.')

@app.get('/api/audit')
def logs(user=Depends(roles('official','admin'))):return sorted(store.all_records('audit'),key=lambda x:x['time'],reverse=True)[:100]

@app.get('/api/export/{kind}')
def export(kind:Literal['sites','reports','alerts'],user=Depends(roles('official','admin'))):
    rows=site_list() if kind=='sites' else store.all_records('report' if kind=='reports' else 'alert')
    clean=[]
    for r in rows:
        clean.append({k:json.dumps(v) if isinstance(v,(dict,list)) else v for k,v in r.items() if k!='evidence'})
    out=io.StringIO();fields=sorted(set().union(*(r.keys() for r in clean))) if clean else ['id']
    w=csv.DictWriter(out,fieldnames=fields);w.writeheader()
    for r in clean:
        # Prevent spreadsheet formula injection when importing community text.
        w.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v) for k,v in r.items()})
    return Response(out.getvalue(),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="slopeguard-{kind}.csv"'})

@app.get('/sw.js')
def sw():return FileResponse(ROOT/'static/sw.js',media_type='application/javascript',headers={'Service-Worker-Allowed':'/','Cache-Control':'no-cache'})

app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')

@app.get('/')
def index():return FileResponse(ROOT/'static/index.html')
