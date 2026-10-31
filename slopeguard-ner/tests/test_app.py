import base64
import uuid
import pytest
from fastapi.testclient import TestClient
from app import store
from app.main import app

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'URL','')
    monkeypatch.setattr(store,'PATH',str(tmp_path/'test.db'))
    with TestClient(app) as c:yield c

def login(c,role='official'):
    r=c.post('/api/auth/login',json={'email':role+'@demo.slopeguard.app','password':'Demo@SlopeGuard26'})
    assert r.status_code==200
    return r

def sample(**kwargs):
    return dict(rainfall_24h=200,rainfall_72h=600,soil_moisture=85,slope=45,past_incidents=8,vegetation_loss=40,**kwargs)

def report_body():
    return dict(client_id=uuid.uuid4().hex,site_id='SG-01',type='Cracks',note='Visible cracks near the road shoulder.',lat=27.61,lon=88.64)

def test_health_and_complete_dashboard(client):
    assert client.get('/api/health').json()['status']=='ok'
    d=client.get('/api/dashboard').json()
    assert len(d['sites'])==16 and d['summary']['states']==8
    assert sum(d['counts'].values())==16
    assert d['counts']['Critical']>0

def test_prediction_validation_and_sensitivity(client):
    dry=dict(rainfall_24h=10,rainfall_72h=35,soil_moisture=25,slope=15,past_incidents=0,vegetation_loss=0)
    wet=dict(rainfall_24h=340,rainfall_72h=1000,soil_moisture=98,slope=60,past_incidents=14,vegetation_loss=70)
    a=client.post('/api/predict',json=dry).json();b=client.post('/api/predict',json=wet).json()
    assert a['score']<b['score'] and a['level']=='Low' and b['level']=='Critical'
    assert b['calibrated_probability'] is False
    bad=dict(wet,rainfall_72h=10)
    assert client.post('/api/predict',json=bad).status_code==422
    assert client.post('/api/predict',json=dict(wet,slope=-1)).status_code==422

def test_auth_role_boundaries(client):
    assert client.post('/api/reports',json=report_body()).status_code==401
    assert client.get('/api/export/sites').status_code==401
    login(client,'field')
    assert client.post('/api/alerts',json={'site_id':'SG-01','message':'Sample advisory message.'}).status_code==403
    assert client.post('/api/ingest',json={'site_id':'SG-01','features':sample()}).status_code==403
    assert client.get('/api/audit').status_code==403

def test_report_offline_retry_is_idempotent_and_reviewable(client):
    login(client,'field');body=report_body()
    first=client.post('/api/reports',json=body);second=client.post('/api/reports',json=body)
    assert first.status_code==201 and first.json()['id']==second.json()['id'] and second.json()['duplicate']
    rid=first.json()['id']
    assert client.patch('/api/reports/'+rid,json={'status':'Verified','note':'Inspected by local field team.'}).status_code==403
    login(client)
    assert client.patch('/api/reports/'+rid,json={'status':'Verified','note':'Inspected by local field team.'}).status_code==200
    assert any(r['id']==rid and r['status']=='Verified' for r in client.get('/api/dashboard').json()['reports'])

def test_evidence_validation_and_storage(client):
    login(client,'field');body=report_body()
    body['evidence']='data:image/png;base64,'+base64.b64encode(b'<script>unsafe</script>').decode()
    assert client.post('/api/reports',json=body).status_code==422
    png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6utkAAAAASUVORK5CYII=')
    body['evidence']='data:image/png;base64,'+base64.b64encode(png).decode()
    r=client.post('/api/reports',json=body);assert r.status_code==201
    evidence=client.get('/api/reports/'+r.json()['id']+'/evidence')
    assert evidence.content==png and evidence.headers['content-type']=='image/png'
    assert 'evidence' not in next(x for x in client.get('/api/dashboard').json()['reports'] if x['id']==r.json()['id'])

def test_alert_state_machine_and_dedup(client):
    login(client)
    body={'site_id':'SG-09','message':'Demonstration advisory: inspect the corridor.'}
    r=client.post('/api/alerts',json=body);assert r.status_code==201
    aid=r.json()['id'];assert client.post('/api/alerts',json=body).json()['id']==aid
    assert client.patch('/api/alerts/'+aid,json={'status':'Dispatched','note':'Field team assigned.'}).status_code==409
    for status in ['Acknowledged','Dispatched','Closed']:
        assert client.patch('/api/alerts/'+aid,json={'status':status,'note':'Demonstration response verified.'}).status_code==200
    assert client.patch('/api/alerts/'+aid,json={'status':'Acknowledged','note':'Cannot reopen a closed advisory.'}).status_code==409

def test_road_update_persists_and_audits(client):
    login(client)
    assert client.patch('/api/roads/SG-12',json={'status':'Restricted','note':'Blocked by demonstration debris.'}).status_code==200
    assert next(s for s in client.get('/api/dashboard').json()['sites'] if s['id']=='SG-12')['road_status']=='Restricted'
    assert any(a['target']=='SG-12' for a in client.get('/api/audit').json())

def test_cross_origin_and_payload_limits(client):
    assert client.post('/api/predict',json=sample(),headers={'Origin':'https://evil.example'}).status_code==403
    assert client.post('/api/predict',content=b'x',headers={'Content-Length':str(9*1024*1024)}).status_code==413

def test_synthetic_metrics_are_labelled(client):
    m=client.get('/api/model').json()
    assert not m['validated_for_operations'] and 'Synthetic' in m['training_source']
    assert m['training_samples']+m['test_samples']==2400

def test_csv_formula_injection_guard(client):
    login(client,'field');body=report_body();body['note']='=HYPERLINK("malicious", "test")'
    client.post('/api/reports',json=body);login(client)
    r=client.get('/api/export/reports')
    assert r.status_code==200 and "'=HYPERLINK" in r.text

def test_session_tampering_and_logout(client):
    login(client);raw=client.cookies.get('sg_session')
    client.cookies.set('sg_session',raw[:-1]+('0' if raw[-1]!='0' else '1'))
    assert client.get('/api/auth/me').status_code==401
    client.cookies.clear();login(client);client.post('/api/auth/logout')
    assert client.get('/api/auth/me').status_code==401

def test_weather_provider_failure_is_explicit(client,monkeypatch):
    import httpx
    async def fail(*args,**kwargs):raise httpx.ConnectError('provider offline')
    monkeypatch.setattr(httpx.AsyncClient,'get',fail)
    r=client.get('/api/weather/SG-01')
    assert r.status_code==503 and 'no live values' in r.json()['detail']

def test_admin_ingestion_and_escalation(client,monkeypatch):
    monkeypatch.setenv('ADMIN_PASSWORD','LocalTestAdminPassword!')
    assert client.post('/api/auth/login',json={'email':'admin@slopeguard.app','password':'LocalTestAdminPassword!'}).status_code==200
    body={'site_id':'SG-15','features':sample(),'source':'sensor'}
    assert client.post('/api/ingest',json=body).status_code==200
    d=client.get('/api/dashboard').json()
    assert next(s for s in d['sites'] if s['id']=='SG-15')['source']=='sensor'
    assert any(a['site_id']=='SG-15' for a in d['alerts'])

def test_static_shell_security(client):
    r=client.get('/')
    assert r.status_code==200 and 'SlopeGuard' in r.text
    assert "frame-ancestors 'none'" in r.headers['content-security-policy']
    assert client.get('/sw.js').headers['service-worker-allowed']=='/'
