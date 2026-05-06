import streamlit as st
import os
import shutil
import pandas as pd
import io
import json
from json_repair import repair_json
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from google import genai
from google.genai import types
from thefuzz import fuzz
from scipy.optimize import linear_sum_assignment
from fpdf import FPDF
from pypdf import PdfWriter
import matplotlib
matplotlib.use('Agg')  # Indispensable pour Streamlit
import matplotlib.pyplot as plt
import re
import time

# --- CONFIGURATION ---
st.set_page_config(page_title="Audit Compta Automatisé", layout="wide")

UPLOAD_DIR = "storage_compta"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

"""
GEMINI_MODEL="gemini-2.5-flash"
API_KEY = st.secrets["GEMINI_API_KEY1"]
client = genai.Client(api_key=API_KEY, http_options={'api_version': 'v1beta'})
"""
GEMINI_MODEL="gemini-1.5-flash"
API_KEY = st.secrets["GEMINI_API_KEY1"]
client = genai.Client(api_key=API_KEY, http_options={'api_version': 'v1'})

THRESHOLD_FUZZ=85

#POUR PATIENTER SI GEMINI EST EN PERIODE DE FORTE AFFLUENCE
MAX_RETRIES = 1 #Nombre d'essais en tout pour chaque appel IA
WAIT_MINUTES = 5 #Temps d'attente avant ré-essai en minutes

##############################################################################################################################################################"

# --- FONCTIONS UTILITAIRES ---

def save_uploaded_file(uploaded_file, sub):
    p = Path(UPLOAD_DIR) / sub / uploaded_file.name
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f: f.write(uploaded_file.getbuffer())
    return p

# FONCTION DE FUSION DES RELEVES DE COMPTE PDF
def merge_pdfs(uploaded_files, sub):
    merger = PdfWriter()
    for pdf in uploaded_files:
        merger.append(pdf)

    output_path = Path(UPLOAD_DIR) / sub / "releves_fusionnes.pdf"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "wb") as f:
        merger.write(f)
    return output_path

##############################################################################################################################################################"

# --- FONCTIONS D'EXTRACTION ---

def convert_pdf_to_excel(pdf_path):
    for attempt in range(MAX_RETRIES):
        try:
            prompt = """Agis comme un extracteur de données comptables de haute précision.
            Analyse ce fichier PDF et extrais chaque écriture comptable.
            Continuité : Identifie les tableaux scindés par des sauts de page et fusionne-les de manière fluide sans répéter les en-têtes.
            Extrait ces données dans excel en retenant uniquement les colonnes: NUMERO_COMPTE | NOM_COMPTE | DATE | PIECE | CODE_JOURNAL_(JNL) | CONTREPARTIE | LIBELLE | DEBIT | CREDIT.
            Si les colonnes NUMERO_COMPTE ou NOM_COMPTE ne sont pas indiquées pour chaque écriture dans le fichier source, va chercher les informations dans l'en-tête de chaque bloc.
            Si les colonnes CODE_JOURNAL (JNL) ou CONTREPARTIE ne sont pas disponibles, laisse les vides.
            Mets les en-têtes des colonnes NUMERO_COMPTE | NOM_COMPTE | DATE | PIECE | CODE_JOURNAL_(JNL) | CONTREPARTIE | LIBELLE | DEBIT | CREDIT en première ligne.
            Les dates doivent être au format date JJ/MM/AAAA.
            Nettoyage : Supprime les symboles monétaires (€, $) et les séparateurs de milliers. Le séparateur de décimales doient être un point. Les nombres doivent être au format numérique.
            Les écritures dont le libellé est 'Report' ou 'Report a nouveau' ou 'A nouveau' en début de bloc doivent être identifiées le cas échéant par AN dans la colonne CODE JOURNAL (JNL).
            Réponds EXCLUSIVEMENT sous forme d'une liste JSON d'objets avec les clés suivantes : NUMERO_COMPTE, NOM_COMPTE, DATE (JJ/MM/AAAA), PIECE, CODE_JOURNAL, CONTREPARTIE, LIBELLE, DEBIT, CREDIT. N'affiche aucun texte avant ou après le JSON."""
    
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[
                    types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                    prompt
                ],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
    
            # Réparation du JSON en cas d'erreur de formatage (gestion des guillemets/virgules mal placés)
            json_propre = repair_json(response.text)
            data = json.loads(json_propre)
            if isinstance(data, list):
                df = pd.DataFrame(data)
            elif isinstance(data, dict):
                # Si Gemini renvoie un dictionnaire au lieu d'une liste, on essaie de trouver la clé qui contient la liste ou on l'encapsule
                df = pd.DataFrame([data])
            else:
                raise ValueError("Le format JSON reçu n'est ni une liste ni un dictionnaire")
    
            if 'DEBIT' in df.columns: df['DEBIT'] = pd.to_numeric(df['DEBIT'], errors='coerce').fillna(0)
            if 'CREDIT' in df.columns: df['CREDIT'] = pd.to_numeric(df['CREDIT'], errors='coerce').fillna(0)
            if 'DATE' in df.columns: df['DATE'] = pd.to_datetime(df['DATE'], dayfirst=True, errors='coerce')
            return df
            
        except Exception as e:
            if "429" in str(e):
                st.error("🚨 QUOTA ÉPUISÉ : Le moteur a atteint sa limite quotidienne. Réessayez demain.")
                st.stop()
            elif "503" in str(e):
                if attempt < MAX_RETRIES - 1:
                    st.warning(f"⏳ FORTE AFFLUENCE sur le moteur, nouvelle tentative automatique dans {WAIT_MINUTES} minute(s)... (essai {attempt + 1}/{RIES})")
                    time.sleep(WAIT_MINUTES * 60)
                else:
                    st.error("🚨 ACTIVITÉ EXCEPTIONNELLE : Le moteur a atteint ses limites de capacité en raison d'une forte affluence. Réessayez plus tard.")
                    st.stop()
            else:
                st.error(f" Erreur technique : {e}")
            
    return pd.DataFrame()

def extract_releve_data(pdf_path):
    for attempt in range(MAX_RETRIES):
        try:
            prompt = """Agis comme un extracteur de données comptables de haute précision. Analyse ce fichier PDF et extrais chaque transaction.
                        Structure des colonnes : DATE | LIBELLE | DEBIT | CREDIT. Affiche ces 4 mots d'en-tête de colonnes dans la première ligne uniquement.
                        Règles impératives :
                        Continuité : Identifie les tableaux scindés par des sauts de page et fusionne-les de manière fluide sans répéter les en-têtes. N'affiche aucun ligne de total.
                        Analyse de position : Identifie rigoureusement la position horizontale des colonnes. Si une valeur est sous l'en-tête DEBIT, elle doit rester dans la colonne DEBIT. Utilise tes capacités de vision pour tracer une ligne verticale imaginaire entre la colonne DEBIT et CREDIT: ne mélange jamais les deux.
                        Une ligne ne peut avoir qu'un seul montant (soit débit, soit crédit). L'autre doit être 0.00.
                        Nettoyage : Supprime les symboles monétaires (€, $) et les séparateurs de milliers. Les nombres doivent être au format 1234.56.
                        Format de date : Utilise le format JJ/MM/AAAA.
                        SORTIE : Réponds EXCLUSIVEMENT sous forme d'une liste JSON d'objets avec ces clés :
                        DATE (JJ/MM/AAAA), LIBELLE, DEBIT, CREDIT.
                        N'affiche aucun texte avant ou après le JSON."""
    
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[
                    types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                    prompt
                ],
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
    
            # Réparation du JSON en cas d'erreur de formatage (gestion des guillemets/virgules mal placés)
            json_propre = repair_json(response.text)
            data = json.loads(json_propre)
            if isinstance(data, list):
                df = pd.DataFrame(data)
            elif isinstance(data, dict):
                # Si Gemini renvoie un dictionnaire au lieu d'une liste, on essaie de trouver la clé qui contient la liste ou on l'encapsule
                df = pd.DataFrame([data])
            else:
                raise ValueError("Le format JSON reçu n'est ni une liste ni un dictionnaire")
    
            if 'DEBIT' in df.columns: df['DEBIT'] = pd.to_numeric(df['DEBIT'], errors='coerce').fillna(0)
            if 'CREDIT' in df.columns: df['CREDIT'] = pd.to_numeric(df['CREDIT'], errors='coerce').fillna(0)
            if 'DATE' in df.columns: df['DATE'] = pd.to_datetime(df['DATE'], dayfirst=True, errors='coerce')
            return df
    
        except Exception as e:
            if "429" in str(e):
                st.error("🚨 QUOTA ÉPUISÉ : Le moteur a atteint sa limite quotidienne. Réessayez demain.")
                st.stop()
            elif "503" in str(e):
                if attempt < MAX_RETRIES - 1:
                    st.warning(f"⏳ FORTE AFFLUENCE sur le moteur, nouvelle tentative automatique dans {WAIT_MINUTES} minute(s)... (essai {attempt + 1}/{RIES})")
                    time.sleep(WAIT_MINUTES * 60)
                else:
                    st.error("🚨 ACTIVITÉ EXCEPTIONNELLE : Le moteur a atteint ses limites de capacité en raison d'une forte affluence. Réessayez plus tard.")
                    st.stop()
            else:
                st.error(f" Erreur technique : {e}")
            
    return pd.DataFrame()



