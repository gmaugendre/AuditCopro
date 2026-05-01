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

# Dépendances pour l'audit algorithmique
from thefuzz import fuzz
from scipy.optimize import linear_sum_assignment

# --- CONFIGURATION ---
st.set_page_config(page_title="Audit Compta Automatisé", layout="wide")

UPLOAD_DIR = "storage_compta"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

API_KEY = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=API_KEY, http_options={'api_version': 'v1beta'})

# --- FONCTIONS D'EXTRACTION ---

def convert_pdf_to_excel(pdf_path):
    """Extraction du Grand Livre via Gemini."""
    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                "Agis comme un extracteur de données spécialisé. Analyse ce PDF et extrais l'ensemble des transactions dans un format CSV strict."
"Structure des colonnes : 'Date', 'Libellé', 'Débit', 'Crédit'. Affiche ces 4 mots d'en-tête de colonnes dans la première ligne uniquement."
"Règles impératives :"
"Continuité : Identifie les tableaux scindés par des sauts de page et fusionne-les de manière fluide sans répéter les en-têtes. N'affiche aucun ligne de total."
" Analyse de position : Identifie rigoureusement la position horizontale des colonnes. Si une valeur est sous l'en-tête 'Débit', elle doit rester dans la colonne 'Débit'. Utilise tes capacités de vision pour tracer une ligne verticale imaginaire entre la colonne Débit et Crédit: ne mélange jamais les deux. Une transaction ne peut pas être à la fois un débit et un crédit. Si une cellule est vide, considère que le montant est 0.00."
"Nettoyage : Supprime les symboles monétaires (€, $), les séparateurs de milliers (espaces) et utilise la virgule comme séparateur CSV. Les nombres doivent être au format 1234.45."
"Format de date : Utilise le format JJ/MM/AAAA."
"Sortie : Réponds uniquement au format CSV pur (séparateur virgule). Aucun texte, aucune introduction, aucune conclusion."
            ]
        )
        return pd.DataFrame(json.loads(response.text.replace("```json", "").replace("```", "").strip()))
    except: return pd.DataFrame()

def extract_releve_data(pdf_path):
    """Extraction des Relevés via Gemini."""
    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        prompt = """Agis comme un extracteur de données comptables de haute précision.
Analyse ce fichier PDF et extrais chaque transaction.
"Structure des colonnes : DATE | LIBELLE | DEBIT | CREDIT. Affiche ces 4 mots d'en-tête de colonnes dans la première ligne uniquement."
"Règles impératives :"
"Continuité : Identifie les tableaux scindés par des sauts de page et fusionne-les de manière fluide sans répéter les en-têtes. N'affiche aucun ligne de total."
" Analyse de position : Identifie rigoureusement la position horizontale des colonnes. Si une valeur est sous l'en-tête DEBIT, elle doit rester dans la colonne DEBIT. Utilise tes capacités de vision pour tracer une ligne verticale imaginaire entre la colonne DEBIT et CREDIT: ne mélange jamais les deux. Une ligne ne peut avoir qu'un seul montant (soit débit, soit crédit). L'autre doit être 0.00."
"Nettoyage : Supprime les symboles monétaires (€, $) et les séparateurs de milliers. Les nombres doivent être au format 1234.56."
"Format de date : Utilise le format JJ/MM/AAAA."
SORTIE : Réponds EXCLUSIVEMENT sous forme d'une liste JSON d'objets avec ces clés :
DATE (JJ/MM/AAAA), LIBELLE, DEBIT, CREDIT.
N'affiche aucun texte avant ou après le JSON."""
        
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"), prompt]
        )
        return pd.DataFrame(json.loads(response.text.replace("```json", "").replace("```", "").strip()))
    except: return pd.DataFrame()

# --- MOTEUR D'AUDIT (SORTIE TEXTE) ---

