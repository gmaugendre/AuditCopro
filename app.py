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
    try:
        prompt = """Agis comme un extracteur de données comptables de haute précision.
        Analyse ce fichier PDF et extrais chaque écriture comptable dans un fichier EXCEL.
        Continuité : Identifie les tableaux scindés par des sauts de page et fusionne-les de manière fluide sans répéter les en-têtes.
        Extrait ces données dans excel en retenant uniquement les colonnes: NUMERO COMPTE | NOM COMPTE | DATE | PIECE | CODE JOURNAL (JNL) | CONTREPARTIE | LIBELLE | DEBIT | CREDIT.
        Si les colonnes NUMERO COMPTE ou NOM COMPTE ne sont pas indiquées pour chaque écriture dans le fichier source, va chercher les informations dans l'en-tête de chaque bloc.
        Si les colonnes CODE JOURNAL (JNL) ou CONTREPARTIE ne sont pas disponibles, laisse les vides.
        Mets les en-têtes des colonnes NUMERO COMPTE | NOM COMPTE | DATE | PIECE | CODE JOURNAL (JNL) | CONTREPARTIE | LIBELLE | DEBIT | CREDIT en première ligne.
        Les dates doivent être au format date JJ/MM/AAAA.
        Nettoyage : Supprime les symboles monétaires (€, $) et les séparateurs de milliers. Les nombres doivent être au format numérique 1234.56. Les écritures dont le libellé est 'Report' ou 'Report a nouveau' ou 'A nouveau' en début de bloc doivent être identifiées le cas échéant par AN dans la colonne CODE JOURNAL (JNL).
        N'affiche aucun autre texte."""

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
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
        # Vérification si l'erreur vient du quota
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
            model="gemini-2.5-flash",
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
        # Vérification si l'erreur vient du quota
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

    # Section A : Trop-payés
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
    
    r.append("\n" + "="*80 + "\nFIN DU RAPPORT")
    return "\n".join(r)

# --- INTERFACE STREAMLIT ---

st.title("Assistant d'analyse des comptes de copropriété")
st.subheader("à partir des écritures détaillées du grand livre et des relevés bancaires")
st.markdown("---")

col1, col2 = st.columns(2)
with col1:
    st.markdown("### 1. Documents")
    gl_file = st.file_uploader("Grand Livre (PDF)", type="pdf")
    releves_files = st.file_uploader("12 Relevés (PDF)", type="pdf", accept_multiple_files=True)

with col2:
    st.markdown("### 2. Traitement")
    if gl_file and releves_files and len(releves_files) == 1:  ############################ REMETTRE 12 APRES DEBOGAGE
        if st.button("Générer le rapport complet", type="primary"):
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
            st.download_button("📥 Télécharger le Rapport (TXT)", rapport_final, "Rapport_Audit.txt")

            # --- APERÇU DES DONNÉES CONVERTIES ---
            st.markdown("---")
            st.markdown("### 🛠️ Aperçu des conversions IA")
            
            with st.expander("Voir le Grand Livre converti"):
                st.dataframe(gl_df)
                # Optionnel : Télécharger le GL en Excel
                output_gl = io.BytesIO()
                with pd.ExcelWriter(output_gl, engine='openpyxl') as writer:
                    gl_df.to_excel(writer, index=False)
                st.download_button("💾 Télécharger GL en Excel", output_gl.getvalue(), "GL_converti.xlsx")

            with st.expander("Voir les Relevés Bancaires cumulés"):
                st.dataframe(bank_df)
                output_bk = io.BytesIO()
                with pd.ExcelWriter(output_bk, engine='openpyxl') as writer:
                    bank_df.to_excel(writer, index=False)
                st.download_button("💾 Télécharger Banque en Excel", output_bk.getvalue(), "Banque_convertie.xlsx")

            # Nettoyage
            shutil.rmtree(UPLOAD_DIR)
            os.makedirs(UPLOAD_DIR)
    else:
        st.info("En attente des documents (1 GL + 12 Relevés)...")

st.markdown("---")
st.markdown(" ###### Ce projet est un prototype mis à disposition gratuitement ; nous vous invitons à nous partager en retour votre expérience en tant qu'utilisateur (pertinence de l'analyse, expression de besoins etc.), par écrit (gael_maugendre@hotmail.com) ou de vive voix (+33 6 14 29 80 29)).")
st.markdown("---")
st.caption(" ###### Disclaimer: Je suis un assistant informatique conçu pour accompagner le Conseil syndical dans sa mission d'analyse et de contrôle des comptes de la copropriété. Mon rôle est d'aider à l'identification de points de vigilance. Mon intervention ne se substitue en aucun cas au pouvoir de contrôle des membres du Conseil syndical ni à l'expertise comptable du Syndic. Les éléments présentés dans le rapport d’analyse sont des pistes d'investigation qui peuvent comporter des erreurs de lecture automatisée, d'interprétation technique et doivent faire l'objet d'une vérification contradictoire et de contrôles sur site.")
st.caption(" ###### Aucune donnée sur votre copropriété n'est conservée ni partagée: tous les fichiers sont immédiatement supprimés dés la fin du traitement et aucun rapport n'est stocké.")