def extraire_grille_tarifaire_universelle(uploaded_file):
    """
    Extrait les tarifs du contrat et les range dans une grille fixe, 
    indépendamment de la formulation utilisée par le syndic.
    En sortie, on a des tarifs du type (exemples ci-dessous mais les tarifs sont lus dans le contrat):
    JSON
    "forfait_annuel": 20700.0,
    "vacation_horaire": 165.0,
    "mise_en_demeure": 45.0,
    "relance_simple": 33.0,
    "etat_date": 380.0,
    "opposition_mutation": 192.0,
    "mise_en_demeure_tiers": 50.0,
    "injonction_payer": 200.0,
    "reprise_compta_forfait": 500.0,
    "ag_supplementaire": 800.0,
    "copie_pv": 30.0   
    """
    # Lecture des octets directement depuis la mémoire
    pdf_bytes = uploaded_file.read() 
    
    # Remise à zéro du pointeur (bonne pratique Streamlit si vous relisez le fichier plus tard)
    uploaded_file.seek(0)
    
    # Grille de référence (Clés fixes pour Python : Description pour l'IA)
    grille_reference = {
        "forfait_annuel": "Rémunération forfaitaire annuelle",
        "vacation_horaire": "Coût horaire pour prestations particulières (prorata du temps passé)",
        "mise_en_demeure": "Mise en demeure par lettre recommandée AR",
        "relance_simple": "Relance après mise en demeure",
        "etat_date": "Établissement de l'état daté (montant maximum)",
        "opposition_mutation": "Opposition sur mutation",
        "mise_en_demeure_tiers": "Mise en demeure d'un tiers par lettre recommandée AR",
        "injonction_payer": "Dépôt d'une requête en injonction de payer",
        "reprise_compta_forfait": "Reprise de comptabilité sur exercices antérieurs (forfait)",
        "ag_supplementaire": "Assemblée générale supplémentaire (par lot, min. 800 € TTC)",
        "copie_pv": "Délivrance d'une copie certifiée conforme d'un PV d'AG"
    } 

    prompt = f"""
    Agis comme un expert en audit de copropriété. Ton objectif est d'extraire les tarifs d'un contrat de syndic pour remplir une grille standardisée.
    
    VOICI LA GRILLE DE DESTINATION (Clé : Description du tarif à chercher) :
    {json.dumps(grille_reference, ensure_ascii=False, indent=2)}

    RÈGLES CRITIQUES :
    1. SYNONYMES : Le syndic peut utiliser des termes différents. Analyse le sens pour remplir la bonne clé (ex: "Honoraires de base" -> "forfait_annuel").
    2. MONTANTS : Extrais uniquement des nombres (float). Si un tarif est au forfait + au lot, extrais la part fixe pour le forfait.
    3. TVA : Extrais toujours le montant TTC. Si seul le HT est écrit, calcule TTC = HT * 1.20.
    4. ABSENCE : Si un tarif n'est pas mentionné ou si la prestation est gratuite/incluse, inscris 0.0.
    5. FORMAT : Retourne UNIQUEMENT un objet JSON dont les clés sont celles de ma grille.
    """
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[
                    types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                    prompt
                ],
                config=types.GenerateContentConfig(response_mime_type="application/json")
                )
            return json.loads(response.text)
        except Exception as e:
            if "429" in str(e):
                st.error("🚨 QUOTA ÉPUISÉ : Le moteur a atteint sa limite quotidienne. Réessayez demain.")
                st.stop()
            elif "503" in str(e):
                if attempt < MAX_RETRIES - 1:
                    st.warning(f"⏳ FORTE AFFLUENCE sur le moteur, nouvelle tentative automatique dans {WAIT_MINUTES} minute(s)... (essai {attempt + 1}/{MAX_RETRIES})")
                    time.sleep(WAIT_MINUTES * 60)
                else:
                    st.error("🚨 ACTIVITÉ EXCEPTIONNELLE : Le moteur a atteint ses limites de capacité en raison d'une forte affluence. Réessayez plus tard.")
                    st.stop()
            else:
                st.error(f" Erreur technique : {e}")
    return {}


##############################################################################################################################################################"

# --- MOTEUR D'AUDIT ---

