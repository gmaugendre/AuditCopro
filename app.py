import streamlit as st
import os
import shutil
import pandas as pd
import io
import json
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from google import genai
from google.genai import types
from thefuzz import fuzz
from scipy.optimize import linear_sum_assignment
from fpdf import FPDF
from pypdf import PdfWriter

# --- CONFIGURATION ---
st.set_page_config(page_title="Audit Compta Automatisé", layout="wide")

UPLOAD_DIR = "storage_compta"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

API_KEY = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=API_KEY, http_options={'api_version': 'v1beta'})

GEMINI_MODEL="gemini-2.5-flash"
#GEMINI_MODEL="gemini-2.0-flash"

##############################################################################################################################################################"

# --- FONCTIONS UTILITAIRES ---

def save_uploaded_file(uploaded_file, sub):
    p = Path(UPLOAD_DIR) / sub / uploaded_file.name
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f: f.write(uploaded_file.getbuffer())
    return p

# FONCTION DE FUSION DES RELEVES DE COMPTE PDF
def merge_pdfs(uploaded_files, sub):
    merger = PdfWriter()
    for pdf in uploaded_files:
        merger.append(pdf)
    
    output_path = Path(UPLOAD_DIR) / sub / "releves_fusionnes.pdf"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "wb") as f:
        merger.write(f)
    return output_path

##############################################################################################################################################################"

# --- FONCTIONS D'EXTRACTION ---

def convert_pdf_to_excel(pdf_path):
    try:
        prompt = """Agis comme un extracteur de données comptables de haute précision.
        Analyse ce fichier PDF et extrais chaque écriture comptable.
        Continuité : Identifie les tableaux scindés par des sauts de page et fusionne-les de manière fluide sans répéter les en-têtes.
        Extrait ces données dans excel en retenant uniquement les colonnes: NUMERO_COMPTE | NOM_COMPTE | DATE | PIECE | CODE_JOURNAL_(JNL) | CONTREPARTIE | LIBELLE | DEBIT | CREDIT.
        Si les colonnes NUMERO_COMPTE ou NOM_COMPTE ne sont pas indiquées pour chaque écriture dans le fichier source, va chercher les informations dans l'en-tête de chaque bloc.
        Si les colonnes CODE_JOURNAL (JNL) ou CONTREPARTIE ne sont pas disponibles, laisse les vides.
        Mets les en-têtes des colonnes NUMERO_COMPTE | NOM_COMPTE | DATE | PIECE | CODE_JOURNAL_(JNL) | CONTREPARTIE | LIBELLE | DEBIT | CREDIT en première ligne.
        Les dates doivent être au format date JJ/MM/AAAA.
        Nettoyage : Supprime les symboles monétaires (€, $) et les séparateurs de milliers. Le séparateur de décimales doient être un point. Les nombres doivent être au format numérique.
        Les écritures dont le libellé est 'Report' ou 'Report a nouveau' ou 'A nouveau' en début de bloc doivent être identifiées le cas échéant par AN dans la colonne CODE JOURNAL (JNL).
        Réponds EXCLUSIVEMENT sous forme d'une liste JSON d'objets avec les clés suivantes : NUMERO_COMPTE, NOM_COMPTE, DATE (JJ/MM/AAAA), PIECE, CODE_JOURNAL, CONTREPARTIE, LIBELLE, DEBIT, CREDIT. N'affiche aucun texte avant ou après le JSON."""

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                prompt
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        df = pd.DataFrame(json.loads(response.text))
        if 'DEBIT' in df.columns: df['DEBIT'] = pd.to_numeric(df['DEBIT'], errors='coerce').fillna(0)
        if 'CREDIT' in df.columns: df['CREDIT'] = pd.to_numeric(df['CREDIT'], errors='coerce').fillna(0)
        if 'DATE' in df.columns: df['DATE'] = pd.to_datetime(df['DATE'], dayfirst=True, errors='coerce')
        return df
        
    except Exception as e:
        if "429" in str(e) or "quota" in str(e).lower():
            st.error("🚨 QUOTA ÉPUISÉ : Le moteur IA a atteint sa limite quotidienne lors du traitement du Grand livre. Réessayez demain.")
        else:
            st.error(f"❌ Erreur technique : {e}")
    return pd.DataFrame()

def extract_releve_data(pdf_path):
    try:
        prompt = """Agis comme un extracteur de données comptables de haute précision. Analyse ce fichier PDF et extrais chaque transaction.
                    Structure des colonnes : DATE | LIBELLE | DEBIT | CREDIT. Affiche ces 4 mots d'en-tête de colonnes dans la première ligne uniquement.
                    Règles impératives :
                    Continuité : Identifie les tableaux scindés par des sauts de page et fusionne-les de manière fluide sans répéter les en-têtes. N'affiche aucun ligne de total.
                    Analyse de position : Identifie rigoureusement la position horizontale des colonnes. Si une valeur est sous l'en-tête DEBIT, elle doit rester dans la colonne DEBIT. Utilise tes capacités de vision pour tracer une ligne verticale imaginaire entre la colonne DEBIT et CREDIT: ne mélange jamais les deux.
                    Une ligne ne peut avoir qu'un seul montant (soit débit, soit crédit). L'autre doit être 0.00.
                    Nettoyage : Supprime les symboles monétaires (€, $) et les séparateurs de milliers. Les nombres doivent être au format 1234.56.
                    Format de date : Utilise le format JJ/MM/AAAA.
                    SORTIE : Réponds EXCLUSIVEMENT sous forme d'une liste JSON d'objets avec ces clés :
                    DATE (JJ/MM/AAAA), LIBELLE, DEBIT, CREDIT.
                    N'affiche aucun texte avant ou après le JSON."""

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                prompt
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        df = pd.DataFrame(json.loads(response.text))
        if 'DEBIT' in df.columns: df['DEBIT'] = pd.to_numeric(df['DEBIT'], errors='coerce').fillna(0)
        if 'CREDIT' in df.columns: df['CREDIT'] = pd.to_numeric(df['CREDIT'], errors='coerce').fillna(0)
        if 'DATE' in df.columns: df['DATE'] = pd.to_datetime(df['DATE'], dayfirst=True, errors='coerce')
        return df

    except Exception as e:
        if "429" in str(e) or "quota" in str(e).lower():
            st.error("🚨 QUOTA ÉPUISÉ : Le moteur IA a atteint sa limite quotidienne lors du traitement des relevés bancaires. Réessayez demain.")
        else:
            st.error(f"❌ Erreur technique : {e}")
    return pd.DataFrame()



