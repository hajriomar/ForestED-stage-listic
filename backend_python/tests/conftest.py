"""
Configuration pytest ForestED.

CRITIQUE : ce fichier est chargé par pytest AVANT tout module de test.
Il force la base de données de TEST, en écrasant toute variable
DATABASE_URL injectée par docker-compose ou l'environnement.

Sans cela, les fixtures drop_all/create_all des tests détruiraient
la vraie base (utilisateurs, permissions, API keys).
"""

import os

# Écrasement volontaire (pas de setdefault) : les tests ne doivent
# JAMAIS toucher la base réelle, quel que soit l'environnement.
os.environ["DATABASE_URL"] = "sqlite:///./test_forested.db"