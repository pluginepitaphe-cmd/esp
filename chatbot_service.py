"""
SIPORTS v2.0 AI Chatbot Service
Service pour chatbot IA gratuit avec support Ollama et simulation pour développement
"""

import time
import random
import logging
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from enum import Enum

logger = logging.getLogger(__name__)

class ContextType(str, Enum):
    GENERAL = "general"
    EXHIBITOR = "exhibitor" 
    PACKAGE = "package"
    EVENT = "event"

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000, description="Message utilisateur sur événements maritimes")
    context_type: ContextType = Field(default=ContextType.GENERAL, description="Type de contexte pour le chatbot")
    user_id: Optional[str] = Field(default=None, description="Identifiant utilisateur pour suivi session")
    session_id: Optional[str] = Field(default=None, description="ID de session de conversation")

class ChatResponse(BaseModel):
    response: str = Field(..., description="Réponse IA générée")
    response_type: str = Field(..., description="Type de réponse fournie")
    confidence: Optional[float] = Field(default=None, description="Score de confiance de la réponse")
    suggested_actions: List[str] = Field(default=[], description="Actions suggérées de suivi")
    session_id: str = Field(..., description="ID de session")
    timestamp: float = Field(default_factory=time.time, description="Timestamp de la réponse")

class SiportsAIService:
    """Service IA pour SIPORTS v2.0 avec support Ollama et mode simulation"""
    
    def __init__(self, mock_mode: bool = True, model_name: str = "tinyllama:1.1b"):
        self.mock_mode = mock_mode
        self.model_name = model_name
        self.conversation_history: Dict[str, List[Dict[str, str]]] = {}
        
        # Templates de contexte pour réponses spécialisées
        self.context_templates = {
            ContextType.GENERAL: """Tu es un assistant expert pour SIPORTS v2.0, spécialisé dans les événements maritimes. 
            Fournis des informations précises sur les événements maritimes, les horaires, et l'assistance générale.
            Répond en français de manière professionnelle et concise.""",
            
            ContextType.EXHIBITOR: """Tu es un conseiller expert en événements maritimes. 
            Aide les utilisateurs à trouver des exposants et fournisseurs pertinents selon leurs intérêts.
            Focus sur les technologies maritimes, shipping, logistics, équipements navals.
            Répond en français avec des recommandations précises.""",
            
            ContextType.PACKAGE: """Tu es un consultant expert en forfaits événements maritimes. 
            Recommande les forfaits appropriés: Free (gratuit), Basic (150€), Premium (350€), VIP (750€).
            Explique les avantages de chaque forfait selon les besoins. Répond en français.""",
            
            ContextType.EVENT: """Tu es un spécialiste des informations événements maritimes. 
            Fournis des détails sur les événements spécifiques, planning, activités, conférences.
            Répond en français avec des informations pratiques et utiles."""
        }
        
        # Base de connaissances SIPORTS pour réponses contextuelles
        self.siports_knowledge = {
            "forfaits": {
                "Free": {"prix": "Gratuit", "rdv_b2b": 0, "avantages": ["Accès exposition", "Conférences publiques", "App mobile"]},
                "Basic": {"prix": "150€", "rdv_b2b": 2, "avantages": ["Expositions", "Conférences", "2 RDV B2B", "Pause café"]},
                "Premium": {"prix": "350€", "rdv_b2b": 5, "avantages": ["Ateliers spécialisés", "Déjeuners", "5 RDV B2B", "Accès VIP"]},
                "VIP": {"prix": "750€", "rdv_b2b": "illimité", "avantages": ["Soirée gala", "Conférences exclusives", "Conciergerie", "Transferts"]}
            },
            "exposants_types": [
                "Technologies maritimes", "Équipements navals", "Logistics et supply chain", 
                "Green shipping", "Smart ports", "Cybersécurité maritime", "Fintech maritime"
            ],
            "événements": [
                "Conférences techniques", "Ateliers innovation", "Sessions networking", 
                "Démos technologiques", "Tables rondes", "Soirées de gala"
            ]
        }

    def get_session_id(self, user_id: str = None) -> str:
        """Génère ou récupère un ID de session"""
        if user_id:
            return f"session_{user_id}_{int(time.time())}"
        return f"session_anonymous_{int(time.time())}"

    async def generate_response_mock(self, message: str, context_type: ContextType, session_id: str) -> str:
        """Génère une réponse simulée intelligente basée sur le contexte"""
        
        message_lower = message.lower()
        
        # Réponses contextuelles basées sur le type
        if context_type == ContextType.PACKAGE:
            if any(word in message_lower for word in ["forfait", "package", "prix", "tarif"]):
                return self._generate_package_response(message_lower)
        
        elif context_type == ContextType.EXHIBITOR:
            if any(word in message_lower for word in ["exposant", "entreprise", "technologie", "fournisseur"]):
                return self._generate_exhibitor_response(message_lower)
        
        elif context_type == ContextType.EVENT:
            if any(word in message_lower for word in ["événement", "conférence", "horaire", "programme"]):
                return self._generate_event_response(message_lower)
        
        # Réponse générale par défaut
        return self._generate_general_response(message_lower)

    def _generate_package_response(self, message: str) -> str:
        """Génère réponse sur les forfaits"""
        if "gratuit" in message or "free" in message:
            return "Le forfait Free est gratuit et inclut l'accès à l'exposition, aux conférences publiques et à l'app mobile. Idéal pour découvrir l'événement."
        
        if "premium" in message or "vip" in message:
            return "Le forfait Premium (350€) est notre plus populaire avec 5 RDV B2B, ateliers spécialisés, déjeuners networking et accès VIP. Le VIP (750€) offre RDV illimités, soirée gala et service conciergerie."
        
        if "basic" in message:
            return "Le forfait Basic (150€) comprend l'accès expositions, conférences principales, 2 RDV B2B garantis et pauses café networking. Parfait pour 1 jour d'événement."
        
        return "Nous proposons 4 forfaits: Free (gratuit), Basic (150€), Premium (350€) et VIP (750€). Chacun offre des avantages différents selon vos besoins. Que recherchez-vous précisément?"

    def _generate_exhibitor_response(self, message: str) -> str:
        """Génère réponse sur les exposants"""
        if any(word in message for word in ["technologie", "tech", "innovation"]):
            return "Nos exposants technologiques incluent des leaders en smart ports, IoT maritime, blockchain pour logistics, et solutions d'automatisation portuaire. Souhaitez-vous des recommandations spécifiques?"
        
        if any(word in message for word in ["shipping", "transport", "logistique"]):
            return "Pour le shipping et logistique, nous avons des exposants spécialisés en supply chain maritime, optimisation de routes, tracking cargo, et solutions green shipping. Je peux vous orienter selon votre secteur."
        
        if any(word in message for word in ["équipement", "naval", "bateau"]):
            return "Les équipementiers navals présents proposent systèmes de navigation, équipements de sécurité, solutions de maintenance prédictive et technologies offshore. Quel type d'équipement vous intéresse?"
        
        return "Nos 200+ exposants couvrent toute la chaîne maritime: technologies, équipements, services, financement. Pouvez-vous préciser votre domaine d'intérêt pour des recommandations ciblées?"

    def _generate_event_response(self, message: str) -> str:
        """Génère réponse sur les événements"""
        if any(word in message for word in ["horaire", "programme", "planning"]):
            return "L'événement se déroule sur 3 jours avec conférences (9h-17h), ateliers techniques (14h-16h), sessions networking (17h-19h) et soirée gala (20h). Voulez-vous le programme détaillé d'une journée?"
        
        if any(word in message for word in ["conférence", "présentation", "speaker"]):
            return "Nous avons 50+ conférences couvrant décarbonation maritime, digitalisation des ports, nouvelles réglementations et innovations technologiques. Les speakers incluent des experts internationaux. Quel thème vous intéresse?"
        
        if "networking" in message or "rencontre" in message:
            return "Les opportunités networking incluent: pauses café (10h et 15h), déjeuners thématiques (12h), cocktail exposants (17h) et soirée gala (20h). Idéal pour créer des connexions professionnelles."
        
        return "L'événement SIPORTS propose conférences, ateliers, networking et expo sur 3 jours. Programme complet avec 200+ exposants et 50+ conférences. Que souhaitez-vous savoir spécifiquement?"

    def _generate_general_response(self, message: str) -> str:
        """Génère réponse générale"""
        greetings = ["bonjour", "hello", "salut", "bonsoir"]
        if any(greeting in message for greeting in greetings):
            return "Bonjour ! Je suis l'assistant IA SIPORTS v2.0. Je peux vous aider avec les informations événements, recommandations exposants, forfaits et planning. Comment puis-je vous assister ?"
        
        if any(word in message for word in ["aide", "help", "assistance"]):
            return "Je peux vous assister sur: 📋 Informations événements, 🏢 Recommandations exposants, 💳 Forfaits et tarifs, 📅 Programme et horaires. Sur quoi souhaitez-vous être accompagné ?"
        
        if "siports" in message or "événement" in message:
            return "SIPORTS est le salon maritime de référence avec 200+ exposants, 50+ conférences et 3 jours d'innovations. Technologies, networking, business opportunities vous attendent. Que voulez-vous découvrir ?"
        
        return "Je suis là pour vous aider avec toutes vos questions sur SIPORTS v2.0. Événements, exposants, forfaits, planning - n'hésitez pas à me demander ! 😊"

    def _generate_suggested_actions(self, context_type: ContextType, message: str) -> List[str]:
        """Génère actions suggérées selon le contexte"""
        actions_map = {
            ContextType.GENERAL: ["📋 Voir programme événement", "🏢 Parcourir exposants", "💳 Découvrir forfaits", "📞 Contact support"],
            ContextType.EXHIBITOR: ["🔍 Voir détails exposant", "📅 Planifier rendez-vous", "📧 Obtenir contact", "🔗 Voir partenariats"],
            ContextType.PACKAGE: ["⚖️ Comparer forfaits", "💰 Voir tarifs", "🎟️ S'inscrire maintenant", "📞 Devis personnalisé"],
            ContextType.EVENT: ["📅 Ajouter au calendrier", "⏰ Définir rappels", "📤 Partager événement", "🎫 Réserver place"]
        }
        return actions_map.get(context_type, [])

    async def generate_response(self, request: ChatRequest) -> ChatResponse:
        """Point d'entrée principal pour génération de réponse"""
        try:
            session_id = request.session_id or self.get_session_id(request.user_id)
            
            # Gestion historique conversation
            if session_id not in self.conversation_history:
                self.conversation_history[session_id] = []
            
            # Ajouter message utilisateur à l'historique
            self.conversation_history[session_id].append({
                "role": "user",
                "content": request.message,
                "timestamp": time.time()
            })
            
            # Limiter historique à 20 derniers échanges
            if len(self.conversation_history[session_id]) > 20:
                self.conversation_history[session_id] = self.conversation_history[session_id][-20:]

            if self.mock_mode:
                # Mode simulation pour développement
                ai_response = await self.generate_response_mock(request.message, request.context_type, session_id)
                confidence = round(random.uniform(0.8, 0.95), 2)
            else:
                # Mode Ollama (à implémenter en production)
                ai_response = await self.generate_response_ollama(request, session_id)
                confidence = 0.85

            # Ajouter réponse IA à l'historique
            self.conversation_history[session_id].append({
                "role": "assistant", 
                "content": ai_response,
                "timestamp": time.time()
            })
            
            # Générer actions suggérées
            suggested_actions = self._generate_suggested_actions(request.context_type, request.message)
            
            return ChatResponse(
                response=ai_response,
                response_type=request.context_type.value if hasattr(request.context_type, 'value') else request.context_type,
                confidence=confidence,
                suggested_actions=suggested_actions,
                session_id=session_id
            )
            
        except Exception as e:
            logger.error(f"Erreur génération réponse chatbot: {str(e)}")
            return ChatResponse(
                response="Désolé, je rencontre une difficulté technique. Pouvez-vous reformuler votre question ?",
                response_type=request.context_type.value if hasattr(request.context_type, 'value') else request.context_type,
                confidence=0.0,
                suggested_actions=["🔄 Réessayer", "📞 Contact support"],
                session_id=session_id or "error_session"
            )

    async def generate_response_ollama(self, request: ChatRequest, session_id: str) -> str:
        """Génération réponse avec Ollama (implémentation future)"""
        # TODO: Implémenter l'intégration Ollama réelle
        try:
            import ollama
            
            # Préparer le contexte système
            system_prompt = self.context_templates[request.context_type]
            
            # Préparer l'historique pour le contexte
            messages = [{"role": "system", "content": system_prompt}]
            
            # Ajouter historique récent (5 derniers échanges)
            recent_history = self.conversation_history[session_id][-10:] if session_id in self.conversation_history else []
            for msg in recent_history:
                messages.append({"role": msg["role"], "content": msg["content"]})
            
            # Générer réponse avec Ollama
            response = ollama.chat(
                model=self.model_name,
                messages=messages,
                options={
                    "temperature": 0.7,
                    "max_tokens": 500,
                    "top_p": 0.9
                }
            )
            
            return response['message']['content']
            
        except ImportError:
            logger.warning("Ollama non disponible, utilisation du mode mock")
            return await self.generate_response_mock(request.message, request.context_type, session_id)
        except Exception as e:
            logger.error(f"Erreur Ollama: {str(e)}")
            return await self.generate_response_mock(request.message, request.context_type, session_id)

    def get_conversation_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Récupère l'historique de conversation pour une session"""
        return self.conversation_history.get(session_id, [])

    def clear_conversation_history(self, session_id: str) -> bool:
        """Efface l'historique d'une session"""
        if session_id in self.conversation_history:
            del self.conversation_history[session_id]
            return True
        return False

# Instance globale du service chatbot
siports_ai_service = SiportsAIService(mock_mode=True)