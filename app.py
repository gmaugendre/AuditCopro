"""

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

st.title("🧪 Test d'accès physique au fichier")

# 1. Upload
uploaded_files = st.file_uploader(
    "Chargez 3 fichiers pour le test", 
    accept_multiple_files=True
)

if uploaded_files:
    if len(uploaded_files) == 3:
        if st.button("Lancer le test d'accès"):
            
            # 2. Création du dossier temporaire
            with tempfile.TemporaryDirectory() as tmpdirname:
                st.info(f"📂 Dossier temporaire créé : `{tmpdirname}`")
                
                # Sauvegarde des fichiers
                for uploaded_file in uploaded_files:
                    path = os.path.join(tmpdirname, uploaded_file.name)
                    with open(path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                
                st.success("✅ Tous les fichiers ont été écrits sur le disque.")

                # --- PARTIE DEMANDÉE : ACCÈS PHYSIQUE AU PREMIER FICHIER ---
                st.divider()
                st.subheader("🔍 Vérification de l'accès physique")

                # On récupère la liste des fichiers présents dans le dossier tmp
                fichiers_physiques = os.listdir(tmpdirname)
                
                if fichiers_physiques:
                    # On cible le premier fichier
                    nom_premier_fichier = fichiers_physiques[0]
                    chemin_complet = os.path.join(tmpdirname, nom_premier_fichier)

                    st.write(f"Tentative d'ouverture de : `{chemin_complet}`")

                    try:
                        # On ouvre le fichier physiquement à partir du chemin
                        with open(chemin_complet, "rb") as f:
                            contenu = f.read(100) # On lit les 100 premiers octets pour tester
                        
                        st.success(f"🔓 Succès ! Le fichier `{nom_premier_fichier}` est bien accessible.")
                        st.write("Début des données brutes lues sur le disque :")
                        st.code(contenu) # Affiche les premiers octets (utile pour voir les headers PDF/Text)
                        
                    except Exception as e:
                        st.error(f"❌ Erreur d'accès au fichier : {e}")
                
                # Petite pause pour te laisser voir le message avant la suppression automatique
                st.info("Attente de 5 secondes avant la suppression automatique du dossier...")
                time.sleep(5)

            # 3. Sortie du bloc 'with'
            st.warning("🗑️ Le dossier temporaire a été supprimé. Le chemin n'est plus accessible.")
            
    else:
        st.error("Veuillez sélectionner exactement 3 fichiers.")