def extraire_grille_tarifaire_universelle(uploaded_file):
    """
    Extrait les tarifs du contrat et les range dans une grille fixe, 
    indépendamment de la formulation utilisée par le syndic.
    En sortie, on a des tarifs du type:
    JSON
    "forfait_annuel": 15000.0,
    "vacation_horaire": 165.0,
    "mise_en_demeure": 45.0,
    "relance_simple": 0.0,
    "etat_date": 380.0,
    "opposition_mutation": 120.0,
    "mise_en_demeure_tiers": 45.0,
    "injonction_payer": 0.0,
    "reprise_compta_forfait": 0.0,
    "reprise_compta_lot": 0.0,
    "ag_supplementaire": 850.0,
    "copie_pv": 15.0
    """
    # Lecture des octets directement depuis la mémoire
    pdf_bytes = uploaded_file.read() 
    
    # Remise à zéro du pointeur (bonne pratique Streamlit si vous relisez le fichier plus tard)
    uploaded_file.seek(0)
    
    # Grille de référence (Clés fixes pour Python : Description pour l'IA)
    grille_reference = {
        "forfait_annuel": "Rémunération forfaitaire annuelle",
        "vacation_horaire": "Coût horaire pour prestations particulières (prorata du temps passé)",
        "mise_en_demeure": "Mise en demeure par lettre recommandée AR",
        "relance_simple": "Relance après mise en demeure",
        "etat_date": "Établissement de l'état daté (montant maximum)",
        "opposition_mutation": "Opposition sur mutation",
        "mise_en_demeure_tiers": "Mise en demeure d'un tiers par lettre recommandée AR",
        "injonction_payer": "Dépôt d'une requête en injonction de payer",
        "reprise_compta_forfait": "Reprise de comptabilité sur exercices antérieurs (forfait)",
        "reprise_compta_lot": "Reprise de comptabilité (par lot principal et par exercice)",
        "ag_supplementaire": "Assemblée générale supplémentaire (par lot, min. 800 € TTC)",
        "copie_pv": "Délivrance d'une copie certifiée conforme d'un PV d'AG"
    }

    prompt = f"""
    Agis comme un expert en audit de copropriété. Ton objectif est d'extraire les tarifs d'un contrat de syndic pour remplir une grille standardisée.
    
    VOICI LA GRILLE DE DESTINATION (Clé : Description du tarif à chercher) :
    {json.dumps(grille_reference, ensure_ascii=False, indent=2)}

    RÈGLES CRITIQUES :
    1. SYNONYMES : Le syndic peut utiliser des termes différents. Analyse le sens pour remplir la bonne clé (ex: "Honoraires de base" -> "forfait_annuel").
    2. MONTANTS : Extrais uniquement des nombres (float). Si un tarif est au forfait + au lot, extrais la part fixe pour le forfait.
    3. TVA : Extrais toujours le montant TTC. Si seul le HT est écrit, calcule TTC = HT * 1.20.
    4. ABSENCE : Si un tarif n'est pas mentionné ou si la prestation est gratuite/incluse, inscris 0.0.
    5. FORMAT : Retourne UNIQUEMENT un objet JSON dont les clés sont celles de ma grille.
    """

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                prompt
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json")
            )
        return json.loads(response.text)
    except Exception as e:
        if "429" in str(e) or "quota" in str(e).lower():
            st.error("🚨 QUOTA ÉPUISÉ : Le moteur IA a atteint sa limite quotidienne lors du traitement du contrat. Réessayez demain.")
        else:
            st.error(f"❌ Erreur technique : {e}")
        return {}


##############################################################################################################################################################"

# --- MOTEUR D'AUDIT ---

