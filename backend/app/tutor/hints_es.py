"""es-MX (Mexican Spanish) translations of the spoken help-string bank (Slice 3.2a).

REVIEWED & PASSED (owner, 2026-06-04). These translations were drafted by an AI assistant and then
reviewed by a human bilingual / math reviewer per V2_TODO Slice 3.2 ("Claude drafts offline → human
review (non-negotiable for a Grade-6 audience) → freeze"). The ``ES_MX_REVIEWED`` flag below is now
``True``, so Slice 3.5 (render the es-MX audio) and Slice 3.6 (the bilingual help-mode toggle) may
treat this bank as production. Re-flip to ``False`` only if the bank is re-drafted and needs
re-review.

WHAT this module is (the bilingual-SCAFFOLD design, V2_TODO 3.6): the on-screen lesson/problem
content stays ENGLISH; only the avatar's spoken help (the nudges) and the misconception framing
labels are translated to Spanish. This module is the es-MX DATA LAYER that parallels the English
banks: a single ``dict[str, str]`` mapping each renderable English ``string_id`` (see
``app/tts/spoken_bank.py`` — ``nudge:<kc>:<index>`` and ``misconception_name:<id>``) to its
Mexican-Spanish text. The keys are IDENTICAL to the English bank's keys, so the build-time
renderer can produce ``manifest["<string_id>|es-MX"]`` 1:1 against ``"<string_id>|en"`` and the
runtime ``manifest_lookup`` (which already reads ``string_id|locale``) serves the right language.

NO LLM, NO SymPy, NO DB, NO network at runtime — this is frozen data read by the offline batch
renderer (CLAUDE.md §8.1). The translation work was done offline; nothing here translates at
request time (which would put an LLM in the turn loop — the anti-pattern §8.1 forbids).

──────────────────────────────────────────────────────────────────────────────────────────────
LOCKED bilingual math termbase (es-MX) — V2_TODO 3.2 task "Lock a bilingual math termbase FIRST"
──────────────────────────────────────────────────────────────────────────────────────────────
The SAME Spanish term is used everywhere below (no drift). A human reviewer can spot-check the
bank against this table. Terms are the US-K-12 / TEKS Mexican-Spanish convention (es-MX), the
locked locale (V2_TODO open-decisions 2026-06-02).

  numerator                    → numerador
  denominator                  → denominador
  common denominator           → denominador común
  equivalent fractions         → fracciones equivalentes
  equivalent ratios            → razones equivalentes
  ratio                        → razón
  unit rate                    → tasa unitaria
  number line                  → recta numérica
  to simplify (a fraction)     → simplificar
  least common multiple        → mínimo común múltiplo
  greatest common factor       → máximo común divisor
  factor (divisor)             → divisor / factor (divisor)
  multiple                     → múltiplo
  to add                       → sumar
  to subtract                  → restar
  to multiply                  → multiplicar
  to divide                    → dividir
  the whole                    → el entero / el total (context: el entero = one whole)
  piece (of a fraction model)  → parte (pedazo, in kid-talk for tangible pieces)
  amount                       → cantidad
  absolute value               → valor absoluto
  distance from zero           → distancia al cero
  opposite (of a number)       → opuesto
  sign (+/-)                   → signo
  negative                     → negativo
  positive                     → positivo
  integer                      → entero
  whole number                 → número entero (non-negative whole)
  rational number              → número racional
  coordinate plane             → plano de coordenadas
  coordinate / ordered pair    → coordenada / par ordenado
  axis                         → eje
  to reflect (across an axis)  → reflejar
  expression                   → expresión
  equivalent expression        → expresión equivalente
  term                         → término
  coefficient                  → coeficiente
  constant                     → constante
  variable / letter            → variable / letra (kid-talk: "la letra")
  to distribute                → distribuir
  parentheses                  → paréntesis
  exponent / power             → exponente / potencia
  base (of a power)            → base
  equation                     → ecuación
  inequality                   → desigualdad
  to solve                     → resolver
  to substitute                → sustituir
  solution                     → solución
  inverse / opposite operation → operación inversa
  to balance (an equation)     → mantener el equilibrio / equilibrar
  input / output               → entrada / salida
  rate                         → tasa
  base (of a triangle)         → base
  height                       → altura
  area                         → área
  volume                       → volumen
  rectangle                    → rectángulo
  parallelogram                → paralelogramo
  triangle                     → triángulo
  straight angle               → ángulo llano (a straight line of angle)
  right angle                  → ángulo recto
  face (of a solid)            → cara
  net                          → patrón / desarrollo plano (kid-talk: "patrón")
  surface area                 → área total (área de la superficie)
  edge                         → arista (kid-talk: "lado/arista")
  mean (average)               → media (promedio)
  median                       → mediana
  range                        → rango
  spread                       → dispersión
  mean absolute deviation (MAD)→ desviación media absoluta (DMA)
  deviation                    → desviación
  data point                   → dato (punto de datos)
  data display                 → representación de datos
  statistical question         → pregunta estadística
  to vary                      → variar
  category                     → categoría
  relative frequency           → frecuencia relativa
  survey                       → encuesta
  deposit                      → depósito
  withdrawal                   → retiro
  balance (money)              → saldo
  income                       → ingreso
  salary                       → salario
  percent                      → por ciento (kid-talk: "por ciento")
  out of one hundred           → de cada cien / sobre cien
  decimal places               → cifras decimales
  decimal point                → punto decimal
  to convert (units)           → convertir
  unit                         → unidad

Decimal convention (V2_TODO 0.4 / open-decisions): es-MX / US-Latino uses the decimal POINT,
SAME as English. (Irrelevant here — the renderable bank is digit-free by construction.)
"""

