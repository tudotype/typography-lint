#!/usr/bin/env python3
"""
Typography Intelligence — Training Dataset Generator
=====================================================
Converts the typography YAML schema into JSONL training pairs
suitable for LoRA fine-tuning with Unsloth / HuggingFace TRL.

Pair types generated:
  1. CORRECTION  — raw text → typographically correct text
  2. DETECTION   — identify errors in text
  3. CROSS-LANG  — same content, different typographic treatment
  4. EXPLANATION  — explain which rule applies and why

Output format: JSONL with instruction/input/output fields
(Alpaca-style, compatible with most fine-tuning frameworks)
"""

import json
import yaml
import random
import itertools
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TrainingPair:
    instruction: str
    input: str
    output: str
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Synthetic text templates
# ---------------------------------------------------------------------------
# These are original sentences designed to trigger specific typographic rules.
# Grouped by the rule they test.

TEMPLATES = {
    "quotation": {
        "pt-PT": [
            ('Ele disse "está bem" e saiu.', 'Ele disse «\u2009está bem\u2009» e saiu.'),
            ('A Maria respondeu "sim, "claro que sim"".', 'A Maria respondeu «\u2009sim, \u201Cclaro que sim\u201D\u2009».'),
            ('"Vamos embora" disse o João.', '«\u2009Vamos embora\u2009» disse o João.'),
            ('O professor perguntou: "Quem sabe a resposta?"', 'O professor perguntou: «\u2009Quem sabe a resposta?\u2009»'),
            ('"Não sei" respondeu ela, "mas posso tentar".', '«\u2009Não sei\u2009» respondeu ela, «\u2009mas posso tentar\u2009».'),
        ],
        "pt-BR": [
            ('Ele disse "está bem" e saiu.', 'Ele disse \u201Cestá bem\u201D e saiu.'),
            ('A resposta foi "sim, "com certeza"".', 'A resposta foi \u201Csim, \u2018com certeza\u2019\u201D.'),
            ('"Vamos embora" disse o João.', '\u201CVamos embora\u201D disse o João.'),
        ],
        "en-US": [
            ('She said "hello" and left.', 'She said \u201Chello\u201D and left.'),
            ("He called it 'remarkable'.", 'He called it \u2018remarkable\u2019.'),
            ('The sign read "No "walk-ins" allowed".', 'The sign read \u201CNo \u2018walk-ins\u2019 allowed\u201D.'),
            ('"I agree," she said.', '\u201CI agree,\u201D she said.'),
            ('She asked "Why not?"', 'She asked \u201CWhy not?\u201D'),
        ],
        "en-GB": [
            ("She said 'hello' and left.", 'She said \u2018hello\u2019 and left.'),
            ('He called it "remarkable".', 'He called it \u201Cremarkable\u201D.'),
            ("The sign read 'No entry'.", 'The sign read \u2018No entry\u2019.'),
            ("'I agree', she said.", '\u2018I agree\u2019, she said.'),
        ],
        "fr-FR": [
            ('Elle a dit "bonjour" et est partie.', 'Elle a dit «\u202Fbonjour\u202F» et est partie.'),
            ('Il a répondu "oui, "bien sûr"".', 'Il a répondu «\u202Foui, \u201Cbien sûr\u201D\u202F».'),
            ('"Allons-y" dit-il.', '«\u202FAllons-y\u202F» dit-il.'),
        ],
        "de-DE": [
            ('Sie sagte "Hallo" und ging.', 'Sie sagte \u201EHallo\u201C und ging.'),
            ('Er nannte es "bemerkenswert".', 'Er nannte es \u201Ebemerkenswert\u201C.'),
            ('"Tschüss" sagte sie.', '\u201ETschüss\u201C sagte sie.'),
            ('Er sagte "sie meinte \'ja\' dazu".', 'Er sagte \u201Esie meinte \u2039ja\u203A dazu\u201C.'),
        ],
        "it-IT": [
            ('Lei ha detto "buongiorno" ed è uscita.', 'Lei ha detto «buongiorno» ed è uscita.'),
            ('Ha risposto "sì, "certo"".', 'Ha risposto «sì, \u201Ccerto\u201D».'),
            ('"Andiamo" disse Marco.', '«Andiamo» disse Marco.'),
        ],
        "es-ES": [
            ('Ella dijo "hola" y se fue.', 'Ella dijo «hola» y se fue.'),
            ('Él lo llamó "extraordinario".', 'Él lo llamó «extraordinario».'),
            ('"Adiós" dijo ella.', '«Adiós» dijo ella.'),
        ],
        "es-MX": [
            ('Ella dijo "hola" y se fue.', 'Ella dijo \u201Chola\u201D y se fue.'),
            ('Él lo llamó "extraordinario".', 'Él lo llamó \u201Cextraordinario\u201D.'),
            ('"Adiós" dijo ella.', '\u201CAdiós\u201D dijo ella.'),
        ],
        "nl-NL": [
            ('Ze zei "hallo" en vertrok.', 'Ze zei \u201Challo\u201D en vertrok.'),
            ('Hij noemde het "opmerkelijk".', 'Hij noemde het \u201Copmerkelijk\u201D.'),
            ('"Tot ziens" zei ze.', '\u201CTot ziens\u201D zei ze.'),
        ],
        "ro-RO": [
            ('Ea a spus "bună ziua" și a plecat.', 'Ea a spus \u201EBună ziua\u201D și a plecat.'),
            ('El a numit-o "remarcabilă".', 'El a numit-o \u201Eremarcabilă\u201D.'),
            ('"La revedere" a spus ea.', '\u201ELa revedere\u201D a spus ea.'),
            ('El a zis "ea a spus "salut" ieri".', 'El a zis \u201Eea a spus «salut» ieri\u201D.'),
        ],
        "sc": [
            ('Issu at nadu "bona die" e si nd\'est andadu.', 'Issu at nadu «bona die» e si nd\u2019est andadu.'),
            ('"Adiosu" at nadu issa.', '«Adiosu» at nadu issa.'),
        ],
    },

    "dashes": {
        "pt-PT": [
            ('O resultado - se acreditas - foi extraordinário.', 'O resultado \u2014 se acreditas \u2014 foi extraordinário.'),
            ('Páginas 10-20 do relatório.', 'Páginas 10\u201320 do relatório.'),
            ('Leia as páginas 5-15.', 'Leia as páginas 5\u201315.'),
        ],
        "en-US": [
            ('The result - if you can believe it - was extraordinary.', 'The result\u2014if you can believe it\u2014was extraordinary.'),
            ('Pages 10-20 of the report.', 'Pages 10\u201320 of the report.'),
            ('The 2020-2025 strategy plan.', 'The 2020\u20132025 strategy plan.'),
            ('She was happy - really happy - to see him.', 'She was happy\u2014really happy\u2014to see him.'),
        ],
        "en-GB": [
            ('The result - if you can believe it - was extraordinary.', 'The result \u2013 if you can believe it \u2013 was extraordinary.'),
            ('Pages 10-20 of the report.', 'Pages 10\u201320 of the report.'),
        ],
        "fr-FR": [
            ('Le résultat - si on peut le croire - était extraordinaire.', 'Le résultat \u2014 si on peut le croire \u2014 était extraordinaire.'),
            ('Pages 10-20 du rapport.', 'Pages 10\u201320 du rapport.'),
        ],
        "de-DE": [
            ('Das Ergebnis - wenn man es glauben kann - war außergewöhnlich.', 'Das Ergebnis \u2013 wenn man es glauben kann \u2013 war außergewöhnlich.'),
            ('Seiten 10-20 des Berichts.', 'Seiten 10\u201320 des Berichts.'),
        ],
        "it-IT": [
            ('Il risultato - se ci puoi credere - è stato straordinario.', 'Il risultato \u2013 se ci puoi credere \u2013 è stato straordinario.'),
            ('Pagine 10-20 del rapporto.', 'Pagine 10\u201320 del rapporto.'),
        ],
        "es-ES": [
            ('El resultado - si puedes creerlo - fue extraordinario.', 'El resultado \u2014si puedes creerlo\u2014 fue extraordinario.'),
            ('Páginas 10-20 del informe.', 'Páginas 10\u201320 del informe.'),
        ],
        "es-MX": [
            ('El resultado - si puedes creerlo - fue extraordinario.', 'El resultado \u2014si puedes creerlo\u2014 fue extraordinario.'),
        ],
        "nl-NL": [
            ('Het resultaat - als je het kunt geloven - was buitengewoon.', 'Het resultaat \u2013 als je het kunt geloven \u2013 was buitengewoon.'),
            ('Pagina 10-20 van het rapport.', 'Pagina 10\u201320 van het rapport.'),
        ],
        "ro-RO": [
            ('Rezultatul - dacă poți crede - a fost extraordinar.', 'Rezultatul \u2013 dacă poți crede \u2013 a fost extraordinar.'),
            ('Paginile 10-20 din raport.', 'Paginile 10\u201320 din raport.'),
        ],
    },

    "ellipsis": {
        "_universal": [
            ('Wait for it...', 'Wait for it\u2026'),
            ('Espera...', 'Espera\u2026'),
            ('Attendez...', 'Attendez\u2026'),
            ('Aspetta...', 'Aspetta\u2026'),
            ('Warte mal...', 'Warte mal\u2026'),
            ('Espera un momento...', 'Espera un momento\u2026'),
        ],
    },

    "measurements": {
        "_universal": [
            ("The room is 12' x 15'.", "The room is 12\u2032 \u00D7 15\u2032."),
            ('A 5\'10" person.', 'A 5\u203210\u2033 person.'),
            ('Screen resolution: 1920x1080.', 'Screen resolution: 1920\u2009\u00D7\u20091080.'),
            ('Dimensions: 800x600 pixels.', 'Dimensions: 800\u2009\u00D7\u2009600 pixels.'),
        ],
    },

    "inverted_punctuation": {
        "es-ES": [
            ('Que hora es?', '¿Qué hora es?'),
            ('Que maravilla!', '¡Qué maravilla!'),
            ('Si quieres, por que no vienes?', 'Si quieres, ¿por qué no vienes?'),
            ('Donde esta la estacion?', '¿Dónde está la estación?'),
            ('Cuantos años tienes?', '¿Cuántos años tienes?'),
            ('Que bonito!', '¡Qué bonito!'),
            ('Como te llamas?', '¿Cómo te llamas?'),
            ('Verdad que si?', '¿Verdad que sí?'),
        ],
        "es-MX": [
            ('Que onda?', '¿Qué onda?'),
            ('Que padre!', '¡Qué padre!'),
            ('Donde queda el metro?', '¿Dónde queda el metro?'),
        ],
    },

    "italian_accents": {
        "it-IT": [
            ("perche'", "perché"),
            ("e' vero", "è vero"),
            ("caffe'", "caffè"),
            ("perchè non vieni?", "perché non vieni?"),
            ("E' importante", "È importante"),
            ("cioe' questo", "cioè questo"),
            ("ne' lui ne' lei", "né lui né lei"),
            ("se' stesso", "sé stesso"),
        ],
    },

    "ordinals": {
        "pt-PT": [
            ('O 1o andar.', 'O 1.\u00BA andar.'),
            ('A 2a edição.', 'A 2.\u00AA edição.'),
            ('O 3o lugar.', 'O 3.\u00BA lugar.'),
        ],
        "it-IT": [
            ('Il 1o piano.', 'Il 1\u00BA piano.'),
            ('La 2a edizione.', 'La 2\u00AA edizione.'),
        ],
        "es-ES": [
            ('El 1er piso.', 'El 1.\u00BA piso.'),
            ('La 2a edicion.', 'La 2.\u00AA edición.'),
            ('El 1o lugar.', 'El 1.\u00BA lugar.'),
        ],
    },

    "french_spacing": {
        "fr-FR": [
            ('Pourquoi?', 'Pourquoi\u202F?'),
            ('Note: ceci est important.', 'Note\u202F: ceci est important.'),
            ('Bravo! Quel résultat!', 'Bravo\u202F! Quel résultat\u202F!'),
            ('Oui; peut-être.', 'Oui\u202F; peut-être.'),
            ('Attention: danger!', 'Attention\u202F: danger\u202F!'),
        ],
    },

    "dialogue": {
        "pt-PT": [
            ('- Boa tarde - disse ele.', '\u2014 Boa tarde \u2014 disse ele.'),
            ('- Não sei - respondeu Maria - mas vou tentar.', '\u2014 Não sei \u2014 respondeu Maria \u2014 mas vou tentar.'),
        ],
        "fr-FR": [
            ('- Bonjour - dit-il.', '\u2014\u00A0Bonjour \u2014\u00A0dit-il.'),
        ],
        "es-ES": [
            ('- Buenas tardes - dijo él.', '\u2014Buenas tardes \u2014dijo él.'),
            ('- No lo sé - respondió María.', '\u2014No lo sé \u2014respondió María.'),
        ],
        "it-IT": [
            ('- Buongiorno - disse Marco.', '\u2014 Buongiorno \u2014 disse Marco.'),
        ],
        "ro-RO": [
            ('- Bună ziua! spuse el.', '\u2014 Bună ziua! spuse el.'),
            ('- Nu știu - răspunse ea - dar voi încerca.', '\u2014 Nu știu \u2014 răspunse ea \u2014, dar voi încerca.'),
        ],
    },

    "romanian_diacritics": {
        "ro-RO": [
            ('\u015Fcoal\u0103',       'școală'),
            ('\u0163ar\u0103',         'țară'),
            ('Bucure\u015Fti',         'București'),
            ('cuno\u015Ftin\u0163e',   'cunoștințe'),
            ('\u015Ftiin\u0163\u0103', 'știință'),
            ('\u0162inuturi',          'Ținuturi'),
            ('gre\u015Feal\u0103',     'greșeală'),
            ('în\u0163elegere',        'înțelegere'),
        ],
    },

    "dutch_ij": {
        "nl-NL": [
            ('Ijsselmeer', 'IJsselmeer'),
            ('Ijmuiden',   'IJmuiden'),
            ('het Ijmeer', 'het IJmeer'),
            ('Ijzer',      'IJzer'),
            ('Ijburg',     'IJburg'),
        ],
    },

    "sardinian_elision": {
        "sc": [
            ("s' abba",   "s\u2019abba"),
            ("s 'abba",   "s\u2019abba"),
            ("d' oe",     "d\u2019oe"),
            ("s' istiu",  "s\u2019istiu"),
            ("b' est",    "b\u2019est"),
        ],
    },

    "minus_sign": {
        "_universal": [
            ("-5 degrees",           "\u22125 degrees"),
            ("The temperature is -15 C.", "The temperature is \u221215\u00A0°C."),
            ("10 - 3 = 7",          "10 \u2212 3 = 7"),
            ("a loss of -2.5%",     "a loss of \u22122.5%"),
            ("-0.3 seconds",        "\u22120.3 seconds"),
        ],
    },

    "legal_symbols": {
        "_universal": [
            ("(c) 2025 Acme Corp",     "\u00A9 2025 Acme Corp"),
            ("Brand(TM)",              "Brand\u2122"),
            ("Logo(R) is registered",  "Logo\u00AE is registered"),
            ("Copyright (c) all rights reserved", "Copyright \u00A9 all rights reserved"),
            ("Product(TM) by Company(R)", "Product\u2122 by Company\u00AE"),
        ],
    },

    "fractions": {
        "_universal": [
            ("1/2 cup of flour",       "\u00BD cup of flour"),
            ("3/4 of the budget",      "\u00BE of the budget"),
            ("1/4 teaspoon",           "\u00BC teaspoon"),
            ("about 1/3 of the time",  "about \u2153 of the time"),
            ("nearly 2/3 complete",    "nearly \u2154 complete"),
        ],
    },

    "degree_symbol": {
        "_universal": [
            ("20oC outside",           "20\u00A0\u00B0C outside"),
            ("set oven to 180oC",      "set oven to 180\u00A0\u00B0C"),
            ("a 45o angle",            "a 45\u00B0 angle"),
            ("it was 32ºF",            "it was 32\u00A0\u00B0F"),
            ("-5oC wind chill",        "\u22125\u00A0\u00B0C wind chill"),
        ],
    },

    "currency": {
        "en-US": [
            ("$ 10.00",           "$10.00"),
            ("10.00$",            "$10.00"),
            ("USD 25",            "$25.00"),
            ("$1000",             "$1,000"),
        ],
        "en-GB": [
            ("£ 10.00",           "£10.00"),
            ("10.00£",            "£10.00"),
            ("GBP 25",            "£25.00"),
        ],
        "pt-PT": [
            ("€10,00",            "10,00\u00A0\u20AC"),
            ("EUR 10,00",         "10,00\u00A0\u20AC"),
            ("10,00€",            "10,00\u00A0\u20AC"),
            ("€ 1.250,00",        "1.250,00\u00A0\u20AC"),
        ],
        "fr-FR": [
            ("€10,00",            "10,00\u00A0\u20AC"),
            ("EUR 10,00",         "10,00\u00A0\u20AC"),
            ("10,00€",            "10,00\u00A0\u20AC"),
        ],
        "de-DE": [
            ("€10,00",            "10,00\u00A0\u20AC"),
            ("EUR 10,00",         "10,00\u00A0\u20AC"),
            ("10,00€",            "10,00\u00A0\u20AC"),
        ],
        "it-IT": [
            ("€10,00",            "10,00\u00A0\u20AC"),
            ("EUR 10,00",         "10,00\u00A0\u20AC"),
        ],
        "es-ES": [
            ("€10,00",            "10,00\u00A0\u20AC"),
            ("EUR 10,00",         "10,00\u00A0\u20AC"),
        ],
        "es-MX": [
            ("$ 500.00",          "$500.00"),
            ("MXN 500",           "$500.00"),
        ],
        "nl-NL": [
            ("€10,00",            "\u20AC\u00A010,00"),
            ("EUR 10,00",         "\u20AC\u00A010,00"),
            ("10,00€",            "\u20AC\u00A010,00"),
        ],
        "ro-RO": [
            ("50 RON",            "50\u00A0lei"),
            ("€10,00",            "10,00\u00A0\u20AC"),
        ],
    },

    "arrows": {
        "_universal": [
            ("click here -> next page",    "click here \u2192 next page"),
            ("go back <- previous",        "go back \u2190 previous"),
            ("option A -> option B",       "option A \u2192 option B"),
            ("input -> process -> output", "input \u2192 process \u2192 output"),
        ],
    },

    "whitespace": {
        "_universal": [
            ("too  many  spaces",    "too many spaces"),
            ("trailing space ",      "trailing space"),
            ("double  space after.", "double space after."),
        ],
    },

    # --- BATCH 1-3 RULES ---

    "french_ligatures": {
        "fr-FR": [
            ("coeur",     "cœur"),
            ("soeur",     "sœur"),
            ("oeuvre",    "œuvre"),
            ("oeuf",      "œuf"),
            ("boeuf",     "bœuf"),
            ("noeud",     "nœud"),
            ("voeu",      "vœu"),
            ("manoeuvre", "manœuvre"),
            ("COEUR",     "CŒUR"),
            ("OEUVRE",    "ŒUVRE"),
        ],
    },

    "french_capital_accents": {
        "fr-FR": [
            ("L'ETAT",      "L'ÉTAT"),
            ("A PARIS",     "À PARIS"),
            ("HOTEL",       "HÔTEL"),
            ("ETRE",        "ÊTRE"),
            ("ECOLE",       "ÉCOLE"),
            ("EVENEMENT",   "ÉVÉNEMENT"),
            ("ETUDE",       "ÉTUDE"),
            ("ELECTRICITE", "ÉLECTRICITÉ"),
        ],
    },

    "german_eszett": {
        "de-DE": [
            ("STRASSE",     "STRA\u1E9E"),
            ("GROSSE",      "GRO\u1E9E"),
            ("FUSSBALL",    "FU\u1E9EBALL"),
            ("GRUSS",       "GRU\u1E9E"),
            ("MASS",        "MA\u1E9E"),
        ],
    },

    "german_din5008": {
        "de-DE": [
            ("z.B.",    "z.\u202FB."),
            ("d.h.",    "d.\u202Fh."),
            ("u.a.",    "u.\u202Fa."),
            ("i.d.R.",  "i.\u202Fd.\u202FR."),
            ("e.V.",    "e.\u202FV."),
            ("s.o.",    "s.\u202Fo."),
        ],
    },

    "homoglyph_correction": {
        "de-DE": [
            ("Straβe",   "Straße"),     # Greek beta → German ß
        ],
        "pt-PT": [
            ("1o andar",  "1.\u00BA andar"),  # superscript o vs ordinal
        ],
        "_universal": [
            ("20ºC",    "20\u00A0°C"),  # ordinal indicator → degree sign
        ],
    },

    "nbsp_obligations": {
        "_universal": [
            ("p. 5",        "p.\u00A05"),
            ("§ 12",        "§\u00A012"),
            ("fig. 3",      "fig.\u00A03"),
            ("100 km",      "100\u00A0km"),
            ("J. R. R. Tolkien",  "J.\u00A0R.\u00A0R.\u00A0Tolkien"),
            ("cap. 4",      "cap.\u00A04"),
            ("No. 42",      "№\u00A042"),
            ("50 kg",       "50\u00A0kg"),
            ("3 May 2025",  "3\u00A0May 2025"),
        ],
        "fr-FR": [
            ("M. Dupont",   "M.\u00A0Dupont"),
            ("Mme Curie",   "Mme\u00A0Curie"),
            ("50 %",        "50\u202F%"),
            ("Dr Lefevre",  "Dr\u00A0Lefevre"),
        ],
        "de-DE": [
            ("Dr. Müller",  "Dr.\u00A0Müller"),
            ("Abb. 4",      "Abb.\u00A04"),
            ("Prof. Schmidt", "Prof.\u00A0Schmidt"),
        ],
        "pt-PT": [
            ("Sr. Silva",   "Sr.\u00A0Silva"),
            ("Dr.ª Sousa",  "Dr.ª\u00A0Sousa"),
            ("n.º 5",       "n.\u00BA\u00A05"),
            ("Dom Pedro",   "Dom\u00A0Pedro"),
        ],
        "pt-BR": [
            ("Sr. Santos",  "Sr.\u00A0Santos"),
            ("Dr.ª Lima",   "Dr.ª\u00A0Lima"),
            ("p. 23",       "p.\u00A023"),
        ],
        "es-ES": [
            ("Sr. García",  "Sr.\u00A0García"),
            ("pág. 12",     "pág.\u00A012"),
            ("Dr. Martínez", "Dr.\u00A0Martínez"),
        ],
        "it-IT": [
            ("Dott. Rossi",  "Dott.\u00A0Rossi"),
            ("Sig. Bianchi", "Sig.\u00A0Bianchi"),
            ("p. 15",        "p.\u00A015"),
        ],
        "nl-NL": [
            ("Dr. de Vries", "Dr.\u00A0de Vries"),
            ("p. 8",         "p.\u00A08"),
            ("Mr. Jansen",   "Mr.\u00A0Jansen"),
        ],
        "ro-RO": [
            ("Dl. Popescu",  "Dl.\u00A0Popescu"),
            ("D-na Ionescu", "D-na\u00A0Ionescu"),
            ("p. 10",        "p.\u00A010"),
        ],
    },

    # --- BATCH 1 — CODE EXCLUSION, NORMALIZATION, ZERO-WIDTH ---

    "code_exclusion": {
        "_universal": [
            # Code blocks must be left untouched — the "correct" output preserves the raw form
            ('The function `printf("hello")` prints text.', 'The function `printf("hello")` prints text.'),
            ('Visit https://example.com/path?q="test" for info.', 'Visit https://example.com/path?q="test" for info.'),
            ('The file is at /usr/bin/python3 on disk.', 'The file is at /usr/bin/python3 on disk.'),
            ('Send mail to user@example.com for details.', 'Send mail to user@example.com for details.'),
            ('Use the --verbose flag for more output.', 'Use the --verbose flag for more output.'),
            ('The variable myVariableName stores the count.', 'The variable myVariableName stores the count.'),
            ('Check version v2.1.0-beta before deploying.', 'Check version v2.1.0-beta before deploying.'),
            ('Set $HOME to your user directory.', 'Set $HOME to your user directory.'),
            ('The regex pattern [a-z]+ matches lowercase.', 'The regex pattern [a-z]+ matches lowercase.'),
            ('Run `npm install --save-dev` first.', 'Run `npm install --save-dev` first.'),
        ],
        "en-US": [
            # Mixed context: code inside prose — only prose gets corrected
            ('She said "yes" and ran `echo "hello"` in terminal.', 'She said \u201Cyes\u201D and ran `echo "hello"` in terminal.'),
            ('The page at https://example.com says "welcome".', 'The page at https://example.com says \u201Cwelcome\u201D.'),
            ('He typed user@mail.com and said "done".', 'He typed user@mail.com and said \u201Cdone\u201D.'),
        ],
        "fr-FR": [
            ('Elle a dit "oui" et a lancé `echo "bonjour"`.', 'Elle a dit «\u202Foui\u202F» et a lancé `echo "bonjour"`.'),
            ('Visitez https://exemple.fr et dites "merci".', 'Visitez https://exemple.fr et dites «\u202Fmerci\u202F».'),
            ('Le fichier /etc/config contient "données".', 'Le fichier /etc/config contient «\u202Fdonnées\u202F».'),
        ],
        "de-DE": [
            ('Sie sagte "ja" und führte `echo "hallo"` aus.', 'Sie sagte \u201Eja\u201C und führte `echo "hallo"` aus.'),
            ('Die Datei C:\\Users\\test enthält "Daten".', 'Die Datei C:\\Users\\test enthält \u201EDaten\u201C.'),
            ('Besuchen Sie https://beispiel.de und sagen Sie "danke".', 'Besuchen Sie https://beispiel.de und sagen Sie \u201Edanke\u201C.'),
        ],
    },

    "normalization": {
        "_universal": [
            # NFC normalization: decomposed sequences should be composed
            # e\u0301 (e + combining acute) → \u00E9 (precomposed é)
            ("caf\u0065\u0301 latte", "caf\u00E9 latte"),
            ("re\u0301sume\u0301 submitted", "r\u00E9sum\u00E9 submitted"),
            ("nai\u0308ve approach", "na\u00EFve approach"),
            ("cre\u0300me bru\u0302le\u0301e", "cr\u00E8me br\u00FBl\u00E9e"),
        ],
        "fr-FR": [
            ("E\u0301TAT", "\u00C9TAT"),
            ("a\u0300 Paris", "\u00E0 Paris"),
            ("Ho\u0302tel de ville", "H\u00F4tel de ville"),
        ],
        "pt-PT": [
            ("ac\u0327a\u0303o", "a\u00E7\u00E3o"),
            ("informa\u0327a\u0303o", "informa\u00E7\u00E3o"),
            ("cora\u0327a\u0303o", "cora\u00E7\u00E3o"),
        ],
        "de-DE": [
            ("Mu\u0308nchen", "M\u00FCnchen"),
            ("u\u0308ber", "\u00FCber"),
            ("A\u0308nderung", "\u00C4nderung"),
        ],
        "ro-RO": [
            ("Roma\u0302nia", "Rom\u00E2nia"),
            ("i\u0302nceput", "\u00EEnceput"),
            ("pa\u0302ine", "p\u00E2ine"),
        ],
    },

    "zero_width_characters": {
        "_universal": [
            # Strip stray ZWSP (U+200B) from prose
            ("Hello\u200B world",           "Hello world"),
            ("typographic\u200B correction", "typographic correction"),
            ("the\u200B quick\u200B fox",   "the quick fox"),
            # Strip stray BOM (U+FEFF) from mid-text
            ("good\uFEFF morning",          "good morning"),
            ("test\uFEFF data\uFEFF here",  "test data here"),
        ],
        "de-DE": [
            # Preserve ZWNJ for ligature suppression in German compounds
            ("Auf\u200Clage",   "Auf\u200Clage"),
            ("Schiff\u200Cfahrt", "Schiff\u200Cfahrt"),
            ("Sauerstoff\u200Cflasche", "Sauerstoff\u200Cflasche"),
            # But strip stray ZWSP
            ("Auf\u200Blage",   "Auflage"),
        ],
        "fr-FR": [
            # Strip ZWSP artifacts in French text
            ("c\u200B\u0153ur",            "c\u0153ur"),
            ("l\u200B'\u00E9tat",          "l\u2019\u00E9tat"),
            ("bonjour\u200B le monde",     "bonjour le monde"),
        ],
    },

    # --- BATCH 2 — EXPANDED HOMOGLYPH AND CAPITAL ACCENT COVERAGE ---

    "capital_accents_multilingual": {
        "es-ES": [
            ("AREA",           "\u00C1REA"),
            ("LINGUISTICA",    "LING\u00DC\u00CDSTICA"),
            ("NUMERO",         "N\u00DAMERO"),
            ("ARTICULO",       "ART\u00CDCULO"),
            ("ULTIMA EDICION", "\u00DALTIMA EDICI\u00D3N"),
        ],
        "pt-PT": [
            ("ACAO",           "A\u00C7\u00C3O"),
            ("INFORMACAO",     "INFORMA\u00C7\u00C3O"),
            ("PORTUGUES",      "PORTUGU\u00CAS"),
            ("CORACAO",        "CORA\u00C7\u00C3O"),
            ("E NECESSARIO",   "\u00C9 NECESS\u00C1RIO"),
        ],
        "pt-BR": [
            ("ACAO",           "A\u00C7\u00C3O"),
            ("SAO PAULO",      "S\u00C3O PAULO"),
            ("INFORMACAO",     "INFORMA\u00C7\u00C3O"),
        ],
        "it-IT": [
            ("CITTA",          "CITT\u00C0"),
            ("PERCHE",         "PERCH\u00C9"),
            ("UNIVERSITA",     "UNIVERSIT\u00C0"),
            ("LUNEDI",         "LUNED\u00CC"),
        ],
        "ro-RO": [
            ("ROMANIA",        "ROM\u00C2NIA"),
            ("INCEPUT",        "\u00CENCEPUT"),
            ("STIINTA",        "\u0218TIIN\u021A\u0102"),
        ],
        "de-DE": [
            ("UBERSICHT",      "\u00DCBERSICHT"),
            ("ANDERUNG",       "\u00C4NDERUNG"),
            ("OFFNUNG",        "\u00D6FFNUNG"),
        ],
    },

    "homoglyph_expanded": {
        "de-DE": [
            # Greek beta vs German eszett
            ("Stra\u03B2e",       "Stra\u00DFe"),
            ("Gru\u03B2",        "Gru\u00DF"),
            ("Fu\u03B2ball",      "Fu\u00DFball"),
        ],
        "_universal": [
            # Ordinal indicator vs degree sign
            ("20\u00BAC",         "20\u00A0\u00B0C"),
            ("It is 32\u00BAF",   "It is 32\u00A0\u00B0F"),
            ("Set to 180\u00BAC", "Set to 180\u00A0\u00B0C"),
            # Grave accent vs apostrophe
            ("it`s fine",         "it\u2019s fine"),
            ("don`t worry",       "don\u2019t worry"),
            ("she`s here",        "she\u2019s here"),
        ],
        "fr-FR": [
            # Grave accent misused as apostrophe
            ("l`\u00E9tat",       "l\u2019\u00E9tat"),
            ("aujourd`hui",       "aujourd\u2019hui"),
            ("c`est vrai",        "c\u2019est vrai"),
        ],
        "it-IT": [
            # Grave accent misused as apostrophe
            ("l`uomo",            "l\u2019uomo"),
            ("un`altra",          "un\u2019altra"),
            ("l`anno",            "l\u2019anno"),
        ],
        "pt-PT": [
            # Ordinal indicator confusion
            ("1\u00B0 andar",     "1.\u00BA andar"),
            ("2\u00B0 lugar",     "2.\u00BA lugar"),
            ("3\u00AA edição",    "3.\u00AA edi\u00E7\u00E3o"),
        ],
        "es-ES": [
            # Ordinal indicator confusion
            ("1\u00B0 piso",      "1.\u00BA piso"),
            ("2\u00B0 lugar",     "2.\u00BA lugar"),
            ("3\u00AA edición",   "3.\u00AA edici\u00F3n"),
        ],
    },

    # --- BATCH 4 — LOCALE-BRANCHED PUNCTUATION ---

    "colon_capitalisation": {
        "en-US": [
            # EN-US capitalises after colon when an independent clause follows (Chicago 6.64)
            ("The verdict was clear: he was guilty.", "The verdict was clear: He was guilty."),
            ("She knew one thing: the plan had failed.", "She knew one thing: The plan had failed."),
            ("The message was simple: we must act now.", "The message was simple: We must act now."),
            # Lowercase when NOT an independent clause
            ("She had one goal: To win.", "She had one goal: to win."),
            ("He brought three items: Bread, cheese, and wine.", "He brought three items: bread, cheese, and wine."),
            ("There was one problem: Too little time.", "There was one problem: too little time."),
        ],
        "en-GB": [
            # EN-GB always lowercase after colon
            ("The verdict was clear: He was guilty.", "The verdict was clear: he was guilty."),
            ("She knew one thing: The plan had failed.", "She knew one thing: the plan had failed."),
            ("The message was simple: We must act now.", "The message was simple: we must act now."),
        ],
        "fr-FR": [
            # FR never capitalises after colon
            ("Le verdict est clair\u202F: Il est coupable.", "Le verdict est clair\u202F: il est coupable."),
            ("Le message était simple\u202F: Nous devons agir.", "Le message était simple\u202F: nous devons agir."),
            ("Elle savait une chose\u202F: Le plan avait échoué.", "Elle savait une chose\u202F: le plan avait échoué."),
        ],
        "de-DE": [
            # DE capitalises after colon when a full sentence follows (Duden R 81)
            ("Das Ergebnis war klar: er war schuldig.", "Das Ergebnis war klar: Er war schuldig."),
            ("Die Botschaft war einfach: wir müssen handeln.", "Die Botschaft war einfach: Wir müssen handeln."),
            ("Er wusste eines: die Zeit war knapp.", "Er wusste eines: Die Zeit war knapp."),
            # Lowercase for fragments (nouns capitalised by German rules, not colon rules)
            ("Er brachte mit: Brot, Käse und Wein.", "Er brachte mit: Brot, Käse und Wein."),
        ],
        "pt-PT": [
            # PT always lowercase after colon
            ("O veredicto foi claro: Ele era culpado.", "O veredicto foi claro: ele era culpado."),
            ("A mensagem era simples: Devemos agir agora.", "A mensagem era simples: devemos agir agora."),
            ("Ela sabia de uma coisa: O plano tinha falhado.", "Ela sabia de uma coisa: o plano tinha falhado."),
        ],
        "pt-BR": [
            ("O veredicto foi claro: Ele era culpado.", "O veredicto foi claro: ele era culpado."),
            ("A mensagem era simples: Devemos agir agora.", "A mensagem era simples: devemos agir agora."),
            ("Ela sabia de uma coisa: O plano tinha falhado.", "Ela sabia de uma coisa: o plano tinha falhado."),
        ],
        "it-IT": [
            # IT always lowercase after colon
            ("Il verdetto era chiaro: Era colpevole.", "Il verdetto era chiaro: era colpevole."),
            ("Il messaggio era semplice: Dobbiamo agire.", "Il messaggio era semplice: dobbiamo agire."),
            ("Sapeva una cosa: Il piano era fallito.", "Sapeva una cosa: il piano era fallito."),
        ],
        "es-ES": [
            # ES always lowercase after colon (except salutations)
            ("El veredicto fue claro: Él era culpable.", "El veredicto fue claro: él era culpable."),
            ("El mensaje fue simple: Debemos actuar.", "El mensaje fue simple: debemos actuar."),
            ("Ella sabía una cosa: El plan había fracasado.", "Ella sabía una cosa: el plan había fracasado."),
        ],
        "es-MX": [
            ("El veredicto fue claro: Él era culpable.", "El veredicto fue claro: él era culpable."),
            ("El mensaje fue simple: Debemos actuar.", "El mensaje fue simple: debemos actuar."),
            ("Ella sabía una cosa: El plan había fracasado.", "Ella sabía una cosa: el plan había fracasado."),
        ],
        "nl-NL": [
            # NL always lowercase after colon
            ("Het oordeel was duidelijk: Hij was schuldig.", "Het oordeel was duidelijk: hij was schuldig."),
            ("De boodschap was simpel: We moeten handelen.", "De boodschap was simpel: we moeten handelen."),
            ("Ze wist één ding: Het plan was mislukt.", "Ze wist één ding: het plan was mislukt."),
        ],
        "ro-RO": [
            # RO always lowercase after colon
            ("Verdictul a fost clar: El era vinovat.", "Verdictul a fost clar: el era vinovat."),
            ("Mesajul era simplu: Trebuie să acționăm.", "Mesajul era simplu: trebuie să acționăm."),
            ("Ea știa un lucru: Planul eșuase.", "Ea știa un lucru: planul eșuase."),
        ],
    },

    "serial_comma": {
        "en-US": [
            # EN-US editorial register enforces serial comma
            ("red, white and blue", "red, white, and blue"),
            ("apples, oranges and bananas", "apples, oranges, and bananas"),
            ("reading, writing and arithmetic", "reading, writing, and arithmetic"),
            # Disambiguation cases — serial comma always required
            ("I love my parents, Batman and Robin.", "I love my parents, Batman, and Robin."),
        ],
        "en-GB": [
            # EN-GB generally omits serial comma
            ("red, white, and blue", "red, white and blue"),
            ("apples, oranges, and bananas", "apples, oranges and bananas"),
            ("reading, writing, and arithmetic", "reading, writing and arithmetic"),
        ],
        "fr-FR": [
            # FR prohibits serial comma
            ("rouge, blanc, et bleu", "rouge, blanc et bleu"),
            ("lire, écrire, ou parler", "lire, écrire ou parler"),
            ("pommes, oranges, et bananes", "pommes, oranges et bananes"),
        ],
        "de-DE": [
            # DE prohibits serial comma
            ("rot, weiß, und blau", "rot, weiß und blau"),
            ("lesen, schreiben, und rechnen", "lesen, schreiben und rechnen"),
            ("Äpfel, Orangen, und Bananen", "Äpfel, Orangen und Bananen"),
        ],
        "pt-PT": [
            ("vermelho, branco, e azul", "vermelho, branco e azul"),
            ("ler, escrever, e falar", "ler, escrever e falar"),
            ("maçãs, laranjas, e bananas", "maçãs, laranjas e bananas"),
        ],
        "pt-BR": [
            ("vermelho, branco, e azul", "vermelho, branco e azul"),
            ("ler, escrever, e falar", "ler, escrever e falar"),
            ("maçãs, laranjas, e bananas", "maçãs, laranjas e bananas"),
        ],
        "it-IT": [
            ("rosso, bianco, e blu", "rosso, bianco e blu"),
            ("leggere, scrivere, e parlare", "leggere, scrivere e parlare"),
            ("mele, arance, e banane", "mele, arance e banane"),
        ],
        "es-ES": [
            ("rojo, blanco, y azul", "rojo, blanco y azul"),
            ("leer, escribir, y hablar", "leer, escribir y hablar"),
            ("manzanas, naranjas, y plátanos", "manzanas, naranjas y plátanos"),
        ],
        "es-MX": [
            ("rojo, blanco, y azul", "rojo, blanco y azul"),
            ("leer, escribir, y hablar", "leer, escribir y hablar"),
            ("manzanas, naranjas, y plátanos", "manzanas, naranjas y plátanos"),
        ],
        "nl-NL": [
            ("rood, wit, en blauw", "rood, wit en blauw"),
            ("lezen, schrijven, en rekenen", "lezen, schrijven en rekenen"),
            ("appels, sinaasappels, en bananen", "appels, sinaasappels en bananen"),
        ],
        "ro-RO": [
            ("roșu, alb, și albastru", "roșu, alb și albastru"),
            ("a citi, a scrie, și a vorbi", "a citi, a scrie și a vorbi"),
            ("mere, portocale, și banane", "mere, portocale și banane"),
        ],
    },

    "quote_punctuation_placement": {
        "en-US": [
            # US typesetters' convention: comma/period always inside closing quote
            ('He called it "magnificent".', 'He called it \u201Cmagnificent.\u201D'),
            ('She whispered "goodbye".', 'She whispered \u201Cgoodbye.\u201D'),
            ('The report labelled it "urgent",', 'The report labelled it \u201Curgent,\u201D'),
            ('They described the event as "historic".', 'They described the event as \u201Chistoric.\u201D'),
        ],
        "en-GB": [
            # Logical convention: comma/period outside unless part of quoted material
            ("He called it \u2018magnificent.\u2019", "He called it \u2018magnificent\u2019."),
            ("She whispered \u2018goodbye.\u2019", "She whispered \u2018goodbye\u2019."),
            ("The report labelled it \u2018urgent,\u2019", "The report labelled it \u2018urgent\u2019,"),
            ("They described the event as \u2018historic.\u2019", "They described the event as \u2018historic\u2019."),
        ],
        "fr-FR": [
            # Logical convention with guillemets
            ("Il a dit \u00AB\u202Fmagnifique.\u202F\u00BB", "Il a dit \u00AB\u202Fmagnifique\u202F\u00BB."),
            ("Elle a murmuré \u00AB\u202Fau revoir.\u202F\u00BB", "Elle a murmuré \u00AB\u202Fau revoir\u202F\u00BB."),
            ("Le rapport le qualifiait d\u2019\u00AB\u202Furgent.\u202F\u00BB", "Le rapport le qualifiait d\u2019\u00AB\u202Furgent\u202F\u00BB."),
        ],
        "de-DE": [
            # Logical convention
            ("Er nannte es \u201Egroßartig.\u201C", "Er nannte es \u201Egroßartig\u201C."),
            ("Sie flüsterte \u201Eauf Wiedersehen.\u201C", "Sie flüsterte \u201Eauf Wiedersehen\u201C."),
            ("Der Bericht bezeichnete es als \u201Edringend.\u201C", "Der Bericht bezeichnete es als \u201Edringend\u201C."),
        ],
        "pt-PT": [
            # Logical convention with guillemets
            ("Ele chamou-o de \u00AB\u2009magnífico.\u2009\u00BB", "Ele chamou-o de \u00AB\u2009magnífico\u2009\u00BB."),
            ("Ela sussurrou \u00AB\u2009adeus.\u2009\u00BB", "Ela sussurrou \u00AB\u2009adeus\u2009\u00BB."),
            ("O relatório classificou-o como \u00AB\u2009urgente.\u2009\u00BB", "O relatório classificou-o como \u00AB\u2009urgente\u2009\u00BB."),
        ],
        "it-IT": [
            # Logical convention with guillemets
            ("Lo ha definito \u00ABmagnifico.\u00BB", "Lo ha definito \u00ABmagnifico\u00BB."),
            ("Ha sussurrato \u00ABaddio.\u00BB", "Ha sussurrato \u00ABaddio\u00BB."),
            ("Il rapporto lo definiva \u00ABurgente.\u00BB", "Il rapporto lo definiva \u00ABurgente\u00BB."),
        ],
        "es-ES": [
            # Logical convention with guillemets
            ("Lo llamó \u00ABmagnífico.\u00BB", "Lo llamó \u00ABmagnífico\u00BB."),
            ("Ella susurró \u00ABadiós.\u00BB", "Ella susurró \u00ABadiós\u00BB."),
            ("El informe lo calificó de \u00ABurgente.\u00BB", "El informe lo calificó de \u00ABurgente\u00BB."),
        ],
        "nl-NL": [
            # Logical convention
            ("Hij noemde het \u201Cprachtig.\u201D", "Hij noemde het \u201Cprachtig\u201D."),
            ("Ze fluisterde \u201Ctot ziens.\u201D", "Ze fluisterde \u201Ctot ziens\u201D."),
            ("Het rapport noemde het \u201Cdringend.\u201D", "Het rapport noemde het \u201Cdringend\u201D."),
        ],
        "ro-RO": [
            # Logical convention
            ("El l-a numit \u201Emagnific.\u201D", "El l-a numit \u201Emagnific\u201D."),
            ("Ea a șoptit \u201Ela revedere.\u201D", "Ea a șoptit \u201Ela revedere\u201D."),
            ("Raportul l-a calificat drept \u201Eurgent.\u201D", "Raportul l-a calificat drept \u201Eurgent\u201D."),
        ],
    },

    "abbreviation_periods": {
        "en-US": [
            # EN-US: period after ALL abbreviations
            ("Mr Smith arrived.", "Mr. Smith arrived."),
            ("Dr Jones is here.", "Dr. Jones is here."),
            ("St Patrick was Irish.", "St. Patrick was Irish."),
            ("Jr was added to his name.", "Jr. was added to his name."),
        ],
        "en-GB": [
            # EN-GB: drop period for contractions; keep for truncations
            ("Mr. Smith arrived.", "Mr Smith arrived."),
            ("Dr. Jones is here.", "Dr Jones is here."),
            ("St. Patrick was Irish.", "St Patrick was Irish."),
            # Truncations keep the period
            ("Prof Smith spoke.", "Prof. Smith spoke."),
            ("Rev Williams officiated.", "Rev. Williams officiated."),
            ("Gen Carter commanded.", "Gen. Carter commanded."),
        ],
        "fr-FR": [
            # FR: M. (truncation → period), Mme/Dr (contraction → no period)
            ("M Dupont est arrivé.", "M. Dupont est arrivé."),
            ("Mme. Curie a parlé.", "Mme Curie a parlé."),
            ("Dr. Martin est là.", "Dr Martin est là."),
            ("Prof Lefèvre a publié.", "Prof. Lefèvre a publié."),
        ],
        "de-DE": [
            # DE: all abbreviations take a period
            ("Dr Müller ist hier.", "Dr. Müller ist hier."),
            ("Prof Schmidt sprach.", "Prof. Schmidt sprach."),
            ("Hr Becker kam an.", "Hr. Becker kam an."),
            ("Nr 42 ist verfügbar.", "Nr. 42 ist verfügbar."),
        ],
        "pt-PT": [
            # PT: period after most abbreviations
            ("Sr Silva chegou.", "Sr. Silva chegou."),
            ("Dra Sousa atendeu.", "Dra. Sousa atendeu."),
            ("Prof Santos publicou.", "Prof. Santos publicou."),
        ],
        "pt-BR": [
            ("Sr Santos chegou.", "Sr. Santos chegou."),
            ("Dra Lima atendeu.", "Dra. Lima atendeu."),
            ("Prof Oliveira publicou.", "Prof. Oliveira publicou."),
        ],
        "es-ES": [
            # ES: period after abbreviations
            ("Sr García llegó.", "Sr. García llegó."),
            ("Dra Martínez atendió.", "Dra. Martínez atendió."),
            ("Ud puede pasar.", "Ud. puede pasar."),
        ],
        "it-IT": [
            # IT: period for truncations, no period when last letter preserved
            ("Sig Rossi è arrivato.", "Sig. Rossi è arrivato."),
            ("Dott Bianchi ha parlato.", "Dott. Bianchi ha parlato."),
            ("Prof Conti ha pubblicato.", "Prof. Conti ha pubblicato."),
        ],
        "nl-NL": [
            # NL: periods in abbreviations
            ("a. u. b. wilt u wachten.", "a.u.b. wilt u wachten."),
            ("J.P. Coen was een bestuurder.", "J. P. Coen was een bestuurder."),
            ("d. w. z. het is klaar.", "d.w.z. het is klaar."),
        ],
    },

    "abbreviation_haplology": {
        "_universal": [
            # Never produce double period at sentence end
            ("They sell fruit, vegetables, etc..", "They sell fruit, vegetables, etc."),
            ("He works for Acme Corp..", "He works for Acme Corp."),
            ("She earned her Ph.D..", "She earned her Ph.D."),
            ("The event starts at 3 p.m..", "The event starts at 3 p.m."),
            ("The company was founded in Washington, D.C..", "The company was founded in Washington, D.C."),
            ("Please refer to vol. III, ch. 5, p. 12, etc..", "Please refer to vol. III, ch. 5, p. 12, etc."),
        ],
    },

    "footnote_mark_placement": {
        "en-US": [
            # EN: footnote mark AFTER punctuation
            ("Typography matters\u00B9.", "Typography matters.\u00B9"),
            ("The study was conclusive\u00B2,", "The study was conclusive,\u00B2"),
            ("She said \u201Cyes\u201D\u00B3.", "She said \u201Cyes.\u201D\u00B3"),
        ],
        "en-GB": [
            ("Typography matters\u00B9.", "Typography matters.\u00B9"),
            ("The study was conclusive\u00B2,", "The study was conclusive,\u00B2"),
            ("He called it \u2018excellent\u2019\u00B3.", "He called it \u2018excellent\u2019.\u00B3"),
        ],
        "de-DE": [
            # DE: footnote mark AFTER punctuation (Duden)
            ("Typografie ist wichtig\u00B9.", "Typografie ist wichtig.\u00B9"),
            ("Die Studie war schlüssig\u00B2,", "Die Studie war schlüssig,\u00B2"),
            ("Er nannte es \u201Eausgezeichnet\u201C\u00B3.", "Er nannte es \u201Eausgezeichnet\u201C.\u00B3"),
        ],
        "fr-FR": [
            # FR: footnote mark BEFORE punctuation (Imprimerie Nationale)
            ("La typographie est importante.\u00B9", "La typographie est importante\u00B9."),
            ("L\u2019étude était concluante,\u00B2", "L\u2019étude était concluante\u00B2,"),
            ("Il a dit \u00AB\u202Fexcellent\u202F\u00BB.\u00B3", "Il a dit \u00AB\u202Fexcellent\u202F\u00BB\u00B3."),
        ],
        "es-ES": [
            # ES: footnote mark BEFORE punctuation (RAE)
            ("La tipografía es importante.\u00B9", "La tipografía es importante\u00B9."),
            ("El estudio fue concluyente,\u00B2", "El estudio fue concluyente\u00B2,"),
            ("Lo llamó \u00ABexcelente\u00BB.\u00B3", "Lo llamó \u00ABexcelente\u00BB\u00B3."),
        ],
        "pt-PT": [
            # PT: footnote mark AFTER punctuation
            ("A tipografia é importante\u00B9.", "A tipografia é importante.\u00B9"),
            ("O estudo foi conclusivo\u00B2,", "O estudo foi conclusivo,\u00B2"),
            ("Ele chamou-o de \u00AB\u2009excelente\u2009\u00BB\u00B3.", "Ele chamou-o de \u00AB\u2009excelente\u2009\u00BB.\u00B3"),
        ],
        "it-IT": [
            # IT: footnote mark AFTER punctuation
            ("La tipografia è importante\u00B9.", "La tipografia è importante.\u00B9"),
            ("Lo studio era conclusivo\u00B2,", "Lo studio era conclusivo,\u00B2"),
            ("Lo ha definito \u00ABeccellente\u00BB\u00B3.", "Lo ha definito \u00ABeccellente\u00BB.\u00B3"),
        ],
        "nl-NL": [
            # NL: footnote mark AFTER punctuation
            ("Typografie is belangrijk\u00B9.", "Typografie is belangrijk.\u00B9"),
            ("Het onderzoek was overtuigend\u00B2,", "Het onderzoek was overtuigend,\u00B2"),
            ("Hij noemde het \u201Cuitstekend\u201D\u00B3.", "Hij noemde het \u201Cuitstekend\u201D.\u00B3"),
        ],
        "ro-RO": [
            # RO: footnote mark AFTER punctuation
            ("Tipografia este importantă\u00B9.", "Tipografia este importantă.\u00B9"),
            ("Studiul a fost concludent\u00B2,", "Studiul a fost concludent,\u00B2"),
            ("L-a numit \u201Eexcelent\u201D\u00B3.", "L-a numit \u201Eexcelent\u201D.\u00B3"),
        ],
    },

    "nested_parentheticals": {
        "_universal": [
            # Inner parentheses become square brackets
            ("The result (as noted by Smith (2020)) was significant.",
             "The result (as noted by Smith [2020]) was significant."),
            ("The theory (proposed by Jones (see appendix (A))) was tested.",
             "The theory (proposed by Jones [see appendix (A)]) was tested."),
            ("The data (from the survey (2019)) confirmed the hypothesis.",
             "The data (from the survey [2019]) confirmed the hypothesis."),
            ("Production increased (by 15% (adjusted for inflation)) last year.",
             "Production increased (by 15% [adjusted for inflation]) last year."),
            ("The author (J. Smith (University of Oxford)) published the paper.",
             "The author (J. Smith [University of Oxford]) published the paper."),
        ],
    },

    # --- BATCH 3 — NNBSP SEMANTICS AND SINGLE-LETTER LINE-ENDING ---

    "nnbsp_thousands_separator": {
        "fr-FR": [
            # French uses NNBSP as thousands separator
            ("1000 habitants",      "1\u202F000 habitants"),
            ("25000 euros",         "25\u202F000 euros"),
            ("1500000 de visiteurs", "1\u202F500\u202F000 de visiteurs"),
            ("Il y a 100000 personnes.", "Il y a 100\u202F000 personnes."),
        ],
    },

    "single_letter_line_end": {
        # Hard rules: Polish, Czech, Slovak would go here, but they are not
        # in the 13 covered languages. We cover the soft rules for covered languages.
        "fr-FR": [
            # Soft rule: à, y bonded to following word
            ("\u00E0 Paris",           "\u00E0\u00A0Paris"),
            ("y compris",              "y\u00A0compris"),
            ("\u00E0 demain",          "\u00E0\u00A0demain"),
        ],
        "it-IT": [
            # Soft rule: e, a, o, è bonded to following word
            ("pane e burro",           "pane e\u00A0burro"),
            ("bianco o nero",          "bianco o\u00A0nero"),
            ("l\u2019uno e l\u2019altro", "l\u2019uno e\u00A0l\u2019altro"),
        ],
        "pt-PT": [
            # Soft rule: e, a, o bonded to following word (literary register)
            ("p\u00E3o e manteiga",    "p\u00E3o e\u00A0manteiga"),
            ("sim o n\u00E3o",         "sim o\u00A0n\u00E3o"),
            ("dia a dia",             "dia a\u00A0dia"),
        ],
        "es-ES": [
            # Soft rule: y, e, o, a, u bonded to following word
            ("pan y mantequilla",      "pan y\u00A0mantequilla"),
            ("uno u otro",             "uno u\u00A0otro"),
            ("blanco o negro",         "blanco o\u00A0negro"),
        ],
    },

    # =========================================================================
    # BATCH 5 — MICRO-TYPOGRAPHY
    # =========================================================================

    "ligature_suppression": {
        # Character-level rule: insert ZWNJ (U+200C) at morpheme boundaries
        # to suppress f-ligatures in compound words. Correction pairs.
        "de-DE": [
            ("Auflage",              "Auf\u200Clage"),
            ("Schifffahrt",          "Schiff\u200Cfahrt"),
            ("Sauerstoffflasche",    "Sauerstoff\u200Cflasche"),
            ("Rückfrage",            "R\u00FCck\u200Cfrage"),
            ("Kaufleute",            "Kauf\u200Cleute"),
            ("Dorfleben",            "Dorf\u200Cleben"),
            ("Senffabrik",           "Senf\u200Cfabrik"),
            ("Stofffarbe",           "Stoff\u200Cfarbe"),
        ],
        "en-US": [
            ("shelfful",             "shelf\u200Cful"),
            ("halflife",             "half\u200Clife"),
            ("roofline",             "roof\u200Cline"),
            ("cufflink",             "cuff\u200Clink"),
            ("offload",              "off\u200Cload"),
        ],
        "en-GB": [
            ("shelfful",             "shelf\u200Cful"),
            ("halflife",             "half\u200Clife"),
            ("roofline",             "roof\u200Cline"),
            ("cufflink",             "cuff\u200Clink"),
            ("offload",              "off\u200Cload"),
        ],
    },

    "orthographic_ligature_preservation": {
        # Correction pairs: decomposed digraphs back to mandatory ligatures.
        # Cross-reference with french_ligatures (Batch 2).
        "fr-FR": [
            ("coeur battant",        "c\u0153ur battant"),
            ("soeur jumelle",        "s\u0153ur jumelle"),
            ("oeuvre d\u2019art",    "\u0153uvre d\u2019art"),
            ("oeuf dur",             "\u0153uf dur"),
            ("boeuf bourguignon",    "b\u0153uf bourguignon"),
            ("noeud papillon",       "n\u0153ud papillon"),
            ("voeu pieux",           "v\u0153u pieux"),
            ("manoeuvre habile",     "man\u0153uvre habile"),
            # Latin loanwords with ae
            ("ex aequo",             "ex \u00E6quo"),
            ("curriculum vitae",     "curriculum vit\u00E6"),
        ],
    },

    "small_caps_acronyms": {
        # Rendering hint: detection/recommendation pairs.
        # The model should FLAG text for small-caps treatment, not change characters.
        # Output is a recommendation, not a character substitution.
        "en-US": [
            ("NATO agreed to the terms.",
             "[SMALL-CAPS: NATO] NATO agreed to the terms. Recommendation: set \u2018NATO\u2019 in small caps for editorial register."),
            ("The UNESCO report was published.",
             "[SMALL-CAPS: UNESCO] The UNESCO report was published. Recommendation: set \u2018UNESCO\u2019 in small caps for editorial register."),
            ("NASA launched the mission in 2024.",
             "[SMALL-CAPS: NASA] NASA launched the mission in 2024. Recommendation: set \u2018NASA\u2019 in small caps for editorial register."),
        ],
        "en-GB": [
            ("The BBC broadcast the event live.",
             "The BBC broadcast the event live. Note: \u2018BBC\u2019 is a brand identity styled as all-caps; do not apply small caps."),
            ("UNESCO published new guidelines.",
             "[SMALL-CAPS: UNESCO] UNESCO published new guidelines. Recommendation: set \u2018UNESCO\u2019 in small caps for editorial register."),
            ("Events from AD 400 to AD 800.",
             "[SMALL-CAPS: AD] Events from AD 400 to AD 800. Recommendation: set \u2018AD\u2019 in small caps for editorial register."),
        ],
        "fr-FR": [
            ("L\u2019OTAN a accept\u00E9 les conditions.",
             "[SMALL-CAPS: OTAN] L\u2019OTAN a accept\u00E9 les conditions. Recommandation\u202F: composer \u00AB\u202FOTAN\u202F\u00BB en petites capitales pour le registre \u00E9ditorial."),
            ("Le rapport de l\u2019UNESCO a \u00E9t\u00E9 publi\u00E9.",
             "[SMALL-CAPS: UNESCO] Le rapport de l\u2019UNESCO a \u00E9t\u00E9 publi\u00E9. Recommandation\u202F: composer \u00AB\u202FUNESCO\u202F\u00BB en petites capitales."),
            ("Le XIXe si\u00E8cle a connu de grands changements.",
             "[SMALL-CAPS: XIX] Le XIXe si\u00E8cle a connu de grands changements. Recommandation\u202F: composer \u00AB\u202FXIX\u202F\u00BB en petites capitales."),
        ],
        "de-DE": [
            ("Die NATO hat den Bedingungen zugestimmt.",
             "[SMALL-CAPS: NATO] Die NATO hat den Bedingungen zugestimmt. Empfehlung: \u201ENATO\u201C in Kapit\u00E4lchen setzen f\u00FCr den redaktionellen Stil."),
            ("Der UNESCO-Bericht wurde ver\u00F6ffentlicht.",
             "[SMALL-CAPS: UNESCO] Der UNESCO-Bericht wurde ver\u00F6ffentlicht. Empfehlung: \u201EUNESCO\u201C in Kapit\u00E4lchen setzen."),
            ("Die GmbH wurde 2020 gegr\u00FCndet.",
             "[SMALL-CAPS: GmbH] Die GmbH wurde 2020 gegr\u00FCndet. Empfehlung: \u201EGmbH\u201C in Kapit\u00E4lchen setzen f\u00FCr den redaktionellen Stil."),
        ],
        "it-IT": [
            ("La NATO ha accettato le condizioni.",
             "[SMALL-CAPS: NATO] La NATO ha accettato le condizioni. Raccomandazione: comporre \u00ABNATO\u00BB in maiuscoletto per il registro editoriale."),
            ("Il rapporto dell\u2019UNESCO \u00E8 stato pubblicato.",
             "[SMALL-CAPS: UNESCO] Il rapporto dell\u2019UNESCO \u00E8 stato pubblicato. Raccomandazione: comporre \u00ABUNESCO\u00BB in maiuscoletto."),
            ("Il XIX secolo ha visto grandi cambiamenti.",
             "[SMALL-CAPS: XIX] Il XIX secolo ha visto grandi cambiamenti. Raccomandazione: comporre \u00ABXIX\u00BB in maiuscoletto."),
        ],
        "es-ES": [
            ("La OTAN acept\u00F3 las condiciones.",
             "[SMALL-CAPS: OTAN] La OTAN acept\u00F3 las condiciones. Recomendaci\u00F3n: componer \u00ABOTAN\u00BB en versalitas para el registro editorial."),
            ("El informe de la UNESCO fue publicado.",
             "[SMALL-CAPS: UNESCO] El informe de la UNESCO fue publicado. Recomendaci\u00F3n: componer \u00ABUNESCO\u00BB en versalitas."),
            ("El siglo XIX trajo grandes cambios.",
             "[SMALL-CAPS: XIX] El siglo XIX trajo grandes cambios. Recomendaci\u00F3n: componer \u00ABXIX\u00BB en versalitas."),
        ],
        "pt-PT": [
            ("A NATO aceitou os termos.",
             "[SMALL-CAPS: NATO] A NATO aceitou os termos. Recomenda\u00E7\u00E3o: compor \u00ABNATO\u00BB em versaletes para o registo editorial."),
            ("O relat\u00F3rio da UNESCO foi publicado.",
             "[SMALL-CAPS: UNESCO] O relat\u00F3rio da UNESCO foi publicado. Recomenda\u00E7\u00E3o: compor \u00ABUNESCO\u00BB em versaletes."),
            ("O s\u00E9culo XIX trouxe grandes mudan\u00E7as.",
             "[SMALL-CAPS: XIX] O s\u00E9culo XIX trouxe grandes mudan\u00E7as. Recomenda\u00E7\u00E3o: compor \u00ABXIX\u00BB em versaletes."),
        ],
    },

    "figure_styles": {
        # Rendering hint: detection/recommendation pairs.
        # The model recommends oldstyle or lining figures depending on context.
        "_universal": [
            ("The population reached 12,500 in 2024.",
             "[FIGURE-STYLE: oldstyle proportional] The population reached 12,500 in 2024. Recommendation: use oldstyle proportional figures (onum+pnum) for numbers in body prose."),
            ("Revenue: $1,250,000 | Expenses: $980,000 | Profit: $270,000",
             "[FIGURE-STYLE: lining tabular] Revenue: $1,250,000 | Expenses: $980,000 | Profit: $270,000. Recommendation: use lining tabular figures (lnum+tnum) for financial/tabular data."),
            ("Chapter 3 covers the events of 1789 in detail.",
             "[FIGURE-STYLE: oldstyle proportional] Chapter 3 covers the events of 1789 in detail. Recommendation: use oldstyle proportional figures (onum+pnum) for numbers in body prose to harmonize with lowercase text."),
            ("Table 2: Q1 sales 45,000 | Q2 sales 52,000 | Q3 sales 61,000",
             "[FIGURE-STYLE: lining tabular] Table 2: Q1 sales 45,000 | Q2 sales 52,000 | Q3 sales 61,000. Recommendation: use lining tabular figures (lnum+tnum) for column alignment in tables."),
        ],
    },

    "caps_letter_spacing": {
        # Rendering hint: detect all-caps runs and recommend tracking.
        "_universal": [
            ("IMPORTANT NOTICE",
             "[TRACKING: IMPORTANT NOTICE] Recommendation: apply 5\u201312% letter-spacing (tracking) to this all-caps run for improved legibility."),
            ("TERMS AND CONDITIONS",
             "[TRACKING: TERMS AND CONDITIONS] Recommendation: apply 8\u201312% letter-spacing to this display-size all-caps heading."),
            ("READ MORE",
             "[TRACKING: READ MORE] Recommendation: apply 5\u20138% letter-spacing to this all-caps UI label."),
            ("THE END",
             "[TRACKING: THE END] Recommendation: apply letter-spacing to this all-caps run. Do NOT insert thin spaces between characters \u2014 use CSS letter-spacing or OpenType tracking."),
        ],
    },

    "hanging_punctuation": {
        # Rendering hint: recommend hanging punctuation where supported.
        "_universal": [
            ('\u201CThe quick brown fox jumps over the lazy dog.\u201D',
             '[HANGING-PUNCTUATION] \u201CThe quick brown fox jumps over the lazy dog.\u201D Recommendation: apply hanging-punctuation: first last; for optical margin alignment. The opening \u201C should hang into the left margin.'),
            ('\u2018Typography matters,\u2019 she said.',
             '[HANGING-PUNCTUATION] \u2018Typography matters,\u2019 she said. Recommendation: the opening \u2018 should receive a full hang into the left margin when at line start.'),
            ('\u00AB\u202FLa typographie est importante.\u202F\u00BB',
             '[HANGING-PUNCTUATION] \u00AB\u202FLa typographie est importante.\u202F\u00BB Recommendation: the opening guillemet \u00AB should hang into the left margin. CSS: hanging-punctuation: first last;'),
            ('This line ends with a hyphen at the break-\npoint of the word.',
             '[HANGING-PUNCTUATION] Recommendation: hyphens at line-end should hang fully into the right margin. Use CSS hanging-punctuation or TeX microtype for optical margin alignment.'),
        ],
    },

    # =========================================================================
    # BATCH 6 — WCAG-SAFE EMISSION
    # =========================================================================

    "wcag_text_spacing": {
        # Output requirement: detect CSS that violates WCAG SC 1.4.12.
        # Detection/explanation pairs.
        "_universal": [
            ("p { line-height: 1.2; font-size: 16px; }",
             "[WCAG 1.4.12 VIOLATION] line-height: 1.2 is below the minimum 1.5\u00D7 font-size override threshold. Users must be able to override to at least 1.5. Recommendation: use line-height: 1.5 or higher, and do not use !important."),
            (".text { letter-spacing: 0; word-spacing: normal; }",
             "[WCAG 1.4.12 NOTE] letter-spacing: 0 and word-spacing: normal are acceptable defaults, but ensure these properties are not locked with !important. Users must be able to override to at least letter-spacing: 0.12em and word-spacing: 0.16em."),
            ("span { line-height: 1.1 !important; letter-spacing: -0.05em !important; }",
             "[WCAG 1.4.12 VIOLATION] !important on line-height and letter-spacing prevents user overrides required by SC 1.4.12. Remove !important from typographic properties. Minimum override thresholds: line-height 1.5\u00D7, letter-spacing 0.12em, word-spacing 0.16em."),
            (".body-text { font-size: 14px; line-height: 18px; }",
             "[WCAG 1.4.12 WARNING] Fixed pixel line-height (18px) on 14px font gives 1.29\u00D7 ratio, below the 1.5\u00D7 threshold. Use relative units: line-height: 1.5 or line-height: 1.5em."),
        ],
    },

    "no_fixed_width_containers": {
        # Output requirement: detect !important on typographic CSS properties.
        "_universal": [
            ("h1 { font-size: 24px !important; }",
             "[ACCESSIBILITY VIOLATION] !important on font-size prevents assistive technology and user stylesheets from overriding. Remove !important from font-size. Use specificity or cascade layers instead."),
            (".card { width: 300px; overflow: hidden; }",
             "[ACCESSIBILITY WARNING] Fixed width (300px) with overflow: hidden on a text container prevents text reflow under WCAG text spacing overrides. Use relative units (%, em, rem, ch) or max-width instead of width, and avoid overflow: hidden on text containers."),
            ("p { white-space: nowrap; width: 200px; }",
             "[ACCESSIBILITY VIOLATION] white-space: nowrap combined with fixed width prevents text wrapping under WCAG text spacing overrides (SC 1.4.12). Remove nowrap from block text elements and use relative widths."),
            (".label { font-family: Arial !important; line-height: 1.2 !important; letter-spacing: 0 !important; }",
             "[ACCESSIBILITY VIOLATION] !important on font-family, line-height, and letter-spacing prevents user overrides. Remove !important from all typographic properties: font-size, line-height, letter-spacing, word-spacing, font-family."),
        ],
    },

    "bidi_isolate_preservation": {
        # Character-level rule: preserve bidi control characters.
        # Correction pairs: restore stripped bidi isolates.
        "_universal": [
            # Text where bidi isolates were stripped and should be restored
            ("The user \u05D3\u05D5\u05D3 left a comment.",
             "The user \u2066\u05D3\u05D5\u05D3\u2069 left a comment."),
            ("Contact \u0645\u062D\u0645\u062F for details.",
             "Contact \u2067\u0645\u062D\u0645\u062F\u2069 for details."),
            ("File uploaded by \u05DE\u05E9\u05EA\u05DE\u05E9 on Monday.",
             "File uploaded by \u2066\u05DE\u05E9\u05EA\u05DE\u05E9\u2069 on Monday."),
            # Preserve existing bidi isolates during correction
            ("She said \u2066\u05E9\u05DC\u05D5\u05DD\u2069 and left.",
             "She said \u2066\u05E9\u05DC\u05D5\u05DD\u2069 and left."),
            ("The product \u2067\u0627\u0644\u0645\u0646\u062A\u062C\u2069 ships globally.",
             "The product \u2067\u0627\u0644\u0645\u0646\u062A\u062C\u2069 ships globally."),
        ],
    },

    "breakable_containers": {
        # Character-level rule: NBSP chain limit.
        # Correction pairs: convert long NBSP chains.
        "_universal": [
            # 4-word NBSP chain → reduced to two 2-word bonds
            ("J.\u00A0R.\u00A0R.\u00A0Tolkien",
             "J.\u00A0R. R.\u00A0Tolkien"),
            ("C.\u00A0S.\u00A0S.\u00A0Lewis wrote fiction.",
             "C.\u00A0S. S.\u00A0Lewis wrote fiction."),
            # 5-word NBSP chain → bonds at edges only
            ("Lt.\u00A0Col.\u00A0J.\u00A0R.\u00A0Smith reported.",
             "Lt.\u00A0Col. J. R.\u00A0Smith reported."),
            # Short tokens are acceptable
            ("a.\u00A0u.\u00A0b.",
             "a.\u00A0u.\u00A0b."),
            # 3-word chain is acceptable, no change
            ("10\u00A0000\u00A0km",
             "10\u00A0000\u00A0km"),
        ],
    },

    "language_tagging": {
        # Output requirement: detect missing lang attributes in HTML.
        # Detection/recommendation pairs.
        "_universal": [
            ('<p>The French say c\'est la vie.</p>',
             '[LANGUAGE-TAG MISSING] The phrase \u201Cc\u2019est la vie\u201D is French embedded in non-French context. Recommendation: <p>The French say <span lang="fr">c\u2019est la vie</span>.</p>'),
            ('<p>She studied at the Sorbonne and loved the joie de vivre.</p>',
             '[LANGUAGE-TAG MISSING] The phrase \u201Cjoie de vivre\u201D is French. Recommendation: <p>She studied at the Sorbonne and loved the <span lang="fr">joie de vivre</span>.</p>'),
            ('<html><head><title>Welcome</title></head><body>Hello world</body></html>',
             '[LANGUAGE-TAG MISSING] The <html> element lacks a lang attribute. Recommendation: <html lang="en"> for English content. WCAG SC 3.1.1 (Level A) requires a lang attribute on the document element.'),
            ('<p>The German concept of Schadenfreude is complex.</p>',
             '[LANGUAGE-TAG MISSING] The word \u201CSchadenfreude\u201D is German. Recommendation: <p>The German concept of <span lang="de">Schadenfreude</span> is complex.</p>'),
            ('<p>In Portuguese, we say saudade for a deep longing.</p>',
             '[LANGUAGE-TAG MISSING] The word \u201Csaudade\u201D is Portuguese. Recommendation: <p>In Portuguese, we say <span lang="pt">saudade</span> for a deep longing.</p>'),
        ],
    },

    "screen_reader_typography": {
        # Output requirement: detection/explanation pairs.
        # Show ASCII approximations vs proper Unicode and screen reader impact.
        "_universal": [
            ("pages 10-20",
             "[SCREEN-READER IMPROVEMENT] \u201Cpages 10-20\u201D with hyphen-minus may be read as \u201Cpages 10 minus 20\u201D or \u201Cpages 10 hyphen 20.\u201D Using en dash: \u201Cpages 10\u201320\u201D is read as \u201Cpages 10 to 20\u201D by NVDA, JAWS, and VoiceOver."),
            ("Wait...",
             "[SCREEN-READER IMPROVEMENT] Three periods \u201C...\u201D may be read as \u201Cperiod period period.\u201D The ellipsis character \u201C\u2026\u201D is read as \u201Cellipsis\u201D or \u201Cdot dot dot\u201D \u2014 a single semantic unit."),
            ("1/4 cup of flour",
             "[SCREEN-READER IMPROVEMENT] \u201C1/4\u201D is read as \u201Cone slash four.\u201D The vulgar fraction \u201C\u00BC\u201D is read as \u201Cone quarter\u201D by modern screen readers."),
            ("10 x 15 cm",
             "[SCREEN-READER IMPROVEMENT] The letter \u201Cx\u201D is read as the letter name. The multiplication sign \u201C\u00D7\u201D (U+00D7) is read as \u201Ctimes\u201D or \u201Cmultiplied by.\u201D Use: 10\u2009\u00D7\u200915\u00A0cm."),
            ("Temperature: -5 degrees",
             "[SCREEN-READER IMPROVEMENT] Hyphen-minus before a number may be read as \u201Chyphen\u201D instead of \u201Cminus.\u201D The minus sign \u201C\u2212\u201D (U+2212) is read as \u201Cminus\u201D by screen readers. Use: \u22125 degrees."),
        ],
    },
}

