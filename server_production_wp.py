#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIPORTS v2.0 - Production Backend with WordPress Integration
FastAPI + SQLite + WordPress Sync + AI Chatbot
Optimisé pour Railway deployment
"""

import os
import sys
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import jwt
import secrets
import json
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import logging

# Import WordPress integration
from wordpress_config import wp_config
from wordpress_sync import get_wp_sync_service

# Import chatbot service
from chatbot_service import siports_ai_service, ChatRequest, ChatResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', secrets.token_hex(32))
DATABASE_URL = os.environ.get('DATABASE_URL', 'instance/siports_production.db')
WORDPRESS_ENABLED = os.environ.get('WORDPRESS_ENABLED', 'true').lower() == 'true'

# FastAPI app
app = FastAPI(
    title="SIPORTS v2.0 API with WordPress",
    description="API pour événements maritimes avec synchronisation WordPress et chatbot IA",
    version="2.0.0"
)

# CORS configuration for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure with your domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()

# Initialize WordPress sync service
wp_sync = get_wp_sync_service(DATABASE_URL) if WORDPRESS_ENABLED else None

# Database initialization (enhanced with WordPress fields)
def init_database():
    """Initialize production database with WordPress integration"""
    os.makedirs('instance', exist_ok=True)
    conn = sqlite3.connect(DATABASE_URL)
    
    # Enhanced users table with WordPress fields
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            user_type TEXT DEFAULT 'visitor',
            first_name TEXT,
            last_name TEXT,
            company TEXT,
            phone TEXT,
            visitor_package TEXT DEFAULT 'Free',
            partnership_package TEXT,
            status TEXT DEFAULT 'pending',
            wp_user_id INTEGER,
            wp_sync_enabled BOOLEAN DEFAULT 1,
            last_wp_sync TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # WordPress sync log table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS wp_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            data TEXT,
            status TEXT DEFAULT 'pending',
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Insert admin user if not exists
    admin_password = generate_password_hash('admin123')
    conn.execute('''
        INSERT OR IGNORE INTO users (email, password_hash, user_type, status, first_name, last_name)
        VALUES (?, ?, 'admin', 'validated', 'Admin', 'SIPORTS')
    ''', ('admin@siportevent.com', admin_password))
    
    # Sample data
    visitor_password = generate_password_hash('visitor123')
    exhibitor_password = generate_password_hash('exhibitor123')
    
    conn.execute('''
        INSERT OR IGNORE INTO users (email, password_hash, user_type, visitor_package, status, first_name, last_name, company)
        VALUES (?, ?, 'visitor', 'Premium', 'validated', 'Marie', 'Dupont', 'Port Autonome Marseille')
    ''', ('visitor@example.com', visitor_password))
    
    conn.execute('''
        INSERT OR IGNORE INTO users (email, password_hash, user_type, partnership_package, status, first_name, last_name, company)
        VALUES (?, ?, 'exhibitor', 'Gold', 'validated', 'Jean', 'Martin', 'Maritime Solutions Ltd')
    ''', ('exposant@example.com', exhibitor_password))
    
    conn.commit()
    conn.close()

# Initialize database on startup
init_database()

# Models
class UserLogin(BaseModel):
    email: str
    password: str
    wordpress_auth: bool = False

class WordPressLogin(BaseModel):
    username: str
    password: str

class UserRegister(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str
    company: Optional[str] = None
    phone: Optional[str] = None
    user_type: str = 'visitor'
    sync_with_wp: bool = True

class PackageUpdate(BaseModel):
    package_type: str
    user_id: int
    sync_to_wp: bool = True

class WebhookData(BaseModel):
    action: str
    post_type: Optional[str] = None
    post_id: Optional[int] = None
    user_id: Optional[int] = None
    user_email: Optional[str] = None
    meta_key: Optional[str] = None
    meta_value: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

# Helper functions (same as before)
def create_jwt_token(user_data: dict) -> str:
    """Create JWT token"""
    payload = {
        'user_id': user_data['id'],
        'email': user_data['email'],
        'user_type': user_data['user_type'],
        'wp_user_id': user_data.get('wp_user_id'),
        'exp': datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm='HS256')

def verify_jwt_token(token: str) -> dict:
    """Verify JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expiré")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token invalide")

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current user from JWT token"""
    token = credentials.credentials
    payload = verify_jwt_token(token)
    
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row
    user = conn.execute(
        'SELECT * FROM users WHERE id = ?',
        (payload['user_id'],)
    ).fetchone()
    conn.close()
    
    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur non trouvé")
    
    return dict(user)

def admin_required(user: dict = Depends(get_current_user)):
    """Admin authorization required"""
    if user['user_type'] != 'admin':
        raise HTTPException(status_code=403, detail="Accès admin requis")
    return user

# =============================================================================
# WORDPRESS AUTHENTICATION ENDPOINTS
# =============================================================================

@app.post("/api/wordpress/login")
async def wordpress_login(wp_login: WordPressLogin):
    """WordPress user authentication"""
    if not WORDPRESS_ENABLED or not wp_sync:
        raise HTTPException(status_code=503, detail="WordPress integration non disponible")
    
    try:
        # Sync WordPress user to SIPORTS
        user_data = wp_sync.sync_wp_user_to_siports(wp_login.username, wp_login.password)
        
        if not user_data:
            raise HTTPException(status_code=401, detail="Identifiants WordPress invalides")
        
        # Create JWT token for synchronized user
        token = create_jwt_token(user_data)
        
        # Log sync activity
        conn = sqlite3.connect(DATABASE_URL)
        conn.execute('''
            INSERT INTO wp_sync_log (user_id, action, data, status)
            VALUES (?, ?, ?, ?)
        ''', (user_data['id'], 'wordpress_login', json.dumps({'wp_user_id': user_data.get('wp_user_id')}), 'success'))
        conn.commit()
        conn.close()
        
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user_data['id'],
                "email": user_data['email'],
                "first_name": user_data['first_name'],
                "last_name": user_data['last_name'],
                "company": user_data.get('company'),
                "user_type": user_data['user_type'],
                "visitor_package": user_data.get('visitor_package', 'Free'),
                "partnership_package": user_data.get('partnership_package'),
                "wp_user_id": user_data.get('wp_user_id'),
                "wp_role": user_data.get('wp_role')
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"WordPress login error: {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur authentification WordPress")

@app.get("/api/wordpress/events")
async def get_wordpress_events():
    """Get events from WordPress"""
    if not WORDPRESS_ENABLED or not wp_sync:
        return {"events": []}
    
    try:
        events = wp_sync.get_wp_events_data()
        return {"events": events, "source": "wordpress"}
        
    except Exception as e:
        logger.error(f"WordPress events error: {str(e)}")
        return {"events": [], "error": str(e)}

@app.get("/api/wordpress/exhibitors")
async def get_wordpress_exhibitors():
    """Get exhibitors from WordPress"""
    if not WORDPRESS_ENABLED or not wp_sync:
        return {"exhibitors": []}
    
    try:
        exhibitors = wp_sync.get_wp_exhibitors_data()
        return {"exhibitors": exhibitors, "source": "wordpress"}
        
    except Exception as e:
        logger.error(f"WordPress exhibitors error: {str(e)}")
        return {"exhibitors": [], "error": str(e)}

@app.post("/api/wordpress/webhook")
async def wordpress_webhook(webhook_data: WebhookData):
    """Handle WordPress webhooks for real-time synchronization"""
    if not WORDPRESS_ENABLED or not wp_sync:
        raise HTTPException(status_code=503, detail="WordPress integration non disponible")
    
    try:
        result = wp_sync.webhook_handler(webhook_data.dict())
        
        # Log webhook processing
        conn = sqlite3.connect(DATABASE_URL)
        conn.execute('''
            INSERT INTO wp_sync_log (action, data, status)
            VALUES (?, ?, ?)
        ''', (f"webhook_{webhook_data.action}", json.dumps(webhook_data.dict()), result['status']))
        conn.commit()
        conn.close()
        
        return result
        
    except Exception as e:
        logger.error(f"WordPress webhook error: {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur traitement webhook")

@app.get("/api/wordpress/sync-status/{user_id}")
async def get_sync_status(user_id: int, user: dict = Depends(get_current_user)):
    """Get WordPress sync status for user"""
    if user['id'] != user_id and user['user_type'] != 'admin':
        raise HTTPException(status_code=403, detail="Accès non autorisé")
    
    try:
        conn = sqlite3.connect(DATABASE_URL)
        conn.row_factory = sqlite3.Row
        
        # Get user sync info
        user_info = conn.execute(
            'SELECT wp_user_id, wp_sync_enabled, last_wp_sync FROM users WHERE id = ?',
            (user_id,)
        ).fetchone()
        
        # Get recent sync logs
        logs = conn.execute('''
            SELECT action, status, created_at, error_message 
            FROM wp_sync_log 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT 10
        ''', (user_id,)).fetchall()
        
        conn.close()
        
        return {
            "wp_user_id": user_info['wp_user_id'] if user_info else None,
            "sync_enabled": user_info['wp_sync_enabled'] if user_info else False,
            "last_sync": user_info['last_wp_sync'] if user_info else None,
            "recent_logs": [dict(log) for log in logs]
        }
        
    except Exception as e:
        logger.error(f"Sync status error: {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur statut synchronisation")

# =============================================================================
# ENHANCED AUTHENTICATION ENDPOINTS (with WordPress support)
# =============================================================================

@app.post("/api/auth/login")
async def login(user: UserLogin):
    """Enhanced login with WordPress support"""
    try:
        # WordPress authentication
        if user.wordpress_auth and WORDPRESS_ENABLED and wp_sync:
            return await wordpress_login(WordPressLogin(username=user.email, password=user.password))
        
        # Standard SIPORTS authentication
        conn = sqlite3.connect(DATABASE_URL)
        conn.row_factory = sqlite3.Row
        
        db_user = conn.execute(
            'SELECT * FROM users WHERE email = ?',
            (user.email,)
        ).fetchone()
        conn.close()
        
        if not db_user or not check_password_hash(db_user['password_hash'], user.password):
            raise HTTPException(status_code=401, detail="Identifiants invalides")
        
        if db_user['status'] != 'validated':
            raise HTTPException(status_code=403, detail="Compte en attente de validation")
        
        # Create JWT token
        user_data = dict(db_user)
        token = create_jwt_token(user_data)
        
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user_data['id'],
                "email": user_data['email'],
                "first_name": user_data['first_name'],
                "last_name": user_data['last_name'],
                "company": user_data['company'],
                "user_type": user_data['user_type'],
                "visitor_package": user_data['visitor_package'],
                "partnership_package": user_data['partnership_package']
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur connexion")

# =============================================================================
# ENHANCED PACKAGE ENDPOINTS (with WordPress sync)
# =============================================================================

@app.post("/api/visitor-packages/update")
async def update_visitor_package(data: PackageUpdate, user: dict = Depends(get_current_user)):
    """Update user's visitor package with WordPress sync"""
    try:
        conn = sqlite3.connect(DATABASE_URL)
        conn.execute(
            'UPDATE users SET visitor_package = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (data.package_type, user['id'])
        )
        conn.commit()
        conn.close()
        
        # Sync to WordPress if enabled
        if data.sync_to_wp and WORDPRESS_ENABLED and wp_sync:
            try:
                success = wp_sync.sync_siports_packages_to_wp(
                    user['id'], 
                    {'visitor_package': data.package_type}
                )
                if success:
                    logger.info(f"Package synced to WordPress for user {user['id']}")
            except Exception as e:
                logger.warning(f"WordPress package sync failed: {e}")
        
        return {"message": "Forfait mis à jour avec succès", "synced_to_wp": data.sync_to_wp}
        
    except Exception as e:
        logger.error(f"Package update error: {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur mise à jour forfait")

