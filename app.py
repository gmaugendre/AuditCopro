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

# --- CONFIGURATION ---
st.set_page_config(page_title="Audit Compta Automatisé", layout="wide")

UPLOAD_DIR = "storage_compta"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

API_KEY = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=API_KEY, http_options={'api_version': 'v1beta'})

# --- FONCTIONS UTILITAIRES ---

def save_uploaded_file(uploaded_file, sub):
    p = Path(UPLOAD_DIR) / sub / uploaded_file.name
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f: f.write(uploaded_file.getbuffer())
    return p

# --- FONCTIONS D'EXTRACTION ---

def convert_pdf_to_excel(pdf_path):
    """Extraction du Grand Livre sans mapping complexe."""
    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                "Extraire les colonnes : NUMERO_COMPTE, NOM_COMPTE, DATE, LIBELLE, DEBIT, CREDIT. JSON uniquement."
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        df = pd.DataFrame(json.loads(response.text))
        # Conversion forcée minimale pour les calculs
        if 'DEBIT' in df.columns: df['DEBIT'] = pd.to_numeric(df['DEBIT'], errors='coerce').fillna(0)
        if 'CREDIT' in df.columns: df['CREDIT'] = pd.to_numeric(df['CREDIT'], errors='coerce').fillna(0)
        if 'DATE' in df.columns: df['DATE'] = pd.to_datetime(df['DATE'], dayfirst=True, errors='coerce')
        return df
    except: return pd.DataFrame()

def extract_releve_data(pdf_path):
    """Extraction des Relevés sans mapping complexe."""
    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                "Extraire transactions : DATE, LIBELLE, DEBIT, CREDIT. JSON uniquement."
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        df = pd.DataFrame(json.loads(response.text))
        if 'DEBIT' in df.columns: df['DEBIT'] = pd.to_numeric(df['DEBIT'], errors='coerce').fillna(0)
        if 'CREDIT' in df.columns: df['CREDIT'] = pd.to_numeric(df['CREDIT'], errors='coerce').fillna(0)
        if 'DATE' in df.columns: df['DATE'] = pd.to_datetime(df['DATE'], dayfirst=True, errors='coerce')
        return df
    except: return pd.DataFrame()

# --- MOTEUR D'AUDIT ---

def fuzzy_check_rejet(libelle):
    cibles = ["REJET", "IMPAYE", "ANNULATION", "REFUS", "ECHEC"]
    for mot in cibles:
        if fuzz.partial_ratio(mot, str(libelle).upper()) >= 90: return True
    return False

def generer_rapport_audit(df_gl, df_bank):
    r = [] 
    date_ref = df_gl['DATE'].max() if ('DATE' in df_gl.columns and not df_gl['DATE'].dropna().empty) else datetime.now()
    
    r.append("="*80)
    r.append(f"RAPPORT D'AUDIT COMPTABLE - GÉNÉRÉ LE {datetime.now().strftime('%d/%m/%Y')}")
    r.append(f"Période analysée jusqu'au : {date_ref.strftime('%d/%m/%Y')}")
    r.append("="*80 + "\n")

    # A. TROP-PAYÉS
    r.append("[SECTION A] ANALYSE DES TROP-PAYÉS")
    if 'NUMERO_COMPTE' in df_gl.columns:
        df_401 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('401')].copy()
        if not df_401.empty:
            synthese = df_401.groupby(['NUMERO_COMPTE', 'NOM_COMPTE']).agg({'DEBIT':'sum', 'CREDIT':'sum'}).reset_index()
            trop = synthese[(synthese['CREDIT'] - synthese['DEBIT']) < -1.00]
            if not trop.empty:
                for _, row in trop.iterrows():
                    r.append(f" - ❌ {row['NOM_COMPTE']} : {abs(row['CREDIT']-row['DEBIT']):.2f}€ à récupérer.")
            else: r.append(" - ✅ Aucun trop-payé.")

    # G. FONDS ALUR
    r.append("\n[SECTION G] CONTRÔLE FONDS ALUR")
    try:
        s105 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('105')]['CREDIT'].sum()
        s502 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('502')]['DEBIT'].sum()
        if (s105 - s502) > 10:
            r.append(f" - ❌ ANOMALIE : {s105 - s502:.2f}€ manquants sur le placement.")
        else: r.append(" - ✅ Placement ALUR conforme.")
    except: r.append(" - ⚠️ Analyse ALUR impossible.")

    r.append("\n" + "="*80 + "\nFIN DU RAPPORT")
    return "\n".join(r)

# --- INTERFACE STREAMLIT (RETOUR À LA VERSION ORIGINALE) ---

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
            
            gl_path = save_uploaded_file(gl_file, "gl")
            gl_df = convert_pdf_to_excel(gl_path)
            progress.progress(30)
            
            all_releves = []
            for i, f in enumerate(releves_files):
                p_rb = save_uploaded_file(f, "rb")
                all_releves.append(extract_releve_data(p_rb))
                progress.progress(30 + int((i/12)*60))
            
            bank_df = pd.concat(all_releves, ignore_index=True)
            rapport_final = generer_rapport_audit(gl_df, bank_df)
            
            progress.progress(100)
            st.success("Analyse terminée.")
            st.download_button("📥 Télécharger le Rapport (TXT)", rapport_final, "Rapport_Audit.txt")
            
            shutil.rmtree(UPLOAD_DIR)
            os.makedirs(UPLOAD_DIR)
    else:
        st.info("En attente des documents (1 GL + 12 Relevés)...")
