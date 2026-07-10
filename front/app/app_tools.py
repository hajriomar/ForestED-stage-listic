"""
app_tools.py — accès aux données et helpers de statistiques.

Les données sont chargées via l'API FastAPI sécurisée, avec le token JWT
de la session utilisateur OU la clé d'accès invité (dashboard partagé) :
le backend filtre PAR SOURCE selon les permissions, le frontend ne décide
de rien.

La signature et le format de retour de load_processed_files() sont
identiques à la version historique : aucun changement nécessaire dans
les pages de visualisation.
"""

import logging

from flask import has_request_context, session

import api_client

logger = logging.getLogger(__name__)


def _empty_datasets():
    return {"competence": [], "curriculum": []}


def extract_programme_from_file_name(file_name: str):
    """Conservé pour compatibilité : programme informatif depuis le nom."""
    return file_name.split("_")[0].strip()


def load_processed_files():
    """Charge les datasets via l'API sécurisée, filtrés par source.

    Fonctionne pour une session utilisateur (JWT) comme pour une session
    invitée (clé dashboard). Retour identique à l'ancienne lecture disque :
        {"competence": [{domain, source, programme, file_name, path, data}],
         "curriculum": [...]}
    """
    if not has_request_context():
        # Import des modules au démarrage du serveur : pas d'utilisateur.
        return _empty_datasets()

    token = session.get("token")
    guest_key = session.get("guest_key")

    if not token and not guest_key:
        return _empty_datasets()

    try:
        return api_client.load_processed_files_from_api(
            token=token, api_key=guest_key,
        )

    except api_client.AuthExpired:
        logger.info("Session expirée pendant un chargement de données.")
        for key in ("token", "user", "guest_key", "guest"):
            session.pop(key, None)
        return _empty_datasets()

    except api_client.Forbidden as exc:
        logger.warning("Accès interdit aux données : %s", exc)
        return _empty_datasets()

    except api_client.ApiUnavailable:
        logger.error("Backend indisponible pendant un chargement de données.")
        return _empty_datasets()


def build_programmes_summary(datasets):
    programmes = {}

    for domain, items in datasets.items():
        for item in items:
            key = f"{item['source']}::{item['programme']}"

            if key not in programmes:
                programmes[key] = {
                    "source": item["source"],
                    "programme": item["programme"],
                    "has_competence": False,
                    "has_curriculum": False,
                    "competences": 0,
                    "ac": 0,              # ← initialisé à 0 (fix : KeyError si curriculum seul)
                    "modules": 0,
                    "modules_lies_competences": 0,
                    "elements_pedagogiques": 0,
                    "ue": 0,
                    "sous_classifications": 0,
                    "niveaux": 0,
                }

            if domain == "competence":
                programmes[key]["has_competence"] = True

                fill_competence_stats(
                    programmes[key],
                    item["data"]
                )

            elif domain == "curriculum":
                programmes[key]["has_curriculum"] = True

                fill_curriculum_stats(
                    programmes[key],
                    item["data"]
                )

    return list(programmes.values())


def count_competence_modules(competence_data):
    """
    Compte les éléments pédagogiques réellement liés aux apprentissages critiques.

    Polytech : ac["modules"]
    BUT      : ac["ressources"] + ac["saes"]
    """
    modules = set()

    if not competence_data:
        return 0

    for sous_classification in competence_data.get("sous_classifications", []):
        for competence in sous_classification.get("competences", []):
            for niveau in competence.get("niveaux_developpement", []):
                for ac in niveau.get("apprentissages_critiques", []):

                    for field in ["modules", "ressources", "saes"]:
                        for module in ac.get(field, []):
                            if module:
                                modules.add(str(module).strip())

    return len(modules)