def generer_rapport_audit(df_gl, df_bank, df_contrat):
    r = [] 
    date_min = df_gl['DATE'].min() if ('DATE' in df_gl.columns and not df_gl['DATE'].dropna().empty) else datetime.now()
    date_ref = df_gl['DATE'].max() if ('DATE' in df_gl.columns and not df_gl['DATE'].dropna().empty) else datetime.now()
    
    r.append("="*80)
    r.append(f"RAPPORT D'AUDIT COMPTABLE - GÉNÉRÉ LE {datetime.now().strftime('%d/%m/%Y')}")
    r.append(f"Période analysée du {date_min.strftime('%d/%m/%Y')} au {date_ref.strftime('%d/%m/%Y')}")
    r.append("="*80 + "\n")

    # --- BUDGET ET COMPTEUR D'ANOMALIES ---
    total_anomalies = 0.0
    # Budget = somme des appels de fonds sur opérations courantes (crédits des comptes 701xxx)
    budget = 0.0
    if 'NUMERO_COMPTE' in df_gl.columns and 'CREDIT' in df_gl.columns:
        df_701 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('701')]
        budget = df_701['CREDIT'].sum()
    
    # --- SECTION A : TROP-PAYÉS ---
    r.append("[SECTION A] ANALYSE DES TROP-PAYÉS")
    r.append("Ce contrôle identifie les fournisseurs dont le solde est débiteur. Cela révèle des factures payées plusieurs fois")
    r.append(" ou des avoirs non récupérés, représentant une trésorerie perdue pour la copropriété.\n")
    if 'NUMERO_COMPTE' in df_gl.columns:
        df_401 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('401')].copy()
        if not df_401.empty:
            synthese_401 = df_401.groupby(['NUMERO_COMPTE', 'NOM_COMPTE']).agg({'DEBIT': 'sum', 'CREDIT': 'sum'}).reset_index()
            synthese_401['SOLDE'] = synthese_401['CREDIT'] - synthese_401['DEBIT']
            trop_payes = synthese_401[synthese_401['SOLDE'] < -1.00]
            if not trop_payes.empty:
                for _, row in trop_payes.iterrows():
                    r.append(f"{row['NOM_COMPTE']} : {abs(row['SOLDE']):.2f}€ à récupérer.")
                    total_anomalies += abs(row['SOLDE'])
            else:
                r.append("    Aucun trop-payé détecté.")
        else:
            r.append("    Aucun fournisseur détecté.")
    else:
        r.append("Données insuffisantes pour l'analyse des trop-payés.")

    # --- SECTION B : DOUBLONS ---
    r.append("\n" + "="*80)
    r.append("[SECTION B] ANALYSE DES DOUBLONS")
    r.append(" Recherche des écritures de charges identiques (montant et compte) sur la période.")
    r.append("   L'objectif est de détecter des saisies multiples d'une même facture.\n")
    if 'NUMERO_COMPTE' in df_gl.columns and 'DEBIT' in df_gl.columns:
        df_6 = df_gl[(df_gl['NUMERO_COMPTE'].astype(str).str.startswith('6')) & (df_gl['DEBIT'] > 0)]
        doublons = df_6[df_6.duplicated(subset=['DEBIT', 'NUMERO_COMPTE'], keep=False)]
        if not doublons.empty:
            r.append(f"    {len(doublons)//2} alertes de doublons potentiels identifiées.")
            total_anomalies += doublons['DEBIT'].sum() / 2
        else:
            r.append("    Aucun doublon détecté.")
    else:
        r.append("Données insuffisantes pour l'analyse des doublons.")

    # --- SECTION C : IMPAYÉS FOURNISSEURS ---
    r.append("\n" + "="*80)
    r.append("[SECTION C] ANALYSE DES IMPAYÉS (> 3 MOIS)")
    r.append(" Liste les factures en attente de paiement depuis plus de 90 jours.")
    r.append(" Un volume élevé indique un risque de contentieux ou une rupture de trésorerie.\n")
    if 'NUMERO_COMPTE' in df_gl.columns:
        df_401 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('401')].copy()
        alertes_impayes = []
        for compte in df_401['NUMERO_COMPTE'].unique():
            sub = df_401[df_401['NUMERO_COMPTE'] == compte]
            if (sub['CREDIT'].sum() - sub['DEBIT'].sum()) > 1.00:
                factures = sub[sub['CREDIT'] > 0]
                for _, f in factures.iterrows():
                    if pd.notnull(f['DATE']):
                        delta_j = (date_ref - pd.to_datetime(f['DATE'])).total_seconds() / 86400
                        if delta_j > 90:
                            alertes_impayes.append(f)
        if alertes_impayes:
            for a in alertes_impayes[:10]:
                r.append(f"{a['NOM_COMPTE'][:20]:<20} | {a['DATE'].strftime('%d/%m/%Y')} | {a['CREDIT']:>8.2f}€")
                total_anomalies += a['CREDIT']
        else:
            r.append("    Aucune facture ancienne en attente.")
    else:
        r.append("    Données insuffisantes pour l'analyse des impayés.")


    
    # --- SECTION D : COMPTES D'ATTENTE (471 & 472) ---
    r.append("\n" + "="*80)
    r.append("[SECTION D] ANALYSE DYNAMIQUE DES COMPTES D'ATTENTE (471 & 472)")
    r.append("L'analyse ne se limite pas au solde final mais examine les flux durant l'exercice")
    r.append("pour détecter des retards de traitement ou des régularisations massives de fin d'année.\n")
    
    if 'NUMERO_COMPTE' in df_gl.columns and 'DATE' in df_gl.columns:
        for racine in ['471', '472']:
            # Filtrage et préparation des données
            df_attente = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith(racine)].copy()
            df_attente['DATE'] = pd.to_datetime(df_attente['DATE'], errors='coerce')
            df_attente = df_attente.dropna(subset=['DATE']).sort_values('DATE')
    
            if not df_attente.empty:
                # 1. Analyse du Solde Final
                solde_final = df_attente['CREDIT'].sum() - df_attente['DEBIT'].sum()
                total_anomalies += abs(solde_final)
                
                # 2. Calcul du Pic de Trésorerie (Le montant max qui a "traîné")
                df_attente['FLUX'] = df_attente['CREDIT'] - df_attente['DEBIT']
                df_attente['SOLDE_CHRONO'] = df_attente['FLUX'].cumsum()
                pic_max = df_attente['SOLDE_CHRONO'].abs().max()
                date_pic = df_attente.loc[df_attente['SOLDE_CHRONO'].abs().idxmax(), 'DATE']
    
                # 3. Analyse du "Nettoyage" de fin d'année
                # On regarde les mouvements dans les 30 derniers jours avant la clôture
                date_cloture = df_attente['DATE'].max()
                seuil_fin_annee = date_cloture - pd.Timedelta(days=30)
                flux_fin_annee = df_attente[df_attente['DATE'] >= seuil_fin_annee]['FLUX'].abs().sum()
                flux_total = df_attente['FLUX'].abs().sum()
                ratio_nettoyage = (flux_fin_annee / flux_total * 100) if flux_total > 0 else 0
    
                # --- AFFICHAGE DES RÉSULTATS ---
                r.append(f"--- ANALYSE DU COMPTE {racine} ---")
                
                # État final
                type_solde = "CRÉDITEUR" if solde_final > 0 else "DÉBITEUR"
                r.append(f"Solde au bilan : {abs(solde_final):.2f}€ ({type_solde if abs(solde_final) > 5 else 'Soldé'})")
    
                # Alerte Pic
                if pic_max > 5000: # Seuil d'alerte à adapter
                    r.append(f"Point de vigilance : Pic de {pic_max:.2f}€ atteint le {date_pic.strftime('%d/%m/%Y')}.")
                
                # Alerte Nettoyage Tardif
                if ratio_nettoyage > 50 and abs(solde_final) < 100:
                    r.append(f"ALERTE COSMÉTIQUE : {ratio_nettoyage:.1f}% des écritures ont été régularisées dans les 30 derniers jours. Nettoyage tardif des comptes.")
    
                # 4. Détail des écritures anciennes (plus de 180 jours)
                # Utilisation de date_ref si définie, sinon la date max du dataframe
                d_ref = date_ref if 'date_ref' in locals() else df_attente['DATE'].max()
                ecritures_anciennes = df_attente[(d_ref - df_attente['DATE']).dt.days > 180]
                
                if not ecritures_anciennes.empty and abs(solde_final) > 5:
                    r.append(f"NÉGLIGENCE : {len(ecritures_anciennes)} ligne(s) stagnent depuis plus de 6 mois.")
                    for _, row in ecritures_anciennes.tail(5).iterrows(): # On montre les 5 plus vieilles
                        r.append(f"   - {row['DATE'].strftime('%d/%m/%Y')} | {max(row['DEBIT'], row['CREDIT']):.2f}€ | {row['LIBELLE'][:40]}")
                
                r.append("") # Espace entre 471 et 472
            else:
                r.append(f"COMPTE {racine} : Aucun mouvement détecté.")
    else:
        r.append("Données (Colonnes NUMERO_COMPTE ou DATE) manquantes pour l'analyse dynamique.")

    

    
    # --- SECTION E : ANALYSE DES TIERS (461 & 462) ---
    r.append("\n" + "="*80)
    r.append("[SECTION F] ANALYSE DES TIERS ET LITIGES (461 & 462)")
    r.append(" Surveille les créances sur tiers et les dossiers au contentieux.")
    r.append(" Un solde créditeur ici est anormal et indique souvent une erreur d'affectation de paiement.\n")
    if 'NUMERO_COMPTE' in df_gl.columns:
        for racine in ['461', '462']:
            df_tiers = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith(racine)].copy()
            if not df_tiers.empty:
                solde_net = df_tiers['DEBIT'].sum() - df_tiers['CREDIT'].sum()
                if racine == '461':
                    r.append("Compte 461 — Débiteurs divers : doit normalement être débiteur (sommes à recevoir).")
                    if solde_net < -1.00:
                        r.append(f"    ANOMALIE : Solde CRÉDITEUR de {abs(solde_net):.2f}€ (illogique pour ce compte).")
                    else:
                        r.append(f"    Solde actuel : {solde_net:.2f}€ (Débiteur).")
                    
                    if 'DATE' in df_tiers.columns:
                        df_tiers['DATE'] = pd.to_datetime(df_tiers['DATE'], errors='coerce')
                        anciennes_461 = df_tiers[(date_ref - df_tiers['DATE']).dt.days > 365]
                        if not anciennes_461.empty:
                            r.append(f"    ATTENTION : {len(anciennes_461)} créance(s) de plus d'un an.")

                elif racine == '462':
                    r.append(" Compte 462 — Copropriétaires douteux : créances transférées pour recouvrement.")
                    if solde_net < -1.00:
                        r.append(f"    ANOMALIE : Solde CRÉDITEUR de {abs(solde_net):.2f}€ (paiement mal affecté ?).")
                    else:
                        r.append(f"    Encours contentieux total : {solde_net:.2f}€.")
                    
                    if 'DATE' in df_tiers.columns:
                        df_tiers['DATE'] = pd.to_datetime(df_tiers['DATE'], errors='coerce')
                        anciennes_462 = df_tiers[(date_ref - df_tiers['DATE']).dt.days > 730]
                        if not anciennes_462.empty:
                            r.append(f"    ATTENTION : {len(anciennes_462)} dossier(s) en litige depuis plus de 2 ans.")
            else:
                r.append(f"    COMPTE {racine} : Aucun mouvement détecté.")
    else:
        r.append("Données insuffisantes pour l'analyse des tiers.")


    
    
    # --- SECTION F : RAPPROCHEMENT BANCAIRE COMPLET ---
    r.append("\n" + "="*80)
    r.append("[SECTION G] RAPPROCHEMENT BANCAIRE (SORTIES ET ENTRÉES)")
    r.append(" Compare ligne à ligne la banque et la comptabilité (Compte 512).")
    r.append(" Rappel : Un CRÉDIT en banque est un DÉBIT en comptabilité (Encaissement).")
    r.append("-" * 80 + "\n")

    DAYS_WINDOW        = 30  # tolérance de date pour le matching 1-to-1 et seuil d'alerte
    DAYS_WINDOW_GROUPE = 7   # tolérance de date pour la recherche de groupements

    # ------------------------------------------------------------------ #
    # Fonction utilitaire : recherche de sous-ensemble (branch & bound)   #
    # ------------------------------------------------------------------ #
    def _trouver_sous_ensemble(gl_v, candidats, cible, tolerance=0.01, max_iter=2000):
        """
        Recherche un sous-ensemble de candidats (indices dans gl_v) dont la somme
        des montants (gl_v[i, 0]) est égale à `cible` à `tolerance` près.
        Retourne la liste des indices GL, ou None si introuvable.
        """
        montants = [gl_v[i, 0] for i in candidats]
        n = len(montants)

        # Suffixes cumulatifs pour l'élagage (somme max restante)
        suffixes = [0.0] * (n + 1)
        for k in range(n - 1, -1, -1):
            suffixes[k] = suffixes[k + 1] + montants[k]

        iterations = [0]

        def backtrack(start, somme_courante, chemin):
            iterations[0] += 1
            if iterations[0] > max_iter:
                return None
            if abs(somme_courante - cible) <= tolerance:
                return chemin[:]
            if start == n:
                return None
            # Élagage : même en prenant tout le reste on ne peut pas atteindre la cible
            if somme_courante + suffixes[start] < cible - tolerance:
                return None
            # Élagage : la somme courante dépasse déjà la cible
            if somme_courante > cible + tolerance:
                return None
            for k in range(start, n):
                chemin.append(candidats[k])
                res = backtrack(k + 1, somme_courante + montants[k], chemin)
                if res is not None:
                    return res
                chemin.pop()
            return None

        return backtrack(0, 0.0, [])

    # ------------------------------------------------------------------ #
    # Fonction principale de rapprochement                                #
    # ------------------------------------------------------------------ #
    def effectuer_rapprochement_complet(df_gl_sub, df_bk_sub, label_gl, label_bk, col_gl_val, col_bk_val):
        nonlocal total_anomalies

        if df_gl_sub.empty and df_bk_sub.empty:
            r.append(f"Aucune écriture à rapprocher pour les {label_gl.lower()}.")
            return

        if df_gl_sub.empty or df_bk_sub.empty:
            if not df_gl_sub.empty:
                r.append(f"TOUTES les écritures de {label_gl} sont absentes en banque.")
            if not df_bk_sub.empty:
                r.append(f"TOUTES les écritures de {label_bk} sont absentes en comptabilité.")
            return

        gl_v = df_gl_sub[[col_gl_val, 'DATE', 'LIBELLE']].reset_index(drop=True).values
        bk_v = df_bk_sub[[col_bk_val, 'DATE', 'LIBELLE']].reset_index(drop=True).values
        n, m = len(gl_v), len(bk_v)

        # ------------------------------------------------------------------ #
        # PHASE 1 — Matching 1-to-1 (algorithme hongrois)                    #
        # Un match est refusé (coût = 1 000 000) si l'écart de dates         #
        # dépasse DAYS_WINDOW : l'écriture tombe alors dans les restes.      #
        # ------------------------------------------------------------------ #
        cost_matrix = np.full((n, m), 1_000_000.0)

        for i in range(n):
            for j in range(m):
                if abs(gl_v[i, 0] - bk_v[j, 0]) < 0.01:
                    if pd.notnull(gl_v[i, 1]) and pd.notnull(bk_v[j, 1]):
                        ecart = abs((gl_v[i, 1] - bk_v[j, 1]).days)
                        cost_matrix[i, j] = ecart if ecart <= DAYS_WINDOW else 1_000_000.0
                    else:
                        cost_matrix[i, j] = 0  # date manquante : on accepte sans pénalité

        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        gl_matched_idx = set()
        bk_matched_idx = set()
        alertes_dates  = []

        for i, j in zip(row_ind, col_ind):
            if cost_matrix[i, j] < 1_000_000:
                gl_matched_idx.add(i)
                bk_matched_idx.add(j)
                if cost_matrix[i, j] > DAYS_WINDOW:
                    # Ne peut plus arriver avec la logique ci-dessus,
                    # mais on garde la garde-fou par cohérence
                    alertes_dates.append({
                        'date_gl': gl_v[i, 1], 'date_bk': bk_v[j, 1],
                        'montant': gl_v[i, 0],  'libelle': gl_v[i, 2],
                        'jours':   int(cost_matrix[i, j]),
                    })

        # Restes après matching 1-to-1
        restes_gl = [i for i in range(n) if i not in gl_matched_idx]
        restes_bk = [j for j in range(m) if j not in bk_matched_idx]

        # ------------------------------------------------------------------ #
        # PHASE 2 — Détection des groupements parmi les restes uniquement    #
        # Cherche : N lignes GL dont la somme = 1 ligne Banque               #
        # La fenêtre DAYS_WINDOW_GROUPE est volontairement plus stricte :    #
        # un prélèvement groupé est toujours exécuté en quelques jours.      #
        # ------------------------------------------------------------------ #
        groupes_detectes = []

        for j in restes_bk[:]:  # copie car on modifie restes_bk en cours de boucle
            bk_montant = bk_v[j, 0]
            bk_date    = bk_v[j, 1]

            # Candidats GL : restes dans la fenêtre stricte
            candidats = [
                i for i in restes_gl
                if not (pd.notnull(bk_date) and pd.notnull(gl_v[i, 1])
                        and abs((gl_v[i, 1] - bk_date).days) > DAYS_WINDOW_GROUPE)
            ]

            if len(candidats) < 2:
                continue

            groupe = _trouver_sous_ensemble(gl_v, candidats, bk_montant)

            if groupe and len(groupe) >= 2:
                for i in groupe:
                    restes_gl.remove(i)
                restes_bk.remove(j)
                gl_matched_idx.update(groupe)
                bk_matched_idx.add(j)
                groupes_detectes.append({
                    'bk_date':    bk_date,
                    'bk_montant': bk_montant,
                    'bk_libelle': bk_v[j, 2],
                    'gl_indices': groupe,
                })

        # ------------------------------------------------------------------ #
        # PHASE 3 — Affichage                                                 #
        # ------------------------------------------------------------------ #

        # --- Alertes délais (matches 1-to-1 hors fenêtre) ---
        if alertes_dates:
            r.append(f"ÉCARTS DE DATES ANORMAUX (> {DAYS_WINDOW} jours) :")
            for a in sorted(alertes_dates,
                            key=lambda x: x['date_gl'] if pd.notnull(x['date_gl'])
                                          else pd.Timestamp.min):
                r.append(
                    f"      - {a['date_gl'].strftime('%d/%m/%Y')} | {a['montant']:>8.2f}€ "
                    f"| {a['jours']}j d'écart (Banque: {a['date_bk'].strftime('%d/%m')}) "
                    f"| {a['libelle'][:30]}"
                )

        # --- Groupements réconciliés ---
        if groupes_detectes:
            r.append(f"ÉCRITURES GROUPÉES RÉCONCILIÉES ({len(groupes_detectes)}) :")
            for g in sorted(groupes_detectes,
                            key=lambda x: x['bk_date'] if pd.notnull(x['bk_date'])
                                          else pd.Timestamp.min):
                d = g['bk_date'].strftime('%d/%m/%Y') if pd.notnull(g['bk_date']) else "N/A"
                r.append(
                    f"      ► {d} | {g['bk_montant']:>8.2f}€ (banque) "
                    f"← {len(g['gl_indices'])} ligne(s) compta | {g['bk_libelle'][:40]}"
                )
                for i in sorted(g['gl_indices'],
                                key=lambda idx: gl_v[idx, 1] if pd.notnull(gl_v[idx, 1])
                                                else pd.Timestamp.min):
                    dg = gl_v[i, 1].strftime('%d/%m/%Y') if pd.notnull(gl_v[i, 1]) else "N/A"
                    r.append(f"          {dg} | {gl_v[i, 0]:>8.2f}€ | {gl_v[i, 2][:40]}")

        # --- Anomalies résiduelles : présence compta / absence banque ---
        absent_banque = [i for i in range(n) if i not in gl_matched_idx]
        if absent_banque:
            r.append(f"PRÉSENCE EN COMPTABILITÉ / ABSENCE EN BANQUE :")
            for i in sorted(absent_banque,
                            key=lambda idx: gl_v[idx, 1] if pd.notnull(gl_v[idx, 1])
                                            else pd.Timestamp.min):
                d = gl_v[i, 1].strftime('%d/%m/%Y') if pd.notnull(gl_v[i, 1]) else "N/A"
                r.append(f"    - {d} | {gl_v[i, 0]:>8.2f}€ | {gl_v[i, 2]}")
                total_anomalies += gl_v[i, 0]

        # --- Anomalies résiduelles : présence banque / absence compta ---
        absent_compta = [j for j in range(m) if j not in bk_matched_idx]
        if absent_compta:
            r.append(f"PRÉSENCE EN BANQUE / ABSENCE EN COMPTABILITÉ :")
            for j in sorted(absent_compta,
                            key=lambda idx: bk_v[idx, 1] if pd.notnull(bk_v[idx, 1])
                                            else pd.Timestamp.min):
                d = bk_v[j, 1].strftime('%d/%m/%Y') if pd.notnull(bk_v[j, 1]) else "N/A"
                r.append(f"    - {d} | {bk_v[j, 0]:>8.2f}€ | {bk_v[j, 2]}")
                total_anomalies += bk_v[j, 0]

        # --- Conclusion ---
        if not any([alertes_dates, groupes_detectes, absent_banque, absent_compta]):
            r.append(f"Rapprochement parfait pour les {label_gl.lower()}.")
        elif not absent_banque and not absent_compta:
            r.append(
                f"Rapprochement complet "
                f"(dont {len(groupes_detectes)} écriture(s) groupée(s) réconciliée(s))."
            )

    # ------------------------------------------------------------------ #
    # PRÉPARATION DES DONNÉES ET APPELS                                   #
    # ------------------------------------------------------------------ #
    if 'NUMERO_COMPTE' in df_gl.columns and 'DATE' in df_gl.columns and not df_bank.empty:

        gl_clean = df_gl.copy()
        gl_clean['DATE'] = pd.to_datetime(gl_clean['DATE'], errors='coerce')

        bk_clean = df_bank.copy()
        bk_clean['DATE'] = pd.to_datetime(bk_clean['DATE'], errors='coerce')

        # Filtrage du compte 512
        mask_512 = gl_clean['NUMERO_COMPTE'].astype(str).str.startswith('512')
        df_512   = gl_clean[mask_512].copy()

        # 1. ENCAISSEMENTS — Débit 512 (compta) vs Crédit banque
        r.append("--- ENCAISSEMENTS (Paiements copropriétaires, etc.) ---")
        gl_e = df_512[df_512['DEBIT'] > 0.001].copy()
        bk_e = bk_clean[bk_clean['CREDIT'] > 0.001].copy()
        effectuer_rapprochement_complet(gl_e, bk_e, "Encaissements", "Banque", "DEBIT", "CREDIT")

        # 2. DÉCAISSEMENTS — Crédit 512 (compta) vs Débit banque
        r.append("\n--- DÉCAISSEMENTS (Paiements fournisseurs, etc.) ---")
        gl_d = df_512[df_512['CREDIT'] > 0.001].copy()
        bk_d = bk_clean[bk_clean['DEBIT'] > 0.001].copy()
        effectuer_rapprochement_complet(gl_d, bk_d, "Décaissements", "Banque", "CREDIT", "DEBIT")

    else:
        r.append("Données insuffisantes (Grand livre ou Relevés) pour le rapprochement.")



    # --- SECTION G : REJETS BANCAIRES ---
    r.append("\n" + "="*80)
    r.append("[SECTION D] ANALYSE DES REJETS BANCAIRES (LOGIQUE FLOUE)")
    r.append(" Vérifie que chaque incident bancaire (impayé copropriétaire) a bien été régularisé.")
    r.append(" Utilise la similarité de Levenshtein pour pallier les erreurs de lecture (OCR).\n")

    DAYS_WINDOW = 60
    
    def fuzzy_check_rejet(libelle):
        if not isinstance(libelle, str): return False
        # Liste de motifs de rejets (on peut inclure des versions avec/sans accents)
        target_keywords = ['rejet', 'impaye', 'sans provision', 'non paye', 'rejete', 'impayé']
        
        libelle_clean = libelle.lower()
        
        # On utilise partial_ratio car le mot "rejet" est souvent au milieu d'une longue phrase
        # exemple: "PRLV SEPA REJET DE M. DUPONT"
        for kw in target_keywords:
            if fuzz.partial_ratio(kw, libelle_clean) >= THRESHOLD_FUZZ:
                return True
        return False

    if 'LIBELLE' in df_bank.columns and 'NUMERO_COMPTE' in df_gl.columns and 'DEBIT' in df_gl.columns:
        # 1. Identification des rejets dans le relevé (Lignes au DÉBIT avec libellé "rejet")
        rejets_detectes = df_bank[df_bank['LIBELLE'].apply(fuzzy_check_rejet) & (df_bank['DEBIT'] > 0)]
        
        # 2. Identification des écritures de régularisation en compta (Débit du compte 450)
        # En compta, un rejet d'encaissement se traduit par un nouveau débit au compte du copropriétaire
        df_450 = df_gl[(df_gl['NUMERO_COMPTE'].astype(str).str.startswith('450')) & (df_gl['DEBIT'] > 0)]
        
        nb_alertes_rejets = 0
        
        for _, rej in rejets_detectes.iterrows():
            date_rej = rej['DATE']
            montant_rej = rej['DEBIT']
            
            if pd.notnull(date_rej):
                # On cherche en compta un montant identique dans les 60 jours suivant le rejet bancaire
                match = df_450[
                    (abs(df_450['DEBIT'] - montant_rej) < 0.05) & 
                    (df_450['DATE'] >= date_rej) & 
                    (df_450['DATE'] <= date_rej + timedelta(days=DAYS_WINDOW))
                ]
            else:
                match = df_450[abs(df_450['DEBIT'] - montant_rej) < 0.05]
                
            if match.empty:
                d_rej_str = date_rej.strftime('%d/%m/%Y') if pd.notnull(date_rej) else "N/A"
                r.append(f"REJET NON RÉPERCUTÉ : {d_rej_str} | {montant_rej:.2f}€ | {rej['LIBELLE']}")
                nb_alertes_rejets += 1
                # total_anomalies += montant_rej (double comptage avec le rapprochement bancaire complet sinon)
                
        if nb_alertes_rejets == 0 and not rejets_detectes.empty:
            r.append("Tous les rejets bancaires détectés ont été correctement imputés en comptabilité.")
        elif rejets_detectes.empty:
            r.append("Aucun rejet bancaire détecté sur la période.")
    else:
        r.append("Données insuffisantes pour l'analyse des rejets (colonnes manquantes).")

 
    

    # --- SECTION H : FOURNISSEURS SUSPECTS (OCCASIONNELS) ---
    r.append("\n" + "="*80)
    r.append("[SECTION H] ANALYSE DES FOURNISSEURS OCCASIONNELS (< 4 écritures/an)")
    r.append(" Isole les prestataires avec très peu d'activité. En copropriété, cela peut révéler")
    r.append(" des factures de complaisance ou des dépenses ponctuelles non mises en concurrence.\n")
    if 'NUMERO_COMPTE' in df_gl.columns:
        df_401 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('401')].copy()
        if not df_401.empty and 'CREDIT' in df_401.columns:
            df_factures = df_401[df_401['CREDIT'] > 0]
            if not df_factures.empty:
                stats_fournisseurs = df_factures.groupby(['NUMERO_COMPTE', 'NOM_COMPTE']).agg({
                    'CREDIT': ['count', 'sum', 'max'],
                    'DATE': 'max'
                }).reset_index()
                
                stats_fournisseurs.columns = ['COMPTE', 'NOM', 'NB_FACTURES', 'TOTAL_ANNUEL', 'MONTANT_MAX', 'DERNIERE_DATE']
                suspects = stats_fournisseurs[stats_fournisseurs['NB_FACTURES'] <= 3].sort_values('TOTAL_ANNUEL', ascending=False)
                
                if not suspects.empty:
                    r.append(f"{len(suspects)} fournisseur(s) à vérifier (peu d'activité annuelle) :")
                    for _, s in suspects.iterrows():
                        d_str = s['DERNIERE_DATE'].strftime('%d/%m/%Y') if pd.notnull(s['DERNIERE_DATE']) else "Inconnue"
                        r.append(f"    - {s['NOM'][:25]:<25} | {s['NB_FACTURES']} fact. | Total: {s['TOTAL_ANNUEL']:>8.2f}€ | Max: {s['MONTANT_MAX']:>8.2f}€ (Dernière: {d_str})")
                else:
                    r.append("Aucun fournisseur occasionnel détecté.")
            else:
                r.append("Aucun mouvement de facture (crédit) détecté pour les fournisseurs.")
        else:
            r.append("Aucun fournisseur détecté.")
    else:
        r.append("Données insuffisantes pour l'analyse des fournisseurs.")

    
    # --- SECTION I : CONTRÔLE DU FONDS DE TRAVAUX (LOI ALUR) ---
    r.append("\n" + "="*80)
    r.append("[SECTION I] CONTRÔLE DU FONDS DE TRAVAUX (COMPTES 105 & 502)")
    r.append(" Vérifie que les sommes appelées pour les travaux (105) sont réellement transférées")
    r.append(" sur le compte d'épargne (502). Un écart indique une utilisation illégale de ces fonds pour la gestion courante.\n")
    if 'NUMERO_COMPTE' in df_gl.columns:
        df_105 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('105')].copy()
        df_502 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('502')].copy()
        
        solde_theorique_travaux = df_105['CREDIT'].sum() - df_105['DEBIT'].sum() if not df_105.empty else 0
        solde_reel_placement = df_502['DEBIT'].sum() - df_502['CREDIT'].sum() if not df_502.empty else 0
        
        r.append(f"Réserves travaux appelées (105) : {solde_theorique_travaux:.2f}€")
        r.append(f"Placement réel sur Livret (502)  : {solde_reel_placement:.2f}€")
        
        ecart_placement = solde_theorique_travaux - solde_reel_placement
        if ecart_placement > 1.00:
            r.append(f"ANOMALIE : {ecart_placement:.2f}€ n'ont pas été virés sur le compte d'épargne !")
            r.append(f"Le syndic utilise cet argent pour financer le fonctionnement courant.")
            total_anomalies += ecart_placement
        elif ecart_placement < -100.00:
            r.append(f"    Sur-placement : {abs(ecart_placement):.2f}€ de plus que prévu sur le Livret.")
        else:
            r.append("Parfaite cohérence : Le fonds de travaux est intégralement placé.")
    else:
        r.append("Données insuffisantes pour l'analyse du fonds de travaux.")


    
    # --- SECTION J : CONTRÔLE DES FRAIS FACTURÉS PAR LE SYNDIC PAR RAPPORT AU CONTRAT DU SYNDIC (comptes 621 et 622) ---
    r.append("\n" + "="*80)
    r.append("[SECTION J] CONTRÔLE DES FRAIS DE SYNDIC")
    r.append("Comparaison des honoraires facturés (comptes 621, 622) avec les tarifs du contrat.")
    r.append(" L'objectif est de détecter des surfacturations ou des prestations indûment facturées.\n")
    r.append("Tarifs extraits du contrat du syndic :")
    for cle, valeur in df_contrat.items():
        r.append(f"    - {cle:<35} : {valeur:.2f} EUR")
    r.append("")
    
    if 'NUMERO_COMPTE' in df_gl.columns and 'DEBIT' in df_gl.columns and 'LIBELLE' in df_gl.columns:
        
        # 1. Traitement spécifique du FORFAIT ANNUEL (Compte 6211)
        tarif_forfait_contrat = df_contrat.get("forfait_annuel", 0.0)
        df_6211 = df_gl[(df_gl['NUMERO_COMPTE'].astype(str).str.startswith('6211')) & (df_gl['DEBIT'] > 0)]
            
        anomalies_detectees = 0
    
        if tarif_forfait_contrat > 0:
            total_paye_6211 = df_6211['DEBIT'].sum()
            if total_paye_6211 > (tarif_forfait_contrat * 1.02): # Tolérance de 2% pour l'inflation
                r.append(f"SURFACTURATION FORFAIT : Le total facturé au compte 6211 est de {total_paye_6211:.2f}€.")
                r.append(f"Le contrat prévoit un forfait annuel de {tarif_forfait_contrat:.2f}€.")
                anomalies_detectees += 1
                total_anomalies += max(0, total_paye_6211 - tarif_forfait_contrat)
            
        # 2. Filtrage des autres honoraires (Compte 622) pour analyse ligne à ligne
        df_622 = df_gl[(df_gl['NUMERO_COMPTE'].astype(str).str.startswith('622')) & (df_gl['DEBIT'] > 0)].copy()
            
        mapping_audit = {
            "Vacation horaire": "vacation_horaire",
            "Mise en demeure": "mise_en_demeure",
            "Relance": "relance_simple",
            "Etat daté": "etat_date",
            "Opposition sur mutation": "opposition_mutation",
            "Mise en demeure d'un tiers": "mise_en_demeure_tiers",
            "Injonction de payer": "injonction_payer",
            "Reprise de comptabilité sur exercices antérieurs (forfait)": "reprise_compta_forfait",
            "Assemblée générale supplémentaire": "ag_supplementaire",
            "Copie PV": "copie_pv"
        }
            
        if not df_622.empty:
            for _, row in df_622.iterrows():
                libelle_brut = str(row['LIBELLE'])
                montant_paye = float(row['DEBIT'])
                date_val = row['DATE']
                date_str = date_val.strftime('%d/%m/%Y') if pd.notnull(date_val) else "N/A"
                
                for nom_cible, cle_contrat in mapping_audit.items():
                    if fuzz.partial_ratio(nom_cible.lower(), libelle_brut.lower()) > THRESHOLD_FUZZ:
                        tarif_contrat = df_contrat.get(cle_contrat, 0.0)
    
                        if tarif_contrat == 0:
                            r.append(f"ALERTE : '{libelle_brut}' ({date_str}) facturé {montant_paye}€.")
                            r.append(f"Prestation non tarifée ou incluse dans le forfait selon le contrat.")
                            anomalies_detectees += 1
                            total_anomalies += montant_paye
                            
                        # Cas spécifique : Vacation horaire (plusieurs heures possibles)
                        elif cle_contrat == "vacation_horaire":
                            if montant_paye > (tarif_contrat + 0.10):
                                n_heures = montant_paye / tarif_contrat
                                r.append(f"INFO : Vacation détectée ({date_str}) pour {montant_paye}€.")
                                r.append(f"Cela correspond à {n_heures:.2f} heure(s) au tarif contractuel de {tarif_contrat}€/h.")
                            # On ne compte pas d'anomalie ici car le montant dépend du temps passé
                            
                        # Cas général : Frais fixes unitaires
                        elif montant_paye > (tarif_contrat + 0.10):
                            r.append(f"SURFACTURATION : '{libelle_brut}' ({date_str}) facturé {montant_paye}€.")
                            r.append(f"Le tarif contractuel est de {tarif_contrat}€ TTC.")
                            anomalies_detectees += 1
                            total_anomalies += montant_paye
                            
                        break 
                        
            if anomalies_detectees == 0:
                r.append("Aucun dépassement de tarif ou frais indu identifié sur les prestations particulières.")
    else:
        r.append("Colonnes nécessaires manquantes dans 'df_gl' pour cette analyse.")        

    
    
    # --- SYNTHESE CHIFFREE DES ANOMALIES EN PROPRORTION DU BUDGET ---
    r.append("\n" + "="*80)
    r.append("[SYNTHÈSE CHIFFRÉE] RATIO D'ANOMALIES / BUDGET")
    r.append("="*80)

    if budget > 0:
        ratio = (total_anomalies / budget) * 100
        r.append(f"Budget (appels de fonds 701xxx) : {budget:>12.0f} EUR")
        r.append(f"Total des anomalies détectées   : {total_anomalies:>12.0f} EUR")
        r.append(f"Ratio anomalies / budget        : {ratio:>11.0f} %")
        if ratio < 0.25:
            r.append("Appréciation : [TRES FAIBLE] Aucune anomalie significative (< 0.25% du budget).")
        elif ratio < 1:
            r.append("Appréciation : [FAIBLE] Anomalies mineures (0.25% à 1% du budget).")
        elif ratio < 3:
            r.append("Appréciation : [MODERE] Niveau d'anomalies notable (1% à 3% du budget). Vérifications recommandées.")
        elif ratio < 5:
            r.append("Appréciation : [ELEVE] Risque significatif identifié (3% à 5% du budget). Contrôles approfondis nécessaires.")
        else:
            r.append("Appréciation : [TRES ELEVE] Niveau d'anomalies critique (> 5% du budget). Action immédiate requise.")    
    else:
        r.append("Impossible de calculer le ratio : aucun appel de fonds (compte 701xxx) détecté.")
        r.append(f"Total des anomalies détectées : {total_anomalies:.2f} EUR")
    
    r.append("\n" + "="*80 + "\nFIN DU RAPPORT")

    return "\n".join(r)

