import streamlit as st
from fpdf import FPDF
from google import genai
import re

"""

# 1. Initialisation du client IA
# Assurez-vous que GEMINI_API_KEY est bien dans vos "Secrets" sur Streamlit Cloud
try:
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
except Exception as e:
    st.error("🔑 Erreur : La clé API n'est pas configurée dans les Secrets.")

st.set_page_config(page_title="Audit Copro", page_icon="📄")
st.title("Audit des comptes")

# 2. Zone de chargement du fichier
uploaded_file = st.file_uploader("Uploadez le grand livre (PDF)", type="pdf")

if uploaded_file is not None:
    st.info(f"Fichier '{uploaded_file.name}' reçu. Analyse en cours...")
    
    # 3. Appel à l'IA
    # On utilise gemini-2.5-flash qui est très stable
    try:
        with st.spinner('L\'IA analyse la question...'):
            prompt = "Est-ce que la comptabilité est importante dans les copropriétés ?"
            response = client.models.generate_content(
                model="gemini-2.5-flash", 
                contents=prompt
            )
            reponse_ia = response.text
            st.success("Analyse IA terminée.")
    except Exception as e:
        reponse_ia = "Désolé, l'IA n'a pas pu répondre."
        st.error(f"Erreur IA (404 ou autre) : {e}")

    # 4. Création du PDF
    try:
        with st.spinner('Génération du rapport PDF...'):
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", "B", 16)
            pdf.cell(0, 10, "Rapport d'Audit Intelligent", ln=True, align='C')
            pdf.ln(10)
            
            pdf.set_font("Arial", size=12)
            # Nettoyage du texte pour éviter les erreurs d'accents dans le PDF
            texte_propre = reponse_ia.encode('latin-1', 'replace').decode('latin-1')
            pdf.multi_cell(0, 10, txt=texte_propre)
            
            # Méthode robuste pour récupérer les données du PDF
            pdf_output = pdf.output(dest='S')
            if isinstance(pdf_output, str):
                pdf_bytes = pdf_output.encode('latin-1')
            else:
                pdf_bytes = bytes(pdf_output)
                
            st.download_button(
                label="📥 Télécharger le rapport PDF",
                data=pdf_bytes,
                file_name="rapport_audit_ia.pdf",
                mime="application/pdf"
            )
    except Exception as e:
        st.error(f"Erreur lors de la création du PDF : {e}")

    # Aperçu visuel dans Streamlit
    st.markdown("---")
    st.markdown("### Aperçu de l'analyse :")
    st.write(reponse_ia)

    """


import streamlit as st
import os
import tempfile
import time
import pandas as pd

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Test Temp Storage", layout="wide")

st.title("🧪 Test d'Upload et Stockage Temporaire")
st.write("Ce script stocke physiquement les fichiers, simule un traitement, puis les supprime.")

# --- ZONE D'UPLOAD ---
uploaded_files = st.file_uploader(
    "Chargez exactement 3 fichiers PDF ou CSV", 
    accept_multiple_files=True
)

# --- LOGIQUE PRINCIPALE ---
if uploaded_files:
    if len(uploaded_files) == 3:
        if st.button("Lancer le cycle complet"):
            
            # 1. Création du dossier temporaire
            with tempfile.TemporaryDirectory() as tmpdirname:
                st.info(f"📂 Dossier temporaire créé : `{tmpdirname}`")
                
                chemins_locaux = []

                # 2. Sauvegarde des fichiers sur le "disque"
                for uploaded_file in uploaded_files:
                    path = os.path.join(tmpdirname, uploaded_file.name)
                    with open(path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    chemins_locaux.append(path)
                    st.success(f"✅ Fichier écrit : `{uploaded_file.name}`")

                st.divider()
                st.subheader("⚙️ Simulation du traitement (ex: Gemini)")
                
                # Barres de progression pour le test
                progress_bar = st.progress(0)
                
                for i, path in enumerate(chemins_locaux):
                    # --- C'est ici que tu mettrais ton code Gemini ---
                    # ex: result = mon_extraction_gemini(path)
                    st.write(f"Analyse en cours de : `{os.path.basename(path)}`...")
                    
                    # Simulation de lecture avec Pandas ou Gemini
                    time.sleep(1.5) # On simule un temps de calcul
                    
                    progress_bar.progress((i + 1) / len(chemins_locaux))
                
                st.divider()
                st.success("✨ Traitement fini. Sortie du bloc temporaire...")

            # 3. Vérification de la suppression
            st.warning("⚠️ Vérification : Tentative d'accès au dossier...")
            if not os.path.exists(tmpdirname):
                st.info("🗑️ Confirmation : Le dossier et les fichiers ont bien été supprimés du serveur.")
            
    else:
        st.error(f"Attention : Vous avez mis {len(uploaded_files)} fichier(s). Il en faut 3.")

# --- ASTUCE POUR TON PROBLÈME DE DÉBIT/CRÉDIT ---
with st.sidebar:
    st.header("Note Technique")
    st.write("""
    Pour éviter que Gemini ne confonde **Débit** et **Crédit**, 
    profite du fait que le fichier est stocké sur le disque pour :
    1. Lire le texte brut avant l'envoi.
    2. Ajouter une instruction : 
       *'Le fichier est situé dans {tmpdirname}, vérifie bien les tabulations.'*
    """)
