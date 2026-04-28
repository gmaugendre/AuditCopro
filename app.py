import streamlit as st
import pandas as pd
from fpdf import FPDF
from google import genai
import re

# 1. Configuration de l'IA 🤖
# Assurez-vous d'avoir ajouté GEMINI_API_KEY dans vos Secrets Streamlit Cloud
try:
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
except Exception as e:
    st.error("Erreur de configuration : Clé API manquante dans les Secrets.")

st.set_page_config(page_title="Audit Copro", page_icon="📄")
st.title("Audit des comptes avec IA")

# 2. Zone d'upload 📤
uploaded_file = st.file_uploader("Uploadez le grand livre (PDF)", type="pdf")

if uploaded_file is not None:
    st.success("Fichier reçu. Préparation de l'analyse...")
    
    # 3. Appel à Gemini 🧠
    with st.spinner('Consultation de Gemini...'):
        try:
            question = "Est-ce que la comptabilité est importante dans les copropriétés ?"
            response = client.models.generate_content(
                model="gemini-1.5-flash", 
                contents=question
            )
            reponse_ia = response.text
        except Exception as e:
            reponse_ia = "Erreur lors de la récupération de la réponse IA."
            st.error(f"Détail de l'erreur : {e}")

    # 4. Génération du rapport PDF 📄
    with st.spinner('Génération du rapport final...'):
        pdf = FPDF()
        pdf.add_page()
        
        # Titre
        pdf.set_font("helvetica", "B", 16)
        pdf.cell(0, 10, "Rapport d'audit des comptes", ln=True, align='C')
        pdf.ln(10)
        
        # Contenu
        pdf.set_font("helvetica", size=12)
        pdf.multi_cell(0, 10, f"Analyse pour le fichier : {uploaded_file.name}")
        pdf.ln(5)
        
        # Insertion de la réponse de l'IA
        pdf.set_font("helvetica", "B", 12)
        pdf.cell(0, 10, "Avis de l'expert IA :", ln=True)
        pdf.set_font("helvetica", size=11)
        
        # Nettoyage pour éviter les erreurs d'encodage PDF
        texte_propre = reponse_ia.encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 8, texte_propre)
        
        pdf_bytes = pdf.output(dest='S').encode('latin-1')

    # 5. Bouton de téléchargement 📥
    st.download_button(
        label="📥 Télécharger le rapport PDF complet",
        data=pdf_bytes,
        file_name="rapport_audit_ia.pdf",
        mime="application/pdf"
    )
    
    # Aperçu dans l'application
    st.markdown("### Aperçu de l'analyse")
    st.write(reponse_ia)