from __future__ import annotations

from typing import Final

# ── HUMAN-REVIEW GATE (required; CLAUDE.md §1 / V2_TODO 3.2 task 4) ──────────────────────────
# True: a human bilingual / math reviewer checked and PASSED the es-MX bank (owner, 2026-06-04), so
# Slice 3.5 (render) and 3.6 (toggle) may treat es-MX as production audio. Flip back to False only
# if the bank is re-drafted and needs re-review.
ES_MX_REVIEWED: Final[bool] = True

# The es-MX locale tag, matching ``app.tts.provider.Locale``'s ``"es-MX"`` member. Kept as a
# named constant so the renderer wiring and any reviewer reference the SAME string.
ES_MX_LOCALE: Final[str] = "es-MX"


# ── The es-MX bank: string_id → Mexican-Spanish text ────────────────────────────────────────
# Keys are EXACTLY the English renderable string_ids (``app/tts/spoken_bank.py``): 129 nudges
# (``nudge:<kc>:<index>``) + 42 misconception names (``misconception_name:<id>``) = 171. Each
# value is the reviewed-quality (DRAFT) es-MX rendering of the English line, using the locked
# termbase above and the same warm, kid-friendly register as the English nudges (no jargon a
# 6th-grader would not meet in class, no digits — the lines are digit-free like their source).
ES_MX_HELP_STRINGS: Final[dict[str, str]] = {
    # ── KC_equivalence ──
    "nudge:KC_equivalence:0": (
        "Si sombreas cada fracción, ¿las partes sombreadas cubren la misma cantidad?"
    ),
    "nudge:KC_equivalence:1": (
        "¿Qué le pasa a la cantidad si cortas cada parte en pedazos más pequeños e iguales?"
    ),
    "nudge:KC_equivalence:2": (
        "Dos fracciones pueden verse distintas y aun así nombrar la misma cantidad. "
        "¿Cómo lo podrías comprobar?"
    ),
    # ── KC_common_denominator ──
    "nudge:KC_common_denominator:0": (
        "¿Qué nos dice el número de abajo sobre el tamaño de cada parte?"
    ),
    "nudge:KC_common_denominator:1": (
        "¿Podrías cortar ambas fracciones para que cada parte sea del mismo tamaño?"
    ),
    "nudge:KC_common_denominator:2": (
        "Es difícil comparar partes de distintos tamaños. ¿Cómo podrías hacer que las partes "
        "coincidan?"
    ),
    # ── KC_addition_unlike ──
    "nudge:KC_addition_unlike:0": (
        "Antes de sumar, ¿las partes son del mismo tamaño? Solo puedes contar partes que coinciden."
    ),
    "nudge:KC_addition_unlike:1": (
        "¿Qué nos dice el número de abajo sobre cada parte? ¿Debería cambiar cuando sumas?"
    ),
    "nudge:KC_addition_unlike:2": (
        "Si juntas ambas cantidades en el mismo dibujo, ¿cuánto queda sombreado?"
    ),
    # ── KC_subtraction_unlike ──
    "nudge:KC_subtraction_unlike:0": ("Antes de quitar algo, ¿las partes son del mismo tamaño?"),
    "nudge:KC_subtraction_unlike:1": (
        "¿Qué nos dice el número de abajo sobre cada parte? ¿Debería cambiar cuando quitas algo?"
    ),
    "nudge:KC_subtraction_unlike:2": (
        "Si empiezas con la primera cantidad y quitas la segunda, ¿cuánto queda sombreado?"
    ),
    # ── KC_number_line_placement ──
    "nudge:KC_number_line_placement:0": (
        "¿Esta cantidad está más cerca de nada, de un entero, o en algún punto intermedio?"
    ),
    "nudge:KC_number_line_placement:1": (
        "Piensa en qué tan grande es la cantidad, no en los dígitos que ves. "
        "¿Dónde quedaría ubicada?"
    ),
    "nudge:KC_number_line_placement:2": (
        "¿Cuántos saltos iguales caben entre los extremos, y qué tan avanzado está este?"
    ),
    # ── KC_ratio_language ──
    "nudge:KC_ratio_language:0": (
        "Una parte DEL total compara un color con TODAS las fichas, no con el otro color."
    ),
    "nudge:KC_ratio_language:1": (
        "La parte del total es menor que el total: ¿tu número de abajo es el total de ellas?"
    ),
    "nudge:KC_ratio_language:2": (
        "Cuenta cada ficha para el número de abajo; pon solo el color que te piden arriba."
    ),
    # ── KC_unit_rate ──
    "nudge:KC_unit_rate:0": (
        "Una tasa unitaria es «cuánto por UNO». ¿Qué cantidad estás repartiendo, y entre cuántos?"
    ),
    "nudge:KC_unit_rate:1": (
        "Si esa cantidad junta cuesta eso, ¿uno solo es mayor o menor que el total?"
    ),
    "nudge:KC_unit_rate:2": (
        "Reparte el total en partes iguales entre esa cantidad. ¿De qué tamaño es una sola parte?"
    ),
    # ── KC_better_buy ──
    "nudge:KC_better_buy:0": (
        "La mejor compra es el menor precio por UN artículo, no el menor precio en total."
    ),
    "nudge:KC_better_buy:1": (
        "Un montón más grande puede costar más en total y aun así salir más barato por artículo. "
        "¿Cuál cuesta menos por artículo?"
    ),
    "nudge:KC_better_buy:2": (
        "Encuentra cuánto cobra cada tienda por un solo artículo, y luego compara esos dos precios."
    ),
    # ── KC_equivalent_ratios ──
    "nudge:KC_equivalent_ratios:0": (
        "Para mantener una razón igual, haz lo MISMO a ambos números. ¿Qué hiciste abajo?"
    ),
    "nudge:KC_equivalent_ratios:1": (
        "¿SUMASTE la misma cantidad, o MULTIPLICASTE por la misma cantidad? "
        "Solo una la mantiene igual."
    ),
    "nudge:KC_equivalent_ratios:2": (
        "¿Cuántas veces más grande es el nuevo segundo número? "
        "Haz crecer el primero esa misma cantidad de veces."
    ),
    # ── KC_percent ──
    "nudge:KC_percent:0": (
        "Un por ciento es una parte DEL total (de cada cien), no el número del por ciento solo."
    ),
    "nudge:KC_percent:1": (
        "¿Tu respuesta es mayor que el total? Una parte de él debería ser menor que el total."
    ),
    "nudge:KC_percent:2": ("Piensa en el total como cien partes iguales. ¿Cuántas de esas tomas?"),
    # ── KC_multiply_fractions ──
    "nudge:KC_multiply_fractions:0": (
        "Multiplica los de arriba, y luego los de abajo. No necesitas un denominador común."
    ),
    "nudge:KC_multiply_fractions:1": (
        "Una fracción DE una fracción es más pequeña. Si tu respuesta creció, seguramente sumaste."
    ),
    "nudge:KC_multiply_fractions:2": (
        "Dos tercios de tres cuartos: multiplica de frente, y luego simplifica el resultado."
    ),
    # ── KC_divide_fractions ──
    "nudge:KC_divide_fractions:0": (
        "Para dividir entre una fracción, VOLTEA la segunda y multiplica. ¿La volteaste?"
    ),
    "nudge:KC_divide_fractions:1": (
        "Dividir entre menos de un entero hace la respuesta MÁS GRANDE. "
        "Si la tuya se encogió, ¿la volteaste?"
    ),
    "nudge:KC_divide_fractions:2": (
        "¿Cuántas veces cabe la segunda fracción dentro de la primera? Ese conteo es el cociente."
    ),
    # ── KC_unit_conversion ──
    "nudge:KC_unit_conversion:0": (
        "¿Cuántas unidades pequeñas caben en UNA unidad grande? Avanza desde ahí para todas ellas."
    ),
    "nudge:KC_unit_conversion:1": (
        "Unidades más pequeñas significan que necesitas MÁS de ellas. "
        "¿Tu respuesta se hizo más grande o más pequeña?"
    ),
    "nudge:KC_unit_conversion:2": (
        "Cada unidad grande está hecha de varias pequeñas. ¿Multiplicas por esa cantidad, "
        "o repartes?"
    ),
    # ── KC_gcf_lcm ──
    "nudge:KC_gcf_lcm:0": (
        "¿Te piden un divisor (que divide a ambos) o un múltiplo (que ambos dividen a él)?"
    ),
    "nudge:KC_gcf_lcm:1": (
        "Un divisor común no es mayor que ninguno de los números; un múltiplo común no es menor."
    ),
    "nudge:KC_gcf_lcm:2": (
        "Para el máximo común divisor, encuentra el número más grande que divide a ambos "
        "de forma exacta."
    ),
    # ── KC_multi_digit_division ──
    "nudge:KC_multi_digit_division:0": (
        "¿Cuántas veces enteras cabe el divisor en el número? Trabájalo cifra por cifra."
    ),
    "nudge:KC_multi_digit_division:1": (
        "Revisa el lugar de cada cifra del cociente: un cero de más o de menos cambia "
        "muchísimo el tamaño."
    ),
    "nudge:KC_multi_digit_division:2": (
        "Multiplica tu respuesta de vuelta por el divisor: ¿llega al número con el que empezaste?"
    ),
    # ── KC_decimal_operations ──
    "nudge:KC_decimal_operations:0": (
        "Cuenta las cifras decimales en AMBOS números: el producto tiene esa cantidad en total."
    ),
    "nudge:KC_decimal_operations:1": (
        "Dos números menores que uno multiplican a algo más pequeño: "
        "¿el punto está en el lugar correcto?"
    ),
    "nudge:KC_decimal_operations:2": (
        "Multiplica como números enteros primero, y luego coloca el punto según las cifras "
        "que van después de él."
    ),
    # ── KC_absolute_value ──
    "nudge:KC_absolute_value:0": (
        "El valor absoluto pregunta qué tan LEJOS del cero está un número: "
        "cuenta los pasos hacia cualquier lado."
    ),
    "nudge:KC_absolute_value:1": (
        "Una distancia nunca es negativa. ¿Tu respuesta debería llevar un signo de menos?"
    ),
    "nudge:KC_absolute_value:2": (
        "Imagina el número en la recta: ¿cuántos pasos hay de vuelta al cero, sin importar el lado?"
    ),
    # ── KC_integer_add_subtract ──
    "nudge:KC_integer_add_subtract:0": (
        "Los signos opuestos jalan en direcciones opuestas: se cancelan en parte, no se amontonan."
    ),
    "nudge:KC_integer_add_subtract:1": (
        "Empieza en el primer número y muévete según el segundo: ¿hacia qué lado te manda su signo?"
    ),
    "nudge:KC_integer_add_subtract:2": (
        "Si solo sumaste los tamaños, ignoraste los signos. El resultado debería ser más pequeño."
    ),
    # ── KC_signed_numbers ──
    "nudge:KC_signed_numbers:0": (
        "El opuesto voltea el signo cruzando el cero: un negativo se vuelve positivo, y al revés."
    ),
    "nudge:KC_signed_numbers:1": (
        "Un opuesto queda a la misma distancia del cero, del otro lado. ¿Cambió el signo?"
    ),
    "nudge:KC_signed_numbers:2": (
        "Si escribiste el mismo número de vuelta, olvidaste voltearlo al otro lado del cero."
    ),
    # ── KC_write_expressions ──
    "nudge:KC_write_expressions:0": (
        "¿Qué operación nombran las palabras, y qué cantidad va primero?"
    ),
    "nudge:KC_write_expressions:1": (
        "Para «menos que» o «dividido entre», el orden se invierte: empieza desde aquello "
        "a lo que le quitas."
    ),
    "nudge:KC_write_expressions:2": (
        "Deja que una letra represente lo desconocido, y luego arma la frase parte por parte."
    ),
    # ── KC_evaluate_expressions ──
    "nudge:KC_evaluate_expressions:0": (
        "Multiplica antes de sumar: resuelve primero la parte de multiplicar, "
        "y luego suma lo que queda."
    ),
    "nudge:KC_evaluate_expressions:1": (
        "Pon primero el valor en lugar de la letra, y luego haz las operaciones en el "
        "orden correcto."
    ),
    "nudge:KC_evaluate_expressions:2": (
        "Si sumaste antes de multiplicar, el orden se te pasó: la parte de multiplicar va primero."
    ),
    # ── KC_exponents ──
    "nudge:KC_exponents:0": (
        "Una potencia significa multiplicar la base por SÍ MISMA, no multiplicar la base "
        "por el numerito."
    ),
    "nudge:KC_exponents:1": (
        "El pequeño número de arriba te dice CUÁNTAS veces multiplicar la base entre sí."
    ),
    "nudge:KC_exponents:2": (
        "Si multiplicaste los dos números una sola vez, te saltaste las repeticiones: "
        "escribe la base esa cantidad de veces y multiplica."
    ),
    # ── KC_one_step_equations ──
    "nudge:KC_one_step_equations:0": (
        "Para dejar a x sola, haz lo OPUESTO de lo que le hacen: deshaz una suma restando, "
        "deshaz una multiplicación dividiendo."
    ),
    "nudge:KC_one_step_equations:1": (
        "Lo que le hagas a un lado, hazlo al otro para que la ecuación se mantenga en equilibrio."
    ),
    "nudge:KC_one_step_equations:2": (
        "Pon tu valor de x de vuelta: si ambos lados quedan iguales, la resolviste."
    ),
    # ── KC_equivalent_expressions ──
    "nudge:KC_equivalent_expressions:0": (
        "Multiplica el número de afuera por CADA término dentro del paréntesis, "
        "no solo por el primero."
    ),
    "nudge:KC_equivalent_expressions:1": (
        "Una expresión equivalente tiene el mismo valor: prueba un número para la letra "
        "y compruébalo."
    ),
    "nudge:KC_equivalent_expressions:2": (
        "Los términos semejantes (la misma letra) se combinan; un término con letra "
        "y un número solo no."
    ),
    # ── KC_inequalities ──
    "nudge:KC_inequalities:0": (
        "¿Hacia qué lado debe apuntar? ¿Los valores permitidos están por arriba o por debajo "
        "del número?"
    ),
    "nudge:KC_inequalities:1": (
        "¿El límite cuenta? «Por lo menos» y «como máximo» lo incluyen; «más que» no."
    ),
    "nudge:KC_inequalities:2": (
        "Deja que una letra represente el número, y luego pregunta qué valores permiten "
        "las palabras."
    ),
    # ── KC_coordinate_plane ──
    "nudge:KC_coordinate_plane:0": (
        "El primer número te mueve de lado (x); el segundo te mueve hacia arriba o hacia abajo (y)."
    ),
    "nudge:KC_coordinate_plane:1": (
        "Una coordenada negativa significa a la izquierda (en x) o hacia abajo (en y) "
        "desde el centro."
    ),
    "nudge:KC_coordinate_plane:2": (
        "Reflejar a través de un eje voltea el signo de una sola coordenada: deja la otra igual."
    ),
    # ── KC_classify_number_sets ──
    "nudge:KC_classify_number_sets:0": (
        "Los conjuntos se anidan: un número de un conjunto más pequeño está en todo conjunto "
        "que lo contiene."
    ),
    "nudge:KC_classify_number_sets:1": (
        "Todo entero se puede escribir como una fracción sobre uno, así que todo entero "
        "es racional."
    ),
    "nudge:KC_classify_number_sets:2": (
        "Los números de contar son naturales; los enteros no negativos agregan el cero; "
        "los enteros agregan los negativos."
    ),
    # ── KC_expression_parts ──
    "nudge:KC_expression_parts:0": (
        "Lee qué parte te piden: el coeficiente, la constante, o cuántos términos hay."
    ),
    "nudge:KC_expression_parts:1": (
        "El coeficiente es el número que multiplica a una variable; la constante va por su cuenta."
    ),
    "nudge:KC_expression_parts:2": (
        "Los términos son las partes unidas por signos de más o de menos: "
        "cuéntalos para saber cuántos hay."
    ),
    # ── KC_integer_multiply_divide ──
    "nudge:KC_integer_multiply_divide:0": (
        "Primero encuentra el tamaño de la respuesta, y luego decide su signo a partir de "
        "los dos signos con los que empezaste."
    ),
    "nudge:KC_integer_multiply_divide:1": (
        "Signos iguales dan un resultado positivo; signos distintos dan uno negativo. ¿Cuál es?"
    ),
    "nudge:KC_integer_multiply_divide:2": (
        "Si el tamaño está bien pero lo marcaron mal, revisa el signo: la regla lo decide."
    ),
    # ── KC_triangle_properties ──
    "nudge:KC_triangle_properties:0": (
        "Los tres ángulos de un triángulo suman un ángulo llano, y su área es la MITAD "
        "de la base por la altura."
    ),
    "nudge:KC_triangle_properties:1": (
        "Los tres ángulos forman una línea recta, no un ángulo recto. Quítale los dos que "
        "conoces a ese total del ángulo llano."
    ),
    "nudge:KC_triangle_properties:2": (
        "Un triángulo llena la MITAD del rectángulo que lo rodea, así que recuerda tomar "
        "la mitad de la base por la altura."
    ),
    # ── KC_area_polygons ──
    "nudge:KC_area_polygons:0": (
        "Un rectángulo o paralelogramo es base por altura; un triángulo es la MITAD de eso."
    ),
    "nudge:KC_area_polygons:1": (
        "Un triángulo llena la mitad de su caja envolvente, así que después de base por altura, "
        "toma la mitad."
    ),
    "nudge:KC_area_polygons:2": (
        "Si tu respuesta del triángulo se ve el doble de grande, seguramente olvidaste "
        "tomar la mitad."
    ),
    # ── KC_volume_fractional_edges ──
    "nudge:KC_volume_fractional_edges:0": (
        "El volumen llena la caja: multiplica las tres aristas, largo por ancho por altura."
    ),
    "nudge:KC_volume_fractional_edges:1": (
        "Multiplica las fracciones de frente: arriba por arriba, abajo por abajo."
    ),
    "nudge:KC_volume_fractional_edges:2": (
        "Si sumaste las aristas, ese es el movimiento equivocado: el volumen viene de "
        "multiplicarlas."
    ),
    # ── KC_polygons_coordinate_plane ──
    "nudge:KC_polygons_coordinate_plane:0": (
        "El primer número te mueve de lado (x); el segundo te mueve hacia arriba o hacia abajo (y)."
    ),
    "nudge:KC_polygons_coordinate_plane:1": (
        "En un rectángulo con lados sobre la cuadrícula, las esquinas se alinean y "
        "comparten sus números."
    ),
    "nudge:KC_polygons_coordinate_plane:2": (
        "La esquina que falta reusa la x de una esquina dada y la y de otra: emparéjalas."
    ),
    # ── KC_surface_area_nets ──
    "nudge:KC_surface_area_nets:0": (
        "Un patrón tiene SEIS caras: suma el área de cada cara, no solo las que puedes ver."
    ),
    "nudge:KC_surface_area_nets:1": (
        "Las caras vienen en pares iguales: cada cara tiene una idéntica del otro lado."
    ),
    "nudge:KC_surface_area_nets:2": (
        "Si sumaste solo tres caras, duplícalo: cada cara tiene su gemela del otro lado."
    ),
    # ── KC_mean_absolute_deviation ──
    "nudge:KC_mean_absolute_deviation:0": (
        "Toma la DISTANCIA de cada valor a la media: las distancias nunca son negativas."
    ),
    "nudge:KC_mean_absolute_deviation:1": (
        "La DMA es la distancia típica a la media: encuentra la media, y luego promedia "
        "las diferencias."
    ),
    "nudge:KC_mean_absolute_deviation:2": (
        "Si tus desviaciones se cancelaron a cero, te saltaste el valor absoluto: "
        "las distancias se suman."
    ),
    # ── KC_center_spread_shape ──
    "nudge:KC_center_spread_shape:0": (
        "Ordena los valores primero. El centro queda en medio; la dispersión mide qué tan "
        "separados están."
    ),
    "nudge:KC_center_spread_shape:1": (
        "El rango y el RIC son DIFERENCIAS: resta para hallar una dispersión, no sumes los valores."
    ),
    "nudge:KC_center_spread_shape:2": (
        "Si una dispersión salió más grande que el valor más grande, sumaste en lugar de restar."
    ),
    # ── KC_summary_statistics ──
    "nudge:KC_summary_statistics:0": (
        "Une el paso con la palabra: la mediana es el centro de los valores ORDENADOS; "
        "ordénalos primero."
    ),
    "nudge:KC_summary_statistics:1": (
        "¿Tiene sentido el tamaño? La media queda entre el valor más pequeño y el más grande."
    ),
    "nudge:KC_summary_statistics:2": (
        "Si leíste el centro de la lista tal como está, ordena los números primero, "
        "y luego toma el centro."
    ),
    # ── KC_data_displays ──
    "nudge:KC_data_displays:0": (
        "Cuenta los puntos, no las etiquetas: un valor con más de un punto encima cuenta "
        "una vez por cada punto."
    ),
    "nudge:KC_data_displays:1": (
        "¿Tiene sentido el tamaño? Un conteo no puede ser mayor que el total de datos."
    ),
    "nudge:KC_data_displays:2": (
        "Si un valor se repite, cada repetición es su propio dato: no los juntes en uno solo."
    ),
    # ── KC_categorical_data ──
    "nudge:KC_categorical_data:0": (
        "Una fracción de los encuestados va SOBRE el total de encuestados, no sobre el conteo "
        "de otra categoría."
    ),
    "nudge:KC_categorical_data:1": (
        "Lee el conteo de cada categoría en el desglose antes de combinarlos."
    ),
    "nudge:KC_categorical_data:2": (
        "Para «cuántos más», resta el conteo de una categoría al de la otra; "
        "para el total, súmalos todos."
    ),
    # ── KC_statistical_questions ──
    "nudge:KC_statistical_questions:0": (
        "Pregúntate: ¿las respuestas VARIARÍAN de una persona o caso al siguiente?"
    ),
    "nudge:KC_statistical_questions:1": (
        "Una pregunta con una sola respuesta fija NO es estadística: una estadística espera "
        "que los datos varíen."
    ),
    "nudge:KC_statistical_questions:2": (
        "Que sea sobre personas o números no basta: las respuestas tienen que diferir "
        "entre el grupo."
    ),
    # ── KC_dependent_vars ──
    "nudge:KC_dependent_vars:0": (
        "La regla MULTIPLICA la entrada por la tasa para obtener la salida: no las suma."
    ),
    "nudge:KC_dependent_vars:1": (
        "Tú eliges el valor de entrada; la regla entonces decide la salida que depende de él."
    ),
    "nudge:KC_dependent_vars:2": (
        "Mete tu entrada en la regla, y luego sigue lo que te dice que es la salida que "
        "le corresponde."
    ),
    # ── KC_equation_solutions ──
    "nudge:KC_equation_solutions:0": (
        "Pon el valor en lugar de la letra, y luego revisa: ¿ambos lados salen iguales?"
    ),
    "nudge:KC_equation_solutions:1": (
        "Un valor es solución solo si hace verdadera la ecuación cuando lo sustituyes."
    ),
    "nudge:KC_equation_solutions:2": (
        "Para encontrar qué valor funciona, deshaz la ecuación con la operación OPUESTA."
    ),
    # ── KC_check_register ──
    "nudge:KC_check_register:0": (
        "Suma cada depósito, pero RESTA cada retiro: el dinero que sale baja el saldo."
    ),
    "nudge:KC_check_register:1": (
        "Trabaja las anotaciones en orden, llevando un total acumulado conforme avanzas."
    ),
    "nudge:KC_check_register:2": (
        "Un retiro saca dinero: revisa que lo hayas quitado, no agregado."
    ),
    # ── KC_lifetime_income ──
    "nudge:KC_lifetime_income:0": (
        "El ingreso de toda la vida es la cantidad anual MULTIPLICADA por cuántos años trabajas."
    ),
    "nudge:KC_lifetime_income:1": (
        "El salario de UN año no es el de toda la vida: multiplica por los años."
    ),
    "nudge:KC_lifetime_income:2": (
        "Para una comparación, encuentra primero la diferencia anual, y luego estírala "
        "a lo largo de los años."
    ),
    # ── Misconception names (domain/misconceptions.py) ──
    "misconception_name:natural-number-bias": "Sesgo de números naturales",
    "misconception_name:add-across-error": "Error de sumar de frente",
    "misconception_name:reduce-means-smaller": "Reducir significa más pequeño",
    "misconception_name:equal-sign-as-procedural": "Signo de igual como procedimiento",
    "misconception_name:procedure-without-concept": "Procedimiento sin concepto",
    "misconception_name:rate-inversion": "Inversión de la tasa",
    "misconception_name:additive-ratio": "Razonamiento aditivo de razones",
    "misconception_name:percent-as-amount": "Por ciento como cantidad",
    "misconception_name:multiply-as-add": "Multiplicar como sumar",
    "misconception_name:conversion-inversion": "Inversión del factor de conversión",
    "misconception_name:part-part-whole-confusion": "Confusión parte-parte y parte-todo",
    "misconception_name:gcf-lcm-confusion": "Confusión entre MCD y mcm",
    "misconception_name:multiply-without-inverting": "Multiplicar sin invertir",
    "misconception_name:place-value-slip": "Desliz de valor posicional",
    "misconception_name:decimal-point-misplacement": "Punto decimal mal colocado",
    "misconception_name:signed-not-magnitude": "Valor con signo, no la magnitud",
    "misconception_name:sign-handling-error": "Error al manejar los signos",
    "misconception_name:sign-error": "Error de signo en los opuestos",
    "misconception_name:reversed-operands": "Operandos invertidos",
    "misconception_name:order-of-operations-slip": (
        "Desliz del orden de las operaciones al evaluar"
    ),
    "misconception_name:inverse-operation-error": "Operación inversa equivocada",
    "misconception_name:distributive-error": "Error en la propiedad distributiva",
    "misconception_name:flipped-inequality": "Desigualdad volteada",
    "misconception_name:coordinate-swap": "Coordenadas intercambiadas",
    "misconception_name:integer-not-rational": "El entero no es racional",
    "misconception_name:part-confusion": "Confunde coeficiente y constante",
    "misconception_name:multiply-base-by-exponent": "Multiplicar la base por el exponente",
    "misconception_name:sign-rule-error": "Error en la regla de signos al multiplicar o dividir",
    "misconception_name:triangle-formula-error": "Error en la fórmula del triángulo",
    "misconception_name:forgot-triangle-half": "Olvidó la mitad en el triángulo",
    "misconception_name:forgot-trapezoid-half": "Olvidó la mitad en el trapecio",
    "misconception_name:add-edges-error": "Suma las aristas en lugar de multiplicar",
    "misconception_name:count-three-faces": "Cuenta solo tres de las seis caras",
    "misconception_name:forgot-absolute-value": "Olvida el valor absoluto en la DMA",
    "misconception_name:range-as-sum": "Calcula el rango como máximo más mínimo",
    "misconception_name:median-without-sorting": "Toma el centro sin ordenar primero",
    "misconception_name:distinct-value-count": "Cuenta valores distintos, no los datos",
    "misconception_name:wrong-denominator": "Frecuencia relativa sobre el denominador equivocado",
    "misconception_name:treats-any-as-statistical": (
        "Trata cualquier pregunta sobre personas o números como estadística"
    ),
    "misconception_name:compare-totals-not-unit-rates": (
        "Compara los precios totales en lugar del precio por artículo"
    ),
    "misconception_name:dependent-independent-swap": (
        "Confunde la relación dependiente e independiente"
    ),
    "misconception_name:solution-substitution-error": (
        "Error de signo al sustituir para probar una solución"
    ),
    "misconception_name:add-withdrawal-instead-of-subtracting": (
        "Suma un retiro en lugar de restarlo"
    ),
    "misconception_name:forgot-multiply-by-years": "Olvida multiplicar el ingreso por los años",
}


def es_mx_text(string_id: str) -> str | None:
    """The Mexican-Spanish text for ``string_id``, or ``None`` if the bank has no entry.

    Pure dict lookup (no LLM/network/DB — CLAUDE.md §8.1). Returns ``None`` rather than raising
    so a caller can fall back to English for any id not yet translated; the parity test
    (``tests/tutor/test_hints_es.py``) guarantees every renderable English id IS present, so in
    practice this returns ``None`` only for an unknown id.
    """
    return ES_MX_HELP_STRINGS.get(string_id)


__all__ = [
    "ES_MX_HELP_STRINGS",
    "ES_MX_LOCALE",
    "ES_MX_REVIEWED",
    "es_mx_text",
]
