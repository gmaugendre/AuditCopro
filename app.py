import streamlit as st
import os
import shutil
import openpyxl
import pandas as pd
import io
from pathlib import Path
from google import genai
from google.genai import types

# --- CONFIGURATION DE L'APPLI ---
st.set_page_config(page_title="Audit Compta Automatisé", layout="wide")

# Dossier local
UPLOAD_DIR = "storage_compta"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# Récupération sécurisée de la clé depuis les Secrets
API_KEY = st.secrets["GEMINI_API_KEY"]

# Initialisation du client avec la clé sécurisée
client = genai.Client(
    api_key=API_KEY, 
    http_options={'api_version': 'v1beta'}
)

# --- FONCTIONS CŒUR ---

def convert_pdf_to_excel(pdf_path):
    """Extraction Gemini intégrée."""
    output_path = pdf_path.with_suffix('.xlsx')
    
    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(
                    data=pdf_bytes,
                    mime_type="application/pdf"
                ),
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

        if not response.text:
            return None

        csv_data = response.text.replace("```csv", "").replace("```", "").strip()

        df = pd.read_csv(
            io.StringIO(csv_data), 
            sep=None, 
            engine='python', 
            on_bad_lines='warn'
        )
        
        df.to_excel(output_path, index=False)
        return output_path

    except Exception as e:
        st.error(f"Erreur lors de la conversion : {e}")
        return None

def save_uploaded_file(uploaded_file, subfolder):
    path = Path(UPLOAD_DIR) / subfolder
    path.mkdir(parents=True, exist_ok=True)
    file_path = path / uploaded_file.name
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path

def traiter_donnees(gl_path, releves_paths):
    """Modifié pour retourner le fichier Excel généré."""
    st.info("Analyse des fichiers en cours par l'IA...")
    excel_result = convert_pdf_to_excel(Path(gl_path))
    return excel_result # Retourne le chemin du fichier Excel

# --- INTERFACE UTILISATEUR ---

st.title("Assistant d'analyse des comptes")
st.subheader("à partir du grand livre et des relevés bancaires")
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.header("1. Import des données")
    gl_file = st.file_uploader("Déposez le Grand Livre (PDF)", type="pdf", key="gl")
    releves_files = st.file_uploader(
        "Déposez les 12 relevés de compte (PDF)", 
        type="pdf", 
        accept_multiple_files=True, 
        key="releves"
    )

with col2:
    st.header("2. Analyse et rapport")
    
    if gl_file and releves_files:
        if len(releves_files) != 12:
            st.warning(f"Attention : Vous avez déposé {len(releves_files)} relevé(s) sur 12 attendus.")
        
        if st.button("Lancer le traitement", type="primary"):
            with st.spinner("Analyse en cours (durée de 5 à 10 min.)..."):
                gl_saved_path = save_uploaded_file(gl_file, "grand_livre")
                paths_releves = [save_uploaded_file(f, "releves") for f in releves_files]
                
                # Récupération du fichier Excel généré par l'IA
                excel_path = traiter_donnees(gl_saved_path, paths_releves)

                if excel_path:
                    # Lecture de l'Excel en mémoire
                    with open(excel_path, "rb") as f:
                        output_data = f.read()
                    
                    # Nettoyage immédiat
                    shutil.rmtree(Path(UPLOAD_DIR) / "grand_livre", ignore_errors=True)
                    shutil.rmtree(Path(UPLOAD_DIR) / "releves", ignore_errors=True)
                    if os.path.exists(excel_path):
                        os.remove(excel_path)
                    
                    st.success("Traitement terminé ! Fichiers supprimés du serveur.")
                    
                    # Téléchargement du fichier Excel
                    st.download_button(
                        label="📥 Télécharger le Grand Livre traité (Excel)",
                        data=output_data,
                        file_name="grand_livre_traite.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
    else:
        st.info("Veuillez uploader tous les documents pour activer le traitement.")

st.markdown("---")
st.markdown(" ###### Ce projet est un prototype mis à disposition gratuitement ; nous vous invitons à nous partager en retour votre expérience en tant qu'utilisateur (pertinence de l'analyse, expression de besoins etc.), par écrit (gael_maugendre@hotmail.com) ou de vive voix (+33 6 14 29 80 29)).")
st.markdown("---")
st.caption(" ###### Disclaimer: Je suis un assistant informatique conçu pour accompagner le Conseil Syndical dans sa mission d'analyse et de contrôle des comptes de la copropriété. Mon rôle est d'aider à l'identification de points de vigilance. Mon intervention ne se substitue en aucun cas au pouvoir de contrôle des membres du Conseil Syndical ni à l'expertise comptable du syndic. Les éléments présentés dans le rapport d’analyse sont des pistes d'investigation qui peuvent comporter des erreurs de lecture automatisée, d'interprétation technique et doivent faire l'objet d'une vérification contradictoire et de contrôles sur site.")
st.caption(" ###### Aucune donnée sur votre copropriété n'est conservée ni partagée: tous les fichiers sont immédiatement supprimés dés la fin du traitement et aucun rapport n'est stocké.")
