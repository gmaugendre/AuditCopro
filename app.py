import streamlit as st

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Audit Copro Express", layout="wide")

# --- DESIGN PERSONNALISÉ (CSS) ---
st.markdown("""
    <style>
    /* Police globale Verdana */
    html, body, [class*="st-"] {
        font-family: 'Verdana', sans-serif;
    }

    /* Le grand cadre principal du haut (ton dessin) */
    .main-frame {
        border: 2px solid #1e3a8a;
        border-radius: 15px;
        padding: 40px;
        background-color: #ffffff;
        max-width: 1100px;
        margin: 0 auto 30px auto;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
    }

    /* La première ligne en gros */
    .title-line {
        font-size: 2.5rem;
        font-weight: 900;
        color: #1e3a8a;
        text-align: center;
        margin-bottom: 25px;
        line-height: 1.2;
    }

    /* Le corps du texte (interligne réduit et taille moyenne) */
    .body-text {
        font-size: 1.05rem;
        color: #475569;
        line-height: 1.4;
        text-align: center;
        margin-bottom: 25px;
    }

    /* La dernière ligne en gros et vert */
    .highlight-line {
        font-size: 2.1rem;
        font-weight: 700;
        color: #10b981;
        text-align: center;
        margin-top: 10px;
    }

    /* Style des zones d'upload (pour qu'elles soient côte à côte) */
    .upload-section {
        max-width: 1100px;
        margin: 0 auto;
    }

    /* Bouton d'analyse */
    .stButton>button {
        background-color: #1e3a8a;
        color: white;
        font-size: 1.2rem;
        font-weight: bold;
        height: 3.5em;
        width: 100%;
        border-radius: 10px;
        margin-top: 20px;
    }
    
    /* Cacher le menu Streamlit pour faire plus pro */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- 1. LE CADRE (TEXTE DU PITCH) ---
st.markdown("""
    <div class="main-frame">
        <div class="title-line">Personne ne lit les comptes de sa copropriété. Nous, si.</div>
        <div class="body-text">
            Comptes indéchiffrables, erreurs invisibles, manque de temps, d’appétence...<br>
            Notre outil fait le travail à votre place: déposez simplement le Grand Livre et les relevés bancaires de la copropriété, et notre algorithme vous dit exactement où regarder.<br><br>
            Une analyse rigoureuse en moins de 5 minutes, gratuitement.<br>
            La transparence et la simplicité que vous méritez pour poser les bonnes questions à votre syndic.
        </div>
        <div class="highlight-line">Reprenez le contrôle !</div>
    </div>
    """, unsafe_allow_html=True)

# --- 2. LES ZONES D'UPLOAD (CÔTE À CÔTE) ---
st.markdown('<div class="upload-section">', unsafe_allow_html=True)
col1, col2 = st.columns(2)

with col1:
    st.markdown("**1. Grand Livre comptable**")
    gl_file = st.file_uploader("Glisser le PDF ici", type=["pdf"], key="gl", label_visibility="collapsed")

with col2:
    st.markdown("**2. Relevés Bancaires (les 12)**")
    rb_files = st.file_uploader("Glisser les PDF ici", type=["pdf"], accept_multiple_files=True, key="rb", label_visibility="collapsed")
st.markdown('</div>', unsafe_allow_html=True)

# --- 3. LE BOUTON D'ACTION ---
# Centré sous les deux colonnes
_, btn_col, _ = st.columns([1, 2, 1])
with btn_col:
    if st.button("Lancer l'analyse technique"):
        if gl_file and len(rb_files) == 12:
            st.success("Analyse lancée...")
        else:
            st.error("Documents manquants (Grand Livre + 12 relevés requis).")

# --- 4. LE DISCLAIMER TOUT EN BAS ---
st.markdown("""
    <div style="font-size: 0.75rem; color: #94a3b8; text-align: center; max-width: 900px; margin: 60px auto 20px auto; line-height: 1.2;">
        <b>Disclaimer :</b> Je suis un assistant informatique conçu pour accompagner le Conseil Syndical. Mon intervention ne se substitue pas au pouvoir de contrôle des membres du Conseil ni à l'expertise du syndic. Les éléments présentés sont des pistes d'investigation. Aucune donnée n'est conservée. 
        Prototype gratuit : gael_maugendre@hotmail.com | +33 6 14 29 80 29
    </div>
    """, unsafe_allow_html=True)