def fill_competence_stats(programme_summary, data):
    competence_codes = set()
    ac_codes = set()
    sous_classification_codes = set()
    niveau_keys = set()

    for sous_classification in data.get("sous_classifications", []):
        sous_code = sous_classification.get("code")

        if sous_code:
            sous_classification_codes.add(sous_code)

        for competence in sous_classification.get("competences", []):
            competence_code = competence.get("code")

            if competence_code:
                competence_codes.add(competence_code)

            for niveau in competence.get("niveaux_developpement", []):
                niveau_value = niveau.get("niveau")

                if competence_code and niveau_value is not None:
                    niveau_keys.add(
                        f"{competence_code}::{niveau_value}"
                    )

                for ac in niveau.get("apprentissages_critiques", []):
                    ac_code = ac.get("code")

                    if ac_code:
                        ac_codes.add(ac_code)


    programme_summary["competences"] = len(competence_codes)
    programme_summary["ac"] = len(ac_codes)
    programme_summary["sous_classifications"] = len(
        sous_classification_codes
    )
    programme_summary["niveaux"] = len(niveau_keys)
    programme_summary["modules_lies_competences"] = count_competence_modules(data)

    if programme_summary["modules_lies_competences"] > 0:
        programme_summary["modules"] = programme_summary["modules_lies_competences"]


def iter_curriculum_elements(programme):
    """
    Itère sur tous les éléments pédagogiques du curriculum.
    Compatible ancien et nouveau méta-modèle.
    """

    for periode in programme.get("periodes", []):

        # Ancien modèle
        for ue in periode.get("unites_enseignement", []):
            for element in ue.get("elements_pedagogiques", []):
                yield {
                    "periode": periode,
                    "ue": ue,
                    "option": None,
                    "parcours": "COMMUN",
                    "element": element,
                }

        # Nouveau modèle
        for group in periode.get("groupes_elements_pedagogiques", []):

            # UE élémentaire directe
            if "elements_pedagogiques" in group:
                for element in group.get("elements_pedagogiques", []):
                    yield {
                        "periode": periode,
                        "ue": group,
                        "option": None,
                        "parcours": group.get("contrainte") or "COMMUN",
                        "element": element,
                    }

            # UE composite avec options
            elif "groupes_elements_pedagogiques" in group:
                ue = group

                for option in group.get("groupes_elements_pedagogiques", []):
                    for element in option.get("elements_pedagogiques", []):
                        yield {
                            "periode": periode,
                            "ue": ue,
                            "option": option,
                            "parcours": option.get("contrainte") or "COMMUN",
                            "element": element,
                        }


def fill_curriculum_stats(programme_summary, data):
    ue_ids = set()
    module_ids = set()

    for row in iter_curriculum_elements(data):
        ue = row["ue"]
        element = row["element"]

        ue_id = ue.get("id")

        if ue_id:
            ue_ids.add(ue_id)

        module_id = element.get("id")

        if module_id:
            module_ids.add(module_id)

    programme_summary["ue"] = len(ue_ids)
    programme_summary["elements_pedagogiques"] = len(module_ids)

    if programme_summary.get("modules_lies_competences", 0) == 0:
        programme_summary["modules"] = len(module_ids)


def compute_global_stats(programmes):
    sources = {
        item["source"]
        for item in programmes
    }

    formations = {
        f"{item['source']}::{item['programme']}"
        for item in programmes
    }

    return {
        "sources": len(sources),
        "formations": len(formations),
        "competences": sum(
            item["competences"]
            for item in programmes
        ),
        "ac": sum(
            item["ac"]
            for item in programmes
        ),
        "modules": sum(
            item["modules"]
            for item in programmes
        ),
        "ue": sum(
            item["ue"]
            for item in programmes
        ),
        "sous_classifications": sum(
            item["sous_classifications"]
            for item in programmes
        ),
        "niveaux": sum(
            item["niveaux"]
            for item in programmes
        ),
        "curricula": sum(
            1 for item in programmes
            if item["has_curriculum"]
        ),
        "referentiels": sum(
            1 for item in programmes
            if item["has_competence"]
        ),
    }