##############################################################################################################################################################"

# --- GENERATION DE GRAPHIQUES ---

def generer_rapport_graphique(df_gl):
    pdf = FPDF()
    
    # =========================================================================
    # --- PAGE 1 : EN-TÊTE ET GRAPHIQUE 1 (RÉPARTITION PAR GRANDS POSTES) ---
    # =========================================================================
    pdf.add_page()
    
    # 1. En-tête Stylisé
    pdf.set_fill_color(41, 128, 185) # Bleu
    pdf.rect(0, 0, 210, 45, 'F')
    pdf.set_font("helvetica", "B", 24)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 25, "ANNEXES GRAPHIQUES", ln=True, align='C')
    pdf.set_font("helvetica", "I", 12)
    pdf.cell(0, 5, "Visualisation des flux financiers de la copropriété", ln=True, align='C')
    pdf.ln(30)
    
    # 2. Graphique Répartition des dépenses par grands postes
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, "1. Répartition des dépenses par grands postes", ln=True)
    pdf.ln(5)

    df_charges = df_gl[(df_gl['NUMERO_COMPTE'].astype(str).str.startswith('6')) & (df_gl['DEBIT'] > 0)].copy()
    if not df_charges.empty:
        df_charges['CLASSE'] = df_charges['NUMERO_COMPTE'].astype(str).str[:2]
        
        mapping_noms = {
            '60': 'Énergie & Fluides (Eau/Elec)',
            '61': 'Contrats d\'entretien & Services',
            '62': 'Frais Admin & Syndic',
            '63': 'Impôts et Taxes',
            '64': 'Personnel (Gardien)',
            '66': 'Frais Financiers',
            '67': 'Travaux exceptionnels',
            '68': 'Dotations aux provisions'
        }
        df_charges['POSTE_NOM'] = df_charges['CLASSE'].map(lambda x: mapping_noms.get(x, f"Autres (Classe {x})"))
        repartition = df_charges.groupby('POSTE_NOM')['DEBIT'].sum()

        graph_path_poste = "temp_repartition.png"
        plt.figure(figsize=(8, 5.5))
        colors = ['#3498db', '#e74c3c', '#2ecc71', '#f1c40f', '#9b59b6', '#34495e', '#1abc9c']
        plt.pie(repartition, labels=repartition.index, autopct='%1.1f%%', startangle=140, colors=colors, pctdistance=0.85)
        centre_circle = plt.Circle((0,0), 0.70, fc='white')
        plt.gca().add_artist(centre_circle)
        plt.title('Où va l\'argent ? (Répartition des charges)', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(graph_path_poste, dpi=300)
        plt.close()

        pdf.image(graph_path_poste, x=25, w=160)
        pdf.ln(5)

        pdf.set_font("helvetica", "I", 11)
        pdf.set_text_color(80, 80, 80)
        analyse_charges = (
            "Analyse : Ce graphique montre les principaux centres de coûts de la copropriété. "
            "Les postes Contrats d'entretien (61) et Énergie (60) représentent généralement "
            "l'essentiel du budget et doivent être contrôlés régulièrement."
        )
        pdf.multi_cell(0, 6, analyse_charges)
        
        if os.path.exists(graph_path_poste):
            os.remove(graph_path_poste)
    else:
        pdf.set_font("helvetica", "I", 11)
        pdf.cell(0, 10, "Données de charges insuffisantes pour générer ce graphique.", ln=True)

    # =========================================================================
    # --- PAGE 2 : GRAPHIQUE 2 (TOP 10 FOURNISSEURS) ---
    # =========================================================================
    pdf.add_page()
    pdf.set_font("helvetica", "B", 16)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, "2. Répartition des 10 principaux prestataires", ln=True)
    pdf.ln(5)

    df_fournisseurs = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('401')].copy()
    if not df_fournisseurs.empty:
        df_fournisseurs['LIBELLE_CLEAN'] = df_fournisseurs['LIBELLE'].str.strip().str.upper()
        top_10 = df_fournisseurs.groupby('LIBELLE_CLEAN')['CREDIT'].sum().sort_values(ascending=True).tail(10)

        graph_path_fourn = "temp_top_10.png"
        plt.figure(figsize=(10, 5.5))
        top_10.plot(kind='barh', color='#3498db')
        plt.title('Top 10 Fournisseurs (Montants TTC)', fontsize=14, fontweight='bold')
        plt.xlabel('Total (€)')
        plt.grid(axis='x', linestyle='--', alpha=0.6)
        plt.tight_layout()
        plt.savefig(graph_path_fourn, dpi=300)
        plt.close()

        pdf.image(graph_path_fourn, x=15, w=180)
        pdf.ln(5)
        
        pdf.set_font("helvetica", "I", 11)
        pdf.set_text_color(80, 80, 80)
        analyse_fournisseurs = (
            "Interprétation : Ce graphique met en évidence la concentration des dépenses par fournisseur. "
            "Si un seul prestataire représente une part disproportionnée du budget, il est conseillé "
            "de solliciter des devis comparatifs."
        )
        pdf.multi_cell(0, 6, analyse_fournisseurs)
        
        if os.path.exists(graph_path_fourn):
            os.remove(graph_path_fourn)
    else:
        pdf.set_font("helvetica", "I", 11)
        pdf.cell(0, 10, "Aucune donnée de fournisseur (classe 401) disponible.", ln=True)

    # =========================================================================
    # --- PAGE 3 : GRAPHIQUE 3 (ÉVOLUTION MENSUELLE DE LA TRÉSORERIE) ---
    # =========================================================================
    # ... (Le reste du code reste inchangé) ...
    pdf.add_page()
    pdf.set_font("helvetica", "B", 16)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, "3. Évolution mensuelle de la trésorerie", ln=True)
    pdf.ln(5)

    df_512 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('512')].copy()
    if not df_512.empty and 'DATE' in df_512.columns:
        df_512['DATE'] = pd.to_datetime(df_512['DATE'], errors='coerce')
        df_512 = df_512.dropna(subset=['DATE'])
        
        df_512['SOLDE_MVT'] = df_512['DEBIT'].fillna(0) - df_512['CREDIT'].fillna(0)
        df_512 = df_512.sort_values('DATE')
        
        df_512['MOIS'] = df_512['DATE'].dt.to_period('M')
        mensuel = df_512.groupby('MOIS')['SOLDE_MVT'].sum().reset_index()
        mensuel['TRESORERIE'] = mensuel['SOLDE_MVT'].cumsum()
        mensuel['MOIS_STR'] = mensuel['MOIS'].astype(str)

        graph_path3 = "temp_tresorerie.png"
        plt.figure(figsize=(10, 5.5))
        plt.plot(mensuel['MOIS_STR'], mensuel['TRESORERIE'], marker='o', color='#2ecc71', linewidth=2.5)
        plt.title('Trésorerie cumulée mois par mois (€)', fontsize=14, fontweight='bold')
        plt.xlabel('Mois')
        plt.ylabel('Solde bancaire (€)')
        plt.xticks(rotation=45)
        plt.grid(True, linestyle='--', alpha=0.5)
        plt.tight_layout()
        plt.savefig(graph_path3, dpi=300)
        plt.close()

        pdf.image(graph_path3, x=15, w=180)
        pdf.ln(5)

        pdf.set_font("helvetica", "I", 11)
        pdf.set_text_color(80, 80, 80)
        analyse_treso = (
            "Analyse : Ce graphique présente le niveau d'argent disponible sur le compte de la "
            "copropriété à la fin de chaque mois."
        )
        pdf.multi_cell(0, 6, analyse_treso)
        
        if os.path.exists(graph_path3):
            os.remove(graph_path3)
    else:
        pdf.set_font("helvetica", "I", 11)
        pdf.cell(0, 10, "Données de trésorerie (compte 512) insuffisantes.", ln=True)

    # =========================================================================
    # --- PAGE 4 : GRAPHIQUE 4 (ÉTAT DES IMPAYÉS DES COPROPRIÉTAIRES) ---
    # =========================================================================
    pdf.add_page()
    pdf.set_font("helvetica", "B", 16)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, "4. État des impayés des copropriétaires", ln=True)
    pdf.ln(5)

    df_450 = df_gl[df_gl['NUMERO_COMPTE'].astype(str).str.startswith('450')].copy()
    if not df_450.empty:
        df_450['LIBELLE_CLEAN'] = df_450['LIBELLE'].str.strip().str.upper()
        
        solde_450 = df_450.groupby('LIBELLE_CLEAN').apply(lambda x: x['DEBIT'].sum() - x['CREDIT'].sum()).reset_index()
        solde_450.columns = ['Copropriétaire', 'Dette']
        
        impayes = solde_450[solde_450['Dette'] > 0.1].sort_values(by='Dette', ascending=False).head(10)
        
        if not impayes.empty:
            impayes['Label_Anon'] = [f"Copropriétaire {chr(65+i)}" for i in range(len(impayes))]

            graph_path4 = "temp_impayes.png"
            plt.figure(figsize=(10, 5.5))
            plt.bar(impayes['Label_Anon'], impayes['Dette'], color='#e74c3c')
            plt.title('Top 10 des impayés les plus importants (€)', fontsize=14, fontweight='bold')
            plt.xlabel('Copropriétaires (Anonymisés)')
            plt.ylabel('Montant de la dette (€)')
            plt.grid(axis='y', linestyle='--', alpha=0.5)
            plt.tight_layout()
            plt.savefig(graph_path4, dpi=300)
            plt.close()

            pdf.image(graph_path4, x=15, w=180)
            pdf.ln(5)

            pdf.set_font("helvetica", "I", 11)
            pdf.set_text_color(80, 80, 80)
            pdf.multi_cell(0, 6, "Analyse : Ce graphique met en évidence les retards de paiement les plus élevés.")
            
            if os.path.exists(graph_path4):
                os.remove(graph_path4)

    nom_fichier = "Rapport_Graphique_Audit.pdf"
    pdf.output(nom_fichier)
    return nom_fichier