def generer_rapport_audit(df_gl, df_bank, df_contrat):
    r = [] 
    date_ref = df_gl['DATE'].max() if ('DATE' in df_gl.columns and not df_gl['DATE'].dropna().empty) else datetime.now()
    
    r.append("="*80)
    r.append(f"RAPPORT D'AUDIT COMPTABLE - GÉNÉRÉ LE {datetime.now().strftime('%d/%m/%Y')}")
    r.append(f"Période analysée jusqu'au : {date_ref.strftime('%d/%m/%Y')}")
    r.append("="*80 + "\n")

    # --- SECTION A : TROP-PAYÉS ---
    r.append("[SECTION A] ANALYSE DES TROP-PAYÉS")
    r.append("👉 Ce contrôle identifie les fournisseurs dont le solde est débiteur. Cela révèle des factures payées plusieurs fois")
    r.append("   ou des avoirs non récupérés, représentant une trésorerie perdue pour la copropriété.\n")
    if 'NUMERO_COMPTE' in df_gl.columns:
        df_401 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('401')].copy()
        if not df_401.empty:
            synthese_401 = df_401.groupby(['NUMERO_COMPTE', 'NOM_COMPTE']).agg({'DEBIT': 'sum', 'CREDIT': 'sum'}).reset_index()
            synthese_401['SOLDE'] = synthese_401['CREDIT'] - synthese_401['DEBIT']
            trop_payes = synthese_401[synthese_401['SOLDE'] < -1.00]
            if not trop_payes.empty:
                for _, row in trop_payes.iterrows():
                    r.append(f"   ❌ {row['NOM_COMPTE']} : {abs(row['SOLDE']):.2f}€ à récupérer.")
            else:
                r.append("   ✅ Aucun trop-payé détecté.")
        else:
            r.append("   ✅ Aucun fournisseur détecté.")
    else:
        r.append("   ⚠️ Données insuffisantes pour l'analyse des trop-payés.")

    # --- SECTION B : DOUBLONS ---
    r.append("\n" + "="*80)
    r.append("[SECTION B] ANALYSE DES DOUBLONS")
    r.append("👉 Recherche des écritures de charges identiques (montant et compte) sur la période.")
    r.append("   L'objectif est de détecter des saisies multiples d'une même facture.\n")
    if 'NUMERO_COMPTE' in df_gl.columns and 'DEBIT' in df_gl.columns:
        df_6 = df_gl[(df_gl['NUMERO_COMPTE'].astype(str).str.startswith('6')) & (df_gl['DEBIT'] > 0)]
        doublons = df_6[df_6.duplicated(subset=['DEBIT', 'NUMERO_COMPTE'], keep=False)]
        if not doublons.empty:
            r.append(f"   ❌ {len(doublons)//2} alertes de doublons potentiels identifiées.")
        else:
            r.append("   ✅ Aucun doublon détecté.")
    else:
        r.append("   ⚠️ Données insuffisantes pour l'analyse des doublons.")

    # --- SECTION C : IMPAYÉS FOURNISSEURS ---
    r.append("\n" + "="*80)
    r.append("[SECTION C] ANALYSE DES IMPAYÉS (> 3 MOIS)")
    r.append("👉 Liste les factures en attente de paiement depuis plus de 90 jours.")
    r.append("   Un volume élevé indique un risque de contentieux ou une rupture de trésorerie.\n")
    if 'NUMERO_COMPTE' in df_gl.columns:
        df_401 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('401')].copy()
        alertes_impayes = []
        for compte in df_401['NUMERO_COMPTE'].unique():
            sub = df_401[df_401['NUMERO_COMPTE'] == compte]
            if (sub['CREDIT'].sum() - sub['DEBIT'].sum()) > 1.00:
                factures = sub[sub['CREDIT'] > 0]
                for _, f in factures.iterrows():
                    if pd.notnull(f['DATE']):
                        delta_j = (date_ref - pd.to_datetime(f['DATE'])).total_seconds() / 86400
                        if delta_j > 90:
                            alertes_impayes.append(f)
        if alertes_impayes:
            for a in alertes_impayes[:10]:
                r.append(f"   ⚠️ {a['NOM_COMPTE'][:20]:<20} | {a['DATE'].strftime('%d/%m/%Y')} | {a['CREDIT']:>8.2f}€")
        else:
            r.append("   ✅ Aucune facture ancienne en attente.")
    else:
        r.append("   ⚠️ Données insuffisantes pour l'analyse des impayés.")

    # --- SECTION D : REJETS BANCAIRES ---
    r.append("\n" + "="*80)
    r.append("[SECTION D] ANALYSE DES REJETS BANCAIRES")
    r.append("👉 Vérifie que chaque incident bancaire (impayé copropriétaire) a bien été régularisé en comptabilité.")
    r.append("   Un rejet non imputé signifie que le compte d'un copropriétaire est artificiellement créditeur.\n")
    
    DAYS_WINDOW = 30
    def fuzzy_check_rejet(libelle):
        if not isinstance(libelle, str): return False
        keywords = ['rejet', 'impaye', 'sans provision', 'non paye']
        return any(kw in libelle.lower() for kw in keywords)

    if 'LIBELLE' in df_bank.columns and 'NUMERO_COMPTE' in df_gl.columns and 'DEBIT' in df_gl.columns:
        rejets_detectes = df_bank[df_bank['LIBELLE'].apply(fuzzy_check_rejet) & (df_bank['DEBIT'] > 0)]
        df_450 = df_gl[(df_gl['NUMERO_COMPTE'].astype(str).str.startswith('450')) & (df_gl['DEBIT'] > 0)]
        nb_alertes_rejets = 0
        for _, rej in rejets_detectes.iterrows():
            if pd.notnull(rej['DATE']):
                match = df_450[
                    (abs(df_450['DEBIT'] - rej['DEBIT']) < 0.05) & 
                    (df_450['DATE'] >= rej['DATE']) & 
                    (df_450['DATE'] <= rej['DATE'] + timedelta(days=DAYS_WINDOW))
                ]
            else:
                match = df_450[abs(df_450['DEBIT'] - rej['DEBIT']) < 0.05]
            if match.empty:
                d_rej = rej['DATE'].strftime('%d/%m/%Y') if pd.notnull(rej['DATE']) else "N/A"
                r.append(f"   ❌ REJET NON RÉPERCUTÉ : {d_rej} | {rej['DEBIT']:.2f}€ | {rej['LIBELLE']}")
                nb_alertes_rejets += 1
        if nb_alertes_rejets == 0:
            r.append("   ✅ Tous les rejets bancaires ont été imputés.")
    else:
        r.append("   ⚠️ Données insuffisantes pour l'analyse des rejets bancaires.")

    # --- SECTION E : COMPTES D'ATTENTE (471 & 472) ---
    r.append("\n" + "="*80)
    r.append("[SECTION E] ANALYSE DES COMPTES D'ATTENTE (471 & 472)")
    r.append("👉 Ces comptes doivent être soldés à la clôture. Un solde persistant indique des fonds non identifiés")
    r.append("   ou des dépenses sans justificatifs, souvent révélateurs d'une négligence administrative.\n")
    if 'NUMERO_COMPTE' in df_gl.columns:
        for racine in ['471', '472']:
            df_attente = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith(racine)].copy()
            if not df_attente.empty:
                solde = df_attente['CREDIT'].sum() - df_attente['DEBIT'].sum()
                if abs(solde) > 5.00:
                    type_solde = "CRÉDITEUR" if solde > 0 else "DÉBITEUR"
                    r.append(f"   ⚠️ COMPTE {racine} : Solde significatif de {abs(solde):.2f}€ ({type_solde})")
                    if solde > 0:
                        r.append("      👉 Solde Créditeur élevé : La copropriété détient une dette (sommes non affectées).")
                    else:
                        r.append("      👉 Solde Débiteur élevé : Fonds avancés sans justification de dépense.")
                else:
                    r.append(f"   ✅ COMPTE {racine} : Le compte est globalement soldé.")

                if 'DATE' in df_attente.columns:
                    df_attente['DATE'] = pd.to_datetime(df_attente['DATE'], errors='coerce')
                    ecritures_anciennes = df_attente[(date_ref - df_attente['DATE']).dt.days > 180]
                    if not ecritures_anciennes.empty:
                        r.append(f"   ❌ NÉGLIGENCE (Compte {racine}) : {len(ecritures_anciennes)} ligne(s) datent de plus de 6 mois.")
                        for _, row in ecritures_anciennes.iterrows():
                            d_str = row['DATE'].strftime('%d/%m/%Y') if pd.notnull(row['DATE']) else "N/A"
                            r.append(f"      - {d_str} | {max(row['DEBIT'], row['CREDIT']):.2f}€ | {row['LIBELLE']}")
            else:
                r.append(f"   ✅ COMPTE {racine} : Aucun mouvement détecté.")
    else:
        r.append("   ⚠️ Données insuffisantes pour l'analyse des comptes d'attente.")

    # --- SECTION F : ANALYSE DES TIERS (461 & 462) ---
    r.append("\n" + "="*80)
    r.append("[SECTION F] ANALYSE DES TIERS ET LITIGES (461 & 462)")
    r.append("👉 Surveille les créances sur tiers et les dossiers au contentieux.")
    r.append("   Un solde créditeur ici est anormal et indique souvent une erreur d'affectation de paiement.\n")
    if 'NUMERO_COMPTE' in df_gl.columns:
        for racine in ['461', '462']:
            df_tiers = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith(racine)].copy()
            if not df_tiers.empty:
                solde_net = df_tiers['DEBIT'].sum() - df_tiers['CREDIT'].sum()
                if racine == '461':
                    r.append("👉 Compte 461 — Débiteurs divers : doit normalement être débiteur (sommes à recevoir).")
                    if solde_net < -1.00:
                        r.append(f"   ❌ ANOMALIE : Solde CRÉDITEUR de {abs(solde_net):.2f}€ (illogique pour ce compte).")
                    else:
                        r.append(f"   ℹ️ Solde actuel : {solde_net:.2f}€ (Débiteur).")
                    
                    if 'DATE' in df_tiers.columns:
                        df_tiers['DATE'] = pd.to_datetime(df_tiers['DATE'], errors='coerce')
                        anciennes_461 = df_tiers[(date_ref - df_tiers['DATE']).dt.days > 365]
                        if not anciennes_461.empty:
                            r.append(f"   ⚠️ ATTENTION : {len(anciennes_461)} créance(s) de plus d'un an.")

                elif racine == '462':
                    r.append("👉 Compte 462 — Copropriétaires douteux : créances transférées pour recouvrement.")
                    if solde_net < -1.00:
                        r.append(f"   ❌ ANOMALIE : Solde CRÉDITEUR de {abs(solde_net):.2f}€ (paiement mal affecté ?).")
                    else:
                        r.append(f"   ℹ️ Encours contentieux total : {solde_net:.2f}€.")
                    
                    if 'DATE' in df_tiers.columns:
                        df_tiers['DATE'] = pd.to_datetime(df_tiers['DATE'], errors='coerce')
                        anciennes_462 = df_tiers[(date_ref - df_tiers['DATE']).dt.days > 730]
                        if not anciennes_462.empty:
                            r.append(f"   ⚠️ ATTENTION : {len(anciennes_462)} dossier(s) en litige depuis plus de 2 ans.")
            else:
                r.append(f"   ✅ COMPTE {racine} : Aucun mouvement détecté.")
    else:
        r.append("   ⚠️ Données insuffisantes pour l'analyse des tiers.")

    # --- SECTION G : RAPPROCHEMENT BANCAIRE COMPLET ---
    r.append("\n" + "="*80)
    r.append("[SECTION G] RAPPROCHEMENT BANCAIRE (SORTIES ET ENTRÉES)")
    r.append("👉 Compare ligne à ligne la banque et la comptabilité. Détecte les flux financiers sans")
    r.append("   justification comptable et les délais anormaux de traitement.\n")

    def rapprochement_cote(df_gl_sub, df_bk_sub, label_gl, label_bk, col_gl, col_bk):
        if not df_gl_sub.empty and not df_bk_sub.empty:
            n, m = len(df_gl_sub), len(df_bk_sub)
            cost_matrix = np.zeros((n, m))
            gl_v = df_gl_sub[[col_gl, 'DATE', 'LIBELLE']].values
            bk_v = df_bk_sub[[col_bk, 'DATE', 'LIBELLE']].values

            for i in range(n):
                for j in range(m):
                    diff_m = abs(gl_v[i, 0] - bk_v[j, 0])
                    diff_j = abs((gl_v[i, 1] - bk_v[j, 1]).days) if pd.notnull(gl_v[i,1]) and pd.notnull(bk_v[j,1]) else 999
                    cost_matrix[i, j] = 1_000_000 if diff_m > 0.01 else diff_j

            row_ind, col_ind = linear_sum_assignment(cost_matrix)
            
            gl_m_set = set()
            bk_m_set = set()
            ecarts_significatifs = []

            for i, j in zip(row_ind, col_ind):
                if cost_matrix[i, j] < 1_000_000:
                    gl_m_set.add(i)
                    bk_m_set.add(j)
                    delai = (gl_v[i, 1] - bk_v[j, 1]).days
                    if abs(delai) > 30:
                        ecarts_significatifs.append({
                            'date_gl': gl_v[i, 1],
                            'date_bk': bk_v[j, 1],
                            'montant': gl_v[i, 0],
                            'libelle': gl_v[i, 2],
                            'delai': delai
                        })

            for j in range(m):
                if j not in bk_m_set:
                    bk_val, bk_date = bk_v[j, 0], bk_v[j, 1]
                    if pd.notnull(bk_date):
                        cand_idx = [i for i in range(n) if i not in gl_m_set and pd.notnull(gl_v[i, 1]) and pd.to_datetime(gl_v[i, 1]).date() == pd.to_datetime(bk_date).date()]
                        if cand_idx and abs(df_gl_sub.iloc[cand_idx][col_gl].sum() - bk_val) < 0.01:
                            gl_m_set.update(cand_idx)
                            bk_m_set.add(j)

            for i in range(n):
                if i not in gl_m_set:
                    gl_val, gl_date = gl_v[i, 0], gl_v[i, 1]
                    if pd.notnull(gl_date):
                        cand_idx = [j for j in range(m) if j not in bk_m_set and pd.notnull(bk_v[j, 1]) and pd.to_datetime(bk_v[j, 1]).date() == pd.to_datetime(gl_date).date()]
                        if cand_idx and abs(df_bk_sub.iloc[cand_idx][col_bk].sum() - gl_val) < 0.01:
                            bk_m_set.update(cand_idx)
                            gl_m_set.add(i)

            if ecarts_significatifs:
                r.append(f"   ⏳ ALERTES DÉLAIS (> 30 JOURS) :")
                for e in sorted(ecarts_significatifs, key=lambda x: x['date_gl']):
                    signe = "AVANCE" if e['delai'] > 0 else "RETARD"
                    r.append(f"      - {e['montant']:>8.2f}€ | {e['libelle'][:20]:<20} | {abs(e['delai'])}j de {signe} (C: {e['date_gl'].strftime('%d/%m')} / B: {e['date_bk'].strftime('%d/%m')})")

            abs_bk = df_gl_sub.iloc[[i for i in range(n) if i not in gl_m_set]].sort_values('DATE')
            if not abs_bk.empty:
                r.append(f"   ❌ {label_bk.upper()} ABSENT (Ligne Compta non trouvée en Banque) :")
                for _, row in abs_bk.iterrows():
                    d = row['DATE'].strftime('%d/%m/%Y') if pd.notnull(row['DATE']) else "N/A"
                    r.append(f"      - {d} | {row[col_gl]:>8.2f}€ | {row['LIBELLE']}")

            abs_gl = df_bk_sub.iloc[[j for j in range(m) if j not in bk_m_set]].sort_values('DATE')
            if not abs_gl.empty:
                r.append(f"   ❌ {label_gl.upper()} ABSENT (Ligne Banque non trouvée en Compta) :")
                for _, row in abs_gl.iterrows():
                    d = row['DATE'].strftime('%d/%m/%Y') if pd.notnull(row['DATE']) else "N/A"
                    r.append(f"      - {d} | {row[col_bk]:>8.2f}€ | {row['LIBELLE']}")
        else:
            r.append(f"   ℹ️ Données insuffisantes pour les {label_gl.lower()}.")

    if 'NUMERO_COMPTE' in df_gl.columns and 'DEBIT' in df_gl.columns and 'CREDIT' in df_gl.columns and 'DATE' in df_gl.columns and 'LIBELLE' in df_gl.columns:
        df_gl_dt = df_gl.copy()
        df_gl_dt['DATE'] = pd.to_datetime(df_gl_dt['DATE'], errors='coerce')
        df_bk_dt = df_bank.copy()
        if 'DATE' in df_bk_dt.columns:
            df_bk_dt['DATE'] = pd.to_datetime(df_bk_dt['DATE'], errors='coerce')

        r.append("\n--- ANALYSE DES DÉCAISSEMENTS ---")
        gl_s = df_gl_dt[df_gl_dt['NUMERO_COMPTE'].astype(str).str.startswith('512') & (df_gl_dt['CREDIT'] > 0)].copy()
        bk_s = df_bk_dt[df_bk_dt['DEBIT'] > 0].copy() if 'DEBIT' in df_bk_dt.columns else pd.DataFrame()
        rapprochement_cote(gl_s, bk_s, "Compta (512)", "Banque", "CREDIT", "DEBIT")

        r.append("\n--- ANALYSE DES ENCAISSEMENTS ---")
        gl_e = df_gl_dt[df_gl_dt['NUMERO_COMPTE'].astype(str).str.startswith('512') & (df_gl_dt['DEBIT'] > 0)].copy()
        bk_e = df_bk_dt[df_bk_dt['CREDIT'] > 0].copy() if 'CREDIT' in df_bk_dt.columns else pd.DataFrame()
        rapprochement_cote(gl_e, bk_e, "Compta (512)", "Banque", "DEBIT", "CREDIT")
    else:
        r.append("   ⚠️ Données insuffisantes pour le rapprochement bancaire.")

    # --- SECTION H : FOURNISSEURS SUSPECTS (OCCASIONNELS) ---
    r.append("\n" + "="*80)
    r.append("[SECTION H] ANALYSE DES FOURNISSEURS OCCASIONNELS (< 4 écritures/an)")
    r.append("👉 Isole les prestataires avec très peu d'activité. En copropriété, cela peut révéler")
    r.append("   des factures de complaisance ou des dépenses ponctuelles non mises en concurrence.\n")
    if 'NUMERO_COMPTE' in df_gl.columns:
        df_401 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('401')].copy()
        if not df_401.empty and 'CREDIT' in df_401.columns:
            df_factures = df_401[df_401['CREDIT'] > 0]
            if not df_factures.empty:
                stats_fournisseurs = df_factures.groupby(['NUMERO_COMPTE', 'NOM_COMPTE']).agg({
                    'CREDIT': ['count', 'sum', 'max'],
                    'DATE': 'max'
                }).reset_index()
                
                stats_fournisseurs.columns = ['COMPTE', 'NOM', 'NB_FACTURES', 'TOTAL_ANNUEL', 'MONTANT_MAX', 'DERNIERE_DATE']
                suspects = stats_fournisseurs[stats_fournisseurs['NB_FACTURES'] <= 3].sort_values('TOTAL_ANNUEL', ascending=False)
                
                if not suspects.empty:
                    r.append(f"   ⚠️ {len(suspects)} fournisseur(s) à vérifier (peu d'activité annuelle) :")
                    for _, s in suspects.iterrows():
                        d_str = s['DERNIERE_DATE'].strftime('%d/%m/%Y') if pd.notnull(s['DERNIERE_DATE']) else "Inconnue"
                        r.append(f"      - {s['NOM'][:25]:<25} | {s['NB_FACTURES']} fact. | Total: {s['TOTAL_ANNUEL']:>8.2f}€ | Max: {s['MONTANT_MAX']:>8.2f}€ (Dernière: {d_str})")
                else:
                    r.append("   ✅ Aucun fournisseur occasionnel détecté.")
            else:
                r.append("   ✅ Aucun mouvement de facture (crédit) détecté pour les fournisseurs.")
        else:
            r.append("   ✅ Aucun fournisseur détecté.")
    else:
        r.append("   ⚠️ Données insuffisantes pour l'analyse des fournisseurs.")

    # --- SECTION I : CONTRÔLE DU FONDS DE TRAVAUX (LOI ALUR) ---
    r.append("\n" + "="*80)
    r.append("[SECTION I] CONTRÔLE DU FONDS DE TRAVAUX (COMPTES 105 & 502)")
    r.append("👉 Vérifie que les sommes appelées pour les travaux (105) sont réellement transférées")
    r.append("   sur le compte d'épargne (502). Un écart indique une utilisation illégale de ces fonds pour la gestion courante.\n")
    if 'NUMERO_COMPTE' in df_gl.columns:
        df_105 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('105')].copy()
        df_502 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('502')].copy()
        
        solde_theorique_travaux = df_105['CREDIT'].sum() - df_105['DEBIT'].sum() if not df_105.empty else 0
        solde_reel_placement = df_502['DEBIT'].sum() - df_502['CREDIT'].sum() if not df_502.empty else 0
        
        r.append(f"   💰 Réserves travaux appelées (105) : {solde_theorique_travaux:.2f}€")
        r.append(f"   🏦 Placement réel sur Livret (502)  : {solde_reel_placement:.2f}€")
        
        ecart_placement = solde_theorique_travaux - solde_reel_placement
        if ecart_placement > 1.00:
            r.append(f"   ❌ ANOMALIE : {ecart_placement:.2f}€ n'ont pas été virés sur le compte d'épargne !")
            r.append(f"      👉 Le syndic utilise cet argent pour financer le fonctionnement courant.")
        elif ecart_placement < -100.00:
            r.append(f"   ℹ️ Sur-placement : {abs(ecart_placement):.2f}€ de plus que prévu sur le Livret.")
        else:
            r.append("   ✅ Parfaite cohérence : Le fonds de travaux est intégralement placé.")
    else:
        r.append("   ⚠️ Données insuffisantes pour l'analyse du fonds de travaux.")

    r.append("\n" + "="*80 + "\nFIN DU RAPPORT")
    return "\n".join(r)


    # --- SECTION J : CONTRÔLE DES FRAIS FACTURES PAR LE SYNDIC PAR RAPPORT AU CONTRAT DU SYNDIC (comptes 621 et 622) ---
    r.append("\n" + "="*80)
    r.append("[SECTION J] CONTRÔLE DES FRAIS DE SYNDIC")
    r.append("👉 Comparaison des honoraires facturés (comptes 621, 622) avec les tarifs du contrat.")
    r.append("   L'objectif est de détecter des surfacturations ou des prestations indûment facturées.\n")

    if 'NUMERO_COMPTE' in df_gl.columns and 'DEBIT' in df_gl.columns and 'LIBELLE' in df_gl.columns:
        
        # 1. Filtrage des honoraires sur df_gl
        df_honoraires = df_gl[(df_gl['NUMERO_COMPTE'].astype(str).str.startswith(('621', '622'))) & (df_gl['DEBIT'] > 0)].copy()
        
        # 2. Mapping pour la logique floue (Libellé cible : Clé dans ton dictionnaire df_contrat)
        mapping_audit = {
            "Mise en demeure": "mise_en_demeure",
            "Relance": "relance_simple",
            "Etat daté": "etat_date",
            "Opposition mutation": "opposition_mutation",
            "Vacation horaire": "vacation_horaire",
            "Copie PV": "copie_pv",
            "Assemblée Générale": "ag_supplementaire",
            "Injonction de payer": "injonction_payer"
        }

        anomalies_detectees = 0
        
        if not df_honoraires.empty:
            for _, row in df_honoraires.iterrows():
                libelle_brut = str(row['LIBELLE'])
                montant_paye = float(row['DEBIT'])
                date_val = row['DATE']
                date_str = date_val.strftime('%d/%m/%Y') if pd.notnull(date_val) else "N/A"
                
                trouve = False

                for nom_cible, cle_contrat in mapping_audit.items():
                    # Comparaison floue entre le libellé de l'écriture et le nom cible
                    if fuzz.partial_ratio(nom_cible.lower(), libelle_brut.lower()) > 80:
                        trouve = True
                        # Extraction du tarif depuis le dictionnaire df_contrat
                        tarif_contrat = df_contrat.get(cle_contrat, 0.0)

                        if tarif_contrat == 0:
                            r.append(f"   ❌ ALERTE : '{libelle_brut}' ({date_str}) facturé {montant_paye}€.")
                            r.append(f"      👉 Prestation non tarifée ou incluse dans le forfait selon le contrat.")
                            anomalies_detectees += 1
                        elif montant_paye > (tarif_contrat + 0.10):
                            r.append(f"   ❌ SURFACTURATION : '{libelle_brut}' ({date_str}) facturé {montant_paye}€.")
                            r.append(f"      👉 Le tarif contractuel est de {tarif_contrat}€ TTC.")
                            anomalies_detectees += 1
                        break # Sortie de la boucle mapping si on a trouvé un match
            
            if anomalies_detectees == 0:
                r.append("   ✅ Aucun dépassement de tarif ou frais indu identifié sur les prestations particulières.")
        else:
            r.append("   ℹ️ Aucune écriture trouvée dans les comptes 621/622.")
    else:
        r.append("   ⚠️ Colonnes nécessaires manquantes dans 'df_gl' pour cette analyse.")


