import os
import logging
from extraccion.pdf_a_bbdd import *
from extraccion.conversion_csv import *
import re

pregunta_identifier = r"PREGUNTA\s+(\d+)"
ficha_identifier="FICHA DE REFERENCIA CURRICULAR"
path = "C:/Users/mvasq/OneDrive/Documentos/Scrapper_PSU_PAES"
input_path = path + "/input"
PSU_path = input_path + "/PSU"
PAES_path= input_path + "/PAES"
output_folder_csv = create_output_folder("output/BBDD")

for conjunto in os.listdir(PSU_path):
    batch = PSU_path + "/" + conjunto
    for ensayo in os.listdir(batch):
        if ensayo.endswith(".pdf"):
            logging.info("🚀 Starting PDF question extraction...")
            pdf_file = batch + "/" + ensayo
            results = process_pdf(pdf_file,pregunta_identifier,ficha_identifier)
            output_path = output_folder_csv + "/" + ensayo.split(".")[0] + ".csv"
            export_to_csv(results,output_path)
            logging.info("🎉 Finished!")
            