##############################################################################################################################################################"

# --- INTERFACE STREAMLIT ---
# Couleurs
NAVY   = (26, 39, 68)
OR     = (201, 168, 76)
GRIS   = (110, 110, 110)
NOIR   = (30, 30, 30)

col_texte, col_logo = st.columns([6, 1], vertical_alignment="center")

with col_texte:
    st.markdown(f'<h1 style="color: rgb{NAVY}; margin-bottom: 0;">Vérification des comptes de copropriété</h1>', unsafe_allow_html=True)
    st.markdown(f'<h3 style="color: rgb{OR}; margin-top: 0;">L\'expert digital. Simple. Automatique. Immédiat. Confidentiel.</h3>', unsafe_allow_html=True)
    st.markdown(f'<h3 style="color: rgb{OR};"><i>Conseils syndicaux : reprenez le contrôle !</i></h3>', unsafe_allow_html=True)

with col_logo:
    # On affiche le logo à droite
    st.image("Logo.png", width=300) # , use_container_width=True)
st.markdown("---")

# --- CHARGEMENT DES DONNEES ---

col1, col2 = st.columns(2)
with col1:
    st.markdown("### 1. Import des documents (exercice N-1)")
    gl_file = st.file_uploader("GRAND LIVRE COMPTABLE (PDF)", type="pdf")
    releves_files = st.file_uploader("12 RELEVES BANCAIRES MENSUELS (PDF)", type="pdf", accept_multiple_files=True)
    contrat_file = st.file_uploader("CONTRAT DU SYNDIC (PDF)", type="pdf")

