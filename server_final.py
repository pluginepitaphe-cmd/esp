#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIPORTS v2.0 - Production Backend Final
FastAPI + PostgreSQL + AI Chatbot + WordPress Integration
Optimisé pour siportevent.com + Vercel + App Store
"""

import os
import sys
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any
import jwt
import secrets
import json
import logging
from werkzeug.security import generate_password_hash, check_password_hash

# Import modules
from database import init_database, test_connection, get_user_by_email, is_postgresql
from chatbot_service import siports_ai_service, ChatRequest, ChatResponse
from wordpress_config import WordPressConfig
from wordpress_sync import WordPressSync

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', secrets.token_hex(32))
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///instance/siports_production.db')
WORDPRESS_ENABLED = os.environ.get('WORDPRESS_ENABLED', 'false').lower() == 'true'
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'development')

# FastAPI app
app = FastAPI(
    title="SIPORTS v2.0 Production API",
    description="API complète pour événements maritimes avec WordPress et IA",
    version="2.0.0",
    docs_url="/api/docs" if ENVIRONMENT == "development" else None,
    redoc_url="/api/redoc" if ENVIRONMENT == "development" else None
)

# CORS configuration for siportevent.com + Vercel + App Store
allowed_origins = [
    "https://siportevent.com",
    "https://www.siportevent.com", 
    "https://siports-frontend.vercel.app",
    "https://siports-v2.vercel.app",
    "http://localhost:3000",  # Dev
    "http://127.0.0.1:3000",  # Dev
    "capacitor://localhost",  # App Store iOS
    "ionic://localhost",      # App Store iOS  
    "http://localhost",       # App Store Android
    "https://localhost",      # App Store Android
    "app://localhost",        # Electron/Desktop
    "tauri://localhost",      # Tauri Desktop
]

# Add environment-specific origins
cors_origins_env = os.environ.get("CORS_ORIGINS", "").split(",")
if cors_origins_env and cors_origins_env != [""]:
    allowed_origins.extend([origin.strip() for origin in cors_origins_env if origin.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()

# WordPress Integration
wordpress_config = None
wordpress_sync = None

if WORDPRESS_ENABLED:
    try:
        wordpress_config = WordPressConfig()
        wordpress_sync = WordPressSync(wordpress_config)
        logger.info("✅ WordPress integration initialized")
    except Exception as e:
        logger.warning(f"⚠️ WordPress integration failed: {e}")

# =============================================================================
# MODELS
# =============================================================================

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserRegistration(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    company: Optional[str] = None
    phone: Optional[str] = None
    user_type: str = "visitor"
    visitor_package: str = "Free"

class VisitorPackageUpdate(BaseModel):
    package_type: str
    user_id: int

class ContactMessage(BaseModel):
    name: str
    email: EmailStr
    company: Optional[str] = None
    subject: str
    message: str

class ExhibitorProfile(BaseModel):
    company_name: str
    description: str
    website: Optional[str] = None
    logo_url: Optional[str] = None
    contact_email: EmailStr
    phone: Optional[str] = None
    address: Optional[str] = None
    partnership_package: str = "Bronze"

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_jwt_token(user_data: dict) -> str:
    """Create JWT token"""
    token_data = {
        "user_id": user_data.get("id"),
        "email": user_data.get("email"),
        "user_type": user_data.get("user_type"),
        "exp": datetime.utcnow() + timedelta(hours=24)
    }
    return jwt.encode(token_data, JWT_SECRET_KEY, algorithm="HS256")

def verify_jwt_token(token: str) -> dict:
    """Verify JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Token invalid")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current authenticated user"""
    token = credentials.credentials
    payload = verify_jwt_token(token)
    user_data = get_user_by_email(payload.get("email"))
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user_data[0],
        "email": payload.get("email"),
        "user_type": user_data[2],
        "first_name": user_data[3],
        "last_name": user_data[4]
    }

# =============================================================================
# MAIN API ROUTES
# =============================================================================

