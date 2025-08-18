# 🚢 SIPORTS v2.0 Backend - Railway Ready avec PostgreSQL

Backend FastAPI optimisé pour Railway avec base de données PostgreSQL.

## 🚀 Configuration Production

- ✅ **PostgreSQL Database** - Base persistante Railway
- ✅ **Gunicorn + Uvicorn Workers** - Performance optimale
- ✅ **Health Checks** - Monitoring intégré
- ✅ **Auto-migration SQLite ↔ PostgreSQL** - Développement flexible
- ✅ **JWT Authentication** - Sécurité renforcée
- ✅ **CORS configuré** - Frontend integration
- ✅ **Chatbot IA** - Service intelligent

## 🔧 Setup Railway

### 1. Ajouter PostgreSQL
```
Railway → Add Service → Database → PostgreSQL
```

### 2. Variables d'environnement
```env
ENVIRONMENT=production
LOG_LEVEL=INFO
JWT_SECRET_KEY=your-secure-jwt-key
DATABASE_URL=postgresql://user:password@host:port/database  # Auto-généré par Railway
```

### 3. Deploy automatique
Le backend détecte automatiquement PostgreSQL et s'adapte !

## 📊 Endpoints principaux

- `GET /` - API status
- `GET /health` - Health check avec DB validation + type de DB
- `POST /api/auth/login` - Authentication
- `GET /api/visitor-packages` - Packages
- `POST /api/chatbot/chat` - AI Chat

## 🧪 Tests rapides

```bash
curl https://your-app.up.railway.app/
curl https://your-app.up.railway.app/health
```

### Réponse health check avec PostgreSQL :
```json
{
  "status": "healthy",
  "database_type": "postgresql",
  "checks": {"database": "healthy"}
}
```

**🎯 Compatible SQLite (dev) + PostgreSQL (production) - Déployé avec Railway 🚄**