def fuzzy_check_rejet(libelle):
    cibles = ["REJET", "IMPAYE", "ANNULATION", "REFUS", "PRLV REFUSE", "ECHEC", "SANS PROVISION"]
    libelle_clean = str(libelle).upper()
    for mot in cibles:
        if fuzz.partial_ratio(mot, libelle_clean) >= 90: return True
    return False

def generer_rapport_audit(df_gl, df_bank):
    """Effectue l'audit complet et compile tout dans une chaîne de caractères."""
    r = [] # Liste des lignes du rapport
    
    # Nettoyage des données
    for df in [df_gl, df_bank]:
        if not df.empty:
            df['DEBIT'] = pd.to_numeric(df['DEBIT'], errors='coerce').fillna(0)
            df['CREDIT'] = pd.to_numeric(df['CREDIT'], errors='coerce').fillna(0)
            df['DATE'] = pd.to_datetime(df['DATE'], dayfirst=True, errors='coerce')

    date_ref = df_gl['DATE'].max() if not df_gl['DATE'].dropna().empty else datetime.now()
    
    r.append("="*80)
    r.append(f"RAPPORT D'AUDIT COMPTABLE - GÉNÉRÉ LE {datetime.now().strftime('%d/%m/%Y')}")
    r.append(f"Période analysée jusqu'au : {date_ref.strftime('%d/%m/%Y')}")
    r.append("="*80 + "\n")

    # A. TROP-PAYÉS
    r.append("[SECTION A] ANALYSE DES TROP-PAYÉS")
    df_401 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('401')].copy()
    if not df_401.empty:
        synthese = df_401.groupby(['NUMERO_COMPTE', 'NOM_COMPTE']).agg({'DEBIT':'sum', 'CREDIT':'sum'}).reset_index()
        trop_payes = synthese[(synthese['CREDIT'] - synthese['DEBIT']) < -1.00]
        if not trop_payes.empty:
            for _, row in trop_payes.iterrows():
                r.append(f" - ❌ {row['NOM_COMPTE']} : {abs(row['CREDIT']-row['DEBIT']):.2f}€ à récupérer.")
        else: r.append(" - ✅ Aucun trop-payé détecté.")
    
    # B. DOUBLONS
    r.append("\n[SECTION B] ANALYSE DES DOUBLONS")
    df_6 = df_gl[(df_gl['NUMERO_COMPTE'].astype(str).str.startswith('6')) & (df_gl['DEBIT'] > 0)]
    doublons = df_6[df_6.duplicated(subset=['DEBIT', 'NUMERO_COMPTE'], keep=False)]
    if not doublons.empty:
        r.append(f" - ⚠️ {len(doublons)//2} alertes de doublons potentiels (montants identiques sur même compte).")
    else: r.append(" - ✅ Aucun doublon détecté.")

    # C. IMPAYÉS FOURNISSEURS (> 90j)
    r.append("\n[SECTION C] IMPAYÉS FOURNISSEURS (> 90 JOURS)")
    impayes = df_401[(df_401['CREDIT'] > 0) & (df_401['DATE'] < (date_ref - timedelta(days=90)))]
    if not impayes.empty:
        for _, row in impayes.head(15).iterrows():
            r.append(f" - ⚠️ {row['NOM_COMPTE'][:20]} | {row['DATE'].strftime('%d/%m/%Y')} | {row['CREDIT']:.2f}€")
    else: r.append(" - ✅ Aucune facture ancienne en attente.")

    # D. REJETS BANCAIRES
    r.append("\n[SECTION D] REJETS BANCAIRES NON RÉPERCUTÉS")
    rejets = df_bank[df_bank['LIBELLE'].apply(fuzzy_check_rejet) & (df_bank['DEBIT'] > 0)]
    df_450 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('450')]
    for _, rej in rejets.iterrows():
        if df_450[(abs(df_450['DEBIT'] - rej['DEBIT']) < 0.05)].empty:
            r.append(f" - ❌ REJET À IMPUTER : {rej['DATE'].strftime('%d/%m/%Y')} | {rej['DEBIT']:.2f}€ | {rej['LIBELLE']}")

    # E. COMPTES D'ATTENTE
    r.append("\n[SECTION E] COMPTES D'ATTENTE (471/472)")
    for c in ['471', '472']:
        sub = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith(c)]
        solde = sub['CREDIT'].sum() - sub['DEBIT'].sum()
        if abs(solde) > 1: r.append(f" - ⚠️ Compte {c} non soldé : {solde:.2f}€")
        else: r.append(f" - ✅ Compte {c} soldé.")

    # F. RAPPROCHEMENT BANCAIRE (Écarts de flux)
    r.append("\n[SECTION F] RAPPROCHEMENT BANCAIRE (FLUX NON JUSTIFIÉS)")
    # Simplifié pour le rapport texte : liste les gros montants banque sans match compta
    bk_sorties = df_bank[df_bank['DEBIT'] > 0]
    gl_sorties = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('512') & (df_gl['CREDIT'] > 0)]
    for _, bk in bk_sorties.iterrows():
        if gl_sorties[abs(gl_sorties['CREDIT'] - bk['DEBIT']) < 0.02].empty:
            r.append(f" - ❌ SORTIE BANQUE SANS COMPTA : {bk['DATE'].strftime('%d/%m')} | {bk['DEBIT']:.2f}€ | {bk['LIBELLE']}")

    # G. FONDS DE TRAVAUX (ALUR)
    r.append("\n[SECTION G] CONTRÔLE FONDS ALUR")
    s105 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('105')]['CREDIT'].sum()
    s502 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('502')]['DEBIT'].sum()
    if (s105 - s502) > 10:
        r.append(f" - ❌ ANOMALIE : {s105 - s502:.2f}€ manquants sur le placement Livret.")
    else: r.append(" - ✅ Placement ALUR conforme aux réserves.")

    r.append("\n" + "="*80)
    r.append("FIN DU RAPPORT")
    return "\n".join(r)

