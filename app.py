import streamlit as st
import os
import time
import shutil
from fpdf import FPDF

# --- FONCTION DE STOCKAGE PHYSIQUE (DOSSIER /TMP POUR STREAMLIT CLOUD) ---
def stocker_fichiers_localement(grand_livre, liste_releves):
    # On utilise /tmp qui est le dossier standard d'ecriture sur Streamlit Cloud
    dossier_session = os.path.join("/tmp", f"audit_{int(time.time())}")
    os.makedirs(dossier_session, exist_ok=True)
    
    # Stockage du Grand Livre
    with open(os.path.join(dossier_session, "grand_livre.pdf"), "wb") as f:
        f.write(grand_livre.getbuffer())
        
    # Stockage des relevés
    for i, fichier in enumerate(liste_releves):
        with open(os.path.join(dossier_session, f"releve_{i+1}.pdf"), "wb") as f:
            f.write(fichier.getbuffer())
            
    return dossier_session

# --- FONCTION D'ANALYSE ---
def executer_analyse_technique(chemin_dossier):
    # Simulation du traitement des fichiers presents dans le dossier
    time.sleep(2) 
    return {
        "date": "01/05/2026",
        "anomalies": [
            {"t": "Compte d'attente (471)", "d": "Solde anormal de 2.450 euros non justifie."},
            {"t": "Avoirs Fournisseurs", "d": "Avoir de 412 euros non reclame chez le prestataire ascenseur."},
            {"t": "Rapprochement", "d": "Ecart de 15 euros sur le mois de Mai."},
            {"t": "Doublons", "d": "Facture ENGIE saisie deux fois en comptabilite."}
        ]
    }

# --- INTERFACE STREAMLIT ---
st.set_page_config(page_title="Audit Copro", layout="centered")

st.markdown('''
    <div style="background-color: #f0f7ff; padding: 20px; border-radius: 10px; border-left: 5px solid #1e3a8a;">
        <h3 style="color: #1e3a8a;">Personne ne lit les comptes de sa copropriété. Nous, si.</h3>
        <p>Notre outil fait le travail à votre place: déposez simplement vos documents et recevez votre analyse.<br>
        <b>Une analyse rigoureuse en moins de 5 minutes, gratuitement.</b></p>
    </div>
''', unsafe_allow_html=True)

st.write(" ")
gl = st.file_uploader("Grand Livre (PDF)", type=["pdf"])
rb = st.file_uploader("Les 12 relevés bancaires (PDF)", type=["pdf"], accept_multiple_files=True)

if st.button("Lancer l'analyse"):
    if gl and len(rb) == 12:
        with st.status("Analyse technique en cours...") as status:
            # 1. Stockage
            chemin = stocker_fichiers_localement(gl, rb)
            
            # 2. Analyse
            data = executer_analyse_technique(chemin)
            
            # 3. PDF (Texte sans accents pour eviter les erreurs d'encodage FPDF)
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(0, 10, "RAPPORT D'ANALYSE COMPTABLE", ln=True, align='C')
            pdf.ln(10)
            
            pdf.set_font("Arial", '', 12)
            pdf.cell(0, 10, f"Analyse generee le {data['date']}", ln=True)
            pdf.ln(5)
            
            for a in data['anomalies']:
                pdf.set_font("Arial", 'B', 11)
                pdf.cell(0, 8, f"- {a['t']}", ln=True)
                pdf.set_font("Arial", '', 11)
                pdf.multi_cell(0, 7, a['d'])
                pdf.ln(3)
                
            pdf_out = "/tmp/Rapport_Audit.pdf"
            pdf.output(pdf_out)
            
            # 4. Nettoyage
            shutil.rmtree(chemin)
            status.update(label="Analyse terminée !", state="complete")
        
        with open(pdf_out, "rb") as f:
            st.download_button("📥 Télécharger le rapport (PDF)", f, file_name="Rapport_Audit_Copro.pdf")
    else:
        st.error("Veuillez charger le Grand Livre et exactement 12 relevés.")

# --- DISCLAIMER ---
st.markdown('''
    <div style="font-size: 0.8em; color: #666; margin-top: 50px; border-top: 1px solid #eee; padding-top: 20px;">
        <b>Disclaimer:</b> Assistant informatique pour le Conseil Syndical. Aide à l'identification de points de vigilance. Ne remplace pas le contrôle légal. Les données sont supprimées immédiatement après traitement.<br><br>
        Contact : gael_maugendre@hotmail.com | +33 6 14 29 80 29
    </div>
''', unsafe_allow_html=True)