# Register-specific instructions
REGISTERS = ["editorial", "marketing", "ui", "literary"]

# Language display names
LANG_NAMES = {
    "pt-PT": "European Portuguese",
    "pt-BR": "Brazilian Portuguese",
    "en-US": "American English",
    "en-GB": "British English",
    "fr-FR": "French",
    "de-DE": "German",
    "it-IT": "Italian",
    "es-ES": "European Spanish",
    "es-MX": "Latin American Spanish",
    "nl-NL": "Dutch",
    "nl-BE": "Flemish Dutch",
    "ro-RO": "Romanian",
    "sc":    "Sardinian",
}


# ---------------------------------------------------------------------------
# Generator functions
# ---------------------------------------------------------------------------

def generate_correction_pairs(templates: dict) -> list[TrainingPair]:
    """Type 1: Given raw text, produce typographically correct output."""
    pairs = []
    for rule_name, lang_examples in templates.items():
        for lang, examples in lang_examples.items():
            actual_lang = lang if lang != "_universal" else None
            for raw, correct in examples:
                if raw == correct:
                    continue
                lang_label = LANG_NAMES.get(lang, "any language")
                for register in [None, "editorial", "marketing"]:
                    reg_suffix = f" for {register} use" if register else ""
                    instruction = (
                        f"Correct the typography in the following "
                        f"{lang_label} text{reg_suffix}."
                    ) if actual_lang else (
                        f"Correct the typography in the following text{reg_suffix}."
                    )
                    pairs.append(TrainingPair(
                        instruction=instruction,
                        input=raw,
                        output=correct,
                        metadata={
                            "type": "correction",
                            "rule": rule_name,
                            "language": lang,
                            "register": register,
                        }
                    ))
    return pairs


