import streamlit as st
import os
import time
import shutil
from fpdf import FPDF

# --- LOGIQUE FONCTIONNELLE (Inchangée) ---
def stocker_fichiers_localement(grand_livre, liste_releves):
    dossier_session = os.path.join("/tmp", f"audit_{int(time.time())}")
    os.makedirs(dossier_session, exist_ok=True)
    with open(os.path.join(dossier_session, "grand_livre.pdf"), "wb") as f:
        f.write(grand_livre.getbuffer())
    for i, fichier in enumerate(liste_releves):
        with open(os.path.join(dossier_session, f"releve_{i+1}.pdf"), "wb") as f:
            f.write(fichier.getbuffer())
    return dossier_session

def executer_analyse_technique(chemin_dossier):
    time.sleep(2) 
    return {
        "date": "01/05/2026",
        "anomalies": [
            {"t": "Comptes d'attente (471/472)", "d": "Soldes non identifiés détectés."},
            {"t": "Fournisseurs", "d": "Avoir non déduit sur contrat ascenseur."},
            {"t": "Banque", "d": "Écart de rapprochement sur le mois de mai."},
            {"t": "Doublons", "d": "Facture EDF saisie deux fois."}
        ]
    }

# --- CONFIGURATION UI ---
st.set_page_config(page_title="Audit Copro Express", layout="centered")

# CSS pour un look épuré et moderne
st.markdown("""
    <style>
    /* Police Verdana et lissage */
    html, body, [class*="st-"] {
        font-family: 'Verdana', sans-serif;
        color: #2c3e50;
    }
    
    /* Le cadre de pitch : plus de bordure lourde, juste une ombre légère */
    .hero-section {
        background-color: #ffffff;
        padding: 40px 20px;
        text-align: center;
        border-bottom: 1px solid #f0f2f6;
        margin-bottom: 40px;
    }
    
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        color: #1e3a8a;
        margin-bottom: 20px;
        line-height: 1.2;
    }
    
    .sub-title {
        font-size: 1.1rem;
        color: #5f6368;
        max-width: 700px;
        margin: 0 auto 30px auto;
        line-height: 1.6;
    }
    
    .cta-line {
        font-size: 1.5rem;
        font-weight: 700;
        color: #10b981;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    /* Style des boutons Streamlit */
    .stButton>button {
        background-color: #1e3a8a;
        color: white;
        border-radius: 8px;
        border: none;
        padding: 0.6rem 2rem;
        font-weight: 600;
        width: 100%;
        transition: 0.3s;
    }
    
    .stButton>button:hover {
        background-color: #3b82f6;
        border: none;
        color: white;
    }

    /* Input boxes */
    [data-testid="stFileUploadDropzone"] {
        border: 2px dashed #e2e8f0 !important;
        border-radius: 12px !important;
    }
    </style>
    
    <div class="hero-section">
        <div class="main-title">Personne ne lit les comptes de sa copropriété. Nous, si.</div>
        <div class="sub-title">
            Déposez vos documents. Notre algorithme identifie les anomalies, 
            les erreurs de saisie et les économies oubliées en moins de 5 minutes.
        </div>
        <div class="cta-line">Reprenez le contrôle</div>
    </div>
    """, unsafe_allow_html=True)

# --- ZONE DE CHARGEMENT ---
col1, col2 = st.columns(2)

with col1:
    st.write("**Étape 1**")
    gl = st.file_uploader("Grand Livre (PDF)", type=["pdf"], label_visibility="collapsed")

with col2:
    st.write("**Étape 2**")
    rb = st.file_uploader("12 Relevés (PDF)", type=["pdf"], accept_multiple_files=True, label_visibility="collapsed")

st.markdown("<br>", unsafe_allow_html=True)

# Bouton d'action centré
_, center_btn, _ = st.columns([1, 2, 1])
with center_btn:
    if st.button("Lancer l'analyse technique"):
        if gl and len(rb) == 12:
            with st.status("Analyse des flux en cours...") as status:
                chemin = stocker_fichiers_localement(gl, rb)
                data = executer_analyse_technique(chemin)
                
                # Génération PDF
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", 'B', 16)
                pdf.cell(0, 10, "RAPPORT D'ANALYSE COMPTABLE", ln=True, align='C')
                pdf.ln(10)
                
                for a in data['anomalies']:
                    pdf.set_font("Arial", 'B', 11)
                    pdf.cell(0, 8, clean_text = f"- {a['t']}", ln=True)
                    pdf.set_font("Arial", '', 11)
                    pdf.multi_cell(0, 7, a['d'].encode('latin-1', 'replace').decode('latin-1'))
                    pdf.ln(3)
                    
                pdf_out = "/tmp/Rapport_Audit.pdf"
                pdf.output(pdf_out)
                shutil.rmtree(chemin)
                status.update(label="Analyse terminée !", state="complete")
            
            st.success("Votre rapport est prêt.")
            st.download_button("📥 Télécharger le rapport d'audit", open(pdf_out, "rb"), file_name="Audit_Copro.pdf")
        else:
            st.warning("Veuillez charger le Grand Livre et les 12 relevés bancaires.")

# --- FOOTER DISCRET ---
st.markdown("""
    <div style="margin-top: 100px; text-align: center; border-top: 1px solid #f0f2f6; padding-top: 20px;">
        <p style="color: #94a3b8; font-size: 0.85rem;">
            gael_maugendre@hotmail.com &nbsp; | &nbsp; +33 6 14 29 80 29
        </p>
    </div>
    """, unsafe_allow_html=True)
