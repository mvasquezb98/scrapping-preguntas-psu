from openai import OpenAI
import base64, json
from pathlib import Path
from dotenv import load_dotenv
import os
import pandas as pd
from collections import defaultdict
from collections.abc import Mapping
import re
from datetime import datetime

from io import BytesIO
from PIL import Image

def img_to_data_uri(path_str: str) -> str:
    p = Path(path_str)
    img = Image.open(p).convert("RGB")
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=80, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"

def parseo_json(response):
    """Devuelve un dict desde response.output_text, tolerando cercas ```json."""
    raw = getattr(response, "output_text", "")
    raw = raw.strip()
    print("Raw output:\n", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        cleaned = raw
        # Quitar fences tipo ```json ... ```
        if cleaned.startswith("```"):
            # elimina primera línea (puede ser ```json o ```), y el cierre ```
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        # Limpiezas adicionales frecuentes
        cleaned = cleaned.replace("\n```", "").replace("```", "").replace("json\n", "").strip()
        return json.loads(cleaned)

def _normalize_qid(x) -> str:
    """Extrae el bloque numérico final; si no hay, devuelve str(x)."""
    m = re.search(r'(\d+)$', str(x))
    return m.group(1) if m else str(x)

def build_rows(df_questions: pd.DataFrame, qids=None):
    """
    Devuelve lista de tuplas (qid:str, lowq_path:str).
    - Normaliza ids del df y de `qids` (soporta 'PREGUNTA_1', 1, '1', etc.)
    - Filtra opcionalmente por `qids`.
    """
    df2 = df_questions.dropna(subset=["lowq_path"]).copy()
    df2["qid_norm"] = df2["question_number"].apply(_normalize_qid)

    if qids is not None:
        qids_norm = { _normalize_qid(q) for q in qids }
        df2 = df2[df2["qid_norm"].isin(qids_norm)]

    # devolvemos el id normalizado para que case con tus dicts
    return list(df2[["qid_norm", "lowq_path"]].itertuples(index=False, name=None))

def chunked(iterable, n):
    """Yield lists of length n (last one may be shorter)."""
    iterable = list(iterable)
    for i in range(0, len(iterable), n):
        yield iterable[i:i+n]

def merge_json_dicts(dst: dict, src: dict) -> dict:
    """Shallow-merge JSON dicts like {"PREGUNTA_1": {...}}."""
    if not src:
        return dst
    for k, v in src.items():
        dst[k] = v
    return dst

def consulta_openai(client, PROMPT, rows, input_text, model="gpt-5-nano"):
    """Hace un único request multimodal (texto + varias imágenes). Si rows está vacío, retorna {}."""
    rows = list(rows)  # asegurar re-iterable
    if not rows:
        return {}

    content_user = [{"type": "input_text", "text": input_text}]
    for qid, path in rows:
        qid = str(qid); path = str(path)
        if not Path(path).exists():
            continue
        content_user.append({"type": "input_text", "text": f"PREGUNTA_{qid}:"})
        content_user.append({"type": "input_image", "image_url": img_to_data_uri(path)})

    input_data = [
        {"role": "system", "content": [{"type": "input_text", "text": PROMPT}]},
        {"role": "user",   "content": content_user},
    ]

    response = client.responses.create(model=model, input=input_data)  # type: ignore
    data_dict = parseo_json(response)
    return data_dict

def _merge_values(a, b):
    """Fusión profunda de dos valores:
    - dict + dict -> merge recursivo
    - list + list -> concatena preservando orden y deduplica
    - list + escalar -> agrega si no está
    - escalar + list -> idem
    - escalar + escalar -> si iguales, deja uno; si distintos, devuelve lista deduplicada en orden [a, b]
    """
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        return deep_merge_dicts(a, b)
    if isinstance(a, list) and isinstance(b, list):
        seen = set()
        out = []
        for x in a + b:
            if x not in seen:
                out.append(x)
                seen.add(x)
        return out
    if isinstance(a, list) and not isinstance(b, list):
        return a if b in a else a + [b]
    if not isinstance(a, list) and isinstance(b, list):
        return b if a in b else [a] + b
    # escalares
    return a if a == b else [a, b]

def deep_merge_dicts(d1, d2):
    """Fusión profunda de diccionarios (no muta los originales)."""
    out = dict(d1)  # copia superficial
    for k, v in d2.items():
        if k in out:
            out[k] = _merge_values(out[k], v)
        else:
            out[k] = v
    return out

def merge_question_dicts(list_dicts):
    """Fusiona una lista de dicts con claves tipo 'PREGUNTA_X' y combina sus campos."""
    result = defaultdict(dict) #type: ignore
    for d in list_dicts:
        if not d:
            continue
        for pregunta, payload in d.items():
            if pregunta in result:
                result[pregunta] = deep_merge_dicts(result[pregunta], payload)
            else:
                result[pregunta] = payload
    return dict(result)

def consulta_batcheada(client, PROMPT, rows_all, input_text, model="gpt-5-nano", batch_size=8):
    """Call consulta_openai in batches and merge responses."""
    final = {}
    rows_all = list(rows_all)  # ensure re-iterable
    print(f"[INFO] input_text: {input_text[:60]}... Total preguntas: {len(rows_all)}")
    for rows_batch in chunked(rows_all, batch_size):
        try:
            out = consulta_openai(client, PROMPT, rows_batch, input_text, model=model)
            merge_json_dicts(final, out)
            print(f"[INFO] Batch procesado: {len(rows_batch)} preguntas.")
        except Exception as e:
            print(f"[ERROR] consulta_batcheada fallo en batch {rows_batch}: {e}")
            break
    return final

# -------------------- Función principal --------------------

def categorize_questions(df_questions: pd.DataFrame):
    dict_habilidades, dict_materia, dict_latex, dict_num, dict_alg_y_fun, dict_geom, dict_prob_y_est = {}, {}, {}, {}, {}, {}, {}
    try:
        
        # 1) Cliente
        load_dotenv()
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # 2) ENTRADA: lista de (id_pregunta, ruta_png) materializada (se reusa varias veces)
        rows = build_rows(df_questions)

        # 3) Prompts
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
        - Elige TODAS las materias que aplique(n) por pregunta.
        - Usa exactamente estos rótulos: "Números", "Álgebra y Funciones", "Geometría", "Probabilidad y Estadística"
        - Si no hay expresiones algebráicas, entonces no es "Álgebra y Funciones".
        - No agregues texto extra: SOLO el JSON pedido.
        """

        PROMPT_LATEX = """
        Tarea:
        A partir de las IMÁGENES de preguntas PAES M1, extrae el enunciado y alternativas en LaTeX.
        Reglas:
        - Si las alternativas son imágenes, ignóralas y pon "[Imagen_<n>.png]" en su lugar.
        - Si el enunciado tiene imágenes, ignóralas y pon "[Imagen_<n>.png]" en su lugar.
        - Si la pregunta no tiene una imagen adjunta, dejar una lista vacía.
        - Devuelves SOLO un JSON válido de la forma:
        {"<id_pregunta>": {"Enunciado": "<enunciado_latex>", "Alternativas": ["<alt1_latex>", "<alt2_latex>", ...]}, ...}
        """

        # 4) Textos de usuario
        input_text_habilidades = (
            "Clasifica las habilidades utilizadas en cada pregunta y devuelve SOLO el JSON pedido. "
            "Cada bloque 'PREGUNTA_<id>' tiene su imagen asociada."
        )
        input_text_materia = (
            "Clasifica las materias utilizadas en cada pregunta y devuelve SOLO el JSON pedido. "
            "Cada bloque 'PREGUNTA_<id>' tiene su imagen asociada."
        )
        input_text_latex = (
            "Redacta en formato LaTeX cada pregunta y devuelve SOLO el JSON pedido. "
            "Cada bloque 'PREGUNTA_<id>' tiene su imagen asociada."
        )

        # 5) Llamadas iniciales (batched de 5)
        dict_habilidades = consulta_batcheada(client, PROMPT_HABILIDADES, rows, input_text_habilidades)
        dict_materia     = consulta_batcheada(client, PROMPT_MATERIA,     rows, input_text_materia)
        # dict_latex       = consulta_batcheada(client, PROMPT_LATEX,       rows, input_text_latex)

        # 6) Derivar listas de qids por Unidad Temática desde dict_materia
        rows_qid_num, rows_qid_alg_y_fun, rows_qid_geom, rows_qid_prob_y_est = [], [], [], []
        for key_preg, data in (dict_materia or {}).items():
            unidades = (data or {}).get("Unidad Temática", [])
            if "Números" in unidades:
                rows_qid_num.append(key_preg)
            if "Álgebra y Funciones" in unidades:
                rows_qid_alg_y_fun.append(key_preg)
            if "Geometría" in unidades:
                rows_qid_geom.append(key_preg)
            if "Probabilidad y Estadística" in unidades:
                rows_qid_prob_y_est.append(key_preg)

        # 7) Construir rows por grupo (materializados)
        rows_num        = build_rows(df_questions, rows_qid_num)
        rows_alg_y_fun  = build_rows(df_questions, rows_qid_alg_y_fun)
        rows_geom       = build_rows(df_questions, rows_qid_geom)
        rows_prob_y_est = build_rows(df_questions, rows_qid_prob_y_est)

        # 8) Prompts Sub-unidades
        prompt_num = """
        Devuelves EXCLUSIVAMENTE un JSON VÁLIDO con la estructura:
        {"<id_pregunta>": {"Sub-unidad": ["<sub-unidad1>", "<sub-unidad2>", ...]}, ...}

        Rol:
        Eres un experto en educación matemática escolar y evaluación PAES. Tu tarea es, a partir de IMÁGENES de preguntas PAES M1 (Unidad: Números), identificar TODAS las sub-unidades temáticas explícitas o implícitas presentes en cada pregunta.

        Hay 3 grandes grupos: porcentajes, potencias y raíces, números enteros y racionales. Utilizando estos como referencia, clasifica según sub-unidad. 

        Criterios de clasificación (usar exactamente estos nombres):

        Sub-unidades de porcentajes:
        - "Concepto y cálculo de porcentaje"
        - "Problemas que involucren porcentaje"

        Sub-unidades de potencias y raíces:
        - "Propiedades de las potencias de base racional y exponente racional"
        - "Descomposición y propiedades de las raíces enésimas en los números reales"
        - "Problemas que involucren potencias y raíces enésimas en los números reales"

        Otras sub-unidades de números enteros y racionales:
        - "Operaciones y orden en el conjunto de los números enteros"
        - "Operaciones y comparación entre números en el conjunto de los números racionales"
        - "Problemas que involucren el conjunto de los números enteros y racionales"

        Instrucciones estrictas:
        - Analiza CADA pregunta por separado y clasifícala según TODAS las sub-unidades que se evidencian.
        - Elige TODAS las sub-unidades que aplique(n) por pregunta.
        - Usa SOLO los nombres de sub-unidad exactamente como están escritos arriba.
        - Si solo hay números enteros, entonces NO clasifiques como "Problemas que involucren el conjunto de los números enteros y racionales"
        - El resultado debe ser un JSON válido SIN texto adicional, comentarios ni explicaciones.
        """
        prompt_alg_y_fun = """
        Devuelves EXCLUSIVAMENTE un JSON VÁLIDO con la estructura:
        {"<id_pregunta>": {"Sub-unidad": ["<sub-unidad1>", "<sub-unidad2>", ...]}, ...}

        Rol:
        Eres un experto en educación matemática escolar y evaluación PAES. A partir de IMÁGENES de preguntas PAES M1 (Unidad: Álgebra y Funciones), tu tarea es identificar TODAS las sub-unidades temáticas explícitas o implícitas presentes en cada pregunta.

        Hay 6 grandes grupos: expresiones algebraicas, proporcionalidad, ecuaciones e inecuaciones de primer grado, sistemas de ecuaciones lineales, función lineal y afín, función cuadrática. Utilizando estos como referencia, clasifica según sub-unidad. 

        Criterios de clasificación (usar exactamente estos nombres):
        
        Sub-unidades de expresiones algebraicas:
        - "Productos notables"
        - "Factorizaciones y desarrollo de expresiones algebraicas"
        - "Operatoria con expresiones algebraicas"
        - "Problemas que involucren expresiones algebraicas"

        Sub-unidades de proporcionalidad:
        - "Concepto de proporción directa e inversa"
        - "Problemas que involucren proporción directa en inversa"

        Sub-unidades de ecuaciones e inecuaciones de primer grado:
        - "Resolución de ecuaciones lineales"
        - "Problemas que involucren ecuaciones lineales"
        - "Resolución de inecuaciones lineales"
        - "Problemas que involucren inecuaciones lineales"

        Sub-unidades de sistemas de ecuaciones lineales:
        - "Resolución de sistemas de ecuaciones lineales"
        - "Problemas que involucren sistemas de ecuaciones lineales"

        Sub-unidades de función lineal y afín:
        - "Concepto de función lineal y función afín"
        - "Tablas y gráficos de función lineal y función afín"
        - "Problemas que involucren función lineal y función afín"

        Sub-unidades de función cuadrática:
        - "Ecuaciones de segundo grado"
        - "Tablas y gráficos de la función cuadrática"
        - "Vértice, ceros de la función e intersección con los ejes, de la función cuadrática"
        - "Función cuadrática"

        Instrucciones estrictas:
        - Analiza CADA pregunta por separado y clasifícala según TODAS las sub-unidades que se evidencian.
        - Elige TODAS las sub-unidades que aplique(n) por pregunta.
        - Usa SOLO los nombres de sub-unidad exactamente como están escritos arriba.
        - El resultado debe ser un JSON válido SIN texto adicional, comentarios ni explicaciones.
        """
        prompt_geom = """
        Devuelves EXCLUSIVAMENTE un JSON VÁLIDO con la estructura:
        {"<id_pregunta>": {"Sub-unidad": ["<sub-unidad1>", "<sub-unidad2>", ...]}, ...}

        Rol:
        Eres un experto en educación matemática escolar y evaluación PAES. A partir de IMÁGENES de preguntas PAES M1 (Unidad: Geometría), tu tarea es identificar TODAS las sub-unidades temáticas explícitas o implícitas presentes en cada pregunta.

        Criterios de clasificación (usar exactamente estos nombres):
        
        Hay 3 grandes grupos: figuras geométricas, cuerpos geométricos y transformaciones isométricas. Utilizando estos como referencia, clasifica según sub-unidad. 

        Sub-unidades de figuras geométricas:
        - "Problemas que involucren el Teorema de Pitágoras en diversos contextos"
        - "Perímetro y áreas de triángulos, paralelogramos, trapecios y círculos"
        - "Problemas que involucren perímetro y áreas de triángulos, paralelogramos, trapecios y círculos en diversos contextos"

        Sub-unidades de cuerpos geométricos:
        - "Área de superficies de paralelepípedos y cubos"
        - "Volumen de paralelepípedos y cubos"
        - "Problemas que involucren área y volumen de paralelepípedos y cubos en diversos contextos"

        Sub-unidades de transformaciones isométricas:
        - "Puntos y vectores en el plano cartesiano"
        - "Rotación, traslación y reflexión de figuras geométricas"
        - "Problemas que involucren rotación, traslación y reflexión en diversos contextos"
        
        Instrucciones estrictas:
        - Analiza CADA pregunta por separado y clasifícala según TODAS las sub-unidades que se evidencian.
        - Elige TODAS las sub-unidades que aplique(n) por pregunta.
        - Usa SOLO los nombres de sub-unidad exactamente como están escritos arriba.
        - El resultado debe ser un JSON válido SIN texto adicional, comentarios ni explicaciones.
        """
        prompt_prob_y_est = """
        Devuelves EXCLUSIVAMENTE un JSON VÁLIDO con la estructura:
        {"<id_pregunta>": {"Sub-unidad": ["<sub-unidad1>", "<sub-unidad2>", ...]}, ...}

        Rol:
        Eres un experto en educación matemática escolar y evaluación PAES. A partir de IMÁGENES de preguntas PAES M1 (Unidad: Probabilidad y estadística), tu tarea es identificar TODAS las sub-unidades temáticas explícitas o implícitas presentes en cada pregunta.

        Criterios de clasificación (usar exactamente estos nombres):
        
        Hay 3 grandes grupos: representación de datos a través de tablas y gráficos, medidas de posición, reglas de las probabilidades. Utilizando estos como referencia, clasifica según sub-unidad. 

        Sub-unidades de representación de datos a través de tablas y gráficos:
        - "Tablas de frecuencia absoluta y relativa" 
        - "Tipos de gráficos que permitan representar datos"
        - "Promedio de un conjunto de datos"
        - "Problemas que involucren tablas y gráficos en diversos contextos"

        Sub-unidades de medidas de posición: 
        - "Cuartiles y percentiles de uno o más grupos de datos" 
        - "Diagrama de cajón para representar distribución de datos"
        - "Problemas que involucren medidas de posición en diversos contextos"

        Sub-unidades de reglas de las probabilidades:
        - "Problemas que involucren probabilidad de un evento en diversos contextos" 
        - "Problemas que involucren la regla aditiva y multiplicativa de probabilidades en diversos contextos"
        
        Instrucciones estrictas:
        - Analiza CADA pregunta por separado y clasifícala según TODAS las sub-unidades que se evidencian.
        - Elige TODAS las sub-unidades que aplique(n) por pregunta.
        - Usa SOLO los nombres de sub-unidad exactamente como están escritos arriba.
        - El resultado debe ser un JSON válido SIN texto adicional, comentarios ni explicaciones.
        """

        input_text_num        = "Clasifica las sub-unidades utilizadas en cada pregunta y devuelve SOLO el JSON pedido. Cada bloque 'PREGUNTA_<id>' tiene su imagen asociada."
        input_text_alg_y_fun  = "Clasifica las sub-unidades utilizadas en cada pregunta y devuelve SOLO el JSON pedido. Cada bloque 'PREGUNTA_<id>' tiene su imagen asociada."
        input_text_geom       = "Clasifica las sub-unidades utilizadas en cada pregunta y devuelve SOLO el JSON pedido. Cada bloque 'PREGUNTA_<id>' tiene su imagen asociada."
        input_text_prob_y_est = "Clasifica las sub-unidades utilizadas en cada pregunta y devuelve SOLO el JSON pedido. Cada bloque 'PREGUNTA_<id>' tiene su imagen asociada."

        # 9) Llamadas por grupo (evitando llamadas vacías)
        dict_num        = consulta_batcheada(client, prompt_num,        rows_num,        input_text_num       )        if rows_num        else {}
        dict_alg_y_fun  = consulta_batcheada(client, prompt_alg_y_fun,  rows_alg_y_fun,  input_text_alg_y_fun )        if rows_alg_y_fun  else {}
        dict_geom       = consulta_batcheada(client, prompt_geom,       rows_geom,       input_text_geom      )        if rows_geom       else {}
        dict_prob_y_est = consulta_batcheada(client, prompt_prob_y_est, rows_prob_y_est, input_text_prob_y_est)        if rows_prob_y_est else {}
    except Exception as e:
        print(f"[ERROR] categorize_questions fallo: {e}")
        pass
    
    # 10) Salida unificada
    list_dicts = [
        dict_habilidades, dict_materia, dict_latex, dict_num, dict_alg_y_fun, dict_geom, dict_prob_y_est
    ]
    
    final_dict = merge_question_dicts(list_dicts)

    return final_dict

def run_categorization(df_questions: pd.DataFrame,output_path: str):
    for doc in df_questions['pdf_file'].unique():
        try:
            df_doc = df_questions[df_questions['pdf_file'] == doc]
            final_dict_path = Path(output_path+f"dict_PAES_{doc}.json")
            if not final_dict_path.exists():    
                inicio = datetime.now()
                final_dict = categorize_questions(df_doc)
                final=datetime.now()
                delta = final - inicio
                print(f"Tiempo de ejecución {doc}: {delta}")

                with final_dict_path.open("w", encoding="utf-8") as f: # type: ignore
                    json.dump(final_dict, f, ensure_ascii=False, indent=2, sort_keys=True)
            else:
                print(f"El archivo {final_dict_path} ya existe. Se omite la categorización para {doc}.")
        except Exception as e:
            print(f"Error processing {doc}: {e}")
    