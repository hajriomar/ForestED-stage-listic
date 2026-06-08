import json
from pathlib import Path


PROCESSED_DIR = Path("/data/processed")


def read_json_file(path: Path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def extract_programme_from_file_name(file_name: str):
    return file_name.split("_")[0].strip()


def load_processed_files():
    result = {
        "competence": [],
        "curriculum": []
    }

    for domain in result.keys():
        domain_path = PROCESSED_DIR / domain

        if not domain_path.exists():
            continue

        for source_path in domain_path.iterdir():
            if not source_path.is_dir():
                continue

            for file_path in source_path.glob("*.json"):
                result[domain].append({
                    "domain": domain,
                    "source": source_path.name,
                    "programme": extract_programme_from_file_name(
                        file_path.name
                    ),
                    "file_name": file_path.name,
                    "path": str(file_path),
                    "data": read_json_file(file_path)
                })

    return result


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
                    "ac": 0,
                    "modules": 0,
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


def fill_curriculum_stats(programme_summary, data):
    ue_ids = set()
    module_ids = set()

    for periode in data.get("periodes", []):
        for ue in periode.get("unites_enseignement", []):
            ue_id = ue.get("id")

            if ue_id:
                ue_ids.add(ue_id)

            for element in ue.get("elements_pedagogiques", []):
                module_id = element.get("id")

                if module_id:
                    module_ids.add(module_id)

    programme_summary["ue"] = len(ue_ids)
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