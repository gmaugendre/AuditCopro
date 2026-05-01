import streamlit as st
import os
import time
import shutil
from fpdf import FPDF

# --- FONCTION DE STOCKAGE PHYSIQUE ---
def stocker_fichiers_localement(grand_livre, liste_releves):
    """
    Crée un répertoire temporaire et enregistre les fichiers PDF.
    Retourne le chemin du dossier créé.
    """
    # Création d'un nom de dossier basé sur le timestamp pour éviter les collisions
    dossier_session = f"storage_{int(time.time())}"
    os.makedirs(dossier_session, exist_ok=True)
    
    # Stockage du Grand Livre
    chemin_gl = os.path.join(dossier_session, grand_livre.name)
    with open(chemin_gl, "wb") as f:
        f.write(grand_livre.getbuffer())
        
    # Stockage des 12 relevés
    for fichier in liste_releves:
        chemin_rb = os.path.join(dossier_session, fichier.name)
        with open(chemin_rb, "wb") as f:
            f.write(fichier.getbuffer())
            
    return dossier_session

# --- FONCTION D'ANALYSE (LOGIQUE INTERNE) ---
def executer_analyse_technique(chemin_dossier):
    """
    Simule l'analyse en lisant les fichiers stockés dans chemin_dossier.
    Toute la sortie est préparée pour le PDF.
    """
    # Ici, l'algorithme scannerait les fichiers dans os.listdir(chemin_dossier)
    time.sleep(3) 
    
    resultats = {
        "date_audit": "01/05/2026",
        "nb_fichiers_lus": len(os.listdir(chemin_dossier)),
        "anomalies": [
            {"titre": "Analyse du Grand Livre", "desc": "Detection de 3 ecritures non lettrees en classe 4."},
            {"titre": "Rapprochement Bancaire", "desc": "Ecart constate sur le releve de decembre (ID_992)."},
            {"titre": "Comptes d'attente", "desc": "Le compte 471 presente un solde crediteur de 2.100 euros."},
            {"titre": "TVA", "desc": "Incoherence detectee sur la recuperation de TVA fournisseur proprette."}
        ]
    }
    return resultats

# --- CONFIGURATION UI ---
st.set_page_config(page_title="Audit Copropriété Express", layout="centered")

# --- AFFICHAGE DU PITCH ---
st.markdown('''
    <div style="background-color: #f0f7ff; padding: 25px; border-radius: 10px; border-left: 5px solid #1e3a8a; margin-bottom: 25px;">
        <h2 style="color: #1e3a8a; margin-top:0;">Personne ne lit les comptes de sa copropriété. Nous, si.</h2>
        <p>Comptes indéchiffrables, erreurs invisibles, manque de temps, d’appétence...<br>
        Notre outil fait le travail à votre place: déposez simplement le Grand Livre et les relevés bancaires de la copropriété, et notre algorithme vous dit exactement où regarder.<br>
        <b>Une analyse rigoureuse en moins de 5 minutes, gratuitement.</b><br>
        La transparence et la simplicité que vous méritez pour poser les bonnes questions à votre syndic. <b>Reprenez le contrôle !</b></p>
    </div>
''', unsafe_allow_html=True)

# --- ZONE DE CHARGEMENT ---
gl = st.file_uploader("Grand Livre (PDF)", type=["pdf"])
rb = st.file_uploader("12 Relevés Bancaires (PDF)", type=["pdf"], accept_multiple_files=True)

# --- BOUTON D'ACTION ---
if st.button("Lancer l'analyse"):
    if gl and len(rb) == 12:
        with st.status("Traitement des fichiers...", expanded=True) as status:
            
            # 1. Stockage local des 13 fichiers
            st.write("📁 Stockage des documents sur le serveur...")
            chemin_local = stocker_fichiers_localement(gl, rb)
            
            # 2. Analyse technique
            st.write("🔍 Analyse algorithmique des données...")
            data = executer_analyse_technique(chemin_local)
            
            # 3. Génération du PDF
            st.write("📄 Génération du rapport final...")
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(0, 10, "RAPPORT D'ANALYSE TECHNIQUE", ln=True, align='C')
            pdf.ln(10)
            
            pdf.set_font("Arial", '', 11)
            pdf.cell(0, 10, f"Dossier traite : {chemin_local} ({data['nb_fichiers_lus']} fichiers)", ln=True)
            pdf.ln(5)
            
            for item in data['anomalies']:
                pdf.set_font("Arial", 'B', 11)
                pdf.cell(0, 8, f"- {item['titre']}", ln=True)
                pdf.set_font("Arial", '', 11)
                pdf.multi_cell(0, 7, item['desc'])
                pdf.ln(3)
                
            pdf_path = "Rapport_Audit_Copro.pdf"
            pdf.output(pdf_path)
            
            # 4. Nettoyage immédiat des fichiers locaux après analyse
            shutil.rmtree(chemin_local)
            
            status.update(label="Analyse terminée !", state="complete")
        
        # Bouton de téléchargement
        with open(pdf_path, "rb") as f:
            st.download_button(
                label="📥 Télécharger le rapport (PDF)",
                data=f,
                file_name="Reporting_Audit.pdf",
                mime="application/pdf"
            )
            
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
            
    else:
        st.error("⚠️ Veuillez uploader le Grand Livre et exactement 12 relevés.")

# --- SECTION DISCLAIMER ---
st.markdown('''
    <div style="font-size: 0.85em; color: #666; margin-top: 50px; padding: 20px; border-top: 1px solid #eee; line-height: 1.6;">
        <b>Disclaimer:</b> Je suis un assistant informatique conçu pour accompagner le Conseil Syndical dans sa mission d'analyse et de contrôle des comptes de la copropriété. Mon rôle est d'aider à l'identification de points de vigilance. Mon intervention ne se substitue en aucun cas au pouvoir de contrôle des membres du Conseil Syndical ni à l'expertise comptable du syndic. Les éléments présentés dans le rapport d’analyse sont des pistes d'investigation qui peuvent comporter des erreurs de lecture automatisée, d'interprétation technique et doivent faire l'objet d'une vérification contradictoire et de contrôles sur site.<br><br>
        Aucune donnée sur votre copropriété n'est conservée ni partagée: tous les fichiers sont immédiatement supprimés dés la fin du traitement et aucun rapport n'est stocké.<br><br>
        Ce projet est encore un prototype. L'analyse est totalement gratuite mais nous vous invitons à nous partager en retour votre expérience en tant qu'utilisateur (pertinence de l'analyse, expression de besoins etc.), par écrit (<b>gael_maugendre@hotmail.com</b>) ou de vive voix (<b>+33 6 14 29 80 29</b>).
    </div>
''', unsafe_allow_html=True)
