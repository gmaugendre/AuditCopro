import streamlit as st
import os
from pathlib import Path
import shutil

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
    Prend le Grand Livre et en fait une copie nommée 'rapport_final.pdf'.
    """
    st.info("Génération du rapport à partir du Grand Livre...")
    
    # Chemin cible
    report_path = Path(UPLOAD_DIR) / "rapport_final.pdf"
    
    # COPIE RÉELLE du fichier PDF (pour qu'il soit valide à l'ouverture)
    shutil.copy(gl_path, report_path)
        
    return report_path


# --- INTERFACE UTILISATEUR ---

st.title("📂 Assistant d'analyse des comptes")
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.header("1. Import des données")
    
    # Upload du Grand Livre
    gl_file = st.file_uploader("Déposez le Grand Livre (PDF)", type="pdf", key="gl")
    
    # Upload des 12 relevés bancaires
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
                # 1. Sauvegarde sur le serveur
                gl_saved_path = save_uploaded_file(gl_file, "grand_livre")
                paths_releves = [save_uploaded_file(f, "releves") for f in releves_files]
                
                # 2. Traitement
                final_report_path = traiter_donnees(gl_saved_path, paths_releves)

                # --- NETTOYAGE IMMÉDIAT DES SOURCES ---
                # On supprime les dossiers 'grand_livre' et 'releves'
                shutil.rmtree(Path(UPLOAD_DIR) / "grand_livre", ignore_errors=True)
                shutil.rmtree(Path(UPLOAD_DIR) / "releves", ignore_errors=True)

                # --- PRÉPARATION DU TÉLÉCHARGEMENT ---
                # On lit le rapport en mémoire pour pouvoir supprimer le fichier physique
                with open(final_report_path, "rb") as f:
                    pdf_data = f.read()
                
                # On supprime le rapport du serveur
                os.remove(final_report_path)
                
                st.success("Traitement terminé !")

                # 3. Téléchargement du rapport
                # On passe 'pdf_data' (la mémoire) et NON le chemin du fichier
                st.download_button(
                    label="📥 Télécharger le rapport d'audit",
                    data=pdf_data,  # Utilise les données lues précédemment
                    file_name="rapport_audit_comptable.pdf",
                    mime="application/pdf"
                    )
                import streamlit as st
import os
from pathlib import Path
import shutil

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
    Prend le Grand Livre et en fait une copie nommée 'rapport_final.pdf'.
    """
    st.info("Génération du rapport à partir du Grand Livre...")
    
    # Chemin cible
    report_path = Path(UPLOAD_DIR) / "rapport_final.pdf"
    
    # COPIE RÉELLE du fichier PDF (pour qu'il soit valide à l'ouverture)
    shutil.copy(gl_path, report_path)
        
    return report_path


# --- INTERFACE UTILISATEUR ---

st.title("📂 Assistant d'analyse des comptes")
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.header("1. Import des données")
    
    # Upload du Grand Livre
    gl_file = st.file_uploader("Déposez le Grand Livre (PDF)", type="pdf", key="gl")
    
    # Upload des 12 relevés bancaires
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
                # 1. Sauvegarde sur le serveur
                gl_saved_path = save_uploaded_file(gl_file, "grand_livre")
                paths_releves = [save_uploaded_file(f, "releves") for f in releves_files]
                
                # 2. Traitement
                final_report_path = traiter_donnees(gl_saved_path, paths_releves)

                # --- NETTOYAGE IMMÉDIAT DES SOURCES ---
                # On supprime les dossiers 'grand_livre' et 'releves'
                shutil.rmtree(Path(UPLOAD_DIR) / "grand_livre", ignore_errors=True)
                shutil.rmtree(Path(UPLOAD_DIR) / "releves", ignore_errors=True)

                # --- PRÉPARATION DU TÉLÉCHARGEMENT ---
                # On lit le rapport en mémoire pour pouvoir supprimer le fichier physique
                with open(final_report_path, "rb") as f:
                    pdf_data = f.read()
                
                # On supprime le rapport du serveur
                os.remove(final_report_path)
                
                st.success("Traitement terminé !")

                # 3. Téléchargement du rapport
                # On passe 'pdf_data' (la mémoire) et NON le chemin du fichier
                st.download_button(
                    label="📥 Télécharger le rapport d'audit",
                    data=pdf_data,  # Utilise les données lues précédemment
                    file_name="rapport_audit_comptable.pdf",
                    mime="application/pdf"
                    )
        st.info("Tous les documents (grand livre, relevés de compte et rapport d'analyse ont été définitivement supprimés.).")

    else:
        st.info("Veuillez uploader tous les documents pour activer le traitement.")

