#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIPORTS v2.0 - AI ChatBot System with Claude
Chatbot maritime intelligent avec IA avancée
"""

import os
import json
import uuid
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import logging
from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger('siports_ai_chatbot')

class ChatMessage(BaseModel):
    id: str
    session_id: str
    user_id: Optional[int] = None
    message: str
    response: str
    timestamp: datetime
    message_type: str = "text"  # text, voice, image
    language: str = "fr"
    context: Dict[str, Any] = {}
    sentiment_score: float = 0.0
    intent: Optional[str] = None

class ChatSession(BaseModel):
    id: str
    user_id: Optional[int] = None
    started_at: datetime
    last_activity: datetime
    language: str = "fr"
    context: Dict[str, Any] = {}
    message_count: int = 0
    status: str = "active"  # active, paused, ended

class MaritimeChatBot:
    """Chatbot IA spécialisé maritime avec Claude"""
    
    def __init__(self, claude_api_key: str):
        self.claude_api_key = claude_api_key
        self.db_path = "/app/instance/siports_production.db"
        self.active_sessions: Dict[str, LlmChat] = {}
        
        # Système prompt spécialisé maritime
        self.maritime_system_prompt = """
Tu es SIPORTS AI, un assistant intelligent spécialisé dans le domaine maritime et portuaire.

EXPERTISE MARITIME:
- Terminologie portuaire et maritime (français, anglais, espagnol)
- Logistique portuaire et transport maritime
- Réglementations maritimes internationales (OMI, SOLAS, MARPOL)
- Technologies portuaires (grues, terminaux, conteneurs)
- Commerce international maritime
- Événements et salons maritimes professionnels

CONTEXTE SIPORTS:
- Plateforme pour salon maritime professionnel
- Gestion des exposants, visiteurs, partenaires
- Systèmes de matching d'affaires
- Forfaits et packages événementiels
- Networking et rendez-vous B2B

STYLE DE COMMUNICATION:
- Professionnel mais accessible
- Expertise technique précise
- Conseils pratiques et actionnables
- Support multilingue (détection automatique)
- Ton amical et serviable

CAPACITÉS SPÉCIALES:
- Recommandations personnalisées basées sur le profil utilisateur
- Analyse des besoins business maritimes
- Suggestions de partenaires potentiels
- Informations en temps réel sur le salon
- Assistance pour navigation dans la plateforme SIPORTS

INSTRUCTIONS:
- Toujours rester dans le contexte maritime/portuaire
- Proposer des actions concrètes quand possible
- Utiliser des emojis maritimes appropriés (⚓ 🚢 🌊 ⛵ 🏢 📊)
- Fournir des réponses structurées avec des points d'action
- Être proactif dans les suggestions d'amélioration

