import streamlit as st

# --- CONFIGURATION ---
st.set_page_config(page_title="Audit Copro Express", layout="centered")

# --- STYLE CSS (Fidèle au dessin) ---
st.markdown("""
    <style>
    /* Police Verdana globale */
    html, body, [class*="st-"] {
        font-family: 'Verdana', sans-serif;
    }

    /* 1. LE GRAND CADRE (Texte du Pitch) */
    .pitch-box {
        border: 2px solid #1e3a8a;
        border-radius: 10px;
        padding: 30px;
        background-color: #ffffff;
        margin-bottom: 40px;
        text-align: center;
    }

    .line-top {
        font-size: 2.2rem;
        font-weight: 900;
        color: #1e3a8a;
        margin-bottom: 20px;
    }

    .line-middle {
        font-size: 1.05rem;
        color: #334155;
        line-height: 1.4;
        margin-bottom: 20px;
        text-align: justify;
    }

    .line-bottom {
        font-size: 1.8rem;
        font-weight: 700;
        color: #10b981;
        margin-top: 10px;
    }

    /* 2. LES ZONES DE DÉPÔT (Rectangles du dessin) */
    .upload-label {
        font-weight: bold;
        color: #1e3a8a;
        margin-bottom: 10px;
        display: block;
    }

    /* Ajustement des zones d'upload pour qu'elles ressemblent à des boites */
    .stFileUploader section {
        border: 1px dashed #1e3a8a !important;
        border-radius: 8px !important;
        padding: 20px !important;
    }

    /* 3. LE BOUTON D'ANALYSE */
    .stButton>button {
        width: 100%;
        background-color: #1e3a8a;
        color: white;
        font-weight: bold;
        font-size: 1.2rem;
        padding: 15px;
        border-radius: 8px;
        border: none;
        margin-top: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    .stButton>button:hover {
        background-color: #2563eb;
        color: white;
    }
    </style>
    """, unsafe_allow_html=True)

# --- RENDU DE LA PAGE ---

# 1. Le Cadre de texte (Pitch)
st.markdown("""
    <div class="pitch-box">
        <div class="line-top">Personne ne lit les comptes de sa copropriété. Nous, si.</div>
        <div class="line-middle">
            Comptes indéchiffrables, erreurs invisibles, manque de temps, d’appétence...<br><br>
            Notre outil fait le travail à votre place: déposez simplement le Grand Livre et les relevés bancaires de la copropriété, et notre algorithme vous dit exactement où regarder.<br><br>
            Une analyse rigoureuse en moins de 5 minutes, gratuitement.<br><br>
            La transparence et la simplicité que vous méritez pour poser les bonnes questions à votre syndic.
        </div>
        <div class="line-bottom">Reprenez le contrôle !</div>
    </div>
    """, unsafe_allow_html=True)

# 2. Les deux zones de dépôt (Côte à côte comme sur le dessin)
col1, col2 = st.columns(2)

with col1:
    st.markdown('<span class="upload-label">1. Grand Livre (PDF)</span>', unsafe_allow_html=True)
    gl_file = st.file_uploader("Upload GL", type=["pdf"], key="gl", label_visibility="collapsed")

with col2:
    st.markdown('<span class="upload-label">2. Relevés Bancaires (12 PDF)</span>', unsafe_allow_html=True)
    rb_files = st.file_uploader("Upload RB", type=["pdf"], accept_multiple_files=True, key="rb", label_visibility="collapsed")

# 3. Le bouton d'analyse technique
if st.button("Lancer l'analyse technique"):
    if gl_file and len(rb_files) == 12:
        st.balloons()
        st.success("Analyse en cours... Votre rapport sera prêt dans un instant.")
    else:
        st.error("Erreur : Assurez-vous d'avoir déposé le Grand Livre et les 12 relevés.")

# --- FOOTER ---
st.markdown("""
    <div style="text-align: center; color: #94a3b8; font-size: 0.8rem; margin-top: 50px;">
        gael_maugendre@hotmail.com | +33 6 14 29 80 29
    </div>
    """, unsafe_allow_html=True)