##############################################################################################################################################################"

# --- INTERFACE STREAMLIT ---

col_texte, col_logo = st.columns([6, 1], vertical_alignment="center")

with col_texte:
    st.title("Assistant d'analyse des comptes de copropriété")
    st.subheader("Conseils syndicaux : reprenez le contrôle !")
with col_logo:
    # On affiche le logo à droite
    # use_container_width permet au logo de s'adapter à la petite colonne
    st.image("Logo.png", width=300) # use_container_width=True
st.markdown("---")
# st.title("Assistant d'analyse des comptes de copropriété")
# st.subheader("Conseils syndicaux : reprenez le contrôle !")
# st.markdown("---")


col1, col2 = st.columns(2)
with col1:
    st.markdown("### 1. Import des documents (exercice N-1)")
    gl_file = st.file_uploader("Grand livre (pdf)", type="pdf")
    releves_files = st.file_uploader("12 relevés bancaires mensuels (pdf)", type="pdf", accept_multiple_files=True)
    contrat_file = st.file_uploader("Contrat du syndic (pdf)", type="pdf")

# --- Saisie des 12 relevés de compte ---
nb_fichiers = len(releves_files) if releves_files else 0
if 0 < nb_fichiers < 12:
    st.warning(f"⏳ Il manque {12 - nb_fichiers} relevé(s).")
