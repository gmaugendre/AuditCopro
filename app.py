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
    """Ta fonction d'extraction Gemini intégrée."""
    # Le fichier de sortie sera dans le même répertoire que le PDF
    output_path = pdf_path.with_suffix('.xlsx')
    
    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        # Envoi à Gemini 2.5 Flash
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

        # Nettoyage du texte reçu
        csv_data = response.text.replace("```csv", "").replace("```", "").strip()

        # Conversion en DataFrame Pandas
        df = pd.read_csv(
            io.StringIO(csv_data), 
            sep=None, 
            engine='python', 
            on_bad_lines='warn'
        )
        
        # Sauvegarde en Excel dans le même répertoire
        df.to_excel(output_path, index=False)
        return output_path

    except Exception as e:
        st.error(f"Erreur lors de la conversion : {e}")
        return None

def save_uploaded_file(uploaded_file, subfolder):
    """Stocke le fichier sur le serveur et retourne le chemin."""
    path = Path(UPLOAD_DIR) / subfolder
    path.mkdir(parents=True, exist_ok=True)
    file_path = path / uploaded_file.name
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path

def traiter_donnees(gl_path, releves_paths):
    """Fonction de traitement qui appelle la conversion."""
    st.info("Analyse des fichiers en cours par l'IA...")
    
    # Appel de la fonction Gemini sur le Grand Livre
    excel_result = convert_pdf_to_excel(Path(gl_path))
    
    if excel_result:
        st.success(f"Fichier Excel généré : {excel_result.name}")
    
    # On prend comme rapport final le grand livre PDF (pour le test)
    report_path = Path(UPLOAD_DIR) / "rapport_final.pdf"
    # shutil.copy(gl_path, report_path)    
    shutil.copy(excel_result, report_path)
        
    return report_path

# --- INTERFACE UTILISATEUR ---

st.title("📂 Assistant d'analyse des comptes")
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
            with st.spinner("Analyse en cours..."):
                # 1. Sauvegarde
                gl_saved_path = save_uploaded_file(gl_file, "grand_livre")
                paths_releves = [save_uploaded_file(f, "releves") for f in releves_files]
                
                # 2. Traitement (incluant Gemini)
                final_report_path = traiter_donnees(gl_saved_path, paths_releves)

                # 3. Préparation du téléchargement (Lecture en mémoire)
                with open(final_report_path, "rb") as f:
                    pdf_data = f.read()
                
                # 4. Nettoyage immédiat du serveur
                shutil.rmtree(Path(UPLOAD_DIR) / "grand_livre", ignore_errors=True)
                shutil.rmtree(Path(UPLOAD_DIR) / "releves", ignore_errors=True)
                if os.path.exists(final_report_path):
                    os.remove(final_report_path)
                
                st.success("Traitement terminé ! Serveur nettoyé.")
                
                st.download_button(
                    label="📥 Télécharger le rapport d'audit",
                    data=pdf_data,
                    file_name="rapport_audit_comptable.pdf",
                    mime="application/pdf"
                )
    else:
        st.info("Veuillez uploader tous les documents pour activer le traitement.")