Si une question n'est pas liée au maritime, redirige poliment vers le contexte SIPORTS.
"""

        # Initialiser la base de données
        self.init_database()
    
    def init_database(self):
        """Initialiser les tables pour le chatbot"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Table des sessions de chat
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id TEXT PRIMARY KEY,
                user_id INTEGER,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                language TEXT DEFAULT 'fr',
                context TEXT DEFAULT '{}',
                message_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        # Table des messages de chat
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                user_id INTEGER,
                message TEXT NOT NULL,
                response TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message_type TEXT DEFAULT 'text',
                language TEXT DEFAULT 'fr',
                context TEXT DEFAULT '{}',
                sentiment_score REAL DEFAULT 0.0,
                intent TEXT,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        # Table des intents détectés pour machine learning
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_intents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                intent TEXT,
                confidence REAL,
                context TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
            )
        """)
        
        # Table des feedbacks pour amélioration continue
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                message_id TEXT,
                rating INTEGER CHECK(rating >= 1 AND rating <= 5),
                feedback_text TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(id),
                FOREIGN KEY (message_id) REFERENCES chat_messages(id)
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info("✅ Base de données chatbot initialisée")
    
    def create_session(self, user_id: Optional[int] = None, language: str = "fr") -> str:
        """Créer une nouvelle session de chat"""
        session_id = str(uuid.uuid4())
        
        # Créer l'instance LlmChat avec Claude
        llm_chat = LlmChat(
            api_key=self.claude_api_key,
            session_id=session_id,
            system_message=self.maritime_system_prompt
        ).with_model("anthropic", "claude-sonnet-4-20250514").with_max_tokens(4096)
        
        self.active_sessions[session_id] = llm_chat
        
        # Sauvegarder en base
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO chat_sessions (id, user_id, language, context)
            VALUES (?, ?, ?, ?)
        """, (session_id, user_id, language, json.dumps({})))
        
        conn.commit()
        conn.close()
        
        logger.info(f"💬 Nouvelle session chat créée: {session_id}")
        return session_id
    
    async def send_message(self, session_id: str, message: str, user_id: Optional[int] = None, 
                          message_type: str = "text", language: str = "fr") -> Dict[str, Any]:
        """Envoyer un message au chatbot et récupérer la réponse"""
        try:
            # Récupérer l'instance LlmChat
            if session_id not in self.active_sessions:
                # Recréer la session si elle n'existe pas
                self.active_sessions[session_id] = LlmChat(
                    api_key=self.claude_api_key,
                    session_id=session_id,
                    system_message=self.maritime_system_prompt
                ).with_model("anthropic", "claude-sonnet-4-20250514").with_max_tokens(4096)
            
            llm_chat = self.active_sessions[session_id]
            
            # Enrichir le message avec le contexte utilisateur
            enriched_message = await self.enrich_message_with_context(message, user_id, session_id)
            
            # Envoyer le message à Claude
            user_message = UserMessage(text=enriched_message)
            response = await llm_chat.send_message(user_message)
            
            # Analyser le sentiment et l'intent
            sentiment_score = await self.analyze_sentiment(message)
            intent = await self.detect_intent(message)
            
            # Sauvegarder le message et la réponse
            message_id = str(uuid.uuid4())
            await self.save_message(
                message_id, session_id, user_id, message, response, 
                message_type, language, sentiment_score, intent
            )
            
            # Mettre à jour l'activité de la session
            await self.update_session_activity(session_id)
            
            return {
                "message_id": message_id,
                "session_id": session_id,
                "response": response,
                "sentiment_score": sentiment_score,
                "intent": intent,
                "timestamp": datetime.utcnow().isoformat(),
                "suggestions": await self.generate_suggestions(response, user_id),
                "quick_replies": await self.generate_quick_replies(intent, language)
            }
            
        except Exception as e:
            logger.error(f"❌ Erreur chatbot: {e}")
            return {
                "error": "Désolé, je rencontre un problème technique. Veuillez réessayer.",
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def enrich_message_with_context(self, message: str, user_id: Optional[int], session_id: str) -> str:
        """Enrichir le message avec le contexte utilisateur et session"""
        context_parts = [message]
        
        if user_id:
            # Récupérer le profil utilisateur
            user_context = await self.get_user_context(user_id)
            if user_context:
                context_parts.append(f"\n\nCONTEXTE UTILISATEUR: {user_context}")
        
        # Récupérer l'historique récent de la session
        session_history = await self.get_session_context(session_id)
        if session_history:
            context_parts.append(f"\n\nHISTORIQUE RÉCENT: {session_history}")
        
        return "\n".join(context_parts)
    
    async def get_user_context(self, user_id: int) -> str:
        """Récupérer le contexte utilisateur pour personnaliser les réponses"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT user_type, visitor_package, partnership_package, company, 
                       first_name, last_name, profile_completion
                FROM users WHERE id = ?
            """, (user_id,))
            
            user = cursor.fetchone()
            conn.close()
            
            if not user:
                return ""
            
            context_info = []
            context_info.append(f"Utilisateur: {user['first_name']} {user['last_name']}")
            context_info.append(f"Type: {user['user_type']}")
            
            if user['company']:
                context_info.append(f"Entreprise: {user['company']}")
            
            if user['visitor_package']:
                context_info.append(f"Package visiteur: {user['visitor_package']}")
            
            if user['partnership_package']:
                context_info.append(f"Package partenaire: {user['partnership_package']}")
            
            context_info.append(f"Profil complété à {user['profile_completion']}%")
            
            return " | ".join(context_info)
            
        except Exception as e:
            logger.error(f"Erreur contexte utilisateur: {e}")
            return ""
    
    async def get_session_context(self, session_id: str, limit: int = 3) -> str:
        """Récupérer l'historique récent de la session"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT message, response
                FROM chat_messages 
                WHERE session_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (session_id, limit))
            
            messages = cursor.fetchall()
            conn.close()
            
            if not messages:
                return ""
            
            history = []
            for msg in reversed(messages):  # Remettre dans l'ordre chronologique
                history.append(f"User: {msg[0][:100]}...")
                history.append(f"AI: {msg[1][:100]}...")
            
            return " | ".join(history[-4:])  # Derniers 2 échanges
            
        except Exception as e:
            logger.error(f"Erreur historique session: {e}")
            return ""
    
    async def analyze_sentiment(self, message: str) -> float:
        """Analyser le sentiment du message (simple heuristique)"""
        positive_words = ['merci', 'excellent', 'parfait', 'super', 'génial', 'bravo', 'formidable']
        negative_words = ['problème', 'erreur', 'bug', 'cassé', 'mauvais', 'nul', 'horrible']
        neutral_words = ['question', 'comment', 'pourquoi', 'quand', 'où', 'info']
        
        message_lower = message.lower()
        
        score = 0.0
        word_count = len(message.split())
        
        for word in positive_words:
            if word in message_lower:
                score += 1.0
        
        for word in negative_words:
            if word in message_lower:
                score -= 1.0
        
        # Normaliser entre -1 et 1
        if word_count > 0:
            score = max(-1.0, min(1.0, score / word_count * 10))
        
        return score
    
    async def detect_intent(self, message: str) -> Optional[str]:
        """Détecter l'intention du message"""
        message_lower = message.lower()
        
        intent_patterns = {
            "info_packages": ["forfait", "package", "prix", "tarif", "coût"],
            "info_event": ["salon", "événement", "programme", "horaires", "lieu"],
            "networking": ["rdv", "rendez-vous", "rencontre", "contact", "réseau"],
            "technical_help": ["problème", "bug", "aide", "support", "erreur"],
            "matching": ["partenaire", "match", "recherche", "recommandation"],
            "navigation": ["comment", "où", "naviguer", "utiliser", "fonctionner"],
            "greeting": ["bonjour", "salut", "hello", "bonsoir", "coucou"],
            "goodbye": ["au revoir", "bye", "salut", "à bientôt"]
        }
        
        for intent, keywords in intent_patterns.items():
            if any(keyword in message_lower for keyword in keywords):
                return intent
        
        return "general_inquiry"
    
    async def generate_suggestions(self, response: str, user_id: Optional[int]) -> List[str]:
        """Générer des suggestions d'actions basées sur la réponse"""
        suggestions = []
        
        response_lower = response.lower()
        
        if "forfait" in response_lower or "package" in response_lower:
            suggestions.extend([
                "Voir tous les forfaits disponibles",
                "Comparer les packages",
                "Obtenir une recommandation personnalisée"
            ])
        
        if "rdv" in response_lower or "rendez-vous" in response_lower:
            suggestions.extend([
                "Consulter mon calendrier",
                "Prendre un nouveau rendez-vous",
                "Voir mes contacts"
            ])
        
        if "matching" in response_lower or "partenaire" in response_lower:
            suggestions.extend([
                "Lancer une recherche de partenaires",
                "Voir mes matches en attente",
                "Optimiser mon profil"
            ])
        
        # Suggestions générales
        if not suggestions:
            suggestions = [
                "Explorer la plateforme SIPORTS",
                "Voir les nouveautés du salon",
                "Contacter le support"
            ]
        
        return suggestions[:3]  # Maximum 3 suggestions
    
    async def generate_quick_replies(self, intent: Optional[str], language: str) -> List[str]:
        """Générer des réponses rapides basées sur l'intention"""
        quick_replies = {
            "fr": {
                "info_packages": ["📦 Voir les forfaits", "💰 Comparer les prix", "⭐ Recommandations"],
                "networking": ["📅 Mon calendrier", "🤝 Nouveaux contacts", "📧 Mes messages"],
                "matching": ["🔍 Rechercher", "💡 Mes matches", "⚙️ Profil"],
                "technical_help": ["🆘 Support", "📚 Guide d'aide", "🔧 Dépannage"],
                "greeting": ["👋 Commencer", "📋 Aide", "🎯 Objectifs"],
                "general_inquiry": ["ℹ️ Plus d'infos", "📞 Contacter", "🔄 Autre question"]
            }
        }
        
        lang_replies = quick_replies.get(language, quick_replies["fr"])
        return lang_replies.get(intent, lang_replies["general_inquiry"])
    
    async def save_message(self, message_id: str, session_id: str, user_id: Optional[int], 
                          message: str, response: str, message_type: str, language: str,
                          sentiment_score: float, intent: Optional[str]):
        """Sauvegarder le message et la réponse en base"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO chat_messages 
                (id, session_id, user_id, message, response, message_type, 
                 language, sentiment_score, intent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (message_id, session_id, user_id, message, response, 
                  message_type, language, sentiment_score, intent))
            
            # Sauvegarder l'intent avec confiance
            if intent:
                cursor.execute("""
                    INSERT INTO chat_intents (session_id, intent, confidence, context)
                    VALUES (?, ?, ?, ?)
                """, (session_id, intent, 0.8, json.dumps({"message_length": len(message)})))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Erreur sauvegarde message: {e}")
    
    async def update_session_activity(self, session_id: str):
        """Mettre à jour l'activité de la session"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE chat_sessions 
                SET last_activity = CURRENT_TIMESTAMP,
                    message_count = message_count + 1
                WHERE id = ?
            """, (session_id,))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Erreur mise à jour session: {e}")
    
    def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """Récupérer les statistiques d'une session"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM chat_sessions WHERE id = ?
            """, (session_id,))
            
            session = cursor.fetchone()
            
            if not session:
                return {}
            
            cursor.execute("""
                SELECT COUNT(*) as message_count,
                       AVG(sentiment_score) as avg_sentiment,
                       COUNT(DISTINCT intent) as unique_intents
                FROM chat_messages 
                WHERE session_id = ?
            """, (session_id,))
            
            stats = cursor.fetchone()
            conn.close()
            
            return {
                "session_id": session_id,
                "started_at": session["started_at"],
                "last_activity": session["last_activity"],
                "language": session["language"],
                "status": session["status"],
                "message_count": stats["message_count"] or 0,
                "avg_sentiment": round(stats["avg_sentiment"] or 0.0, 2),
                "unique_intents": stats["unique_intents"] or 0
            }
            
        except Exception as e:
            logger.error(f"Erreur stats session: {e}")
            return {}
    
    def end_session(self, session_id: str):
        """Terminer une session de chat"""
        try:
            # Retirer de la mémoire active
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
            
            # Marquer comme terminée en base
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE chat_sessions 
                SET status = 'ended', last_activity = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (session_id,))
            
            conn.commit()
            conn.close()
            
            logger.info(f"🔚 Session terminée: {session_id}")
            
        except Exception as e:
            logger.error(f"Erreur fin session: {e}")

# Instance globale du chatbot (à initialiser avec la clé API)
maritime_chatbot: Optional[MaritimeChatBot] = None

def initialize_chatbot(claude_api_key: str):
    """Initialiser le chatbot global"""
    global maritime_chatbot
    maritime_chatbot = MaritimeChatBot(claude_api_key)
    logger.info("🤖 Chatbot maritime SIPORTS initialisé avec Claude !")

def get_chatbot() -> MaritimeChatBot:
    """Récupérer l'instance du chatbot"""
    if maritime_chatbot is None:
        raise HTTPException(status_code=500, detail="Chatbot non initialisé - clé API manquante")
    return maritime_chatbot