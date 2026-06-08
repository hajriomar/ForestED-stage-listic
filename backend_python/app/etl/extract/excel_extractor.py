from pathlib import Path
from openpyxl import load_workbook
import logging

logger = logging.getLogger(__name__)


def extract_excel(file_path: str):
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    workbook = load_workbook(
        filename=file_path,
        data_only=True
    )

    extracted_data = {
        "file_name": file_path.name,
        "sheets": []
    }

    for sheet in workbook.worksheets:
        rows = [
            list(row)
            for row in sheet.iter_rows(values_only=True)
        ]

        if not rows:
            continue

        extracted_data["sheets"].append(
            {
                "sheet_name": sheet.title,
                "rows": rows
            }
        )

    logger.info(f"Successfully extracted Excel data from {file_path}")

    return extracted_data