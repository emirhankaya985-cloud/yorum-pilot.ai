"""YorumPilot AI demo-ready REST API. All data in mock mode is synthetic."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .config import get_settings
from .db import get_db, engine, Base
from . import models
from .models import User, Organization, Membership, Location, Review, Draft, Audit, Publication, utcnow
from .schemas import Register, Login, DraftUpdate, PublishRequest
from .auth import hash_password, verify_password, set_session, clear_session, identity, membership
from .ai import RuleBasedProvider
from .google import MockGoogleAdapter, PendingGoogleAdapter, GoogleIntegrationPending
from .ingestion import ingest
from .lifecycle import purge_expired


@asynccontextmanager
async def lifespan(_: FastAPI):
    if get_settings().environment != 'production':
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title='YorumPilot AI API', version='0.1.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[get_settings().frontend_url],
                   allow_credentials=True, allow_methods=['GET','POST','PATCH','DELETE'],
                   allow_headers=['content-type','x-csrf-token'])


@app.middleware('http')
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Cache-Control'] = 'no-store'
    return response


def current(request: Request, db: Session = Depends(get_db)) -> User:
    return identity(request, db)


def editable(request: Request, db: Session = Depends(get_db)) -> User:
    return identity(request, db, write=True)


def org_access(db: Session, user: User, org_id: str, roles=('owner','admin','editor','viewer')):
    return membership(db, user, org_id, roles)


def review_access(db: Session, user: User, org_id: str, review_id: str, roles=('owner','admin','editor','viewer')):
    org_access(db, user, org_id, roles)
    review = db.scalar(select(Review).where(Review.id == review_id, Review.organization_id == org_id, Review.expires_at > utcnow()))
    if not review:
        raise HTTPException(404, 'Yorum bulunamadı')
    return review


def review_json(review: Review, loc_name: str):
    return dict(id=review.id, location_id=review.location_id, location=loc_name,
                stars=review.stars, content=review.content, sentiment=review.sentiment,
                priority=review.priority, category=review.category, language=review.language,
                status=review.status, created_at=review.created_at.isoformat(),
                draft=review.draft.text if review.draft else None,
                approved=bool(review.draft and review.draft.approved_by),
                source='DEMO_DATA')


@app.get('/healthz')
def health():
    return {'status': 'ok', 'google_mode': get_settings().google_mode}


@app.get('/api/system/status')
def status():
    return {'mode': 'DEMO' if get_settings().google_mode == 'mock' else 'GOOGLE_INTEGRATION_PENDING',
            'google_integration': 'MOCK_ONLY' if get_settings().google_mode == 'mock' else 'API_ACCESS_PENDING',
            'live_google_publish_enabled': False, 'ai_provider': 'rules_mock'}


@app.post('/api/auth/register', status_code=201)
def register(data: Register, response: Response, db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(User.email == data.email)):
        raise HTTPException(409, 'E-posta zaten kayıtlı')
    user = User(email=data.email, password_hash=hash_password(data.password))
    org = Organization(name=data.organization_name)
    db.add_all([user, org])
    db.flush()
    db.add(Membership(user_id=user.id, organization_id=org.id, role='owner'))
    if get_settings().google_mode == 'mock':
        loc = Location(organization_id=org.id, name=f'{org.name} — Demo Şubesi', is_demo=True)
        db.add(loc)
        db.flush()
        for idx, (stars, content) in enumerate([
            (2, 'Yemek lezzetliydi ama çok geç geldi. Personel daha ilgili olabilirdi.'),
            (5, 'Çok güzel bir deneyimdi, teşekkür ederim!'),
            (3, 'Fiyatlar biraz yüksek ama ortam güzeldi.')], start=1):
            ingest(db, org.id, loc.id, f'synthetic-{idx}', 'v1', content, stars)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Kayıt çakışması') from None
    set_session(response, user.id)
    return {'user_id':user.id, 'organization_id':org.id, 'demo':get_settings().google_mode=='mock'}


@app.post('/api/auth/login')
def login(data: Login, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.strip().lower()))
    if not user or not verify_password(user.password_hash, data.password):
        raise HTTPException(401,'E-posta veya şifre hatalı')
    set_session(response, user.id)
    return {'ok': True}


@app.post('/api/auth/logout')
def logout(response: Response, _: User = Depends(editable)):
    clear_session(response)
    return {'ok': True}


@app.get('/api/me')
def me(user: User = Depends(current), db: Session = Depends(get_db)):
    rows = db.execute(select(Organization, Membership).join(Membership, Membership.organization_id==Organization.id)
                      .where(Membership.user_id==user.id)).all()
    return {'email':user.email,'organizations':[{'id':o.id,'name':o.name,'role':m.role} for o,m in rows]}


@app.get('/api/organizations/{org_id}/dashboard')
def dashboard(org_id: str, user: User = Depends(current), db: Session = Depends(get_db)):
    org_access(db,user,org_id)
    reviews = db.scalars(select(Review).where(Review.organization_id==org_id, Review.expires_at > utcnow())).all()
    return {'source':'DEMO_DATA' if get_settings().google_mode=='mock' else 'N/A',
            'location_count':db.scalar(select(func.count()).select_from(Location).where(Location.organization_id==org_id)),
            'review_count':len(reviews),
            'pending_count':sum(r.status=='awaiting_approval' for r in reviews),
            'negative_count':sum(r.sentiment=='negative' for r in reviews),
            'draft_count':sum(bool(r.draft) for r in reviews),
            'simulated_published_count':sum(r.status=='simulated_published' for r in reviews),
            'google_connected':False,
            'average_stars':round(sum(r.stars for r in reviews)/len(reviews),1) if reviews else None}


@app.get('/api/organizations/{org_id}/locations')
def locations(org_id: str, user: User = Depends(current), db: Session = Depends(get_db)):
    org_access(db,user,org_id)
    return [{'id':x.id,'name':x.name,'demo':x.is_demo} for x in db.scalars(select(Location).where(Location.organization_id==org_id))]


@app.get('/api/organizations/{org_id}/reviews')
def reviews(org_id: str, sentiment: str | None = None, user: User = Depends(current), db: Session = Depends(get_db)):
    org_access(db,user,org_id)
    query = select(Review).where(Review.organization_id==org_id, Review.expires_at > utcnow())
    if sentiment:
        if sentiment not in ('positive','negative','neutral','mixed'):
            raise HTTPException(400,'Geçersiz filtre')
        query = query.where(Review.sentiment==sentiment)
    rows = db.scalars(query.order_by(Review.created_at.desc()).limit(100)).all()
    names = {x.id:x.name for x in db.scalars(select(Location).where(Location.organization_id==org_id))}
    return [review_json(r,names.get(r.location_id, '')) for r in rows]


@app.patch('/api/organizations/{org_id}/reviews/{review_id}/draft')
def change_draft(org_id: str, review_id: str, data: DraftUpdate, user: User = Depends(editable), db: Session = Depends(get_db)):
    review = review_access(db,user,org_id,review_id,('owner','admin','editor'))
    if review.status == 'simulated_published':
        raise HTTPException(409,'Simülasyonda yayımlanmış yanıt düzenlenemez')
    review.draft.text = data.text
    review.draft.approved_by = None
    review.draft.approved_at = None
    review.status = 'awaiting_approval'
    db.add(Audit(organization_id=org_id,user_id=user.id,action='draft_edited',object_id=review.id))
    db.commit()
    return {'status':review.status,'approved':False}


@app.post('/api/organizations/{org_id}/reviews/{review_id}/regenerate')
def regenerate(org_id: str, review_id: str, user: User = Depends(editable), db: Session = Depends(get_db)):
    review = review_access(db,user,org_id,review_id,('owner','admin','editor'))
    if review.status == 'simulated_published':
        raise HTTPException(409,'Simülasyonda yayımlanmış yanıt değiştirilemez')
    analysis = RuleBasedProvider().analyze(review.content, review.stars)
    review.draft.text = analysis.reply_draft
    review.draft.approved_by = None
    review.draft.approved_at = None
    review.status = 'awaiting_approval'
    db.commit()
    return {'status':review.status,'draft':review.draft.text}


@app.post('/api/organizations/{org_id}/reviews/{review_id}/approve')
def approve(org_id: str, review_id: str, user: User = Depends(editable), db: Session = Depends(get_db)):
    review = review_access(db,user,org_id,review_id,('owner','admin'))
    if review.status not in ('awaiting_approval','approved') or review.draft.review_revision != review.revision:
        raise HTTPException(409,'Yorum güncel değil veya cevap zaten işlemde')
    review.draft.approved_by = user.id
    review.draft.approved_at = utcnow()
    review.status = 'approved'
    db.add(Audit(organization_id=org_id,user_id=user.id,action='reply_approved',object_id=review.id))
    db.commit()
    return {'status':review.status}


@app.post('/api/organizations/{org_id}/reviews/{review_id}/publish')
def publish(org_id: str, review_id: str, data: PublishRequest, user: User = Depends(editable), db: Session = Depends(get_db)):
    review = review_access(db,user,org_id,review_id,('owner','admin'))
    if not data.confirm:
        raise HTTPException(400,'Açık onay gerekli')
    existing = db.scalar(select(Publication).where(Publication.organization_id==org_id,
                                                  Publication.idempotency_key==data.idempotency_key))
    if existing:
        if existing.review_id != review.id:
            raise HTTPException(409, 'Idempotency key farklı yorumla kullanılmış')
        return {'status':existing.status,'duplicate':True}
    if review.status != 'approved' or not review.draft.approved_by or review.draft.review_revision != review.revision:
        raise HTTPException(409,'Güncel ve onaylı bir taslak bulunamadı')
    if len(review.draft.text.encode('utf-8')) > 4096:
        raise HTTPException(422,'4096 bayt sınırı aşıldı')
    loc = db.scalar(select(Location).where(Location.id==review.location_id, Location.organization_id==org_id))
    if not loc:
        raise HTTPException(409,'Şube eşleştirmesi bulunamadı')
    try:
        adapter = MockGoogleAdapter() if get_settings().google_mode=='mock' else PendingGoogleAdapter()
        result = adapter.publish_reply(review.external_id, review.draft.text)
    except GoogleIntegrationPending as exc:
        raise HTTPException(503,str(exc)) from exc
    review.status=result.status
    db.add(Publication(organization_id=org_id,review_id=review.id,
                       idempotency_key=data.idempotency_key,status=result.status))
    db.add(Audit(organization_id=org_id,user_id=user.id,action='reply_simulated',object_id=review.id))
    db.commit()
    return {'status':result.status,'duplicate':False,'live_google_publish':False}


@app.post('/api/organizations/{org_id}/reviews/{review_id}/reject')
def reject(org_id: str, review_id: str, user: User = Depends(editable), db: Session = Depends(get_db)):
    review = review_access(db,user,org_id,review_id,('owner','admin'))
    if review.status not in ('awaiting_approval','approved'):
        raise HTTPException(409,'Bu yanıt reddedilemez')
    review.status = 'rejected'
    review.draft.approved_by = None
    review.draft.approved_at = None
    db.add(Audit(organization_id=org_id,user_id=user.id,action='reply_rejected',object_id=review.id))
    db.commit()
    return {'status':'rejected'}
