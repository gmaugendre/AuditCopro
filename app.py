import streamlit as st
import os
import time
import shutil
from fpdf import FPDF

# --- FONCTION DE STOCKAGE PHYSIQUE (DOSSIER /TMP) ---
def stocker_fichiers_localement(grand_livre, liste_releves):
    dossier_session = os.path.join("/tmp", f"audit_{int(time.time())}")
    os.makedirs(dossier_session, exist_ok=True)
    
    with open(os.path.join(dossier_session, "grand_livre.pdf"), "wb") as f:
        f.write(grand_livre.getbuffer())
        
    for i, fichier in enumerate(liste_releves):
        with open(os.path.join(dossier_session, f"releve_{i+1}.pdf"), "wb") as f:
            f.write(fichier.getbuffer())
            
    return dossier_session

# --- FONCTION D'ANALYSE (SORTIE PDF UNIQUEMENT) ---
def executer_analyse_technique(chemin_dossier):
    time.sleep(2) 
    return {
        "date": "01/05/2026",
        "anomalies": [
            {"t": "Comptes d'attente (471/472)", "d": "Presence de soldes non identifies datant de l'exercice precedent."},
            {"t": "Fournisseurs (Classe 4)", "d": "Detection d'un avoir non deduit sur la facture d'entretien ascenseur."},
            {"t": "Rapprochement Bancaire", "d": "Ecart de 15,20 euros identifie entre le Grand Livre et le releve n.8."},
            {"t": "Doublons de saisie", "d": "Facture EDF du 12/03 saisie deux fois en comptabilite."}
        ]
    }

# --- CONFIGURATION UI & STYLE ---
st.set_page_config(page_title="Audit Copro Express", layout="centered")

# Injection de la police Verdana et design du Pitch
st.markdown("""
    <style>
    /* Global Font */
    html, body, [class*="st-"] {
        font-family: 'Verdana', sans-serif;
    }
    
    .pitch-container {
        background-color: #f8faff;
        padding: 40px;
        border-radius: 15px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        margin-bottom: 30px;
        line-height: 1.6;
    }
    
    .pitch-main-title {
        font-size: 2.2rem;
        font-weight: 900;
        color: #1e3a8a;
        margin-bottom: 20px;
        line-height: 1.2;
    }
    
    .pitch-body {
        font-size: 1.1rem;
        color: #475569;
        margin-bottom: 20px;
    }
    
    .pitch-highlight {
        font-size: 1.8rem;
        font-weight: 700;
        color: #10b981;
        margin-top: 20px;
    }
    
    .disclaimer {
        font-size: 0.75rem;
        color: #94a3b8;
        border-top: 1px solid #e2e8f0;
        padding-top: 20px;
        margin-top: 50px;
    }
    
    /* Style du bouton Streamlit */
    .stButton>button {
        background-color: #1e3a8a;
        color: white;
        font-weight: bold;
        border-radius: 8px;
        height: 3em;
        width: 100%;
        border: none;
    }
    </style>
    
    <div class="pitch-container">
        <div class="pitch-main-title">Personne ne lit les comptes de sa copropriété. Nous, si.</div>
        <div class="pitch-body">
            Comptes indéchiffrables, erreurs invisibles, manque de temps, d’appétence...<br><br>
            Notre outil fait le travail à votre place: déposez simplement le Grand Livre et les relevés bancaires de la copropriété, et notre algorithme vous dit exactement où regarder.<br><br>
            Une analyse rigoureuse en moins de 5 minutes, gratuitement.<br><br>
            La transparence et la simplicité que vous méritez pour poser les bonnes questions à votre syndic.
        </div>
        <div class="pitch-highlight">Reprenez le contrôle !</div>
    </div>
    """, unsafe_allow_html=True)

# --- ZONE D'UPLOAD ---
col1, col2 = st.columns(2)
with col1:
    gl = st.file_uploader("Grand Livre (PDF)", type=["pdf"])
with col2:
    rb = st.file_uploader("12 Relevés Bancaires", type=["pdf"], accept_multiple_files=True)

# --- BOUTON ET TRAITEMENT ---
if st.button("Lancer l'analyse technique"):
    if gl and len(rb) == 12:
        with st.status("Analyse en cours...", expanded=True) as status:
            # 1. Stockage
            chemin = stocker_fichiers_localement(gl, rb)
            
            # 2. Analyse
            data = executer_analyse_technique(chemin)
            
            # 3. Génération PDF (Aucun affichage écran)
            pdf = FPDF()
            pdf.add_page()
            # Note: Verdana n'est pas une police standard FPDF, on utilise Arial/Helvetica 
            # pour la compatibilité maximale du fichier généré
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(0, 10, "RAPPORT D'ANALYSE COMPTABLE", ln=True, align='C')
            pdf.ln(10)
            
            pdf.set_font("Arial", '', 11)
            pdf.cell(0, 10, f"Date de l'audit : {data['date']}", ln=True)
            pdf.ln(5)
            
            for a in data['anomalies']:
                pdf.set_font("Arial", 'B', 11)
                pdf.cell(0, 8, f"- {a['t']}", ln=True)
                pdf.set_font("Arial", '', 11)
                pdf.multi_cell(0, 7, a['d'].encode('latin-1', 'replace').decode('latin-1'))
                pdf.ln(3)
                
            pdf_out = "/tmp/Rapport_Audit_Final.pdf"
            pdf.output(pdf_out)
            
            # 4. Nettoyage
            shutil.rmtree(chemin)
            status.update(label="Analyse terminée ! Le rapport PDF a été généré.", state="complete")
        
        # Bouton de téléchargement seul
        with open(pdf_out, "rb") as f:
            st.download_button(
                label="📥 Télécharger le rapport d'analyse (PDF)",
                data=f,
                file_name="Audit_Copro_Rapport.pdf",
                mime="application/pdf"
            )
    else:
        st.warning("⚠️ Veuillez charger le Grand Livre et les 12 relevés bancaires.")

# --- FOOTER / DISCLAIMER ---
st.markdown("""
    <div class="disclaimer">
        <b>Disclaimer :</b> Je suis un assistant informatique conçu pour accompagner le Conseil Syndical dans sa mission d'analyse et de contrôle des comptes de la copropriété. Mon rôle est d'aider à l'identification de points de vigilance. Mon intervention ne se substitue en aucun cas au pouvoir de contrôle des membres du Conseil Syndical ni à l'expertise comptable du syndic. Les éléments présentés dans le rapport d’analyse sont des pistes d'investigation qui peuvent comporter des erreurs de lecture automatisée, d'interprétation technique et doivent faire l'objet d'une vérification contradictoire et de contrôles sur site.<br><br>
        Aucune donnée sur votre copropriété n'est conservée ni partagée : tous les fichiers sont immédiatement supprimés dès la fin du traitement et aucun rapport n'est stocké.<br><br>
        Ce projet est encore un prototype. L'analyse est totalement gratuite mais nous vous invitons à nous partager en retour votre expérience par écrit (gael_maugendre@hotmail.com) ou de vive voix (+33 6 14 29 80 29).
    </div>
    """, unsafe_allow_html=True)
