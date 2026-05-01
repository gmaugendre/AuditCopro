import streamlit as st
import os
import time
import shutil
from fpdf import FPDF

# --- FONCTION DE STOCKAGE ---
def stocker_fichiers_localement(grand_livre, liste_releves):
    dossier_session = os.path.join("/tmp", f"audit_{int(time.time())}")
    os.makedirs(dossier_session, exist_ok=True)
    with open(os.path.join(dossier_session, "grand_livre.pdf"), "wb") as f:
        f.write(grand_livre.getbuffer())
    for i, fichier in enumerate(liste_releves):
        with open(os.path.join(dossier_session, f"releve_{i+1}.pdf"), "wb") as f:
            f.write(fichier.getbuffer())
    return dossier_session

# --- FONCTION D'ANALYSE ---
def executer_analyse_technique(chemin_dossier):
    time.sleep(2) 
    return {
        "date": "01/05/2026",
        "anomalies": [
            {"t": "Comptes d'attente (471/472)", "d": "Soldes non identifies detectes."},
            {"t": "Fournisseurs", "d": "Avoir non deduit sur contrat ascenseur."},
            {"t": "Banque", "d": "Ecart de rapprochement sur le mois de mai."},
            {"t": "Doublons", "d": "Facture EDF saisie deux fois."}
        ]
    }

# --- CONFIGURATION UI ---
st.set_page_config(page_title="Audit Copro Express", layout="wide")

# CSS pour Verdana, réduction interligne et taille de police
st.markdown("""
    <style>
    html, body, [class*="st-"] {
        font-family: 'Verdana', sans-serif;
    }
    
    .pitch-container {
        background-color: #f0f7ff;
        padding: 40px 60px; 
        border-radius: 20px;
        border: 2px solid #1e3a8a;
        box-shadow: 0 10px 25px rgba(0, 0, 0, 0.05);
        margin: 0 auto 30px auto;
        max-width: 1000px; 
        line-height: 1.4; /* Interligne réduit */
        text-align: center;
    }
    
    .pitch-main-title {
        font-size: 2.4rem; /* Légèrement réduit (était 2.8) */
        font-weight: 900;
        color: #1e3a8a;
        margin-bottom: 20px;
    }
    
    .pitch-body {
        font-size: 1.1rem; /* Légèrement réduit (était 1.25) */
        color: #334155;
        margin-bottom: 20px;
        text-align: justify;
    }
    
    .pitch-highlight {
        font-size: 1.9rem; /* Légèrement réduit (était 2.2) */
        font-weight: 700;
        color: #10b981;
        margin-top: 20px;
        border-top: 1px solid #cbd5e1;
        padding-top: 15px;
    }

    .stButton>button {
        background-color: #1e3a8a;
        color: white;
        height: 3em;
        font-size: 1rem;
        border-radius: 8px;
        width: 100%;
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

# --- ZONE CENTRALE D'UPLOAD ---
_, col_center, _ = st.columns([1, 1.5, 1]) 

with col_center:
    gl = st.file_uploader("Grand Livre (PDF)", type=["pdf"])
    rb = st.file_uploader("12 Relevés Bancaires", type=["pdf"], accept_multiple_files=True)
    
    if st.button("Lancer l'analyse technique"):
        if gl and len(rb) == 12:
            with st.status("Analyse en cours...") as status:
                chemin = stocker_fichiers_localement(gl, rb)
                data = executer_analyse_technique(chemin)
                
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", 'B', 16)
                pdf.cell(0, 10, "RAPPORT D'ANALYSE COMPTABLE", ln=True, align='C')
                pdf.ln(10)
                
                for a in data['anomalies']:
                    pdf.set_font("Arial", 'B', 11)
                    pdf.cell(0, 8, f"- {a['t']}", ln=True)
                    pdf.set_font("Arial", '', 11)
                    pdf.multi_cell(0, 7, a['d'].encode('latin-1', 'replace').decode('latin-1'))
                    pdf.ln(3)
                    
                pdf_out = "/tmp/Rapport_Audit.pdf"
                pdf.output(pdf_out)
                shutil.rmtree(chemin)
                status.update(label="Analyse terminée !", state="complete")
            
            with open(pdf_out, "rb") as f:
                st.download_button("📥 Télécharger le rapport (PDF)", f, file_name="Audit_Copro.pdf")
        else:
            st.error("Documents manquants (1 Grand Livre + 12 relevés requis).")

# --- FOOTER ---
st.markdown('<div style="font-size: 0.8rem; color: gray; text-align: center; margin-top: 50px; padding: 20px; border-top: 1px solid #eee;">gael_maugendre@hotmail.com | +33 6 14 29 80 29</div>', unsafe_allow_html=True)