def generate_detection_pairs(templates: dict) -> list[TrainingPair]:
    """Type 2: Given text with errors, identify what's wrong."""
    pairs = []
    
    error_descriptions = {
        "quotation": "Straight quotation marks should be replaced with typographic quotation marks appropriate for {lang}.",
        "dashes": "Incorrect dash usage. Hyphens should not be used for ranges (use en dash) or parenthetical asides (use em/en dash per language convention).",
        "ellipsis": "Three consecutive periods should be replaced with a single ellipsis character (U+2026).",
        "measurements": "Straight quotes used for measurements should be replaced with prime/double prime marks. Letter 'x' for dimensions should be the multiplication sign (\u00D7).",
        "inverted_punctuation": "Missing inverted punctuation mark (\u00BF or \u00A1) at the start of the interrogative or exclamatory clause.",
        "italian_accents": "Incorrect accent or apostrophe-as-accent substitution on Italian word.",
        "ordinals": "Incorrect ordinal indicator formatting.",
        "french_spacing": "Missing non-breaking space before high punctuation (: ; ! ?) in French.",
        "dialogue": "Incorrect dialogue punctuation. Hyphens should be replaced with em dashes with language-appropriate spacing.",
        "romanian_diacritics": "Wrong diacritic form. Romanian uses comma-below (\u0219 \u021B), not cedilla (\u015F \u0163). The cedilla forms are Turkish characters incorrectly used in Romanian due to legacy encodings.",
        "dutch_ij": "The Dutch digraph IJ should be capitalised as a unit. Both letters must be uppercase when the word is capitalised: IJ, not Ij.",
        "sardinian_elision": "Sardinian elision uses a typographic apostrophe with no surrounding spaces. The apostrophe joins directly to both the preceding consonant and the following word.",
        "minus_sign": "Hyphen-minus used where a proper minus sign (\u2212 U+2212) is required. The minus sign is wider, vertically centred, and semantically correct for negative numbers and subtraction.",
        "legal_symbols": "ASCII approximation of a legal symbol. Replace (c) with \u00A9, (R) with \u00AE, and (TM) with \u2122.",
        "fractions": "Common fraction written with solidus (/) should use the dedicated Unicode fraction character in running prose (\u00BD, \u00BC, \u00BE, etc.).",
        "degree_symbol": "Incorrect character used for degree sign. Use the proper degree sign (\u00B0 U+00B0), not a superscript o, ordinal indicator, or ring above. Temperature format: number + non-breaking space + \u00B0 + unit letter.",
        "currency": "Incorrect currency formatting. Currency symbol position (before/after amount) and spacing (non-breaking space or no space) vary by language. The symbol and amount must never be separated by a line break.",
        "arrows": "ASCII arrow approximation (->, <-) should be replaced with proper Unicode arrow characters (\u2192, \u2190) in running prose. Do not replace in code contexts.",
        "whitespace": "Whitespace normalisation error. Multiple consecutive spaces should be reduced to a single space. Trailing whitespace should be removed.",
        "french_ligatures": "Decomposed French orthographic ligature. In French, \u0153 and \u00E6 are mandatory letters, not optional. coeur\u2192c\u0153ur, soeur\u2192s\u0153ur.",
        "french_capital_accents": "Missing accent on French capital letter. French requires accents on capitals: \u00C9TAT not ETAT, \u00C0 PARIS not A PARIS.",
        "german_eszett": "German capital \u1E9E (U+1E9E) is preferred since 2024 over SS. STRA\u1E9E preferred over STRASSE.",
        "german_din5008": "German abbreviation missing narrow no-break space (U+202F) between parts per DIN 5008. z.B.\u2192z.\u202FB.",
        "homoglyph_correction": "Visually similar but semantically wrong character used. Check: \u00B0 vs \u00BA, \u00DF vs \u03B2.",
        "nbsp_obligations": "Missing non-breaking space between logically bonded elements (number+unit, title+name, abbreviation+number).",
        "code_exclusion": "Text inside code-like contexts (backtick code spans, URLs, file paths, email addresses, CLI flags, variable names, version strings) must NOT be typographically corrected. Only surrounding prose is corrected.",
        "normalization": "Text should be stored in NFC (Canonical Decomposition followed by Canonical Composition). Decomposed sequences (e.g., e + combining acute) should be composed into precomposed characters (e.g., \u00E9). Never use NFKC for output.",
        "zero_width_characters": "Stray zero-width spaces (U+200B) and inline byte-order marks (U+FEFF) should be stripped from prose. ZWNJ (U+200C) for ligature suppression, ZWJ (U+200D) for emoji sequences, and word joiner (U+2060) are intentional and must be preserved.",
        "capital_accents_multilingual": "Accents must be preserved on capital letters. This applies across multiple languages: French (\u00C9TAT), Spanish (\u00C1REA), Portuguese (A\u00C7\u00C3O), Italian (CITT\u00C0), Romanian (ROM\u00C2NIA), German (\u00DCBERSICHT).",
        "homoglyph_expanded": "Visually similar but semantically wrong character used. Common confusables include: Greek \u03B2 vs German \u00DF, ordinal indicator \u00BA vs degree sign \u00B0, grave accent ` vs typographic apostrophe \u2019.",
        "nnbsp_thousands_separator": "French uses narrow no-break space (U+202F) as the thousands separator per CLDR: 1\u202F000, 25\u202F000. This prevents line breaks within large numbers.",
        "single_letter_line_end": "Single-letter words at line end should be bonded to the following word with a non-breaking space to prevent orphaning. Mandatory in Polish/Czech/Slovak; recommended in French, Italian, Portuguese, and Spanish for editorial/literary registers.",
        "colon_capitalisation": "Incorrect capitalisation after colon. Language conventions differ: EN-US capitalises independent clauses after a colon (Chicago 6.64); DE capitalises full sentences (Duden R 81); FR, EN-GB, PT, ES, IT, NL, RO always use lowercase after a colon (except proper nouns).",
        "serial_comma": "Incorrect serial (Oxford) comma usage. EN-US editorial register enforces the serial comma before the final conjunction in lists of three or more. EN-GB generally omits it. FR, DE, ES, IT, PT, NL, RO prohibit the serial comma \u2014 the conjunction is considered sufficient separation.",
        "quote_punctuation_placement": "Incorrect punctuation placement relative to closing quotation mark. EN-US typesetters\u2019 convention places commas and periods INSIDE the closing quote. EN-GB and all other covered languages use logical placement: punctuation goes inside only when it belongs to the quoted material.",
        "abbreviation_periods": "Incorrect period usage with abbreviation. EN-US uses a period after ALL abbreviations (Mr., Dr., St.). EN-GB drops the period for contractions ending in the last letter of the full word (Mr, Dr, St) but keeps it for truncations (Prof., Rev.). FR, DE, and other languages have specific conventions per abbreviation type.",
        "abbreviation_haplology": "Double period at sentence end. When an abbreviation ending with a period falls at the end of a sentence, the abbreviation period also serves as the sentence-final full stop. Never produce two consecutive periods.",
        "footnote_mark_placement": "Incorrect footnote mark position. EN, DE, PT, IT, NL, RO place footnote marks AFTER punctuation. FR and ES place footnote marks BEFORE punctuation.",
        "nested_parentheticals": "Nested parenthetical uses wrong bracket type. When parentheses are nested inside other parentheses, the inner layer should use square brackets to avoid ambiguity: (text (inner)) \u2192 (text [inner]).",
        # Batch 5 — Micro-typography
        "ligature_suppression": "Missing ZWNJ (U+200C) at morpheme boundary in compound word. OpenType f-ligatures (fi, fl, ff, ffi, ffl) should be suppressed at morpheme boundaries using ZWNJ: Auf\u200Clage, Schiff\u200Cfahrt, shelf\u200Cful. The ligature visually merges parts that are semantically separate.",
        "orthographic_ligature_preservation": "Decomposed orthographic ligature. In French, \u0153 and \u00E6 are mandatory letters, not optional typographic ligatures. coeur\u2192c\u0153ur, oeuvre\u2192\u0153uvre. Decomposition is a misspelling, not merely a typographic degradation.",
        "small_caps_acronyms": "Acronym of 3+ letters detected that should be flagged for small-caps rendering in editorial/literary register. Small caps reduce typographic \u201Cshouting\u201D from all-caps acronyms. The characters remain uppercase in the data layer; only the rendering changes.",
        "figure_styles": "Numeric context detected that would benefit from a figure-style recommendation. Body prose should use oldstyle proportional figures (onum+pnum); tables and financial data should use lining tabular figures (lnum+tnum).",
        "caps_letter_spacing": "All-caps or small-caps text run detected that should receive increased letter-spacing (tracking) of 5\u201312% for improved legibility. Do not insert thin/hair spaces between characters \u2014 use CSS letter-spacing or OpenType tracking.",
        "hanging_punctuation": "Punctuation at line edge detected. For optically aligned margins, opening quotes should hang into the left margin, hyphens should hang at line-end, and periods/commas should partially hang (~50%). CSS: hanging-punctuation: first last;",
        # Batch 6 — WCAG-safe emission
        "wcag_text_spacing": "CSS violates or risks violating WCAG SC 1.4.12 (Text Spacing, Level AA). Content must remain functional when users override: line-height to 1.5\u00D7, paragraph spacing to 2\u00D7, letter-spacing to 0.12em, word-spacing to 0.16em.",
        "no_fixed_width_containers": "CSS uses !important on typographic properties or fixed-width containers that prevent WCAG-compliant text reflow. Remove !important from font-size, line-height, letter-spacing, word-spacing, font-family. Use relative units instead of fixed widths on text containers.",
        "bidi_isolate_preservation": "Missing or stripped Unicode bidi isolate characters. Mixed-direction text (LTR/RTL) requires bidi isolates (LRI U+2066, RLI U+2067, FSI U+2068, PDI U+2069) to prevent rendering errors and ensure correct screen reader pronunciation.",
        "breakable_containers": "NBSP chain exceeds 3 words, creating an unbreakable block that may prevent text reflow in narrow viewports or under WCAG text spacing overrides. Use regular spaces for middle joins, NBSP only at critical bond points (first and last pairs).",
        "language_tagging": "HTML missing lang attribute for embedded foreign-language text. WCAG SC 3.1.2 (Language of Parts, Level AA) requires lang attributes on elements containing text in a different language. Screen readers use lang to switch pronunciation engines.",
        "screen_reader_typography": "ASCII approximation used where proper Unicode would improve screen reader output. EN DASH is read as \u201Cto\u201D in ranges; ellipsis character is read as \u201Cellipsis\u201D; vulgar fractions are read as words; multiplication sign is read as \u201Ctimes.\u201D",
    }
    
    for rule_name, lang_examples in templates.items():
        for lang, examples in lang_examples.items():
            lang_label = LANG_NAMES.get(lang, "the given")
            for raw, correct in examples:
                if raw == correct:
                    continue
                desc = error_descriptions.get(rule_name, "Typographic error detected.")
                desc = desc.format(lang=lang_label)
                
                pairs.append(TrainingPair(
                    instruction=f"Identify typographic errors in this {lang_label} text.",
                    input=raw,
                    output=f"Error: {desc}\nCorrected: {correct}",
                    metadata={
                        "type": "detection",
                        "rule": rule_name,
                        "language": lang,
                    }
                ))
    return pairs


