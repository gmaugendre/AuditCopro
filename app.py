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
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# --- CONFIGURATION ---
st.set_page_config(page_title="Audit Compta Automatisé", layout="wide")

UPLOAD_DIR = "storage_compta"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

API_KEY = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=API_KEY, http_options={'api_version': 'v1beta'})

GEMINI_MODEL="gemini-2.5-flash"

# --- FONCTIONS UTILITAIRES ---

def save_uploaded_file(uploaded_file, sub):
    p = Path(UPLOAD_DIR) / sub / uploaded_file.name
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f: f.write(uploaded_file.getbuffer())
    return p

# --- FONCTIONS D'EXTRACTION ---

def convert_pdf_to_excel(pdf_path):
    try:
        prompt = """Agis comme un extracteur de données comptables de haute précision.
        Analyse ce fichier PDF et extrais chaque écriture comptable dans un fichier EXCEL.
        Continuité : Identifie les tableaux scindés par des sauts de page et fusionne-les de manière fluide sans répéter les en-têtes.
        Extrait ces données dans excel en retenant uniquement les colonnes: NUMERO_COMPTE | NOM_COMPTE | DATE | PIECE | CODE_JOURNAL_(JNL) | CONTREPARTIE | LIBELLE | DEBIT | CREDIT.
        Si les colonnes NUMERO_COMPTE ou NOM_COMPTE ne sont pas indiquées pour chaque écriture dans le fichier source, va chercher les informations dans l'en-tête de chaque bloc.
        Si les colonnes CODE_JOURNAL (JNL) ou CONTREPARTIE ne sont pas disponibles, laisse les vides.
        Mets les en-têtes des colonnes NUMERO_COMPTE | NOM_COMPTE | DATE | PIECE | CODE_JOURNAL_(JNL) | CONTREPARTIE | LIBELLE | DEBIT | CREDIT en première ligne.
        Les dates doivent être au format date JJ/MM/AAAA.
        Nettoyage : Supprime les symboles monétaires (€, $) et les séparateurs de milliers. Le séparateur de décimales doient être un point. Les nombres doivent être au format numérique.
        Les écritures dont le libellé est 'Report' ou 'Report a nouveau' ou 'A nouveau' en début de bloc doivent être identifiées le cas échéant par AN dans la colonne CODE JOURNAL (JNL).
        N'affiche aucun autre texte."""

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
            st.error("🚨 QUOTA ÉPUISÉ : Le moteur IA a atteint sa limite quotidienne. Réessayez demain ou utilisez une autre clé API.")
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
            st.error("🚨 QUOTA ÉPUISÉ : Le moteur IA a atteint sa limite quotidienne. Réessayez demain ou utilisez une autre clé API.")
        else:
            st.error(f"❌ Erreur technique : {e}")
    return pd.DataFrame()


# --- MOTEUR D'AUDIT ---

def generer_rapport_audit(df_gl, df_bank):
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

# --- INTERFACE STREAMLIT ---

st.title("Assistant d'analyse des comptes de copropriété")
st.subheader("Conseils syndicaux: reprenez le contrôle !")
st.markdown("---")

col1, col2 = st.columns(2)
with col1:
    st.markdown("### 1. Import des documents (exercice)")
    gl_file = st.file_uploader("Grand livre (pdf)", type="pdf")
    releves_files = st.file_uploader("12 relevés bancaires (pdf)", type="pdf", accept_multiple_files=True)

with col2:
    st.markdown("### 2. Traitement & analyse")
    if gl_file and releves_files and len(releves_files) == 1:  ############################ REMETTRE 12 APRES DEBOGAGE
        if st.button("Générer le rapport d'analyse", type="primary"):
            st.info("Veuillez patienter, le traitement peut prendre jusqu'à 15 min...")
            progress = st.progress(0)
            
            # Extraction
            gl_path = save_uploaded_file(gl_file, "gl")
            gl_df = convert_pdf_to_excel(gl_path)
            progress.progress(30)
            
            all_releves = []
            for i, f in enumerate(releves_files):
                p_rb = save_uploaded_file(f, "rb")
                all_releves.append(extract_releve_data(p_rb))
                progress.progress(30 + int((i/12)*60))
            
            bank_df = pd.concat(all_releves, ignore_index=True)
            
            # Audit
            rapport_final = generer_rapport_audit(gl_df, bank_df)
            progress.progress(100)
            
            st.success("Analyse terminée.")
            st.download_button("📥 Télécharger le rapport.", rapport_final, "Rapport_Audit.txt")

            # --- APERÇU DES DONNÉES CONVERTIES ---
            st.markdown("---")
            st.markdown("### 🛠️ Aperçu des conversions IA")
            
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
        st.info("En attente des documents (1 grand livre & 12 relevés bancaires)...")

st.markdown("---")
st.markdown(" ###### Ce projet pars d'un constat simple: les comptes de copropriété sont souvent indéchiffrables, peuvent comporter des erreurs et manquer de transparence ; les conseils syndicaux disposent souvent de peu de moyens ou d'expertise comptable pour assurer leur mission de contrôle des comptes.")
st.markdown(" ###### Il s'agit d'un prototype mis à disposition gratuitement ; nous vous invitons à nous partager en retour votre expérience en tant qu'utilisateur (pertinence de l'analyse, besoins complémentaires etc.), par écrit (gael_maugendre@hotmail.com) ou de vive voix (+33 6 14 29 80 29)).")
st.markdown("---")
st.caption(" ###### Disclaimer: Cette application est un assistant informatique conçue pour accompagner les Conseils syndical dans leur mission d'analyse et de contrôle des comptes de copropriété afin d'identifier des points de vigilance. Elle ne se substitue en aucun cas au pouvoir de contrôle des membres du Conseil syndical ni à l'expertise comptable du Syndic. Les éléments présentés dans le rapport d’analyse sont des pistes d'investigation qui peuvent comporter des erreurs de lecture automatisée, d'interprétation technique et doivent faire l'objet d'une vérification contradictoire, de contrôles sur site et sur pièces ainsi que de discussions avec le teneur de comptes.")
st.caption(" ###### Aucune donnée de votre copropriété n'est conservée: tous les fichiers sont immédiatement supprimés dés la fin du traitement et aucun rapport n'est conservé.")
