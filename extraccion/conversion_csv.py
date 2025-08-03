import pandas as pd
import logging

def export_to_csv(data, output_csv):
    df = pd.DataFrame(data)
    df = df.sort_values(by="question_number")
    df.to_csv(output_csv, index=False)
    logging.info(f"✅ Metadata exported to {output_csv} with {len(df)} questions.")
