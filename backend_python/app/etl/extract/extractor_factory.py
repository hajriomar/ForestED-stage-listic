from app.etl.extract.json_extractor import (
    extract_json
)

from app.etl.extract.excel_extractor import (
    extract_excel
)

from app.etl.extract.csv_extractor import (
    extract_csv
)


class ExtractorFactory:

    EXTRACTORS = {
        ".json": extract_json,
        ".xlsx": extract_excel,
        ".xls": extract_excel,
        ".csv": extract_csv
    }

    @classmethod
    def get_extractor(cls, file_path):

        suffix = file_path.suffix.lower()

        if suffix not in cls.EXTRACTORS:
            raise ValueError(
                f"Unsupported file type: {suffix}"
            )

        return cls.EXTRACTORS[suffix]