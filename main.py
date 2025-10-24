from core.identificacion_preguntas_PAES import get_questions
from core.categorizacion_gpt import categorize_questions

import json
from pathlib import Path

import pandas as pd
from datetime import datetime

input_path = "input/PAES/"
output_path= "output/PAES/"

#df_questions = get_questions(input_path, output_path, padding_cm = -0.25 , left_ratio=0.143)
df_questions = pd.read_excel("output/PAES/bbdd_PAES_20251022_230341.xlsx") 

for doc in df_questions['pdf_file'].unique():
    try:
        df_doc = df_questions[df_questions['pdf_file'] == doc]
        final_dict_path = Path(f"output/PAES/dict_PAES_{doc}.json")
        
        inicio = datetime.now()
        final_dict = categorize_questions(df_doc)
        final=datetime.now()
        delta = final - inicio
        print(f"Tiempo de ejecución {doc}: {delta}")

        with final_dict_path.open("w", encoding="utf-8") as f: # type: ignore
            json.dump(final_dict, f, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception as e:
        print(f"Error processing {doc}: {e}")