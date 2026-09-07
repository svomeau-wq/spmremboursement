# Boutique Meindjo — Service Client (version simple)

**3 fichiers, rien d'autre** : `app.py`, `templates/`, `requirements.txt` (+ `.env` à créer).
Aucune base de données, aucun fichier de données : tout arrive par email.

## Ce que fait le site

- Page d'accueil avec 3 options
- **Remboursement** en 2 pages : identité & commande → vérification → confirmation
- **Devis** en 2 pages : coordonnées → demande → confirmation
- **Résiliation** en 1 page
- À chaque demande : le client reçoit un email de confirmation avec sa référence,
  et vous recevez la copie complète (toutes les infos des 2 pages) sur OWNER_EMAIL.
- Pendant l'envoi : écran de chargement avec cercle.

## Installation (Visual Studio Code)

1. Créez le fichier `.env` (copiez `.env.example` — vos clés sont déjà dedans)
2. Dans le terminal :
   ```
   pip install -r requirements.txt
   python app.py
   ```
3. Ouvrez http://localhost:5000

C'est tout. Aucun compte MongoDB, aucun cloud.

## Rappel

- Les emails partent via votre compte Resend (RESEND_API_KEY)
- Les réponses des clients arrivent sur EMAIL_REPLY_TO
- Ne mettez jamais le fichier `.env` sur GitHub
