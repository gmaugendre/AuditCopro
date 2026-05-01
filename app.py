import streamlit as st
import os
import shutil
import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
from pathlib import Path
from google import genai
from google.genai import types
from thefuzz import fuzz

# --- CONFIGURATION ---
st.set_page_config(page_title="Audit Copro Direct", layout="wide")

UPLOAD_DIR = "storage_audit"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

API_KEY = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=API_KEY, http_options={'api_version': 'v1beta'})

# --- FONCTIONS UTILITAIRES ---

def save_uploaded_file(uploaded_file, sub_folder):
    p = Path(UPLOAD_DIR) / sub_folder / uploaded_file.name
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return p

# --- EXTRACTION SANS NETTOYAGE ---

def extract_data_via_ia(pdf_path, prompt):
    """Extrait les données en JSON pur selon le prompt fourni."""
    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"), prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        df = pd.DataFrame(json.loads(response.text))
        
        # Conversion minimale pour les calculs (numérique et dates)
        if 'DEBIT' in df.columns: df['DEBIT'] = pd.to_numeric(df['DEBIT'], errors='coerce').fillna(0)
        if 'CREDIT' in df.columns: df['CREDIT'] = pd.to_numeric(df['CREDIT'], errors='coerce').fillna(0)
        if 'DATE' in df.columns: df['DATE'] = pd.to_datetime(df['DATE'], dayfirst=True, errors='coerce')
        
        return df
    except Exception as e:
        st.error(f"Erreur d'extraction sur {pdf_path.name} : {e}")
        return pd.DataFrame()

# --- MOTEUR D'AUDIT (SORTIE RAPPORT) ---

def fuzzy_check_rejet(libelle):
    cibles = ["REJET", "IMPAYE", "ANNULATION", "REFUS", "ECHEC", "SANS PROVISION"]
    lib_clean = str(libelle).upper()
    for mot in cibles:
        if fuzz.partial_ratio(mot, lib_clean) >= 90: return True
    return False

def generer_audit_final(df_gl, df_bk):
    res = []
    
    # Date de référence
    valid_dates = df_gl['DATE'].dropna() if 'DATE' in df_gl.columns else []
    date_ref = valid_dates.max() if len(valid_dates) > 0 else datetime.now()

    res.append("═"*85)
    res.append(f"   RAPPORT D'AUDIT GÉNÉRAL - {datetime.now().strftime('%d/%m/%Y')}")
    res.append(f"   PÉRIODE ANALYSÉE JUSQU'AU : {date_ref.strftime('%d/%m/%Y')}")
    res.append("═"*85 + "\n")

    # A : TROP-PAYÉS
    res.append("🔍 ANALYSE DES TROP-PAYÉS (401)")
    if 'NUMERO_COMPTE' in df_gl.columns:
        df_401 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('401')].copy()
        if not df_401.empty:
            syn = df_401.groupby(['NUMERO_COMPTE', 'NOM_COMPTE']).agg({'DEBIT':'sum', 'CREDIT':'sum'}).reset_index()
            trop = syn[(syn['CREDIT'] - syn['DEBIT']) < -1.00]
            if not trop.empty:
                for _, r in trop.iterrows():
                    res.append(f"   ❌ {r['NOM_COMPTE']} : {abs(r['CREDIT']-r['DEBIT']):.2f}€ à récupérer.")
            else: res.append("   ✅ Aucun trop-payé détecté.")

    # B : DOUBLONS
    res.append("\n🔍 ANALYSE DES DOUBLONS (CLASSE 6)")
    df_6 = df_gl[(df_gl['NUMERO_COMPTE'].astype(str).str.startswith('6')) & (df_gl['DEBIT'] > 0)]
    doublons = df_6[df_6.duplicated(subset=['DEBIT', 'NUMERO_COMPTE'], keep=False)]
    if not doublons.empty:
        res.append(f"   ⚠️ {len(doublons)//2} alertes de doublons potentiels identifiées.")
    else: res.append("   ✅ Aucun doublon détecté.")

    # D : REJETS
    res.append("\n🔍 ANALYSE DES REJETS BANCAIRES")
    rejets = df_bk[df_bk['LIBELLE'].apply(fuzzy_check_rejet) & (df_bk['DEBIT'] > 0)]
    df_450 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('450')]
    alertes_r = 0
    for _, rej in rejets.iterrows():
        match = df_450[(abs(df_450['DEBIT'] - rej['DEBIT']) < 0.05)]
        if match.empty:
            res.append(f"   ❌ REJET NON RÉPERCUTÉ : {rej['DATE'].strftime('%d/%m/%Y')} | {rej['DEBIT']:.2f}€ | {rej['LIBELLE']}")
            alertes_r += 1
    if alertes_r == 0: res.append("   ✅ Tous les rejets bancaires ont été imputés.")

    # I : FONDS ALUR
    res.append("\n🔍 CONTRÔLE DU FONDS DE TRAVAUX (LOI ALUR)")
    try:
        s105 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('105')]['CREDIT'].sum() - df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('105')]['DEBIT'].sum()
        s502 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('502')]['DEBIT'].sum() - df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('502')]['CREDIT'].sum()
        res.append(f"   💰 Réserves (105) : {s105:.2f}€ | Placement (502) : {s502:.2f}€")
        if (s105 - s502) > 10:
            res.append(f"   ❌ ANOMALIE : {s105 - s502:.2f}€ d'écart (fonds non placés).")
        else: res.append("   ✅ Fonds de travaux intégralement placés.")
    except: res.append("   ⚠️ Données insuffisantes pour l'analyse ALUR.")

    res.append("\n" + "═"*85 + "\n   FIN DU RAPPORT")
    return "\n".join(res)

# --- INTERFACE ---

st.title("🛡️ Audit Copropriété Expert")

c1, c2 = st.columns(2)
with c1:
    gl_up = st.file_uploader("Grand Livre (PDF)", type="pdf")
with c2:
    bk_ups = st.file_uploader("12 Relevés (PDF)", type="pdf", accept_multiple_files=True)

if gl_up and bk_ups:
    if st.button("Lancer l'audit", type="primary"):
        with st.spinner("Traitement IA..."):
            # Extraction Grand Livre
            gl_prompt = "Extraire tableau avec clés EXACTES : NUMERO_COMPTE, NOM_COMPTE, DATE, LIBELLE, DEBIT, CREDIT."
            df_gl = extract_data_via_ia(save_uploaded_file(gl_up, "gl"), gl_prompt)
            
            # Extraction Relevés
            bk_prompt = "Extraire transactions avec clés EXACTES : DATE, LIBELLE, DEBIT, CREDIT."
            list_bk = [extract_data_via_ia(save_uploaded_file(f, "bk"), bk_prompt) for f in bk_ups]
            df_bk_all = pd.concat(list_bk, ignore_index=True)
            
            # Audit
            rapport = generer_audit_final(df_gl, df_bk_all)
            
            st.success("Audit terminé.")
            st.download_button("📥 Télécharger le Rapport", rapport, "Audit.txt")
            
            shutil.rmtree(UPLOAD_DIR)
            os.makedirs(UPLOAD_DIR)
