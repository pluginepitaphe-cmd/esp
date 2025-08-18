# Dockerfile pour SIPORTS Backend v2.0
FROM python:3.9-slim

# Variables d'environnement
ENV PORT=8000
ENV PYTHONPATH=/app
ENV DATABASE_URL=instance/siports_production.db
ENV JWT_SECRET_KEY=siports-jwt-production-2024

# Répertoire de travail
WORKDIR /app

# Copier les fichiers de requirements
COPY requirements.txt .

# Installer les dépendances
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source
COPY . .

# Créer le répertoire instance s'il n'existe pas
RUN mkdir -p instance

# Exposer le port
EXPOSE 8000

# Commande de démarrage
CMD ["python", "server.py"]