# --- Saisie des 12 relevés de compte ---
nb_fichiers = len(releves_files) if releves_files else 0
if 0 < nb_fichiers < 12:
    st.warning(f" Il manque {12 - nb_fichiers} relevé(s).")
elif nb_fichiers > 12:
    st.error(f"🚫 Trop de fichiers : vous avez importé {nb_fichiers} relevés au lieu de 12.")

# --- Sécurité anti-doublons (noms et tailles) ---
fichiers_doublons = False
if releves_files:
    noms = [f.name for f in releves_files]
    tailles = [f.size for f in releves_files]
    if len(noms) != len(set(noms)):
        st.error(" Doublon détecté : certains fichiers portent le même nom.")
        fichiers_doublons = True
    elif len(tailles) != len(set(tailles)):
        st.error(" Doublon détecté : certains fichiers ont la même taille (contenu probablement identique).")
        fichiers_doublons = True

with col2:
    st.markdown("### 2. Traitement & analyse")
 
    documents_prets = (
        gl_file is not None and
        contrat_file is not None and
        releves_files is not None and
        len(releves_files) == 1 and   #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! Remettre 12 après débogage
        not fichiers_doublons
    )
 
    if documents_prets:
        st.markdown(" ")
        st.markdown(" ")
 
        # --- INITIALISATION DU SESSION STATE ---
        for key in ["pdf_synthese", "pdf_graphique", "synthese_texte", "gl_df", "bank_df", "contrat_df"]:
            if key not in st.session_state:
                st.session_state[key] = None
 
        if st.button("Générer le rapport d'analyse", type="primary"):
            with st.status("🚀 Initialisation de l'audit...", expanded=True) as status:
                progress_bar = st.progress(10)
 
                # Lecture Grand Livre
                status.update(label="📄 Lecture du Grand livre... Veuillez patienter", expanded=True)
                gl_path = save_uploaded_file(gl_file, "gl")
                gl_df = convert_pdf_to_excel(gl_path)

                if gl_df.empty:
                    st.error("❌ Le Grand livre n'a pas pu être extrait. Relancez le traitement.")
                    st.stop()

                progress_bar.progress(40)
 
                # Fusion et lecture des relevés bancaires
                merged_bank_path = merge_pdfs(releves_files, "rb")
                status.update(label="🏦 Lecture des relevés bancaires... Veuillez patienter", expanded=True)
                bank_df = extract_releve_data(merged_bank_path)
                progress_bar.progress(60)
 
                # Lecture contrat
                status.update(label="⚖️ Analyse du contrat du syndic... Veuillez patienter", expanded=True)
                contrat_df = extraire_grille_tarifaire_universelle(contrat_file)
                progress_bar.progress(70)
 
                # Audit comptable
                status.update(label="🔍 Analyse approfondie des écritures comptables...", expanded=True)
                rapport_final = generer_rapport_audit(gl_df, bank_df, contrat_df)
                progress_bar.progress(80)
 
                # Génération synthèse IA
                status.update(label="✍️ Rédaction de la synthèse... Veuillez patienter", expanded=True)
 
                prompt_complet = f"""
                Tu es un auditeur spécialisé en copropriété. Ton objectif est de rédiger 
                un rapport de synthèse clair et pédagogue à partir des contrôles comptables ci-dessous:
                
                <DEBUT DU RESULTAT DES CONTROLES COMPTABLES>
                {rapport_final}
                <FIN DU RESULTAT DES CONTROLES COMPTABLES>
                
                POSTURE ET TON :
                - Pédagogue : explique les raisons derrière chaque anomalie détectée.
                - Diplomate : ne sois jamais accusateur envers le syndic. Remplace 
                  "surfacturation" par "écart à clarifier", "erreur" par "point à vérifier".
                - Prudent : utilise le conditionnel ("il semblerait", "pourrait indiquer").
                - Humble : rappelle que ces analyses sont automatisées et peuvent comporter 
                  des erreurs nécessitant vérification.
                
                CIBLE : Copropriétaires et membres du conseil syndical sans formation comptable.

                LONGUEUR: 2 à 4 pages
                
                STRUCTURE OBLIGATOIRE :
                1. Ne mets aucun titre. Indique la date du rapport et la période analysée. Puis fais une phrase indiquant le Total des anomalies détectées et le Ratio anomalies / budget.
                2. Sections thématiques : une section par grande catégorie de contrôles effectués lorsque des anomalies ou interrogations ont été soulevées.
                3. Conclusion : synthèse des points principaux à discuter avec le syndic, accompagnée pour chacun d'une recommandation concrète (régularisation, demande de justificatif, mise en concurrence...).

                FORMAT:
                - N'utilise aucun emoji ni symbole Unicode spécial. 
                - Utilise uniquement des caractères ASCII standard (lettres, chiffres, ponctuation classique). 
                - N'utilise ni gras, ni italique, ni mise en forme complexe.
                """
  
                # --- GÉNÉRATION DU PDF DE SYNTHÈSE ---
                for attempt in range(MAX_RETRIES):
                    try:
                        response = client.models.generate_content(
                            model=GEMINI_MODEL,
                            contents=prompt_complet
                        )
                        synthese_texte = response.text
    
                        # --- CONFIGURATION INITIALE DU PDF ---
                        pdf = FPDF()
                        pdf.add_page()
                        pdf.set_margins(left=25, top=15, right=15)
                        pdf.set_auto_page_break(auto=True, margin=15)
    
                        # --- AJOUT DU LOGO ---
                        pdf.image("Logo.png", x=170, y=10, w=25)
                        pdf.ln(30)
    
                        # --- AJOUT DU TITRE ET PRÉAMBULE ---
                        pdf.set_text_color(*NAVY)
                        pdf.set_font("helvetica", "B", 14)
                        pdf.cell(0, 8, "RAPPORT DE SYNTHESE D'ANALYSE AUTOMATISEE", new_x="LMARGIN", new_y="NEXT", align='C')
                        pdf.cell(0, 8, "DES COMPTES DE COPROPRIETE", new_x="LMARGIN", new_y="NEXT", align='C')
                        pdf.ln(10)
                        pdf.set_draw_color(*OR)
                        pdf.set_line_width(0.5)
                        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
                        pdf.ln(20)
                        
                        # 1. Préambule
                        pdf.set_font("helvetica", 11)
                        pdf.set_text_color(*NOIR)
                        texte_preambule = "Ce rapport présente une synthèse des contrôles automatiques réalisés sur l'ensemble des écritures du grand livre de la copropriété, les relevés de compte bancaire du syndicat et le contrat du syndic pour l'exercice concerné. Des détails sont fournis en annexes."
                        pdf.multi_cell(0, 6, texte_preambule)
                        pdf.ln(10)
         
                        # Disclaimer
                        pdf.set_text_color(*GRIS)
                        pdf.set_font("helvetica", "I", 10)
                        texte_disclaimer = "Disclaimer: Cet examen a été exécuté par un assistant digital conçu pour accompagner les Conseils syndicaux dans leur mission d'analyse et de contrôle des comptes de copropriété. Il ne se substitue en aucun cas au pouvoir de contrôle des membres du Conseil syndical ni à l'expertise comptable du Syndic. Les éléments présentés dans le rapport d'analyse sont des pistes d'investigation qui peuvent comporter des erreurs de lecture automatisée, d'interprétation technique et doivent faire l'objet d'une vérification contradictoire, de contrôles sur pièces ainsi que de discussions avec le teneur de comptes."
                        pdf.multi_cell(0, 5, texte_disclaimer)
                        pdf.ln(10)
                        
                        # On réinitialise la couleur et la police pour la suite
                        pdf.set_text_color(*NOIR)
                        pdf.set_font("helvetica", size=11)
    
                        # Ligne de séparation
                        pdf.set_draw_color(*OR)
                        pdf.set_line_width(0.5)
                        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
                        pdf.ln(20)
                                        
                        # Titre de la section IA
                        pdf.set_font("helvetica", "B", 14)
                        pdf.set_text_color(*NAVY)
                        pdf.cell(0, 10, "Synthèse de l'analyse", new_x="LMARGIN", new_y="NEXT")
                        pdf.ln(20)
                        
                        # Nettoyage du texte pour éviter les erreurs d'encodage communes
                        texte_final = (synthese_texte
                            .replace("’", "'").replace("‘", "'")
                            .replace("“", '"').replace("”", '"')
                            .replace("–", "-").replace("—", "-")
                            .replace("…", "...")
                            .replace("•", "-")
                            .replace("€", " EUR")
                            .replace("²", "2")
                            .replace("\u00a0", " ") # Espace insécable
                        )
                        texte_final = re.sub(r'(?m)^\s*\*\s+', '  - ', texte_final)
    
                        # On continue sur la même page ou la suivante automatiquement
                        pdf.multi_cell(0, 6, texte_final, markdown=False)
    
                        # --- ANNEXES : Résultat brut des contrôles comptables ---
                        pdf.add_page()
                        pdf.set_font("helvetica", "B", 14)
                        pdf.set_text_color(*NAVY)
                        pdf.cell(0, 12, "Annexes", new_x="LMARGIN", new_y="NEXT", align='C')
                        pdf.ln(10)
                        pdf.set_draw_color(*OR)
                        pdf.set_line_width(0.5)
                        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
                        pdf.ln(20)
                        
                        pdf.set_font("courier", size=10)
                        pdf.set_text_color(*NOIR)
                        texte_annexes = (rapport_final
                            .replace("’", "'").replace("‘", "'")
                            .replace("“", '"').replace("”", '"')
                            .replace("–", "-").replace("—", "-")
                            .replace("…", "...")
                            .replace("•", "-")
                            .replace("€", " EUR")
                            .replace("²", "2")
                            .replace("\u00a0", " ") # Espace insécable
                        )
                        pdf.multi_cell(0, 4.5, texte_annexes)
     
                        st.session_state["pdf_synthese"] = bytes(pdf.output())
                        st.session_state["synthese_texte"] = synthese_texte
     
                    except Exception as e:
                        if "429" in str(e):
                            st.error("🚨 QUOTA ÉPUISÉ : Le moteur a atteint sa limite quotidienne. Réessayez demain.")
                            st.stop()
                        elif "503" in str(e):
                            if attempt < MAX_RETRIES - 1:
                                st.warning(f"⏳ FORTE AFFLUENCE sur le moteur, nouvelle tentative automatique dans {WAIT_MINUTES} minute(s)... (essai {attempt + 1}/{MAX_RETRIES})")
                                time.sleep(WAIT_MINUTES * 60)
                            else:
                                st.error("🚨 ACTIVITÉ EXCEPTIONNELLE : Le moteur a atteint ses limites de capacité en raison d'une forte affluence. Réessayez plus tard.")
                                st.stop()
                        else:
                            st.error(f" Erreur technique : {e}")
    
                        st.session_state["pdf_synthese"] = None
                        st.session_state["synthese_texte"] = f"ERREUR : {str(e)}"

                
                # --- GÉNÉRATION DU PDF DES GRAPHIQUES --- (désactivé)
                # try:
                #     nom_graphique = generer_rapport_graphique(gl_df)
                #     with open(nom_graphique, "rb") as f:
                #         st.session_state["pdf_graphique"] = f.read()
                #     os.remove(nom_graphique)
                # except Exception as e:
                #     st.session_state["pdf_graphique"] = None
                
                # Stockage des DataFrames
                st.session_state["gl_df"] = gl_df
                st.session_state["bank_df"] = bank_df
                st.session_state["contrat_df"] = contrat_df
 
                progress_bar.progress(100)
                status.update(label=" Audit terminé !", state="complete", expanded=False)
 
        # ── AFFICHAGE DES RÉSULTATS ── hors du if st.button(), même niveau que lui
        if st.session_state.get("pdf_synthese"):
            st.success(" Analyse terminée avec succès !")
            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                st.download_button(
                    label="📥 Télécharger le rapport de synthèse (PDF)",
                    data=st.session_state["pdf_synthese"],
                    file_name="Rapport_Synthese.pdf",
                    mime="application/pdf"
                )
            # with col_dl2:
            #     if st.session_state.get("pdf_graphique"):
            #         st.download_button(
            #             label="📊 Télécharger les annexes graphiques (PDF)",
            #             data=st.session_state["pdf_graphique"],
            #             file_name="Rapport_Graphique_Audit.pdf",
            #             mime="application/pdf"
            #         )
        
        elif st.session_state.get("synthese_texte"):
            st.warning(" Le PDF n'a pas pu être généré. Affichage du texte brut :")
            st.markdown(st.session_state["synthese_texte"])
 
        # ── APERÇU DES DONNÉES CONVERTIES ── même niveau que if st.button()
        if st.session_state.get("gl_df") is not None:
            st.markdown("---")
            st.markdown("### 🛠️ Aperçu des conversions")
 
            with st.expander("Voir le Grand livre converti"):
                st.dataframe(st.session_state["gl_df"])
                output_gl = io.BytesIO()
                with pd.ExcelWriter(output_gl, engine='openpyxl') as writer:
                    st.session_state["gl_df"].to_excel(writer, index=False)
                st.download_button("💾 Télécharger GL en Excel", output_gl.getvalue(), "GL_converti.xlsx")
 
            with st.expander("Voir les relevés bancaires cumulés"):
                st.dataframe(st.session_state["bank_df"])
                output_bk = io.BytesIO()
                with pd.ExcelWriter(output_bk, engine='openpyxl') as writer:
                    st.session_state["bank_df"].to_excel(writer, index=False)
                st.download_button("💾 Télécharger Banque en Excel", output_bk.getvalue(), "Banque_convertie.xlsx")
 
            with st.expander("Voir les tarifs extraits du contrat"):
                st.json(st.session_state["contrat_df"])
 
        shutil.rmtree(UPLOAD_DIR)
        os.makedirs(UPLOAD_DIR)
        st.info("Toutes les données ont été supprimées.")
 
    else:
        st.markdown(" ")
        st.markdown(" ")
        st.info("Charger tous les documents avant de lancer le traitement ...")
 
