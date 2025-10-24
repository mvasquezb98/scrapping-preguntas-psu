from core.identificacion_preguntas_PAES import get_questions
from core.categorizacion_gpt import run_categorization
import pandas as pd

input_path = "input/PAES/"
output_path= "output/PAES/"

#df_questions = get_questions(input_path, output_path, padding_cm = -0.25 , left_ratio=0.143)
df_questions = pd.read_excel("output/PAES/bbdd_PAES_20251022_230341.xlsx") 
run_categorization(df_questions, output_path)