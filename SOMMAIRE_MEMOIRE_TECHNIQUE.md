é# Sommaire Memoire Technique

Ce document propose un plan de memoire technique adapte au projet KiVendTout.

## 1. Remerciements

## 2. Resume executif
- contexte du projet
- objectif general
- principaux resultats
- apports techniques et metier

## 3. Introduction
### 3.1 Contexte
### 3.2 Problematique
### 3.3 Objectifs du projet
### 3.4 Perimetre retenu
### 3.5 Methodologie
### 3.6 Organisation du document

## 4. Presentation du besoin metier
### 4.1 Enjeux e-commerce et fraude
### 4.2 Controle de majorite sur les produits sensibles
### 4.3 Supervision en temps reel
### 4.4 Contraintes fonctionnelles
### 4.5 Contraintes techniques et de securite

## 5. Analyse des exigences
### 5.1 Exigences du sujet 1
### 5.2 Exigences complementaires
### 5.3 Criteres de succes
### 5.4 Risques identifies

## 6. Architecture globale de la solution
### 6.1 Vue d'ensemble
### 6.2 Architecture applicative
### 6.3 Architecture data
### 6.4 Flux temps reel
### 6.5 Flux micro-batch
### 6.6 Data Lake bronze -> silver -> gold

## 7. Description des composants techniques
### 7.1 API FastAPI
### 7.2 Base PostgreSQL
### 7.3 Base MongoDB
### 7.4 Kafka et flux evenements
### 7.5 MinIO comme Data Lake
### 7.6 Dashboards de supervision
### 7.7 Scripts de validation et d'exploitation

## 8. Gouvernance et cycle de vie de la donnee
### 8.1 Sources de donnees
### 8.2 Structure des donnees
### 8.3 Historisation
### 8.4 Qualite de la donnee
### 8.5 Securisation et masquage
### 8.6 Retention et reutilisation

## 9. Logique metier implemente
### 9.1 Verification d'identite
### 9.2 Blocage des commandes mineur + produit Adult
### 9.3 Detection de fraude sur les paiements
### 9.4 Typologies d'alertes
### 9.5 Notifications et traitement des alertes
### 9.6 Episodes de fraude massive

## 10. Conception detaillee
### 10.1 Modelisation des donnees
### 10.2 Contrats API
### 10.3 Regles de scoring
### 10.4 KPI et indicateurs
### 10.5 Choix d'implementation

## 11. Implementation
### 11.1 Construction de l'API
### 11.2 Integration des controles identite
### 11.3 Mise en place des dashboards
### 11.4 Mise en place du pipeline Data Lake
### 11.5 Mise en place du micro-batch
### 11.6 Industrialisation des scripts

## 12. Securite, conformite et exploitation
### 12.1 RBAC et quotas API
### 12.2 Gestion des secrets
### 12.3 Securite du Data Lake
### 12.4 Journalisation et auditabilite
### 12.5 Reinitialisation et reprise

## 13. Strategie de tests et validation
### 13.1 Tests fonctionnels
### 13.2 Tests de charge
### 13.3 Tests de resilience
### 13.4 Validation du sujet 1
### 13.5 Validation de conformite complementaire
### 13.6 Resultats obtenus

## 14. Demonstration et use cases
### 14.1 Commande mineur bloquee
### 14.2 Commande majeur acceptee
### 14.3 Verification d'identite
### 14.4 Flux paiements realiste
### 14.5 Episode fraude commandes 3 minutes
### 14.6 Lecture des dashboards

## 15. Analyse des resultats
### 15.1 Valeur metier apportee
### 15.2 Lecture des KPI
### 15.3 Robustesse de la solution
### 15.4 Limites actuelles

## 16. Ameliorations et perspectives
### 16.1 Cycle paiement plus complet
### 16.2 Chargeback et fraude confirmee
### 16.3 Enrichissement du gold layer
### 16.4 Industrialisation CI/CD
### 16.5 Monitoring avance et drift

## 17. Conclusion

## 18. Annexes
### 18.1 Commandes d'installation
### 18.2 Commandes de verification
### 18.3 Exemples de payload API
### 18.4 Extraits de rapports
### 18.5 Captures des dashboards
### 18.6 Glossaire

## Conseils de redaction
- viser un document clair, factuel et oriente decisions techniques
- illustrer chaque grande partie par une figure ou un schema
- relier chaque composant a un besoin metier concret
- faire apparaitre les preuves de validation dans la partie tests
- conserver une separation nette entre fraude detectee, fraude confirmee et controle identite