def save_uploaded_file(uploaded_file, sub):
    p = Path(UPLOAD_DIR) / sub / uploaded_file.name
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f: f.write(uploaded_file.getbuffer())
    return p

# --- INTERFACE STREAMLIT ---

st.title("Système d'Audit Automatisé")

col1, col2 = st.columns(2)
with col1:
    st.markdown("### 1. Documents")
    gl_file = st.file_uploader("Grand Livre (PDF)", type="pdf")
    releves_files = st.file_uploader("12 Relevés (PDF)", type="pdf", accept_multiple_files=True)

with col2:
    st.markdown("### 2. Traitement")
    if gl_file and releves_files and len(releves_files) == 12:
        if st.button("Générer le rapport complet", type="primary"):
            progress = st.progress(0)
            
            # 1. Extraction GL
            gl_df = convert_pdf_to_excel(save_uploaded_file(gl_file, "gl"))
            progress.progress(30)
            
            # 2. Extraction Relevés
            all_releves = []
            for i, f in enumerate(releves_files):
                all_releves.append(extract_releve_data(save_uploaded_file(f, "rb")))
                progress.progress(30 + int((i/12)*60))
            
            # 3. Audit
            bank_df = pd.concat(all_releves, ignore_index=True)
            rapport_final = generer_rapport_audit(gl_df, bank_df)
            
            progress.progress(100)
            st.success("Analyse terminée. Aucun détail affiché ici par mesure de confidentialité.")
            
            st.download_button(
                label="📥 Télécharger le Rapport d'Audit (TXT)",
                data=rapport_final,
                file_name=f"Rapport_Audit_{datetime.now().strftime('%Y%m%d')}.txt",
                mime="text/plain"
            )
            
            # Nettoyage
            shutil.rmtree(UPLOAD_DIR)
            os.makedirs(UPLOAD_DIR)
    else:
        st.info("En attente des documents (1 GL + 12 Relevés)...")