st.markdown("---")
st.markdown(" ###### Les comptes de copropriété sont souvent abscons pour les non-spécialistes, peuvent présenter des erreurs et manquer de transparence ; un grand livre peut comporter plus d'une centaine de pages d'écritures et les conseils syndicaux disposent de peu de moyens ou d'expertise pour assurer leur mission de contrôle des comptes.")
st.markdown(" ###### Il s'agit d'un prototype mis à disposition gratuitement ; nous vous invitons à nous partager en retour votre expérience en tant qu'utilisateur (pertinence de l'analyse, besoins complémentaires etc.), par écrit (gael_maugendre@hotmail.com) ou de vive voix (+33 6 14 29 80 29)).")
st.markdown("---")
st.caption(" ###### Disclaimer : Cette application est un assistant digital conçu pour accompagner les Conseils syndicaux dans leur mission d'analyse et de contrôle des comptes de copropriété. Elle ne se substitue en aucun cas au pouvoir de contrôle des membres du Conseil syndical ni à l'expertise comptable du Syndic. Les éléments présentés dans le rapport d'analyse sont des pistes d'investigation qui peuvent comporter des erreurs de lecture automatisée, d'interprétation technique et doivent faire l'objet d'une vérification contradictoire, de contrôles sur pièces ainsi que de discussions avec le teneur de comptes.")
st.caption(" ###### Protection des données : aucune donnée n'est conservée ; tous les fichiers restent confidentiels et sont intégralement supprimés dés la fin du traitement ; aucun rapport n'est enregistré.")
st.caption(" ###### Tous droits réservés.")
