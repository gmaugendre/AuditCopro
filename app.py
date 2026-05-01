import streamlit as st
import os
from pathlib import Path

# --- CONFIGURATION DE L'APPLI ---
st.set_page_config(page_title="Audit Compta Automatisé", layout="wide")

# Dossier local pour stocker les fichiers sur le serveur
UPLOAD_DIR = "storage_compta"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# --- FONCTIONS CŒUR ---

def save_uploaded_file(uploaded_file, subfolder):
    """Stocke le fichier sur le serveur et retourne le chemin."""
    path = Path(UPLOAD_DIR) / subfolder
    path.mkdir(parents=True, exist_ok=True)
    
    file_path = path / uploaded_file.name
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path

def traiter_donnees(gl_path, releves_paths):
    """
    Fonction de traitement (actuellement vide).
    C'est ici que tu mettras ta logique d'analyse PDF (PyMuPDF, Camelot, etc.)
    """
    # Simulation de traitement
    st.info("Analyse des fichiers en cours... (Logique à implémenter)")
    
    # Chemin vers le rapport généré (exemple)
    report_path = Path(UPLOAD_DIR) / "rapport_final.pdf"
    
    # Création d'un fichier PDF vide pour la démo (si il n'existe pas)
    with open(report_path, "w") as f:
        f.write("Ceci est un rapport généré automatiquement.")
        
    return report_path

# --- INTERFACE UTILISATEUR ---

st.title("📂 Assistant de Révision Comptable")
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.header("1. Importation des données")
    
    # Upload du Grand Livre
    gl_file = st.file_uploader("Déposez le Grand Livre (PDF)", type="pdf", key="gl")
    
    # Upload des 12 relevés
    releves_files = st.file_uploader(
        "Déposez les 12 relevés de compte (PDF)", 
        type="pdf", 
        accept_multiple_files=True, 
        key="releves"
    )

with col2:
    st.header("2. Actions & Statut")
    
    if gl_file and releves_files:
        if len(releves_files) != 12:
            st.warning(f"Attention : Vous avez déposé {len(releves_files)} relevé(s) sur 12 attendus.")
        
        if st.button("Lancer le traitement", type="primary"):
            with st.spinner("Enregistrement et analyse..."):
                # 1. Sauvegarde sur le serveur
                gl_saved_path = save_uploaded_file(gl_file, "grand_livre")
                paths_releves = [save_uploaded_file(f, "releves") for f in releves_files]
                
                # 2. Traitement
                final_report_path = traiter_donnees(gl_saved_path, paths_releves)
                
                st.success("Traitement terminé !")
                
                # 3. Téléchargement du rapport
                with open(final_report_path, "rb") as pdf_file:
                    st.download_button(
                        label="📥 Télécharger le rapport d'audit",
                        data=pdf_file,
                        file_name="rapport_audit_comptable.pdf",
                        mime="application/pdf"
                    )
    else:
        st.info("Veuillez uploader tous les documents pour activer le traitement.")

# --- VISUALISATION DU SERVEUR (OPTIONNEL) ---
if st.checkbox("Afficher les fichiers sur le serveur"):
    st.write(os.listdir(UPLOAD_DIR))
