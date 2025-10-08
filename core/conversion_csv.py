import pandas as pd
import logging

def export_to_csv(data, output_csv):
    df = pd.DataFrame(data)
    try:
        df = df.sort_values(by="question_number")
    except:
        logging.warning("⚠️ No se pudo ordenar las preguntas por 'question_number'. Verifique los datos.")
    df.to_csv(output_csv, index=False)
    logging.info(f"✅ Metadata exported to {output_csv} with {len(df)} questions.")