def generate_cross_language_pairs(templates: dict) -> list[TrainingPair]:
    """Type 3: Same content adapted to different language typography."""
    pairs = []
    
    # Parallel sentences with equivalent meaning across languages
    parallel_texts = [
        {
            "en-US": ('She said "hello" and left.', 'She said \u201Chello\u201D and left.'),
            "en-GB": ("She said 'hello' and left.", 'She said \u2018hello\u2019 and left.'),
            "pt-PT": ('Ela disse "olá" e saiu.', 'Ela disse «\u2009olá\u2009» e saiu.'),
            "pt-BR": ('Ela disse "olá" e saiu.', 'Ela disse \u201Colá\u201D e saiu.'),
            "fr-FR": ('Elle a dit "bonjour" et est partie.', 'Elle a dit «\u202Fbonjour\u202F» et est partie.'),
            "de-DE": ('Sie sagte "Hallo" und ging.', 'Sie sagte \u201EHallo\u201C und ging.'),
            "it-IT": ('Ha detto "ciao" ed è uscita.', 'Ha detto «ciao» ed è uscita.'),
            "es-ES": ('Ella dijo "hola" y se fue.', 'Ella dijo «hola» y se fue.'),
            "es-MX": ('Ella dijo "hola" y se fue.', 'Ella dijo \u201Chola\u201D y se fue.'),
            "nl-NL": ('Ze zei "hallo" en vertrok.', 'Ze zei \u201Challo\u201D en vertrok.'),
            "ro-RO": ('Ea a spus "bună ziua" și a plecat.', 'Ea a spus \u201Ebună ziua\u201D și a plecat.'),
        },
        {
            "en-US": ('The result - amazing - surprised everyone.', 'The result\u2014amazing\u2014surprised everyone.'),
            "en-GB": ('The result - amazing - surprised everyone.', 'The result \u2013 amazing \u2013 surprised everyone.'),
            "pt-PT": ('O resultado - incrível - surpreendeu todos.', 'O resultado \u2014 incrível \u2014 surpreendeu todos.'),
            "fr-FR": ('Le résultat - incroyable - a surpris tout le monde.', 'Le résultat \u2014 incroyable \u2014 a surpris tout le monde.'),
            "de-DE": ('Das Ergebnis - erstaunlich - überraschte alle.', 'Das Ergebnis \u2013 erstaunlich \u2013 überraschte alle.'),
            "it-IT": ('Il risultato - incredibile - ha sorpreso tutti.', 'Il risultato \u2013 incredibile \u2013 ha sorpreso tutti.'),
            "es-ES": ('El resultado - increíble - sorprendió a todos.', 'El resultado \u2014increíble\u2014 sorprendió a todos.'),
            "nl-NL": ('Het resultaat - verbazingwekkend - verraste iedereen.', 'Het resultaat \u2013 verbazingwekkend \u2013 verraste iedereen.'),
            "ro-RO": ('Rezultatul - uimitor - a surprins pe toți.', 'Rezultatul \u2013 uimitor \u2013 a surprins pe toți.'),
        },
        {
            "en-US": ('Pages 10-20, resolution 1920x1080.', 'Pages 10\u201320, resolution 1920\u2009\u00D7\u20091080.'),
            "pt-PT": ('Páginas 10-20, resolução 1920x1080.', 'Páginas 10\u201320, resolução 1920\u2009\u00D7\u20091080.'),
            "fr-FR": ('Pages 10-20, résolution 1920x1080.', 'Pages 10\u201320, résolution 1920\u2009\u00D7\u20091080.'),
            "de-DE": ('Seiten 10-20, Auflösung 1920x1080.', 'Seiten 10\u201320, Auflösung 1920\u2009\u00D7\u20091080.'),
            "it-IT": ('Pagine 10-20, risoluzione 1920x1080.', 'Pagine 10\u201320, risoluzione 1920\u2009\u00D7\u20091080.'),
            "es-ES": ('Páginas 10-20, resolución 1920x1080.', 'Páginas 10\u201320, resolución 1920\u2009\u00D7\u20091080.'),
        },
        # Cross-language: code exclusion with mixed prose/code
        {
            "en-US": ('Run `echo "test"` and say "done".', 'Run `echo "test"` and say \u201Cdone\u201D.'),
            "fr-FR": ('Lancez `echo "test"` et dites "fini".', 'Lancez `echo "test"` et dites «\u202Ffini\u202F».'),
            "de-DE": ('Führen Sie `echo "test"` aus und sagen Sie "fertig".', 'Führen Sie `echo "test"` aus und sagen Sie \u201Efertig\u201C.'),
            "pt-PT": ('Execute `echo "test"` e diga "pronto".', 'Execute `echo "test"` e diga «\u2009pronto\u2009».'),
            "it-IT": ('Esegui `echo "test"` e di "fatto".', 'Esegui `echo "test"` e di «fatto».'),
            "es-ES": ('Ejecute `echo "test"` y diga "listo".', 'Ejecute `echo "test"` y diga «listo».'),
        },
        # Cross-language: capital accents preservation
        {
            "fr-FR": ('L\'ETAT FRANCAIS', 'L\u2019\u00C9TAT FRAN\u00C7AIS'),
            "es-ES": ('EL AREA PUBLICA', 'EL \u00C1REA P\u00DABLICA'),
            "pt-PT": ('A ACAO DO GOVERNO', 'A A\u00C7\u00C3O DO GOVERNO'),
            "it-IT": ('LA CITTA ITALIANA', 'LA CITT\u00C0 ITALIANA'),
            "de-DE": ('DIE UBERSICHT', 'DIE \u00DCBERSICHT'),
            "ro-RO": ('ROMANIA MODERNA', 'ROM\u00C2NIA MODERN\u0102'),
        },
        # Cross-language: NBSP obligations (title + name)
        {
            "en-US": ('See p. 5 by Dr. Smith.', 'See p.\u00A05 by Dr.\u00A0Smith.'),
            "fr-FR": ('Voir p. 5 par M. Dupont.', 'Voir p.\u00A05 par M.\u00A0Dupont.'),
            "de-DE": ('Siehe S. 5 von Dr. Müller.', 'Siehe S.\u00A05 von Dr.\u00A0Müller.'),
            "pt-PT": ('Ver p. 5 do Sr. Silva.', 'Ver p.\u00A05 do Sr.\u00A0Silva.'),
            "it-IT": ('Vedi p. 5 del Dott. Rossi.', 'Vedi p.\u00A05 del Dott.\u00A0Rossi.'),
            "es-ES": ('Ver p. 5 del Sr. García.', 'Ver p.\u00A05 del Sr.\u00A0García.'),
        },
        # Cross-language: colon capitalisation — same semantic content, different casing
        {
            "en-US": ('The verdict was clear: he was guilty.', 'The verdict was clear: He was guilty.'),
            "en-GB": ('The verdict was clear: He was guilty.', 'The verdict was clear: he was guilty.'),
            "fr-FR": ('Le verdict est clair\u202F: Il est coupable.', 'Le verdict est clair\u202F: il est coupable.'),
            "de-DE": ('Das Ergebnis war klar: er war schuldig.', 'Das Ergebnis war klar: Er war schuldig.'),
            "pt-PT": ('O veredicto foi claro: Ele era culpado.', 'O veredicto foi claro: ele era culpado.'),
            "es-ES": ('El veredicto fue claro: Él era culpable.', 'El veredicto fue claro: él era culpable.'),
            "it-IT": ('Il verdetto era chiaro: Era colpevole.', 'Il verdetto era chiaro: era colpevole.'),
            "nl-NL": ('Het oordeel was duidelijk: Hij was schuldig.', 'Het oordeel was duidelijk: hij was schuldig.'),
            "ro-RO": ('Verdictul a fost clar: El era vinovat.', 'Verdictul a fost clar: el era vinovat.'),
        },
        # Cross-language: serial comma — same list structure, different conventions
        {
            "en-US": ('red, white and blue', 'red, white, and blue'),
            "en-GB": ('red, white, and blue', 'red, white and blue'),
            "fr-FR": ('rouge, blanc, et bleu', 'rouge, blanc et bleu'),
            "de-DE": ('rot, weiß, und blau', 'rot, weiß und blau'),
            "pt-PT": ('vermelho, branco, e azul', 'vermelho, branco e azul'),
            "es-ES": ('rojo, blanco, y azul', 'rojo, blanco y azul'),
            "it-IT": ('rosso, bianco, e blu', 'rosso, bianco e blu'),
            "nl-NL": ('rood, wit, en blauw', 'rood, wit en blauw'),
            "ro-RO": ('roșu, alb, și albastru', 'roșu, alb și albastru'),
        },
        # Cross-language: quote punctuation placement — US inside vs logical
        {
            "en-US": ('He called it "magnificent".', 'He called it \u201Cmagnificent.\u201D'),
            "en-GB": ("He called it \u2018magnificent.\u2019", "He called it \u2018magnificent\u2019."),
            "fr-FR": ("Il a dit \u00AB\u202Fmagnifique.\u202F\u00BB", "Il a dit \u00AB\u202Fmagnifique\u202F\u00BB."),
            "de-DE": ("Er nannte es \u201Egroßartig.\u201C", "Er nannte es \u201Egroßartig\u201C."),
            "pt-PT": ("Ele chamou-o de \u00AB\u2009magnífico.\u2009\u00BB", "Ele chamou-o de \u00AB\u2009magnífico\u2009\u00BB."),
            "it-IT": ("Lo ha definito \u00ABmagnifico.\u00BB", "Lo ha definito \u00ABmagnifico\u00BB."),
            "es-ES": ("Lo llamó \u00ABmagnífico.\u00BB", "Lo llamó \u00ABmagnífico\u00BB."),
            "nl-NL": ("Hij noemde het \u201Cprachtig.\u201D", "Hij noemde het \u201Cprachtig\u201D."),
            "ro-RO": ("El l-a numit \u201Emagnific.\u201D", "El l-a numit \u201Emagnific\u201D."),
        },
        # Cross-language: abbreviation periods — Dr with/without period
        {
            "en-US": ('Dr Jones is here.', 'Dr. Jones is here.'),
            "en-GB": ('Dr. Jones is here.', 'Dr Jones is here.'),
            "fr-FR": ('Dr. Martin est là.', 'Dr Martin est là.'),
            "de-DE": ('Dr Müller ist hier.', 'Dr. Müller ist hier.'),
            "pt-PT": ('Sr Silva chegou.', 'Sr. Silva chegou.'),
            "es-ES": ('Sr García llegó.', 'Sr. García llegó.'),
        },
        # Cross-language: footnote mark placement — after vs before punctuation
        {
            "en-US": ('Typography matters\u00B9.', 'Typography matters.\u00B9'),
            "en-GB": ('Typography matters\u00B9.', 'Typography matters.\u00B9'),
            "fr-FR": ('La typographie est importante.\u00B9', 'La typographie est importante\u00B9.'),
            "de-DE": ('Typografie ist wichtig\u00B9.', 'Typografie ist wichtig.\u00B9'),
            "es-ES": ('La tipografía es importante.\u00B9', 'La tipografía es importante\u00B9.'),
            "pt-PT": ('A tipografia é importante\u00B9.', 'A tipografia é importante.\u00B9'),
            "it-IT": ('La tipografia è importante\u00B9.', 'La tipografia è importante.\u00B9'),
            "nl-NL": ('Typografie is belangrijk\u00B9.', 'Typografie is belangrijk.\u00B9'),
            "ro-RO": ('Tipografia este importantă\u00B9.', 'Tipografia este importantă.\u00B9'),
        },
        # Cross-language: ligature suppression — DE compounds vs EN compounds
        {
            "de-DE": ('Schifffahrt auf dem Rhein.', 'Schiff\u200Cfahrt auf dem Rhein.'),
            "en-US": ('The shelfful of books.', 'The shelf\u200Cful of books.'),
            "en-GB": ('The shelfful of books.', 'The shelf\u200Cful of books.'),
        },
        # Cross-language: small caps — same acronym across Romance + Germanic
        {
            "en-US": ('NATO agreed to the terms.',
                       '[SMALL-CAPS: NATO] NATO agreed to the terms. Recommendation: set \u2018NATO\u2019 in small caps for editorial register.'),
            "fr-FR": ('L\u2019OTAN a accept\u00E9 les conditions.',
                       '[SMALL-CAPS: OTAN] L\u2019OTAN a accept\u00E9 les conditions. Recommandation\u202F: composer \u00AB\u202FOTAN\u202F\u00BB en petites capitales pour le registre \u00E9ditorial.'),
            "de-DE": ('Die NATO hat den Bedingungen zugestimmt.',
                       '[SMALL-CAPS: NATO] Die NATO hat den Bedingungen zugestimmt. Empfehlung: \u201ENATO\u201C in Kapit\u00E4lchen setzen f\u00FCr den redaktionellen Stil.'),
            "it-IT": ('La NATO ha accettato le condizioni.',
                       '[SMALL-CAPS: NATO] La NATO ha accettato le condizioni. Raccomandazione: comporre \u00ABNATO\u00BB in maiuscoletto per il registro editoriale.'),
            "es-ES": ('La OTAN acept\u00F3 las condiciones.',
                       '[SMALL-CAPS: OTAN] La OTAN acept\u00F3 las condiciones. Recomendaci\u00F3n: componer \u00ABOTAN\u00BB en versalitas para el registro editorial.'),
            "pt-PT": ('A NATO aceitou os termos.',
                       '[SMALL-CAPS: NATO] A NATO aceitou os termos. Recomenda\u00E7\u00E3o: compor \u00ABNATO\u00BB em versaletes para o registo editorial.'),
        },
        # Cross-language: Roman-numeral centuries across Romance languages
        {
            "fr-FR": ('Le XIXe si\u00E8cle a connu de grands changements.',
                       '[SMALL-CAPS: XIX] Le XIXe si\u00E8cle a connu de grands changements. Recommandation\u202F: composer \u00AB\u202FXIX\u202F\u00BB en petites capitales.'),
            "it-IT": ('Il XIX secolo ha visto grandi cambiamenti.',
                       '[SMALL-CAPS: XIX] Il XIX secolo ha visto grandi cambiamenti. Raccomandazione: comporre \u00ABXIX\u00BB in maiuscoletto.'),
            "es-ES": ('El siglo XIX trajo grandes cambios.',
                       '[SMALL-CAPS: XIX] El siglo XIX trajo grandes cambios. Recomendaci\u00F3n: componer \u00ABXIX\u00BB en versalitas.'),
            "pt-PT": ('O s\u00E9culo XIX trouxe grandes mudan\u00E7as.',
                       '[SMALL-CAPS: XIX] O s\u00E9culo XIX trouxe grandes mudan\u00E7as. Recomenda\u00E7\u00E3o: compor \u00ABXIX\u00BB em versaletes.'),
        },
    ]

    for parallel_set in parallel_texts:
        lang_pairs = list(parallel_set.items())
        for (source_lang, (src_raw, _)), (target_lang, (_, tgt_correct)) in itertools.permutations(lang_pairs, 2):
            src_name = LANG_NAMES[source_lang]
            tgt_name = LANG_NAMES[target_lang]
            pairs.append(TrainingPair(
                instruction=f"Apply {tgt_name} typography conventions to this text, which was originally typeset for {src_name}.",
                input=src_raw,
                output=tgt_correct,
                metadata={
                    "type": "cross_language",
                    "source_language": source_lang,
                    "target_language": target_lang,
                }
            ))
    
    return pairs