elif nb_fichiers > 12:
    st.error(f"🚫 Trop de fichiers : vous avez importé {nb_fichiers} relevés au lieu de 12.")

# --- Sécurité anti-doublons (noms et tailles) ---
fichiers_doublons = False
if releves_files:
    noms = [f.name for f in releves_files]
    tailles = [f.size for f in releves_files]
    if len(noms) != len(set(noms)):
        st.error("⚠️ Doublon détecté : certains fichiers portent le même nom.")
        fichiers_doublons = True
    elif len(tailles) != len(set(tailles)):
        st.error("⚠️ Doublon détecté : certains fichiers ont la même taille (contenu probablement identique).")
        fichiers_doublons = True

with col2:
    st.markdown("### 2. Traitement & analyse")
    documents_prets = gl_file is not None and contrat_file is not None and releves_files is not None and len(releves_files) == 1 and not fichiers_doublons  #################### REMETTTRE 12 APRES DEBOGAGE
    if documents_prets:
        st.markdown(" ")
        st.markdown(" ")
        if st.button("Générer le rapport d'analyse", type="primary"):
            with st.status("🚀 Initialisation de l'audit...", expanded=True) as status:
                progress_bar = st.progress(10)
                
                # Extraction
                status.update(label="📄 Lecture du Grand livre...", expanded=True)
                gl_path = save_uploaded_file(gl_file, "gl")
                gl_df = convert_pdf_to_excel(gl_path)
                progress_bar.progress(30)
                
                # On fusionne les relevés de banque pdf
                merged_bank_path = merge_pdfs(releves_files, "rb")
                
                # Un seul appel IA pour tous les relevés bancaires agrégés
                status.update(label=f"🏦 Lecture des relevés bancaires", expanded=True)
                bank_df = extract_releve_data(merged_bank_path)
                progress_bar.progress(50)

                # Un appel IA pour lire le contrat
                status.update(label="⚖️ Analyse du contrat du syndic...", expanded=True)
                contrat_df = extraire_grille_tarifaire_universelle(contrat_file)
                progress_bar.progress(70)
        

                # AUDIT COMPTABLE
                status.update(label="🔍 Analyse approfondie des écritures comptables...", expanded=True)
                rapport_final = generer_rapport_audit(gl_df, bank_df, contrat_df)
                progress_bar.progress(80)
    
        
                # --- GÉNÉRATION DU RAPPORT DE SYNTHÈSE PAR L'IA ---
                status.update(label="✍️ Rédaction de la synthèse...")
                
                instructions_gemini = """Ton objectif est de rédiger un rapport de synthèse basé sur les données d'analyse brute fournies. 
                Tu dois impérativement être pédagogue, diplomate, prudent et humble (car des erreurs d'analyse ne sont pas exclues).
                Contenu: Insère tous les détails disponibles dans des tableaux propres: dates, montants, libellés etc.
                La cible : Les copropriétaires et les membres du conseil syndical qui n'ont pas de connaissances en comptabilité.
                Les contraintes de rédaction:
                Ton & Style : Utilise un français soutenu mais accessible. Évite le jargon technique sans l'expliquer.
                Diplomatie : Ne sois jamais agressif envers le syndic. Remplace les termes accusateurs par des termes neutres.
                Prudence légale : Utilise le conditionnel si nécessaire.
                Structure du rapport : Introduction, Sections thématiques, Conclusion.
                Et ajoute en annexes de ce rapport de synthèse un strict copier coller du rapport technique (c'est à dire des données d'analyse brute fournies).
                """
    
                prompt_complet = f"{instructions_gemini}\n\n--- DONNÉES D'ANALYSE BRUTE ---\n{rapport_final}"
            
                # --- GÉNÉRATION DU PDF VIA FPDF2 ---
                try:
                    response = client.models.generate_content(
                        model=GEMINI_MODEL,
                        contents=prompt_complet
                    )
                    synthese_texte = response.text
                
                    pdf = FPDF()
                    pdf.add_page()
                    pdf.set_auto_page_break(auto=True, margin=15)
                    # Police standard (fpdf2 gère mieux l'UTF-8 par défaut)
                    pdf.set_font("helvetica", "B", 16)
                    pdf.cell(0, 10, "Rapport de Synthèse de Copropriété", new_x="LMARGIN", new_y="NEXT", align='C')
                    pdf.ln(5)
        
                    # Nettoyage du texte pour éviter les erreurs d'encodage communes
                    # fpdf2 supporte mieux l'euro, mais on sécurise les apostrophes
                    texte_final = synthese_texte.replace('’', "'").replace('€', ' Euros')
                    
                    # Utilisation de write_html pour interpréter le gras (**) de Gemini
                    # fpdf2 convertit automatiquement le Markdown simple en HTML interne
                    pdf.set_font("helvetica", size=11)
                    
                    # On utilise le rendu Markdown de fpdf2
                    # Si 'markdown=True' a échoué dans multi_cell, c'est souvent qu'il faut 
                    # passer par la méthode dédiée aux textes longs :
                    pdf.multi_cell(0, 6, texte_final, markdown=True) 
                
                    pdf_output = pdf.output() # fpdf2 renvoie des bytes par défaut
                   
                    progress_bar.progress(100)
                    st.success("Analyse terminée.")
                    
                    st.download_button(
                        label="📥 Télécharger le rapport de synthèse (pdf)",
                        data=pdf_output,
                        file_name="Rapport_Synthese.pdf",
                        mime="application/pdf"
                    )
                except Exception as e:
                    st.error(f"❌ Erreur lors de la génération du pdf : {e}")
            
            
            
            # --- APERÇU DES DONNÉES CONVERTIES ---
            st.markdown("---")
            st.markdown("### 🛠️ Aperçu des conversions")
            
            with st.expander("Voir le Grand livre converti"):
                st.dataframe(gl_df)
                output_gl = io.BytesIO()
                with pd.ExcelWriter(output_gl, engine='openpyxl') as writer:
                    gl_df.to_excel(writer, index=False)
                st.download_button("💾 Télécharger GL en Excel", output_gl.getvalue(), "GL_converti.xlsx")

            with st.expander("Voir les relevés bancaires cumulés"):
                st.dataframe(bank_df)
                output_bk = io.BytesIO()
                with pd.ExcelWriter(output_bk, engine='openpyxl') as writer:
                    bank_df.to_excel(writer, index=False)
                st.download_button("💾 Télécharger Banque en Excel", output_bk.getvalue(), "Banque_convertie.xlsx")

            st.info("Toutes les données ont été supprimées.")
    else:
        st.markdown(" ")
        st.markdown(" ")
        st.info("Charger tous les documents avant de lancer le traitement ...")

