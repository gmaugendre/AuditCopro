import streamlit as st
from fpdf import FPDF

# Configuration de la page
st.set_page_config(page_title="Audit Copro", page_icon="📄")

st.title("Audit des comptes")
st.write("Uploadez le grand livre pour générer votre rapport.")

# 1. Zone d'upload
uploaded_file = st.file_uploader("Choisissez un fichier PDF", type="pdf")

if uploaded_file is not None:
    st.success("Fichier bien reçu.")
    
    # 2. Simulation de traitement
    with st.spinner('Génération du PDF...'):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("helvetica", "B", 16)
        pdf.cell(0, 10, "Rapport d'audit des comptes", ln=True, align='C')
        
        pdf.ln(10)
        pdf.set_font("helvetica", size=12)
        pdf.cell(0, 10, "Voici le rapport d'audit des comptes de votre copropriété.", ln=True)
        pdf.cell(0, 10, "Le document a été traité avec succès.", ln=True)
        
        # On génère les données et on les convertit en format compatible
        pdf_output = pdf.output()
        pdf_bytes = bytes(pdf_output)

    # 3. Bouton de téléchargement (Aligné avec le début du bloc "with")
    st.download_button(
        label="📥 Télécharger le rapport PDF",
        data=pdf_bytes,
        file_name="rapport_audit.pdf",
        mime="application/pdf"
    )