def generate_explanation_pairs(templates: dict) -> list[TrainingPair]:
    """Type 4: Explain which rule applies and why."""
    pairs = []
    
    explanations = {
        ("quotation", "pt-PT"): "In European Portuguese, primary quotation marks are guillemets (« ») with thin spaces inside. Nested quotations use curly double quotes (\u201C \u201D). Straight quotes should never be used in typeset Portuguese text.",
        ("quotation", "en-US"): "In American English, primary quotation marks are curly double quotes (\u201C \u201D). Nested quotations use curly single quotes (\u2018 \u2019). Commas and periods are placed inside closing quotes.",
        ("quotation", "en-GB"): "In British English, primary quotation marks are curly single quotes (\u2018 \u2019). Nested quotations use curly double quotes (\u201C \u201D). Commas and periods are typically placed outside closing quotes.",
        ("quotation", "fr-FR"): "In French, primary quotation marks are guillemets (« ») with narrow no-break spaces (U+202F) inside. This prevents the guillemet from being separated from its content at line breaks.",
        ("quotation", "de-DE"): "In German, primary quotation marks use the low-9 opening quote (\u201E) and the left double quote (\u201C) as the closer \u2014 an unusual system where what looks like an opening mark in English serves as the closing mark in German.",
        ("quotation", "it-IT"): "In Italian, primary quotation marks are guillemets (« ») with no inner spaces \u2014 unlike Portuguese (thin spaces) and French (narrow no-break spaces). Modern Italian publishing increasingly uses curly double quotes as an alternative.",
        ("quotation", "es-ES"): "In European Spanish, the RAE prescribes guillemets (« ») as primary quotation marks with no inner spaces. However, curly double quotes are increasingly common in newspapers and digital publishing.",
        ("dashes", "en-US"): "American English uses em dashes (\u2014) without spaces for parenthetical asides, and en dashes (\u2013) without spaces for ranges. A hyphen (-) should only be used for compound words.",
        ("dashes", "en-GB"): "British English uses en dashes (\u2013) with spaces on both sides for parenthetical asides, and en dashes without spaces for ranges. This is different from American convention which uses em dashes.",
        ("dashes", "de-DE"): "German uses en dashes (\u2013) with spaces for parenthetical asides (Gedankenstrich), the same as British English convention. Ranges also use en dashes without spaces.",
        ("inverted_punctuation", "es-ES"): "Spanish requires inverted punctuation marks (¿ ¡) at the start of interrogative or exclamatory clauses. The inverted mark opens where the intonation shift begins, which may be mid-sentence, not necessarily at the start.",
        ("french_spacing", "fr-FR"): "French typography requires a narrow no-break space (U+202F) before high punctuation marks: colon (:), semicolon (;), exclamation mark (!), and question mark (?). This is a fundamental rule of French typesetting.",
        ("italian_accents", "it-IT"): "Italian requires correct accent direction on final stressed vowels. The grave accent (è) marks the open 'e' sound, while the acute accent (é) marks the closed 'e'. Using an apostrophe instead of an accent (e.g., perche' instead of perché) is a common keyboard shortcut error.",
        ("dialogue", "es-ES"): "Spanish dialogue uses the raya (em dash) with specific asymmetric spacing: no space after the opening raya, space before attribution rayas. The raya joins directly to the attribution verb. This differs from Portuguese and French conventions.",
        ("quotation", "nl-NL"): "Dutch uses curly double quotes (\u201C \u201D) as primary quotation marks, the same system as American English. Some older or literary Dutch publications use the German-style low-9 opening quote (\u201E) or Flemish reversed guillemets.",
        ("quotation", "ro-RO"): "Romanian uses the low-9 opening quote (\u201E) like German, but closes with the standard right double quote (\u201D) rather than the German left double quote closer. Nested quotations use guillemets (« ») without inner spaces.",
        ("dashes", "nl-NL"): "Dutch uses en dashes (\u2013) with spaces on both sides for parenthetical asides, following the British/German convention rather than the American em dash convention.",
        ("dashes", "ro-RO"): "Romanian uses en dashes (\u2013) with spaces for parenthetical asides. Dialogue uses em dashes (linie de dialog) with a space after, similar to Portuguese.",
        ("romanian_diacritics", "ro-RO"): "Romanian requires comma-below diacritics: \u0219 (s with comma below) and \u021B (t with comma below). The visually similar cedilla forms \u015F and \u0163 are Turkish characters, wrong for Romanian. This error is endemic due to legacy encodings and keyboard layouts that mapped to the wrong Unicode codepoints.",
        ("dutch_ij", "nl-NL"): "The Dutch digraph IJ functions as a single letter. When a word starting with ij is capitalised, both letters must be uppercase: IJsselmeer, not Ijsselmeer. This applies to title case, sentence case, and any automated case conversion.",
        ("sardinian_elision", "sc"): "Sardinian articles and prepositions elide before vowels using a typographic apostrophe with no surrounding spaces: s\u2019abba (the water), d\u2019oe (from today). A space before or after the apostrophe in elision is always an error.",
        ("dialogue", "ro-RO"): "Romanian uses the em dash (linie de dialog) for dialogue, with a space after the opening dash. Attribution dashes have a space before them. This convention is similar to Portuguese and Italian.",
        ("french_ligatures", "fr-FR"): "In French, \u0153 (oe ligature) and \u00E6 (ae ligature) are distinct orthographic letters, not decorative ligatures. Writing 'coeur' instead of 'c\u0153ur' is a misspelling. These characters survive NFC normalization and must never be decomposed.",
        ("french_capital_accents", "fr-FR"): "The Acad\u00E9mie fran\u00E7aise requires accents on capital letters in French. \u00C9TAT not ETAT, \u00C0 PARIS not A PARIS, H\u00D4TEL not HOTEL. Legacy AZERTY keyboards lacked capital accented characters, making bare capitals endemic in digital French text. Acronyms (CEE, OTAN) are exempt.",
        ("german_eszett", "de-DE"): "The capital form of \u00DF is \u1E9E (U+1E9E), officially valid since 2017 and preferred since the 2024 Rat f\u00FCr deutsche Rechtschreibung update. STRA\u1E9E is preferred over STRASSE. Swiss German uses only ss. Never confuse \u00DF with Greek \u03B2 (beta).",
        ("german_din5008", "de-DE"): "German multi-part abbreviations per DIN 5008:2020 require a narrow no-break space (U+202F) between parts to prevent line breaks within the abbreviation: z.\u202FB. (zum Beispiel), d.\u202Fh. (das hei\u00DFt), i.\u202Fd.\u202FR. (in der Regel).",
        ("nbsp_obligations", "fr-FR"): "French typography requires non-breaking spaces in specific contexts: after M. and Mme (title+name bond), before % with NNBSP, and between all numbers and their units. This prevents orphaned elements at line breaks.",
        ("nbsp_obligations", "it-IT"): "Italian uses non-breaking spaces between title abbreviations and names (Dott.\u00A0Rossi, Sig.\u00A0Bianchi) and between page/figure abbreviations and their numbers. This prevents line breaks from separating logically bonded elements.",
        ("code_exclusion", "_universal"): "Code-like contexts must be exempt from typographic corrections. URLs, file paths, email addresses, backtick code spans, CLI flags, variable names, and version strings use ASCII characters intentionally. The corrector should only modify surrounding prose, never code or identifiers.",
        ("code_exclusion", "en-US"): "When prose and code appear together, only the prose portions receive typographic corrections. Straight quotes inside backtick code spans, URLs, and email addresses are intentional and must not be replaced with curly quotes. The surrounding prose follows normal English typographic rules.",
        ("code_exclusion", "fr-FR"): "In French text containing code elements, the code context detection must fire before any other rule. Guillemet substitution, NNBSP insertion, and other French typography rules apply only to the prose portions, never to URLs, file paths, or inline code.",
        ("normalization", "_universal"): "NFC normalization composes decomposed character sequences into their precomposed equivalents. For example, e + combining acute accent (U+0065 U+0301) becomes \u00E9 (U+00E9). This ensures consistent text storage and comparison. NFKC must never be used for output because it destroys intentional ligatures (\uFB01 \u2192 fi), collapses NNBSP to regular space, and decomposes Dutch \u0132.",
        ("normalization", "fr-FR"): "French text is especially sensitive to normalization. NFC preserves \u0153 (oe ligature) and NNBSP (U+202F) while composing decomposed accented characters. Using NFKC would destroy French orthographic ligatures and spacing conventions.",
        ("zero_width_characters", "_universal"): "Zero-width spaces (U+200B) are common copy-paste artifacts that corrupt search, diffs, and credential fields. They should be stripped from prose. However, ZWNJ (U+200C) serves intentional ligature suppression in German compounds, ZWJ (U+200D) is essential for emoji composition, and word joiner (U+2060) prevents line breaks. These must be preserved.",
        ("zero_width_characters", "de-DE"): "In German, ZWNJ (U+200C) is used at morpheme boundaries to suppress unwanted ligatures in compound words: Auf\u200Clage, Schiff\u200Cfahrt. This is a Duden requirement. The selnolig package has approximately 2,000 German suppression patterns. ZWSP (U+200B), by contrast, is always an error in German text and should be stripped.",
        ("capital_accents_multilingual", "es-ES"): "The RAE (Real Academia Espa\u00F1ola) since 2010 explicitly requires accents on capital letters: \u00C1REA not AREA, LING\u00DC\u00CDSTICA not LINGUISTICA. Omitting accents on capitals was historically common due to typewriter limitations but is now considered an orthographic error.",
        ("capital_accents_multilingual", "pt-PT"): "Portuguese requires all diacritics on capital letters: A\u00C7\u00C3O not ACAO, CORA\u00C7\u00C3O not CORACAO. The cedilla (\u00C7) and tilde (\u00C3) are essential \u2014 their omission changes the word or makes it unreadable.",
        ("capital_accents_multilingual", "it-IT"): "Italian accents on capitals are mandatory: CITT\u00C0 not CITTA, UNIVERSIT\u00C0 not UNIVERSITA. The accent on the final vowel is orthographically required and its absence is a misspelling, not merely a typographic issue.",
        ("capital_accents_multilingual", "de-DE"): "German umlauts must be preserved on capitals: \u00DCBERSICHT not UBERSICHT, \u00C4NDERUNG not ANDERUNG. The alternative AE/OE/UE substitution is only acceptable in ASCII-only contexts like email addresses or legacy systems, never in typeset text.",
        ("homoglyph_expanded", "de-DE"): "Greek beta (\u03B2 U+03B2) is commonly confused with German eszett (\u00DF U+00DF) in scientific and technical texts. They are visually similar but semantically different characters from different scripts. In German text, \u03B2 is always wrong and should be \u00DF.",
        ("homoglyph_expanded", "_universal"): "The grave accent (` U+0060) is a programming character and should never appear in typeset prose as an apostrophe. The correct typographic apostrophe is \u2019 (U+2019 RIGHT SINGLE QUOTATION MARK). Similarly, the ordinal indicator (\u00BA) should not be confused with the degree sign (\u00B0).",
        ("nnbsp_thousands_separator", "fr-FR"): "French and ISO convention uses the narrow no-break space (U+202F) as the thousands group separator: 1\u202F000, 25\u202F000, 1\u202F500\u202F000. This is specified in CLDR 34+ for the fr locale. The NNBSP prevents line breaks within numbers while providing the correct visual spacing.",
        ("single_letter_line_end", "fr-FR"): "Some French style guides recommend bonding single-letter words (\u00E0, y) to the following word with a non-breaking space to prevent them from being orphaned at line end. This is a soft rule applied mainly in editorial and literary registers.",
        ("single_letter_line_end", "es-ES"): "In Spanish, single-letter conjunctions and prepositions (y, e, o, a, u) can be bonded to the following word with a non-breaking space to prevent line-end orphaning. This is a stylistic recommendation followed by some publishers, not a mandatory rule like in Polish or Czech.",
        # Batch 4 — colon capitalisation
        ("colon_capitalisation", "en-US"): "American English capitalises the first word after a colon when what follows is an independent clause \u2014 a clause that could stand on its own as a sentence (Chicago Manual of Style 6.64). Dependent clauses, lists, and appositives remain lowercase. This is the most locale-specific capitalisation rule in English and a common source of error.",
        ("colon_capitalisation", "en-GB"): "British English does not capitalise after a colon, even when a full sentence follows. This is one of the clearest EN-US/EN-GB divergences: American style capitalises independent clauses, British style never does. The only exception is proper nouns, which retain their inherent capitalisation.",
        ("colon_capitalisation", "fr-FR"): "French never capitalises the word after a colon (Imprimerie Nationale, Lexique des r\u00E8gles typographiques). This applies regardless of whether what follows is a complete sentence. Only proper nouns retain their capitalisation after a colon.",
        ("colon_capitalisation", "de-DE"): "German capitalises after a colon when what follows is a complete sentence (vollst\u00E4ndiger Satz), per Duden R 81. For fragments, enumerations, and dependent clauses, lowercase is used \u2014 though German nouns are always capitalised by grammar rules, not colon rules. This makes German colon capitalisation similar to EN-US but with the added complexity of noun capitalisation.",
        ("colon_capitalisation", "pt-PT"): "Portuguese does not capitalise after a colon in standard prose. Only proper nouns retain their inherent capitalisation. This is consistent across European and Brazilian Portuguese.",
        ("colon_capitalisation", "it-IT"): "Italian does not capitalise after a colon, even when a full sentence follows. Only proper nouns retain capitalisation. This is consistent with the majority European convention.",
        ("colon_capitalisation", "es-ES"): "Spanish does not capitalise after a colon in running prose. RAE specifies exceptions only for the salutation of a letter (Estimado se\u00F1or: Le escribo\u2026) and after certain labels. In all other contexts, lowercase follows the colon.",
        ("colon_capitalisation", "nl-NL"): "Dutch does not capitalise after a colon. This is consistent with the majority European convention where only proper nouns retain capitalisation after a colon.",
        ("colon_capitalisation", "ro-RO"): "Romanian does not capitalise after a colon in standard prose. Only proper nouns retain their capitalisation.",
        # Batch 4 — serial comma
        ("serial_comma", "en-US"): "The serial (Oxford) comma before the final conjunction in a list of three or more items is enforced in American English editorial register (Chicago Manual of Style, APA, Oxford). Marketing and journalism registers (AP Stylebook) often omit it. When ambiguity would result from omission, the serial comma should always be included regardless of register.",
        ("serial_comma", "en-GB"): "British English uses the serial comma less frequently than American English. While Oxford University Press uses it (hence \u2018Oxford comma\u2019), most UK publishers and style guides (Guardian, Times) omit it. It should always be included when omission creates ambiguity.",
        ("serial_comma", "fr-FR"): "French prohibits the serial comma. The conjunction (et, ou, ni) is considered sufficient separation in a list. Adding a comma before the conjunction is a grammatical error in standard French typesetting.",
        ("serial_comma", "de-DE"): "German prohibits a comma before the final conjunction (und, oder) in simple enumerations. The Duden is explicit: no comma before und/oder in a series. This is a grammatical rule, not a style choice.",
        ("serial_comma", "pt-PT"): "Portuguese does not use a comma before the final conjunction (e, ou, nem) in enumerations. The conjunction is considered sufficient separation. This applies equally to European and Brazilian Portuguese.",
        ("serial_comma", "it-IT"): "Italian does not use a comma before the final conjunction (e, o, n\u00E9) in enumerations. This is standard across all Italian style guides and publishers.",
        ("serial_comma", "es-ES"): "Spanish prohibits the serial comma before the final conjunction (y, e, o, u, ni) in enumerations. RAE is explicit: the conjunction provides sufficient separation. A comma before the conjunction is only acceptable in rare cases where the last element is a complex clause that could cause genuine ambiguity.",
        ("serial_comma", "nl-NL"): "Dutch does not use a comma before the final conjunction (en, of) in enumerations. Standard Dutch grammar treats the conjunction as sufficient separation between the last two items.",
        ("serial_comma", "ro-RO"): "Romanian does not use a comma before the final conjunction (\u0219i, sau, nici) in enumerations. This follows the standard European convention.",
        # Batch 4 — quote punctuation placement
        ("quote_punctuation_placement", "en-US"): "American English uses the typesetters\u2019 convention: commas and periods are ALWAYS placed inside the closing quotation mark, regardless of whether they are part of the quoted material. This originated in the era of metal type and persists in American publishing. Colons and semicolons go outside; question marks and exclamation marks follow logic.",
        ("quote_punctuation_placement", "en-GB"): "British English uses logical punctuation placement: commas and periods go inside the closing quotation mark only if they are part of the original quoted material. Otherwise, they go outside. This is also called \u2018logical\u2019 or \u2018British\u2019 style and is the convention used by most non-American English-speaking countries.",
        ("quote_punctuation_placement", "fr-FR"): "French uses logical punctuation placement with guillemets: punctuation goes inside the guillemets only if it belongs to the quoted material. Sentence-final punctuation that applies to the surrounding sentence goes outside the closing guillemet.",
        ("quote_punctuation_placement", "de-DE"): "German uses logical punctuation placement: punctuation goes inside the closing quotation mark only when it belongs to the quoted material. When the period belongs to the enclosing sentence rather than the quoted word or phrase, it goes after the closing quote.",
        ("quote_punctuation_placement", "pt-PT"): "Portuguese uses logical punctuation placement: punctuation goes inside the closing quotation mark only when it belongs to the quoted material. This applies to both guillemet-style quotation marks in European Portuguese and curly quotes in Brazilian Portuguese.",
        ("quote_punctuation_placement", "it-IT"): "Italian uses logical punctuation placement: punctuation goes inside the closing quotation mark only when it is part of the quoted material. This is consistent across Italian publishing whether guillemets or curly quotes are used.",
        ("quote_punctuation_placement", "es-ES"): "Spanish uses logical punctuation placement: punctuation goes inside the closing quotation mark only when it belongs to the quoted material. RAE is explicit on this rule, which applies regardless of whether guillemets or curly quotes are used.",
        ("quote_punctuation_placement", "nl-NL"): "Dutch uses logical punctuation placement: punctuation goes inside the closing quotation mark only when it belongs to the quoted material. This follows the majority European convention.",
        ("quote_punctuation_placement", "ro-RO"): "Romanian uses logical punctuation placement: punctuation goes inside the closing quotation mark only when it belongs to the quoted material. This follows the majority European convention.",
        # Batch 4 — abbreviation periods
        ("abbreviation_periods", "en-US"): "American English uses a period after ALL abbreviations and contractions: Mr., Mrs., Dr., St., Jr., Sr., Ave. This is the simplest rule among covered languages \u2014 every abbreviation gets a period, no exceptions.",
        ("abbreviation_periods", "en-GB"): "British English distinguishes contractions from truncations. Contractions that include the last letter of the full word DROP the period: Mr (Mister), Dr (Doctor), St (Saint). True truncations that do NOT end with the final letter KEEP the period: Prof. (Professor), Rev. (Reverend), Gen. (General). This is a clean, logical rule based on whether the abbreviated form ends with the same letter as the full word.",
        ("abbreviation_periods", "fr-FR"): "French abbreviation conventions depend on whether the last letter of the full word is preserved. Truncations take a period: M. (Monsieur), Prof. (Professeur). Contractions that preserve the final letter omit the period: Mme (Madame), Dr (Docteur), Me (Ma\u00EEtre). The superscript convention signals the contraction visually.",
        ("abbreviation_periods", "de-DE"): "German abbreviations take a period: Dr., Prof., Hr. (Herr), Fr. (Frau), Nr. (Nummer), Str. (Stra\u00DFe). Multi-part abbreviations per DIN 5008 require narrow no-break spaces between parts: z.\u202FB., d.\u202Fh., i.\u202Fd.\u202FR.",
        ("abbreviation_periods", "pt-PT"): "Portuguese uses a period after most abbreviations: Sr. (Senhor), Sra. (Senhora), Dr. (Doutor), Dra. (Doutora), Prof. (Professor), Eng. (Engenheiro). Feminine forms with superscript indicators (Sr.\u00AA) are used in formal contexts.",
        # Batch 4 — abbreviation haplology
        ("abbreviation_haplology", "_universal"): "When an abbreviation that ends with a period falls at the end of a sentence, the abbreviation period also serves as the sentence-final full stop. Producing two consecutive periods is always wrong: \u2018etc..\u2019 \u2192 \u2018etc.\u2019, \u2018Corp..\u2019 \u2192 \u2018Corp.\u2019 This rule is universal across all covered languages.",
        # Batch 4 — footnote mark placement
        ("footnote_mark_placement", "en-US"): "In American English (Chicago 14.26), the superscript footnote mark follows the comma, period, or closing quotation mark. It never precedes punctuation. This convention is also followed by German, Portuguese, Italian, Dutch, and Romanian.",
        ("footnote_mark_placement", "en-GB"): "British English follows the same convention as American English for footnote placement: the mark goes after the punctuation. This is the majority convention across English-speaking publishing.",
        ("footnote_mark_placement", "fr-FR"): "French convention (Imprimerie Nationale) places the superscript footnote mark BEFORE the punctuation: mot\u00B9. This is the opposite of the English and German convention. The mark sits between the word and the punctuation, interacting with the NNBSP-before-punctuation rule in complex spacing sequences.",
        ("footnote_mark_placement", "es-ES"): "Spanish convention (RAE) places the superscript footnote mark BEFORE the punctuation, similar to the French convention. This means the mark precedes the period or comma: importante\u00B9.",
        ("footnote_mark_placement", "de-DE"): "German places footnote marks AFTER punctuation (Duden), following the same convention as English. The mark follows the comma, period, or closing quotation mark.",
        ("footnote_mark_placement", "pt-PT"): "Portuguese follows the after-punctuation convention for footnote marks, consistent with the English and German tradition. The superscript mark appears after the period, comma, or closing quotation mark.",
        ("footnote_mark_placement", "it-IT"): "Italian follows the after-punctuation convention for footnote marks. The superscript mark appears after the period or comma, consistent with the majority European tradition.",
        ("footnote_mark_placement", "nl-NL"): "Dutch follows the after-punctuation convention for footnote marks. The mark goes after the period, comma, or closing quotation mark.",
        ("footnote_mark_placement", "ro-RO"): "Romanian follows the after-punctuation convention for footnote marks, consistent with the majority European tradition.",
        # Batch 4 — nested parentheticals
        ("nested_parentheticals", "_universal"): "When a parenthetical expression is nested inside another, the inner layer should use square brackets to avoid ambiguity: (text (inner)) \u2192 (text [inner]). This convention is widely followed in English (Chicago, Oxford), French, German, Spanish, Portuguese, Italian, Dutch, and Romanian. Legal and academic citation formats may override this general typographic rule.",
        # Batch 5 — Micro-typography
        ("ligature_suppression", "de-DE"): "German compound words frequently produce f-ligature sequences (fi, fl, ff, ffi, ffl) that cross morpheme boundaries. The Duden requires ligature suppression at these boundaries using ZWNJ (U+200C): Auf\u200Clage (not the fl-ligature across Auf+lage), Schiff\u200Cfahrt (not the ff-ligature across Schiff+fahrt). The German selnolig package documents approximately 2,000 suppression patterns. ZWNJ is invisible and does not affect search, copy-paste, or accessibility \u2014 it only instructs the shaping engine to break the ligature.",
        ("ligature_suppression", "en-US"): "English compound words occasionally produce f-ligature sequences across morpheme boundaries: shelf\u200Cful (shelf+ful), half\u200Clife (half+life), roof\u200Cline (roof+line). ZWNJ (U+200C) at the boundary prevents the ligature from visually merging parts that are semantically separate. This is less common than in German but applies to any compound with f at the morpheme junction.",
        ("ligature_suppression", "en-GB"): "British English follows the same ligature suppression rules as American English. ZWNJ is inserted at morpheme boundaries where f-ligatures would incorrectly span compound elements: shelf\u200Cful, half\u200Clife, cuff\u200Clink, off\u200Cload.",
        ("orthographic_ligature_preservation", "fr-FR"): "In French, \u0153 (oe ligature) and \u00E6 (ae ligature) are distinct orthographic letters, not decorative typographic ligatures. Writing \u2018coeur\u2019 instead of \u2018c\u0153ur\u2019 is a misspelling \u2014 the same severity as writing \u2018skool\u2019 for \u2018school\u2019 in English. These characters are preserved by NFC normalization (unlike fi/fl ligatures which are compatibility forms). The preservation rule has the HIGHEST priority, equal to Romanian \u0219/\u021B. Latin loanwords also require \u00E6: ex \u00E6quo, curriculum vit\u00E6 in formal registers.",
        ("small_caps_acronyms", "en-US"): "In editorial and literary registers, acronyms of three or more letters (NATO, UNESCO, NASA) should be set in small caps to avoid typographic \u2018shouting\u2019 that disrupts the colour of the page. The text remains uppercase in the data layer; only the rendering is affected. Exceptions: two-letter acronyms (US, UK) stay in full caps, words derived from acronyms (laser, radar) are lowercase, and brand identities styled as all-caps (IBM, BMW) respect the brand.",
        ("small_caps_acronyms", "fr-FR"): "French editorial convention sets acronyms of three or more letters in small caps: OTAN, UNESCO, ALENA. Roman-numeral centuries are also candidates: le XIXe si\u00E8cle. The model flags these for small-caps rendering; it does not change the characters. Marketing register may prefer full caps for visual impact.",
        ("small_caps_acronyms", "de-DE"): "German editorial typography sets acronyms in small caps: NATO, UNESCO, GmbH. This reduces the visual weight of all-caps clusters in running text. The model annotates acronyms for small-caps rendering without changing the underlying characters.",
        ("small_caps_acronyms", "it-IT"): "Italian editorial convention follows the European tradition of setting acronyms in small caps. Roman-numeral centuries (il XIX secolo) are especially common candidates. The model flags these for rendering treatment.",
        ("small_caps_acronyms", "es-ES"): "Spanish editorial style (RAE) recommends small caps for acronyms in literary and academic registers: OTAN, UNESCO. Roman-numeral centuries (el siglo XIX) are also set in small caps. The model flags these for rendering, not character substitution.",
        ("small_caps_acronyms", "pt-PT"): "Portuguese editorial convention uses small caps for acronyms in literary registers. Roman-numeral centuries (o s\u00E9culo XIX) are common candidates. The model flags text for small-caps rendering without modifying the characters.",
        ("figure_styles", "_universal"): "OpenType fonts typically offer four figure variants. Oldstyle proportional figures (onum+pnum) have ascenders and descenders that harmonize with lowercase body text. Lining tabular figures (lnum+tnum) sit on the baseline and are monospaced for column alignment. The model recommends the appropriate style: oldstyle for body prose (editorial/literary), lining for tables, financial data, and UI contexts. All-caps settings always use lining figures.",
        ("caps_letter_spacing", "_universal"): "All-caps and small-caps text benefits from increased letter-spacing (tracking) to improve legibility. The recommended range is 5\u201312% of font size: 5\u20138% for body-size small caps, 8\u201312% for display-size all-caps headings. This is a rendering recommendation \u2014 the corrector annotates all-caps runs with a tracking hint. Never insert thin or hair spaces between characters to simulate tracking, as this breaks search, selection, copy-paste, and accessibility.",
        ("hanging_punctuation", "_universal"): "Hanging punctuation is one of the hallmarks of professional typesetting. Opening quotation marks at line start and hyphens at line end receive a full hang into the margin. Periods, commas, colons, and semicolons at line end receive a partial hang (~50%). Em dashes and parentheses are too wide to hang. CSS: hanging-punctuation: first last; TeX: \\usepackage{microtype}. Not all rendering contexts support it \u2014 web support is limited to Safari as of 2025.",
        # Batch 6 — WCAG-safe emission
        ("wcag_text_spacing", "_universal"): "WCAG 2.1 SC 1.4.12 (Text Spacing, Level AA) requires that content remains functional when users override text spacing to: line-height 1.5\u00D7 font-size, paragraph spacing 2\u00D7 font-size, letter-spacing 0.12em, word-spacing 0.16em. The corrector must not emit output that relies on specific spacing values or uses !important on spacing properties. NBSP and NNBSP characters are acceptable (they create bonds, not fixed widths), but see the breakable_containers rule for chain limits.",
        ("no_fixed_width_containers", "_universal"): "When the corrector emits styled HTML+CSS output, it must not use !important on typographic properties (font-size, line-height, letter-spacing, word-spacing, font-family) or set fixed widths on text containers. These prevent assistive technology and user stylesheets from overriding properties for accessibility. Use relative units (%, em, rem, ch), avoid overflow: hidden on text containers, and avoid white-space: nowrap on blocks of text.",
        ("bidi_isolate_preservation", "_universal"): "Unicode bidi isolate characters (LRI U+2066, RLI U+2067, FSI U+2068, PDI U+2069) are essential for correct rendering of mixed-direction text. The corrector must never strip these during normalization or correction. Bidi isolate pairs must be treated as balanced delimiters \u2014 removing one without its partner creates bidi leakage. Screen readers rely on bidi isolates to announce text direction changes correctly; stripping them garbles multilingual content.",
        ("breakable_containers", "_universal"): "Non-breaking spaces create bonds between words. When 4+ consecutive words are NBSP-joined, the resulting unbreakable chunk may be too wide for narrow viewports or WCAG text spacing overrides. Rule: use regular spaces for middle joins, NBSP only at the critical bond points (first and last pairs). Exception: short tokens (1\u20132 characters each) in chains up to 5 are acceptable because the total width remains small. 3-word chains like \u201C10\u00A0000\u00A0km\u201D are fine.",
        ("language_tagging", "_universal"): "WCAG SC 3.1.2 (Language of Parts, Level AA) requires lang attributes on HTML elements containing text in a different language than the document\u2019s declared language. Screen readers use lang attributes to switch pronunciation engines. Without them, French names in English text are mispronounced, German compounds get wrong stress, and Portuguese nasals are mangled. The corrector should detect language switches and emit appropriate lang markup.",
        ("screen_reader_typography", "_universal"): "Using correct Unicode characters directly benefits screen reader users. EN DASH in ranges is read as \u201Cto\u201D; EM DASH is paused as a parenthetical break; ellipsis is announced as \u201Cellipsis\u201D rather than \u201Cperiod period period\u201D; vulgar fractions are read as words (\u201Cone quarter\u201D); multiplication sign is read as \u201Ctimes.\u201D Hyphen-minus in ranges may be read as \u201Cminus\u201D or \u201Chyphen\u201D \u2014 semantically wrong. The typographic corrections this schema enforces are therefore accessibility improvements by default.",
    }
    
    for (rule_name, lang), explanation in explanations.items():
        if rule_name in templates and lang in templates[rule_name]:
            examples = templates[rule_name][lang]
            for raw, correct in examples[:2]:  # use first 2 examples per rule
                lang_label = LANG_NAMES.get(lang, lang)
                pairs.append(TrainingPair(
                    instruction=f"Explain why this typographic correction is needed in {lang_label}.",
                    input=f"Original: {raw}\nCorrected: {correct}",
                    output=explanation,
                    metadata={
                        "type": "explanation",
                        "rule": rule_name,
                        "language": lang,
                    }
                ))
    
    return pairs


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def generate_dataset(output_path: str = "typography_training.jsonl") -> dict:
    """Generate the full training dataset and write to JSONL."""
    
    all_pairs: list[TrainingPair] = []
    
    # Generate all pair types
    correction_pairs = generate_correction_pairs(TEMPLATES)
    detection_pairs = generate_detection_pairs(TEMPLATES)
    cross_lang_pairs = generate_cross_language_pairs(TEMPLATES)
    explanation_pairs = generate_explanation_pairs(TEMPLATES)
    
    all_pairs.extend(correction_pairs)
    all_pairs.extend(detection_pairs)
    all_pairs.extend(cross_lang_pairs)
    all_pairs.extend(explanation_pairs)
    
    # Shuffle for training
    random.seed(42)
    random.shuffle(all_pairs)
    
    # Write JSONL
    output = Path(output_path)
    with output.open("w", encoding="utf-8") as f:
        for pair in all_pairs:
            record = {
                "instruction": pair.instruction,
                "input": pair.input,
                "output": pair.output,
                "metadata": pair.metadata,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    # Stats
    stats = {
        "total_pairs": len(all_pairs),
        "by_type": {
            "correction": len(correction_pairs),
            "detection": len(detection_pairs),
            "cross_language": len(cross_lang_pairs),
            "explanation": len(explanation_pairs),
        },
        "by_language": {},
        "by_rule": {},
    }
    
    for pair in all_pairs:
        lang = pair.metadata.get("language") or pair.metadata.get("target_language", "multi")
        stats["by_language"][lang] = stats["by_language"].get(lang, 0) + 1
        rule = pair.metadata.get("rule", "cross_language")
        stats["by_rule"][rule] = stats["by_rule"].get(rule, 0) + 1
    
    return stats


if __name__ == "__main__":
    output_file = str(Path(__file__).parent / "typography_training.jsonl")
    stats = generate_dataset(output_file)
    
    print("=" * 60)
    print("TYPOGRAPHY TRAINING DATASET GENERATED")
    print("=" * 60)
    print(f"\nTotal pairs: {stats['total_pairs']}")
    print(f"\nBy type:")
    for t, count in stats["by_type"].items():
        print(f"  {t:20s} {count:5d}")
    print(f"\nBy language:")
    for lang, count in sorted(stats["by_language"].items(), key=lambda x: -x[1]):
        print(f"  {lang:20s} {count:5d}")
    print(f"\nBy rule:")
    for rule, count in sorted(stats["by_rule"].items(), key=lambda x: -x[1]):
        print(f"  {rule:20s} {count:5d}")
    print(f"\nOutput: {output_file}")