st.markdown("---")
st.markdown(" ###### Ce projet part d'un simple constat : les comptes de copropriété sont souvent abscons pour les non-spécialistes, peuvent présenter des erreurs et manquer de transparence ; un grand livre peut comporter plus d'une centaine de pages d'écritures et les conseils syndicaux disposent de peu de moyens ou d'expertise pour assurer leur mission de contrôle des comptes.")
st.markdown(" ###### Il s'agit d'un prototype mis à disposition gratuitement ; nous vous invitons à nous partager en retour votre expérience en tant qu'utilisateur (pertinence de l'analyse, besoins complémentaires etc.), par écrit (gael_maugendre@hotmail.com) ou de vive voix (+33 6 14 29 80 29)).")
st.markdown("---")
st.caption(" ###### Disclaimer: Cette application est un assistant informatique conçue pour accompagner les Conseils syndicaux dans leur mission d'analyse et de contrôle des comptes de copropriété et identifier des points de vigilance. Elle ne se substitue en aucun cas au pouvoir de contrôle des membres du Conseil syndical ni à l'expertise comptable du Syndic. Les éléments présentés dans le rapport d’analyse sont des pistes d'investigation qui peuvent comporter des erreurs de lecture automatisée, d'interprétation technique et doivent faire l'objet d'une vérification contradictoire, de contrôles sur site et sur pièces ainsi que de discussions avec le teneur de comptes.")
st.caption(" ###### Protection des données: aucune donnée de votre copropriété n'est conservée ; tous les fichiers restent confidentiels et sont intégralement supprimés dés la fin du traitement ; aucun rapport n'est enregistré.")
st.caption(" ###### Tous droits réservés.")
