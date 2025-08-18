#!/usr/bin/env python3
"""
Database configuration for SIPORTS v2.0
Compatible avec SQLite (dev) et PostgreSQL (production)
"""

import os
import sqlite3
from typing import Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash
import logging

logger = logging.getLogger(__name__)

# Configuration base de données
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///instance/siports_production.db')

# Gestion PostgreSQL Railway (conversion format URL)
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def is_postgresql():
    """Vérifie si on utilise PostgreSQL"""
    return DATABASE_URL.startswith("postgresql://")

def get_connection():
    """Obtient une connexion à la base de données"""
    if is_postgresql():
        # PostgreSQL avec SQLAlchemy
        engine = create_engine(DATABASE_URL)
        return engine.connect()
    else:
        # SQLite direct
        return sqlite3.connect(DATABASE_URL.replace("sqlite:///", ""))

def init_database():
    """Initialize database (SQLite ou PostgreSQL)"""
    try:
        if is_postgresql():
            # PostgreSQL initialization
            engine = create_engine(DATABASE_URL)
            
            with engine.connect() as conn:
                # Create users table
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        email VARCHAR(255) UNIQUE NOT NULL,
                        password_hash VARCHAR(255) NOT NULL,
                        user_type VARCHAR(50) DEFAULT 'visitor',
                        first_name VARCHAR(100),
                        last_name VARCHAR(100),
                        company VARCHAR(255),
                        phone VARCHAR(50),
                        visitor_package VARCHAR(50) DEFAULT 'Free',
                        partnership_package VARCHAR(50),
                        status VARCHAR(50) DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                
                # Insert admin user
                admin_password = generate_password_hash('admin123')
                conn.execute(text("""
                    INSERT INTO users (email, password_hash, user_type, status, first_name, last_name)
                    VALUES (:email, :password, 'admin', 'validated', 'Admin', 'SIPORTS')
                    ON CONFLICT (email) DO NOTHING
                """), {
                    "email": "admin@siportevent.com",
                    "password": admin_password
                })
                
                # Sample data
                visitor_password = generate_password_hash('visitor123')
                exhibitor_password = generate_password_hash('exhibitor123')
                
                conn.execute(text("""
                    INSERT INTO users (email, password_hash, user_type, visitor_package, status, first_name, last_name, company)
                    VALUES (:email, :password, 'visitor', 'Premium', 'validated', 'Marie', 'Dupont', 'Port Autonome Marseille')
                    ON CONFLICT (email) DO NOTHING
                """), {
                    "email": "visitor@example.com",
                    "password": visitor_password
                })
                
                conn.execute(text("""
                    INSERT INTO users (email, password_hash, user_type, partnership_package, status, first_name, last_name, company)
                    VALUES (:email, :password, 'exhibitor', 'Gold', 'validated', 'Jean', 'Martin', 'Maritime Solutions Ltd')
                    ON CONFLICT (email) DO NOTHING
                """), {
                    "email": "exposant@example.com",
                    "password": exhibitor_password
                })
                
                conn.commit()
                logger.info("PostgreSQL database initialized successfully")
                
        else:
            # SQLite initialization (mode développement)
            os.makedirs('instance', exist_ok=True)
            conn = sqlite3.connect(DATABASE_URL.replace("sqlite:///", ""))
            
            # Users table
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Insert admin user
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
            logger.info("SQLite database initialized successfully")
            
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

def test_connection():
    """Test database connection"""
    try:
        if is_postgresql():
            engine = create_engine(DATABASE_URL)
            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                return result.fetchone() is not None
        else:
            conn = sqlite3.connect(DATABASE_URL.replace("sqlite:///", ""))
            conn.execute("SELECT 1")
            conn.close()
            return True
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return False

def get_user_by_email(email: str):
    """Get user by email"""
    try:
        if is_postgresql():
            engine = create_engine(DATABASE_URL)
            with engine.connect() as conn:
                result = conn.execute(
                    text("SELECT id, password_hash, user_type, first_name, last_name FROM users WHERE email = :email"),
                    {"email": email}
                )
                return result.fetchone()
        else:
            conn = sqlite3.connect(DATABASE_URL.replace("sqlite:///", ""))
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, password_hash, user_type, first_name, last_name FROM users WHERE email = ?",
                (email,)
            )
            result = cursor.fetchone()
            conn.close()
            return result
    except Exception as e:
        logger.error(f"Error getting user by email: {e}")
        return None