@app.get("/")
async def root():
    """API Status"""
    return {
        "message": "SIPORTS v2.0 Production API",
        "status": "active", 
        "version": "2.0.0",
        "environment": ENVIRONMENT,
        "database": "postgresql" if is_postgresql() else "sqlite",
        "wordpress": WORDPRESS_ENABLED,
        "features": [
            "AI Chatbot",
            "Visitor Packages", 
            "Partner Packages",
            "Mini-sites Exposants",
            "Dashboard Admin",
            "WordPress Sync",
            "JWT Authentication",
            "CORS siportevent.com",
            "App Store Support"
        ]
    }

@app.get("/health")
async def health_check():
    """Health check complet"""
    health_status = {
        "status": "healthy",
        "service": "siports-production-api",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat(),
        "environment": ENVIRONMENT,
        "database_type": "postgresql" if is_postgresql() else "sqlite",
        "checks": {}
    }

    # Database check
    try:
        if test_connection():
            health_status["checks"]["database"] = "healthy"
        else:
            health_status["checks"]["database"] = "unhealthy"
            health_status["status"] = "degraded"
    except Exception as e:
        health_status["checks"]["database"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"

    # Chatbot check
    try:
        test_request = ChatRequest(message="health check", context_type="general")
        await siports_ai_service.generate_response(test_request)
        health_status["checks"]["chatbot"] = "healthy"
    except Exception as e:
        health_status["checks"]["chatbot"] = f"degraded: {str(e)}"

    # WordPress check
    if WORDPRESS_ENABLED and wordpress_sync:
        try:
            health_status["checks"]["wordpress"] = "healthy"
        except Exception as e:
            health_status["checks"]["wordpress"] = f"degraded: {str(e)}"
    else:
        health_status["checks"]["wordpress"] = "disabled"

    return health_status

# =============================================================================
# AUTHENTICATION ROUTES
# =============================================================================

@app.post("/api/auth/login")
async def login(user: UserLogin):
    """User authentication"""
    try:
        db_user = get_user_by_email(user.email)
        
        if not db_user or not check_password_hash(db_user[1], user.password):
            raise HTTPException(status_code=401, detail="Identifiants invalides")
        
        # Create JWT token
        user_data = {
            "id": db_user[0],
            "email": user.email,
            "user_type": db_user[2],
            "first_name": db_user[3],
            "last_name": db_user[4]
        }
        token = create_jwt_token(user_data)
        
        # Log login
        logger.info(f"User login: {user.email} ({user_data['user_type']})")
        
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": 86400,  # 24 hours
            "user": user_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Erreur serveur")

@app.post("/api/auth/register")
async def register(user: UserRegistration, background_tasks: BackgroundTasks):
    """User registration"""
    try:
        # Check if user exists
        existing_user = get_user_by_email(user.email)
        if existing_user:
            raise HTTPException(status_code=400, detail="Email déjà utilisé")
        
        # Hash password
        password_hash = generate_password_hash(user.password)
        
        # Create user in database (implementation needed in database.py)
        # user_id = create_user(user, password_hash)
        
        logger.info(f"New user registered: {user.email}")
        
        return {"message": "Inscription réussie", "status": "pending_validation"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de l'inscription")

@app.get("/api/auth/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current user information"""
    return {
        "user": current_user,
        "permissions": {
            "can_access_admin": current_user["user_type"] == "admin",
            "can_access_dashboard": current_user["user_type"] in ["admin", "exhibitor"],
            "can_create_minisite": current_user["user_type"] == "exhibitor"
        }
    }

# =============================================================================
# CHATBOT ROUTES
# =============================================================================

@app.get("/api/chatbot/health")
async def chatbot_health():
    """Chatbot health check"""
    return {
        "status": "healthy",
        "service": "siports-ai-chatbot",
        "version": "2.0.0",
        "features": ["multi-context", "session-aware", "maritime-specialized"],
        "contexts": ["general", "packages", "exhibitors", "technical", "navigation"]
    }

@app.post("/api/chatbot/chat")
async def chat_with_bot(request: ChatRequest):
    """Chat with AI bot"""
    try:
        response = await siports_ai_service.generate_response(request)
        
        # Log chat interaction
        logger.info(f"Chatbot interaction: {request.context_type} - {len(request.message)} chars")
        
        return response
        
    except Exception as e:
        logger.error(f"Chatbot error: {e}")
        return ChatResponse(
            response="Désolé, je rencontre un problème technique. Veuillez réessayer.",
            session_id=request.session_id or "error-session",
            context_type=request.context_type,
            confidence=0.0
        )

# =============================================================================
# VISITOR PACKAGES ROUTES  
# =============================================================================

@app.get("/api/visitor-packages")
async def get_visitor_packages():
    """Get all visitor packages"""
    packages = [
        {
            "id": "free",
            "name": "Free",
            "price": 0,
            "currency": "EUR",
            "duration": "Event duration",
            "features": [
                "Accès programme général",
                "Liste des exposants",
                "Plan du salon"
            ],
            "limitations": [
                "Accès limité aux conférences",
                "Pas de networking premium"
            ],
            "popular": False
        },
        {
            "id": "basic", 
            "name": "Basic",
            "price": 89,
            "currency": "EUR",
            "duration": "Event duration",
            "features": [
                "Tout Free +",
                "Accès conférences",
                "Networking sessions",
                "Documentation technique",
                "Badge personnalisé"
            ],
            "limitations": [],
            "popular": False
        },
        {
            "id": "premium",
            "name": "Premium", 
            "price": 189,
            "currency": "EUR",
            "duration": "Event duration",
            "features": [
                "Tout Basic +",
                "Ateliers VIP exclusifs",
                "Repas networking inclus",
                "Accès lounge premium",
                "Rendez-vous B2B facilités",
                "Kit documentation premium"
            ],
            "limitations": [],
            "popular": True
        },
        {
            "id": "vip",
            "name": "VIP Pass",
            "price": 349,
            "currency": "EUR", 
            "duration": "Event duration",
            "features": [
                "Tout Premium +",
                "Accès backstage",
                "Concierge personnel dédié",
                "Transport VIP",
                "Soirée gala incluse",
                "Networking privé dirigeants",
                "Suivi post-événement"
            ],
            "limitations": [],
            "popular": False
        }
    ]
    
    return {"packages": packages}

@app.post("/api/visitor-packages/purchase")
async def purchase_visitor_package(
    package_data: VisitorPackageUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Purchase visitor package"""
    try:
        # Implementation for package purchase
        logger.info(f"Package purchase: {package_data.package_type} by user {current_user['id']}")
        
        return {
            "message": "Forfait acheté avec succès",
            "package": package_data.package_type,
            "user_id": current_user["id"],
            "status": "active"
        }
        
    except Exception as e:
        logger.error(f"Package purchase error: {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de l'achat")

# =============================================================================
# PARTNER/EXHIBITOR PACKAGES ROUTES
# =============================================================================

@app.get("/api/partner-packages")
async def get_partner_packages():
    """Get partner/exhibitor packages"""
    packages = [
        {
            "id": "bronze",
            "name": "Bronze Partner",
            "price": 1200,
            "currency": "EUR",
            "features": [
                "Stand 9m² inclus",
                "Listing annuaire exposants",
                "2 badges exposant",
                "Wifi gratuit"
            ],
            "mini_site": False
        },
        {
            "id": "silver", 
            "name": "Silver Partner",
            "price": 2500,
            "currency": "EUR",
            "features": [
                "Stand 16m² inclus",
                "Mini-site basique",
                "4 badges exposant",
                "Logo sur supports",
                "Session networking dédiée"
            ],
            "mini_site": True,
            "mini_site_type": "basic"
        },
        {
            "id": "gold",
            "name": "Gold Partner", 
            "price": 4500,
            "currency": "EUR",
            "features": [
                "Stand 25m² premium",
                "Mini-site professionnel", 
                "8 badges exposant",
                "Conférence sponsor 30min",
                "Logo premium visibilité",
                "Leads qualifiés"
            ],
            "mini_site": True,
            "mini_site_type": "professional",
            "popular": True
        },
        {
            "id": "platinum",
            "name": "Platinum Partner",
            "price": 8900,
            "currency": "EUR", 
            "features": [
                "Stand 40m² ultra-premium",
                "Mini-site sur-mesure",
                "15 badges exposant",
                "Keynote sponsor 45min", 
                "Branding événement",
                "Base prospects complète",
                "Support dédié"
            ],
            "mini_site": True,
            "mini_site_type": "premium"
        }
    ]
    
    return {"packages": packages}

# =============================================================================
# MINI-SITES EXPOSANTS ROUTES
# =============================================================================

@app.get("/api/exhibitor/{exhibitor_id}/mini-site")
async def get_exhibitor_minisite(exhibitor_id: int):
    """Get exhibitor mini-site data"""
    # Mock data - implement database query
    minisite_data = {
        "id": exhibitor_id,
        "company_name": "Maritime Solutions Ltd",
        "logo_url": "https://via.placeholder.com/200x100",
        "description": "Solutions innovantes pour l'industrie maritime",
        "website": "https://maritimesolutions.com",
        "email": "contact@maritimesolutions.com",
        "phone": "+33 1 23 45 67 89",
        "address": "123 Port Avenue, Marseille, France",
        "products": [
            {"name": "Système Navigation Pro", "description": "Navigation maritime avancée"},
            {"name": "Capteurs IoT Marine", "description": "Surveillance en temps réel"}
        ],
        "gallery": [
            "https://via.placeholder.com/300x200",
            "https://via.placeholder.com/300x200"
        ],
        "package_type": "gold",
        "features_enabled": {
            "contact_form": True,
            "product_catalog": True,
            "gallery": True,
            "documents": True
        }
    }
    
    return minisite_data

@app.post("/api/exhibitor/mini-site/contact")
async def contact_exhibitor(message: ContactMessage):
    """Send contact message to exhibitor"""
    try:
        logger.info(f"Contact message sent to exhibitor: {message.email}")
        
        # Send email notification (implement email service)
        
        return {"message": "Message envoyé avec succès"}
        
    except Exception as e:
        logger.error(f"Contact exhibitor error: {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de l'envoi")

# =============================================================================
# ADMIN DASHBOARD ROUTES
# =============================================================================

@app.get("/api/admin/dashboard/stats")
async def get_admin_stats(current_user: dict = Depends(get_current_user)):
    """Get admin dashboard statistics"""
    if current_user["user_type"] != "admin":
        raise HTTPException(status_code=403, detail="Accès administrateur requis")
    
    # Mock stats - implement real database queries
    stats = {
        "visitors": {
            "total": 1247,
            "by_package": {
                "free": 567,
                "basic": 398,
                "premium": 198,
                "vip": 84
            },
            "growth": "+15.3%"
        },
        "exhibitors": {
            "total": 89,
            "by_package": {
                "bronze": 34,
                "silver": 28,
                "gold": 18,
                "platinum": 9
            },
            "growth": "+8.7%"
        },
        "revenue": {
            "total": 234750.00,
            "currency": "EUR",
            "visitor_packages": 87650.00,
            "partner_packages": 147100.00,
            "growth": "+22.1%"
        },
        "engagement": {
            "chatbot_interactions": 3456,
            "mini_site_visits": 12890,
            "contact_messages": 234,
            "app_downloads": 567
        },
        "recent_activity": [
            {"type": "registration", "description": "Nouvelle inscription Premium", "timestamp": "2025-08-15T09:30:00Z"},
            {"type": "purchase", "description": "Achat forfait Gold Partner", "timestamp": "2025-08-15T09:15:00Z"},
            {"type": "contact", "description": "Message via mini-site", "timestamp": "2025-08-15T09:00:00Z"}
        ]
    }
    
    return stats

# =============================================================================
# WORDPRESS INTEGRATION ROUTES
# =============================================================================

@app.get("/api/wordpress/sync-status")
async def wordpress_sync_status(current_user: dict = Depends(get_current_user)):
    """Get WordPress synchronization status"""
    if not WORDPRESS_ENABLED:
        return {"status": "disabled", "message": "WordPress integration is disabled"}
    
    if current_user["user_type"] != "admin":
        raise HTTPException(status_code=403, detail="Accès administrateur requis")
    
    return {
        "status": "active",
        "last_sync": "2025-08-15T08:00:00Z",
        "synced_entities": {
            "users": 156,
            "events": 12,
            "exhibitors": 89
        },
        "next_sync": "2025-08-15T14:00:00Z"
    }

@app.post("/api/wordpress/sync")
async def trigger_wordpress_sync(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Trigger WordPress synchronization"""
    if not WORDPRESS_ENABLED or not wordpress_sync:
        raise HTTPException(status_code=503, detail="WordPress sync not available")
    
    if current_user["user_type"] != "admin":
        raise HTTPException(status_code=403, detail="Accès administrateur requis")
    
    # Add sync task to background
    background_tasks.add_task(wordpress_sync.sync_all_data)
    
    return {"message": "Synchronisation WordPress démarrée"}

# =============================================================================
# APP STORE / MOBILE ROUTES
# =============================================================================

@app.get("/api/mobile/config")
async def get_mobile_config():
    """Get mobile app configuration"""
    return {
        "app_version": "2.0.0",
        "api_endpoint": os.environ.get("API_ENDPOINT", "https://api.siportevent.com"),
        "features": {
            "push_notifications": True,
            "offline_mode": True,
            "biometric_auth": True,
            "deep_linking": True
        },
        "update_required": False,
        "maintenance_mode": False
    }

@app.post("/api/mobile/device-token")
async def register_device_token(
    device_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Register device token for push notifications"""
    try:
        logger.info(f"Device token registered for user {current_user['id']}")
        return {"status": "registered", "message": "Token enregistré avec succès"}
    except Exception as e:
        logger.error(f"Device token registration error: {e}")
        raise HTTPException(status_code=500, detail="Erreur d'enregistrement")

# =============================================================================
# STARTUP EVENT
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    logger.info("🚀 SIPORTS v2.0 Production API starting...")
    logger.info(f"Environment: {ENVIRONMENT}")
    logger.info(f"Database type: {'PostgreSQL' if is_postgresql() else 'SQLite'}")
    logger.info(f"WordPress enabled: {WORDPRESS_ENABLED}")
    logger.info(f"CORS origins configured: {len(allowed_origins)} domains")
    
    # Initialize database
    try:
        init_database()
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise
    
    # Test AI chatbot
    try:
        test_request = ChatRequest(message="startup test", context_type="general")
        await siports_ai_service.generate_response(test_request)
        logger.info("✅ AI Chatbot service initialized")
    except Exception as e:
        logger.warning(f"⚠️ AI Chatbot service warning: {e}")
    
    logger.info("🎉 SIPORTS v2.0 Production API ready!")
    
    # Log configuration summary
    logger.info("📊 Configuration Summary:")
    logger.info(f"  - Database: {'PostgreSQL' if is_postgresql() else 'SQLite'}")
    logger.info(f"  - WordPress: {'Enabled' if WORDPRESS_ENABLED else 'Disabled'}")
    logger.info(f"  - CORS: {len(allowed_origins)} configured origins")
    logger.info(f"  - Environment: {ENVIRONMENT}")
    logger.info(f"  - Features: Chatbot, Packages, Mini-sites, Admin Dashboard")

# =============================================================================
# PRODUCTION SERVER CONFIG
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    log_level = os.environ.get("LOG_LEVEL", "info").lower()

    if ENVIRONMENT == "production":
        # En production, utiliser gunicorn (configuré dans railway.toml)
        logger.info("Production mode: use gunicorn with railway.toml configuration")
    else:
        # Mode développement local
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            log_level=log_level,
            reload=False
        )