# =============================================================================
# ALL OTHER ENDPOINTS (same as server_production.py)
# =============================================================================

@app.post("/api/auth/register")
async def register(user: UserRegister):
    """User registration with WordPress sync option"""
    try:
        conn = sqlite3.connect(DATABASE_URL)
        
        # Check if user exists
        existing = conn.execute(
            'SELECT id FROM users WHERE email = ?',
            (user.email,)
        ).fetchone()
        
        if existing:
            raise HTTPException(status_code=400, detail="Utilisateur existant")
        
        # Create user
        password_hash = generate_password_hash(user.password)
        cursor = conn.execute('''
            INSERT INTO users (email, password_hash, user_type, first_name, last_name, company, phone, wp_sync_enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user.email, password_hash, user.user_type, user.first_name, user.last_name, user.company, user.phone, user.sync_with_wp))
        
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return {"message": "Inscription réussie", "user_id": user_id}
        
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur inscription")

# Include all other endpoints from server_production.py
@app.get("/api/visitor-packages")
async def get_visitor_packages():
    """Get visitor packages"""
    packages = [
        {
            "id": 1,
            "name": "Free Pass",
            "price": 0,
            "currency": "€",
            "description": "Accès gratuit aux espaces d'exposition",
            "features": [
                "Accès aux espaces d'exposition",
                "Conférences publiques",
                "Application mobile",
                "Plan du salon"
            ],
            "limitations": {
                "b2b_meetings": 0,
                "networking": "Limité"
            }
        },
        {
            "id": 2,
            "name": "Basic Pass",
            "price": 150,
            "currency": "€",
            "description": "Pass essentiel pour 1 journée",
            "features": [
                "Tout du Free Pass",
                "2 rendez-vous B2B garantis",
                "Accès aux pauses café",
                "Badge visiteur personnalisé"
            ],
            "limitations": {
                "b2b_meetings": 2,
                "networking": "Standard"
            }
        },
        {
            "id": 3,
            "name": "Premium Pass",
            "price": 350,
            "currency": "€",
            "description": "Pass complet pour 2 journées",
            "features": [
                "Tout du Basic Pass",
                "5 rendez-vous B2B garantis",
                "Ateliers techniques spécialisés",
                "Déjeuners networking",
                "Accès zone VIP"
            ],
            "popular": True,
            "limitations": {
                "b2b_meetings": 5,
                "networking": "Avancé"
            }
        },
        {
            "id": 4,
            "name": "VIP Pass",
            "price": 750,
            "currency": "€",
            "description": "Accès privilégié 3 journées complètes",
            "features": [
                "Tout du Premium Pass",
                "Rendez-vous B2B illimités",
                "Soirée de gala exclusive",
                "Conférences privées C-Level",
                "Service de conciergerie",
                "Transferts inclus"
            ],
            "limitations": {
                "b2b_meetings": "unlimited",
                "networking": "Premium"
            }
        }
    ]
    return {"packages": packages}

@app.get("/api/partnership-packages")
async def get_partnership_packages():
    """Get partnership packages"""
    packages = [
        {
            "id": 1,
            "name": "Startup Package",
            "price": 2500,
            "currency": "$",
            "description": "Idéal pour les jeunes entreprises maritimes",
            "features": [
                "Stand 6m² (2x3m)",
                "2 badges exposant",
                "Listing annuaire digital",
                "Support technique de base"
            ],
            "category": "startup"
        },
        {
            "id": 2,
            "name": "Silver Package", 
            "price": 8000,
            "currency": "$",
            "description": "Package standard pour exposants confirmés",
            "features": [
                "Stand 12m² (3x4m)",
                "4 badges exposant",
                "Mobilier standard inclus",
                "1 session de networking sponsorisée",
                "Présence catalogue premium"
            ],
            "category": "standard"
        },
        {
            "id": 3,
            "name": "Gold Package",
            "price": 15000,
            "currency": "$", 
            "description": "Package avancé avec visibilité renforcée",
            "features": [
                "Stand 20m² (4x5m) - Emplacement premium",
                "6 badges exposant",
                "Mobilier sur-mesure",
                "2 conférences sponsorisées (30min)",
                "Logo sur supports officiels",
                "1 cocktail networking privé"
            ],
            "popular": True,
            "category": "premium"
        },
        {
            "id": 4,
            "name": "Platinum Package",
            "price": 25000,
            "currency": "$",
            "description": "Package prestige - Partenaire officiel",
            "features": [
                "Stand 40m² (5x8m) - Hall d'entrée",
                "10 badges exposant",
                "Design stand personnalisé",
                "Keynote session dédiée (45min)",
                "Mini-site SIPORTS Premium dédié",
                "Branding événement (logos, panneaux)",
                "Dîner VIP avec comité d'organisation",
                "Communiqué de presse co-signé"
            ],
            "category": "prestige"
        }
    ]
    return {"packages": packages}

# Admin endpoints (same as before)
@app.get("/api/admin/dashboard/stats")
async def get_admin_stats(admin: dict = Depends(admin_required)):
    """Get admin dashboard statistics"""
    try:
        conn = sqlite3.connect(DATABASE_URL)
        
        total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        visitors = conn.execute('SELECT COUNT(*) FROM users WHERE user_type = "visitor"').fetchone()[0]
        exhibitors = conn.execute('SELECT COUNT(*) FROM users WHERE user_type = "exhibitor"').fetchone()[0]
        partners = conn.execute('SELECT COUNT(*) FROM users WHERE user_type = "partner"').fetchone()[0]
        
        pending = conn.execute('SELECT COUNT(*) FROM users WHERE status = "pending"').fetchone()[0]
        validated = conn.execute('SELECT COUNT(*) FROM users WHERE status = "validated"').fetchone()[0]
        rejected = conn.execute('SELECT COUNT(*) FROM users WHERE status = "rejected"').fetchone()[0]
        
        # WordPress sync stats
        wp_synced = conn.execute('SELECT COUNT(*) FROM users WHERE wp_user_id IS NOT NULL').fetchone()[0] if WORDPRESS_ENABLED else 0
        
        conn.close()
        
        return {
            "total_users": total_users,
            "visitors": visitors,
            "exhibitors": exhibitors,
            "partners": partners,
            "pending": pending,
            "validated": validated,
            "rejected": rejected,
            "wordpress_synced": wp_synced
        }
        
    except Exception as e:
        logger.error(f"Admin stats error: {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur statistiques")

@app.get("/api/admin/users/pending")
async def get_pending_users(admin: dict = Depends(admin_required)):
    """Get users pending validation"""
    try:
        conn = sqlite3.connect(DATABASE_URL)
        conn.row_factory = sqlite3.Row
        
        users = conn.execute('''
            SELECT id, email, first_name, last_name, company, user_type, wp_user_id, created_at
            FROM users WHERE status = 'pending'
            ORDER BY created_at DESC
        ''').fetchall()
        conn.close()
        
        return {"users": [dict(user) for user in users]}
        
    except Exception as e:
        logger.error(f"Pending users error: {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur récupération utilisateurs")

@app.post("/api/admin/users/{user_id}/validate")
async def validate_user(user_id: int, admin: dict = Depends(admin_required)):
    """Validate a user"""
    try:
        conn = sqlite3.connect(DATABASE_URL)
        conn.execute(
            'UPDATE users SET status = "validated", updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (user_id,)
        )
        conn.commit()
        conn.close()
        
        return {"message": "Utilisateur validé avec succès"}
        
    except Exception as e:
        logger.error(f"User validation error: {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur validation utilisateur")

@app.post("/api/admin/users/{user_id}/reject") 
async def reject_user(user_id: int, admin: dict = Depends(admin_required)):
    """Reject a user"""
    try:
        conn = sqlite3.connect(DATABASE_URL)
        conn.execute(
            'UPDATE users SET status = "rejected", updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (user_id,)
        )
        conn.commit()
        conn.close()
        
        return {"message": "Utilisateur rejeté"}
        
    except Exception as e:
        logger.error(f"User rejection error: {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur rejet utilisateur")

# AI Chatbot endpoints (same as before)
@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """Main AI chatbot endpoint"""
    try:
        response = await siports_ai_service.generate_response(request)
        logger.info(f"Chatbot response generated for context: {request.context_type}")
        return response
        
    except Exception as e:
        logger.error(f"Chatbot error: {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur chatbot")

@app.post("/api/chat/exhibitor", response_model=ChatResponse)
async def exhibitor_chat_endpoint(request: ChatRequest):
    """Specialized endpoint for exhibitor recommendations"""
    request.context_type = "exhibitor"
    return await chat_endpoint(request)

@app.post("/api/chat/package", response_model=ChatResponse) 
async def package_chat_endpoint(request: ChatRequest):
    """Specialized endpoint for package suggestions"""
    request.context_type = "package"
    return await chat_endpoint(request)

@app.post("/api/chat/event", response_model=ChatResponse)
async def event_chat_endpoint(request: ChatRequest):
    """Specialized endpoint for event information"""
    request.context_type = "event"
    return await chat_endpoint(request)

@app.get("/api/chatbot/health")
async def chatbot_health_check():
    """Chatbot health check"""
    try:
        test_request = ChatRequest(message="test health", context_type="general")
        response = await siports_ai_service.generate_response(test_request)
        
        return {
            "status": "healthy",
            "service": "siports-ai-chatbot",
            "version": "2.0.0",
            "mock_mode": siports_ai_service.mock_mode,
            "wordpress_enabled": WORDPRESS_ENABLED,
            "test_response_length": len(response.response)
        }
    except Exception as e:
        logger.error(f"Chatbot health check failed: {str(e)}")
        return {"status": "unhealthy", "error": str(e)}

# System endpoints
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "SIPORTS v2.0 API with WordPress", 
        "status": "active", 
        "version": "2.0.0",
        "wordpress_enabled": WORDPRESS_ENABLED
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    wp_status = "enabled" if WORDPRESS_ENABLED else "disabled"
    return {
        "status": "healthy", 
        "service": "siports-api", 
        "version": "2.0.0",
        "wordpress": wp_status
    }

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    logger.info("SIPORTS v2.0 API with WordPress starting...")
    logger.info(f"Database: {DATABASE_URL}")
    logger.info(f"WordPress integration: {'Enabled' if WORDPRESS_ENABLED else 'Disabled'}")
    logger.info("AI Chatbot service initialized")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)