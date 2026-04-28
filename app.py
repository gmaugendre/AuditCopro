import streamlit as st
from fpdf import FPDF
from google import genai
import re

# 1. Initialisation du client IA
# Assurez-vous que GEMINI_API_KEY est bien dans vos "Secrets" sur Streamlit Cloud
try:
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
except Exception as e:
    st.error("🔑 Erreur : La clé API n'est pas configurée dans les Secrets.")

st.set_page_config(page_title="Audit Copro", page_icon="📄")
st.title("🛡️ Audit des comptes avec Gemini")

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
