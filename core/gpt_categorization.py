from openai import OpenAI
import base64, json
from pathlib import Path
from dotenv import load_dotenv
import os
from openai import OpenAI

def img_to_data_uri(path_str: str) -> str:
    p = Path(path_str)
    mime = "image/png" if p.suffix.lower()==".png" else "image/jpeg"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def categorize_questions(df_questions):
    # 1) Cliente
    load_dotenv()  # Carga el archivo .env
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    # 2) Prompt de sistema (compacto) con las 4 habilidades y reglas
    PROMPT_HABILIDADES = """
    Devuelves SOLO un JSON válido de la forma:
    {"<id_pregunta>": {"Habilidades":["Resolver Problemas"|"Modelar"|"Representar"|"Argumentar", ...]}, ...}

    Tarea:
    A partir de las IMÁGENES de preguntas PAES M1, clasifica TODAS las habilidades que se evidencian en cada pregunta (selección múltiple).

    Definiciones (resumen operativo):
    - Resolver Problemas: solucionar una situación problemática (contextualizada o no), aplicando cálculos/conocimientos/estrategias; opcionalmente interpretar/validar resultados.
    - Modelar: traducir una situación real/científica a una expresión matemática (ecuación, función, inecuación, etc.) y/o usarla para responder sobre la situación.
    - Representar: transferir/transformar información entre formas matemáticas (símbolos, tablas, gráficos, diagramas, recta, plano).
    - Argumentar: reconocer/explicar/justificar validez de procedimientos, pasos deductivos, demostraciones, o detectar argumentos erróneos.

    Reglas:
    - Elige TODAS las habilidades que aplique(n) por pregunta.
    - Si solo hay manipulación simbólica sin contexto → favorece Representar (no Modelar).
    - Si hay contexto pero NO se traduce a expresión que describa la situación → no es Modelar.
    - Si el foco es justificar o explicar por qué algo es válido → incluye Argumentar.
    - Si el ítem da un modelo y solo pide cálculo directo sin decisiones → puede ser Resolver (rutinario), pero no Modelar per se.
    - Usa exactamente estos rótulos: "Resolver Problemas", "Modelar", "Representar", "Argumentar".
    - No agregues texto extra: SOLO el JSON pedido.
    """

    PROMPT_MATERIA = """
    Devuelves SOLO un JSON válido de la forma:
    {"<id_pregunta>": {"Unidad Temática": ["<unidad>", ...]}, ...}
    
    Tarea:
    Eres un experto en educación y evaluación. A partir de las IMÁGENES de preguntas PAES M1, clasifica TODAS las unidades temáticas que se evidencian en cada pregunta.
    
    Definiciones (resumen operativo):
    - Números: Conjunto de los Números Enteros y Racionales, Porcentaje, Potencias y Raíces Enésimas.
    - Álgebra y Funciones: Expresiones algebráicas, Proporcionalidad, Ecuaciones e Inecuaciones de Primer Grado, Sistemas de Ecuaciones Lineales, Función Lineal y Afín, Función Cuadrática.
    - Geometría: Figuras Geométricas, Cuerpos Geométricos, Transformaciones Isométricas.
    - Probabilidad y Estadística: Representación de Datos a Través de Tablas y Gráficos, Medidas de Posición, Reglas de las Probabilidades.
    
    Reglas:
    - Usa exactamente estos rótulos: "Números", "Álgebra y Funciones", "Geometría", "Probabilidad y Estadística"
    - No agregues texto extra: SOLO el JSON pedido.
    """

    PROMPT_LATEX = """
    Tarea:
    A partir de las IMÁGENES de preguntas PAES M1, extrae el enunciado y alternativas en LaTeX.
    Reglas:
    - Si las alternativas son imágenes, ignóralas y pon "Imagen_<n>.png" en su lugar.
    - Si el enunciado tiene imágenes, ignóralas y pon "Imagen" en su lugar.
    - Devuelves SOLO un JSON válido de la forma:
    {"<id_pregunta>": {"Enunciado": "<enunciado_latex>", "Alternativas": ["<alt1_latex>", "<alt2_latex>", ...], "Imagenes": ["Imagen_1.png", "Imagen_2.png", ...]}, ...}
    
    """

    # 3) ======= ENTRADA: lista de (id_pregunta, ruta_png) =======

    rows = (
        df_questions
        .dropna(subset=["png_path"])
        [["question_number", "png_path"]]
        .itertuples(index=False, name=None)
    )
    
    # 4) Construcción del input multimodal (un SOLO prompt con varias imágenes)
    content_user = []
    content_user.append({
        "type": "input_text",
        "text": (
            "Clasifica las habilidades utilizadas en cada pregunta y devuelve SOLO el JSON pedido. "
            "Cada bloque 'PREGUNTA_<id>' tiene su imagen asociada."
        )
    })

    for qid, path in rows:
        qid = str(qid); path = str(path)
        if not Path(path).exists():
            # log/skip if needed
            continue
        content_user.append({"type": "input_text", "text": f"PREGUNTA_{qid}:"})
        content_user.append({"type": "input_image", "image_url": img_to_data_uri(path)})
    
    # 5) Llamada a Responses API (un solo request)
    input_data = [
        {"role": "system", "content": [{"type": "input_text", "text": PROMPT_HABILIDADES}]},
        {"role": "user",   "content": content_user},
    ]

    response = client.responses.create(
        model="gpt-5",
        input=input_data #type: ignore
    )

    # 6) Parseo robusto del JSON devuelto
    raw = response.output_text.strip()
    print("Raw output:\n", raw)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        cleaned = raw.strip().strip("```").replace("json\n", "").replace("\n```", "")
        result = json.loads(cleaned)

    # 7) Resultado final: dict { "<id>": [<habilidades>...] }
    print("\nDict clasificado:")
    final = json.dumps(result, indent=2, ensure_ascii=False)
    return final

