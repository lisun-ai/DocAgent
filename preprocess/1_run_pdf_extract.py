"""
Copyright 2024 Adobe
All Rights Reserved.

NOTICE: Adobe permits you to use, modify, and distribute this file in
accordance with the terms of the Adobe license agreement accompanying it.
"""

import argparse
import glob
import logging
import os
from datetime import datetime

from adobe.pdfservices.operation.auth.service_principal_credentials import \
    ServicePrincipalCredentials
from adobe.pdfservices.operation.exception.exceptions import (
    SdkException, ServiceApiException, ServiceUsageException)
from adobe.pdfservices.operation.io.cloud_asset import CloudAsset
from adobe.pdfservices.operation.io.stream_asset import StreamAsset
from adobe.pdfservices.operation.pdf_services import PDFServices
import argparse
from adobe.pdfservices.operation.pdf_services_media_type import \
    PDFServicesMediaType
from adobe.pdfservices.operation.pdfjobs.jobs.extract_pdf_job import \
    ExtractPDFJob
from adobe.pdfservices.operation.pdfjobs.params.extract_pdf.extract_element_type import \
    ExtractElementType
from adobe.pdfservices.operation.pdfjobs.params.extract_pdf.extract_pdf_params import \
    ExtractPDFParams
from adobe.pdfservices.operation.pdfjobs.params.extract_pdf.extract_renditions_element_type import \
    ExtractRenditionsElementType
from adobe.pdfservices.operation.pdfjobs.result.extract_pdf_result import \
    ExtractPDFResult

# Initialize the logger
logging.basicConfig(level=logging.INFO)

def parse_arguments():
    parser = argparse.ArgumentParser(description="Extract text and tables from PDF files")
    parser.add_argument("--client-id", default="9871642959ea4f2c8ec67483a1044e92",
                        help="PDF Services Client ID")
    parser.add_argument("--client-secret", default="p8e-85rwivHG-K222iUJf8JuaE45kxUkdHW8",
                        help="PDF Services Client Secret")
    parser.add_argument("--raw-data-dir", default="../sample_data/",
                        help="Directory containing raw PDF files")
    parser.add_argument("--result-dir", default="./extract_output/",
                        help="Directory for output results")
    return parser.parse_args()

args = parse_arguments()

PDF_SERVICES_CLIENT_ID = args.client_id
PDF_SERVICES_CLIENT_SECRET = args.client_secret
RAW_DATA_DIR = args.raw_data_dir
RESULT_DIR = args.result_dir


#
# This sample illustrates how to extract Text, Table Elements Information from PDF along with renditions of Figure,
# Table elements.
#
# Refer to README.md for instructions on how to run the samples & understand output zip file.
#
class ExtractTextTableInfoWithFiguresTablesRenditionsFromPDF:
    def __init__(self, file_path, sid):
        # Creates an output stream and copy stream asset's content to it
        output_file_path = self.create_output_file_path(sid)
        if os.path.exists(output_file_path):
            return

        try:
            file = open(file_path, "rb")
            input_stream = file.read()
            file.close()

            # Initial setup, create credentials instance
            credentials = ServicePrincipalCredentials(
                client_id=PDF_SERVICES_CLIENT_ID,
                client_secret=PDF_SERVICES_CLIENT_SECRET,
            )

            # Creates a PDF Services instance
            pdf_services = PDFServices(credentials=credentials)

            # Creates an asset(s) from source file(s) and upload
            input_asset = pdf_services.upload(
                input_stream=input_stream, mime_type=PDFServicesMediaType.PDF
            )

            # Create parameters for the job
            extract_pdf_params = ExtractPDFParams(
                elements_to_extract=[
                    ExtractElementType.TEXT,
                    ExtractElementType.TABLES,
                ],
                elements_to_extract_renditions=[
                    ExtractRenditionsElementType.TABLES,
                    ExtractRenditionsElementType.FIGURES,
                ],
            )

            # Creates a new job instance
            extract_pdf_job = ExtractPDFJob(
                input_asset=input_asset, extract_pdf_params=extract_pdf_params
            )

            # Submit the job and gets the job result
            location = pdf_services.submit(extract_pdf_job)
            pdf_services_response = pdf_services.get_job_result(
                location, ExtractPDFResult
            )

            # Get content from the resulting asset(s)
            result_asset: CloudAsset = pdf_services_response.get_result().get_resource()
            stream_asset: StreamAsset = pdf_services.get_content(result_asset)

            with open(output_file_path, "wb") as file:
                file.write(stream_asset.get_input_stream())

        except (ServiceApiException, ServiceUsageException, SdkException) as e:
            logging.exception(f"Exception encountered while executing operation: {e}")
            exit()

    # Generates a string containing a directory structure and file name for the output file
    @staticmethod
    def create_output_file_path(sid) -> str:
        return f"{RESULT_DIR}/{sid}.zip"


def main():
    os.makedirs(RESULT_DIR, exist_ok=True)

    for file_path in glob.glob(RAW_DATA_DIR + "/*"):
        pdf_path = file_path + "/document.pdf"
        sid = pdf_path.split("/")[-2]
        print(pdf_path)
        ExtractTextTableInfoWithFiguresTablesRenditionsFromPDF(pdf_path, sid)


if __name__ == "__main__":
    main()
