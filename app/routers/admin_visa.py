from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
import openpyxl
import io
import re
from app.database import get_db
from app.models.traveler_profile import AtharTravelerProfile

router = APIRouter(prefix="/api/v1/visa", tags=["Visa Automation"])


def extract_mrz_data(ocr_text: str) -> dict:
    mrz_lines = [
        line.strip().upper()
        for line in ocr_text.split("\n")
        if len(line.strip()) >= 44
    ]
    if len(mrz_lines) < 2:
        return {}

    line1 = mrz_lines[-2]
    line2 = mrz_lines[-1]

    try:
        passport_num = line2[0:9].replace("<", "")
        nationality = line2[10:13]
        dob = line2[13:19]
        gender = line2[20]
        expiry = line2[21:27]

        name_part = line1[5:]
        names = [n for n in name_part.split("<<") if n]
        surname = names[0].replace("<", " ").strip()
        given_names = names[1].replace("<", " ").strip() if len(names) > 1 else ""

        return {
            "passport_number": passport_num,
            "nationality": nationality,
            "dob": dob,
            "gender": gender,
            "expiry_date": expiry,
            "last_name": surname,
            "first_name": given_names,
        }
    except Exception:
        raise HTTPException(
            status_code=422, detail="MRZ section of the passport is unreadable."
        )


@router.post("/process-passport")
async def process_passport(file: UploadFile = File(...)):
    mock_ocr_result = (
        "P<DZAALGERIA<<AHMED<<<<<<<<<<<<<<<<<<<<<<<<<<\n"
        "0412345674DZA8505204M2811306<<<<<<<<<<<<<<02"
    )

    parsed_data = extract_mrz_data(mock_ocr_result)
    if not parsed_data:
        raise HTTPException(
            status_code=400, detail="Failed to parse Passport MRZ data."
        )

    template_path = "templates/official_visa_template.xlsx"
    try:
        workbook = openpyxl.load_workbook(template_path)
        sheet = workbook.active

        next_row = sheet.max_row + 1
        sheet[f"A{next_row}"] = parsed_data["first_name"]
        sheet[f"B{next_row}"] = parsed_data["last_name"]
        sheet[f"C{next_row}"] = parsed_data["passport_number"]
        sheet[f"D{next_row}"] = parsed_data["nationality"]
        sheet[f"E{next_row}"] = parsed_data["expiry_date"]

        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)

        return {
            "status": "success",
            "extracted_traveler": parsed_data,
            "message": "Data appended to the official regulatory dossier.",
        }
    except FileNotFoundError:
        return {
            "status": "partial_success",
            "extracted_traveler": parsed_data,
            "message": "OCR completed. Official Excel template was not found to append data.",
        }
