# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 devkancheti4-design
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version. It is distributed WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Affero General Public License for more details. You should have received a copy
# of the license along with this program. If not, see
# <https://www.gnu.org/licenses/>.
"""Repair act dictionary. The router is imported verbatim and never modified;
it infers the fault-kind -> act mapping from ONE worked example, so acts must be
numbered k+5 in kind order and the mapping must never be written down here."""
import os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
from fluid_router import route as router
WORKED_EXAMPLE = (0, 5)

# YOUR JOB: fill in observe() and acts().
#   observe(line) -> list of integer fault KINDS, contiguous from 0.
#   acts(line, act) -> list of EVERY candidate replacement line that act offers.
#                      Act number for kind k is ALWAYS k+5. Return [] if it does
#                      not apply. Never return the input line unchanged.
# Pure text/regex transforms. Only `re` is available.

# ---------------------------------------------------------------------------
# shared lexical helpers
# ---------------------------------------------------------------------------

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_DOTTED_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*")
_TOKEN_RE = re.compile(r"\S+")
_ALPHA_RE = re.compile(r"[A-Za-z][A-Za-z']*")
_NUM_RE = re.compile(r"(?<![A-Za-z_0-9.])(\d+)(?![.\d])")

_KEYWORDS = set("""False None True and as assert async await break class continue def del
elif else except finally for from global if import in is lambda nonlocal not or pass raise
return try while with yield print self cls""".split())


def _scan(line):
    """Return (string_spans, bracket_groups, comment_start).

    string_spans : list of (start, end) covering quotes inclusive
    bracket_groups : list of (open_idx, close_idx, opener_char)
    """
    n = len(line)
    strs = []
    groups = []
    stack = []
    comment = None
    i = 0
    while i < n:
        c = line[i]
        if c == "#":
            comment = i
            break
        if c == '"' or c == "'":
            q = c
            if line[i:i + 3] == q * 3:
                j = line.find(q * 3, i + 3)
                if j == -1:
                    strs.append((i, n))
                    i = n
                    break
                strs.append((i, j + 3))
                i = j + 3
                continue
            j = i + 1
            closed = False
            while j < n:
                if line[j] == "\\":
                    j += 2
                    continue
                if line[j] == q:
                    closed = True
                    break
                j += 1
            if closed:
                strs.append((i, j + 1))
                i = j + 1
                continue
            strs.append((i, n))
            i = n
            break
        if c in "([{":
            stack.append((c, i))
        elif c in ")]}":
            if stack:
                o, j = stack.pop()
                groups.append((j, i, o))
        i += 1
    groups.sort()
    return strs, groups, comment


def _in_spans(pos, spans):
    for (s, e) in spans:
        if s <= pos < e:
            return True
    return False


def _split_args(s):
    """Top level comma split of `s`; returns list of (start, end) offsets."""
    if not s.strip():
        return []
    parts = []
    depth = 0
    q = None
    start = 0
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if q:
            if ch == "\\":
                i += 2
                continue
            if ch == q:
                q = None
            i += 1
            continue
        if ch in "\"'":
            q = ch
            i += 1
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append((start, i))
            start = i + 1
        i += 1
    parts.append((start, n))
    return parts


def _callspans(line):
    """list of (name_start, open_idx, close_idx, opener, name) for every bracket
    group; name_start == open_idx and name == '' when it is not a call."""
    strs, groups, comment = _scan(line)
    out = []
    for (o, c, op) in groups:
        j = o
        while j > 0 and (line[j - 1].isalnum() or line[j - 1] in "_."):
            j -= 1
        name = line[j:o]
        if not name or not re.match(r"^[A-Za-z_][A-Za-z_0-9.]*$", name):
            j = o
            name = ""
        out.append((j, o, c, op, name))
    return out


def _idents(line):
    """identifiers appearing in the code (non-string, non-comment) part."""
    strs, groups, comment = _scan(line)
    end = comment if comment is not None else len(line)
    seen = []
    for m in _IDENT_RE.finditer(line):
        if m.start() >= end:
            break
        if _in_spans(m.start(), strs):
            continue
        w = m.group(0)
        if w not in seen:
            seen.append(w)
    return seen


def _ident_positions(line):
    strs, groups, comment = _scan(line)
    end = comment if comment is not None else len(line)
    out = []
    for m in _IDENT_RE.finditer(line):
        if m.start() >= end:
            break
        if _in_spans(m.start(), strs):
            continue
        out.append((m.start(), m.end(), m.group(0)))
    return out


def _code_end(line):
    strs, groups, comment = _scan(line)
    return comment if comment is not None else len(line)


def _trim_span(line, s, e):
    while s < e and line[s] in " \t":
        s += 1
    while e > s and line[e - 1] in " \t,:;\\":
        e -= 1
    return s, e


def _expr_targets(line):
    """Plausible expression spans (start, end) on the line."""
    strs, groups, comment = _scan(line)
    end = comment if comment is not None else len(line)
    body = line[:end]
    out = []

    def add(s, e):
        s, e = _trim_span(line, s, e)
        if e > s and (s, e) not in out:
            out.append((s, e))

    stripped = body.strip()
    if stripped:
        s = len(body) - len(body.lstrip())
        add(s, s + len(stripped))

    # right hand side of an assignment / keyword argument
    depth = 0
    q = None
    i = 0
    while i < len(body):
        ch = body[i]
        if q:
            if ch == "\\":
                i += 2
                continue
            if ch == q:
                q = None
            i += 1
            continue
        if ch in "\"'":
            q = ch
            i += 1
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "=" and body[i:i + 2] != "==" and (i == 0 or body[i - 1] not in "=!<>+-*/%&|^~"):
            add(i + 1, len(body))
        i += 1

    # after leading keywords
    for kw in ("return", "yield", "assert", "if", "elif", "while", "del", "raise",
               "yield from", "await", "not", "in", "and", "or", "else", "for", "with",
               "print", "lambda"):
        for m in re.finditer(r"(?:(?<=^)|(?<=[\s(\[{:,]))" + re.escape(kw) + r"\s+", body):
            add(m.end(), len(body))

    # bracket groups: both with and without their brackets
    for (o, c, op) in groups:
        if c >= end:
            continue
        add(o, c + 1)
        add(o + 1, c)
        content = line[o + 1:c]
        for (a, b) in _split_args(content):
            add(o + 1 + a, o + 1 + b)

    # whole call spans including callee
    for (ns, o, c, op, name) in _callspans(line):
        if name and c < end:
            add(ns, c + 1)

    for (s, e) in strs:
        if s < end:
            add(s, e)

    return out


# ---------------------------------------------------------------------------
# vocabularies
# ---------------------------------------------------------------------------

_CHARSET = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    " _.,:;'\"()[]{}=+-*/%<>!&|^~@#?$\\"
)

_NAME_VOCAB = [
    "None", "True", "False", "self", "cls", "default", "value", "values", "key", "keys",
    "name", "item", "items", "data", "text", "word", "words", "s", "n", "i", "j", "k", "v",
    "x", "y", "num", "number", "count", "index", "idx", "result", "res", "obj", "other",
    "arg", "args", "kwargs", "months", "follow", "precision", "format", "fmt", "sep",
    "end", "start", "stop", "step", "encoding", "base", "size", "length", "width",
    "depth", "limit", "offset", "minimum", "maximum", "strict", "reverse", "case",
    "plural", "singular", "string", "char", "line", "lines", "path", "filename", "mode",
    "flag", "func", "f", "g", "pred", "seq", "coll", "colls", "lst", "d", "ctx", "out",
    "ret", "acc", "total", "delta", "seconds", "minutes", "hours", "days", "years",
    "value_", "exponent", "suffix", "prefix", "unit", "units", "part", "parts", "match",
    "pattern", "regex", "rest", "first", "last", "left", "right", "old", "new", "tmp",
    "err", "exc", "cache", "table", "word_list", "gender", "person", "verb", "noun",
]

_ARG_VOCAB = _NAME_VOCAB + [
    "0", "1", "-1", "2", "3", "10", "100", "1000", "0.0", "1.0",
    "''", '""', "[]", "{}", "()", "' '", '" "', "'\\n'", '"\\n"',
    "'utf-8'", '"utf-8"', "'rb'", '"rb"', "'r'", '"r"', "'w'", '"w"',
    "*args", "**kwargs",
    "default=None", "default=False", "default=True",
    "encoding='utf-8'", 'encoding="utf-8"',
    "key=None", "reverse=True", "reverse=False", "strict=False", "strict=True",
    "sep=''", 'sep=""', "sep=' '", "maxsplit=1", "count=1",
    "re.I", "re.IGNORECASE", "re.UNICODE", "re.DOTALL", "flags=re.I",
    "None, None", "0, 0",
]

_WRAP_UNARY = [
    "str", "int", "float", "bool", "list", "tuple", "set", "dict", "frozenset",
    "len", "abs", "round", "max", "min", "sorted", "reversed", "sum", "any", "all",
    "repr", "iter", "next", "type", "bytes", "ord", "chr", "enumerate", "range",
    "re.escape", "re.compile", "_", "gettext", "_gettext", "cls", "self.__class__",
    "math.floor", "math.ceil", "math.fabs", "Decimal", "str.strip", "text_type",
    "''.join", '"".join', "', '.join", '", ".join', "' '.join", '" ".join',
    "'\\n'.join", "self", "copy", "deepcopy",
]

_WRAP_BINARY = [
    ("max(0, ", ")"), ("min(0, ", ")"), ("max(1, ", ")"), ("min(1, ", ")"),
    ("max(", ", 0)"), ("min(", ", 0)"), ("max(", ", 1)"), ("min(", ", 1)"),
    ("round(", ", 2)"), ("round(", ", 1)"), ("int(", ", 10)"),
    ("float(", ")"), ("abs(", ")"),
]

_METHOD_APPEND = [
    ".strip()", ".lstrip()", ".rstrip()", ".lower()", ".upper()", ".title()",
    ".capitalize()", ".copy()", ".read()", ".split()", ".splitlines()", ".items()",
    ".keys()", ".values()", ".group()", ".groups()", ".pop()", ".close()",
    ".decode('utf-8')", '.decode("utf-8")', ".encode('utf-8')", '.encode("utf-8")',
    ".replace('%d', '%s')", '.replace("%d", "%s")',
    ".strip('\\n')", '.strip("\\n")', ".rstrip('\\n')", '.rstrip("\\n")',
    ".lower().strip()", ".format()", ".__name__", ".value", ".text",
]

_TOKEN_SWAPS = [
    ("==", "!="), ("!=", "=="), ("==", "is"), ("is", "=="),
    ("<", ">"), (">", "<"), ("<=", ">="), (">=", "<="),
    ("<", "<="), ("<=", "<"), (">", ">="), (">=", ">"),
    ("<", ">="), (">", "<="), ("<=", ">"), (">=", "<"),
    ("+", "-"), ("-", "+"), ("*", "/"), ("/", "*"), ("/", "//"), ("//", "/"),
    ("%", "//"), ("//", "%"), ("*", "**"), ("**", "*"),
    ("+=", "-="), ("-=", "+="), ("=", "=="), ("==", "="),
    ("%s", "%d"), ("%d", "%s"), ("%s", "%r"), ("%r", "%s"), ("%i", "%d"), ("%d", "%i"),
]

_WORD_SWAPS = [
    ("and", "or"), ("or", "and"), ("True", "False"), ("False", "True"),
    ("None", "False"), ("None", "True"), ("False", "None"), ("True", "None"),
    ("is", "is not"), ("is not", "is"), ("in", "not in"), ("not in", "in"),
    ("if", "elif"), ("elif", "if"), ("if", "while"), ("while", "if"),
    ("return", "yield"), ("yield", "return"), ("yield", "yield from"),
    ("append", "extend"), ("extend", "append"), ("append", "insert"),
    ("keys", "values"), ("values", "keys"), ("keys", "items"), ("items", "keys"),
    ("values", "items"), ("items", "values"),
    ("lower", "upper"), ("upper", "lower"),
    ("startswith", "endswith"), ("endswith", "startswith"),
    ("lstrip", "rstrip"), ("rstrip", "lstrip"), ("strip", "rstrip"), ("strip", "lstrip"),
    ("split", "rsplit"), ("rsplit", "split"), ("find", "rfind"), ("rfind", "find"),
    ("index", "rindex"), ("min", "max"), ("max", "min"),
    ("int", "float"), ("float", "int"), ("str", "repr"), ("repr", "str"),
    ("ljust", "rjust"), ("rjust", "ljust"), ("floor", "ceil"), ("ceil", "floor"),
    ("get", "pop"), ("pop", "get"), ("sorted", "reversed"), ("reversed", "sorted"),
    ("self", "cls"), ("cls", "self"), ("update", "add"), ("add", "update"),
    ("match", "search"), ("search", "match"), ("sub", "subn"),
    ("first", "last"), ("last", "first"), ("next", "iter"),
    ("assert", "if"), ("break", "continue"), ("continue", "break"),
    ("singular", "plural"), ("plural", "singular"),
    ("isdigit", "isnumeric"), ("isnumeric", "isdigit"), ("isalpha", "isalnum"),
    ("__init__", "__new__"), ("len", "sum"), ("all", "any"), ("any", "all"),
    ("years", "months"), ("months", "years"), ("days", "months"), ("hours", "minutes"),
    ("minutes", "seconds"), ("seconds", "minutes"),
    ("iteritems", "items"), ("iterkeys", "keys"), ("itervalues", "values"),
    ("unicode", "str"), ("basestring", "str"), ("xrange", "range"),
    ("raw_input", "input"), ("long", "int"), ("unichr", "chr"),
    ("izip", "zip"), ("imap", "map"), ("ifilter", "filter"),
    ("str", "unicode"), ("range", "xrange"),
    ("upper", "title"), ("title", "upper"), ("count", "index"),
    ("insert", "append"), ("remove", "discard"), ("discard", "remove"),
    ("copy", "deepcopy"), ("abs", "int"), ("round", "int"), ("int", "round"),
    ("group", "groups"), ("groups", "group"), ("groupdict", "groups"),
    ("write", "writelines"), ("read", "readlines"), ("readline", "readlines"),
    ("startswith", "__contains__"), ("format", "__mod__"),
    ("isupper", "islower"), ("islower", "isupper"),
    ("or", "and"), ("if", "assert"),
]

_SUFFIX_SWAPS = [
    ("ance", "ence"), ("ence", "ance"), ("ant", "ent"), ("ent", "ant"),
    ("able", "ible"), ("ible", "able"), ("ise", "ize"), ("ize", "ise"),
    ("ised", "ized"), ("ized", "ised"), ("ising", "izing"), ("izing", "ising"),
    ("our", "or"), ("or", "our"), ("yse", "yze"), ("yze", "yse"),
    ("ll", "l"), ("l", "ll"), ("cion", "tion"), ("tion", "sion"),
    ("sion", "tion"), ("ies", "ys"), ("ys", "ies"), ("ceed", "cede"),
    ("cede", "ceed"), ("ent", "ant"), ("ance", "ancy"), ("ancy", "ance"),
]

_INSERT_WORDS = [
    "not", "no", "a", "an", "the", "is", "are", "be", "to", "of", "in", "on", "and",
    "or", "only", "also", "will", "can", "may", "if", "as", "for", "with", "that",
    "it", "this", "these", "than", "then", "you", "we", "all", "any", "must", "should",
    "does", "do", "was", "were", "has", "have", "when", "which", "but", "by", "from",
    "at", "into", "up", "out", "so", "just", "e.g.", "i.e.",
]

_MISSPELL = {
    "accesible": "accessible", "acheive": "achieve", "aditional": "additional",
    "adress": "address", "allignment": "alignment", "alot": "a lot",
    "alredy": "already", "alwasy": "always", "amoung": "among", "anounce": "announce",
    "aplication": "application", "apropriate": "appropriate", "aquire": "acquire",
    "arbitary": "arbitrary", "arguement": "argument", "arguemnt": "argument",
    "arguent": "argument", "assigment": "assignment", "atribute": "attribute",
    "attirbute": "attribute", "avaiable": "available", "availabe": "available",
    "avalible": "available", "becuase": "because", "begining": "beginning",
    "behaviour": "behavior", "beleive": "believe", "bellow": "below",
    "boundry": "boundary", "calcualte": "calculate", "calender": "calendar",
    "cant": "can't", "carefull": "careful", "catagory": "category",
    "charater": "character", "charcter": "character", "choise": "choice",
    "colum": "column", "commited": "committed", "comparision": "comparison",
    "compatability": "compatibility", "compatiblity": "compatibility",
    "completly": "completely", "concatinate": "concatenate", "conatins": "contains",
    "confortable": "comfortable", "conjuction": "conjunction", "consistant": "consistent",
    "containes": "contains", "contructor": "constructor", "conver": "convert",
    "converions": "conversions", "coversion": "conversion", "correspoding": "corresponding",
    "curently": "currently", "decorater": "decorator", "defalut": "default",
    "defautl": "default", "definately": "definitely", "definiton": "definition",
    "dependancy": "dependency", "dependant": "dependent", "deprected": "deprecated",
    "descripton": "description", "desribe": "describe", "destory": "destroy",
    "determin": "determine", "dictionay": "dictionary", "diferent": "different",
    "differnt": "different", "dictionnary": "dictionary", "dispaly": "display",
    "documention": "documentation", "doesnt": "doesn't", "dont": "don't",
    "eachother": "each other", "efficent": "efficient", "elemnt": "element",
    "enviroment": "environment", "excpetion": "exception", "excpt": "except",
    "exeception": "exception", "exisiting": "existing", "existance": "existence",
    "existant": "existent", "explicitely": "explicitly", "expresion": "expression",
    "extention": "extension", "fales": "false", "fasle": "false", "fetaure": "feature",
    "flase": "false", "follwing": "following", "formated": "formatted",
    "formating": "formatting", "fullfill": "fulfill", "funcion": "function",
    "funtion": "function", "futher": "further", "gaurd": "guard", "generaly": "generally",
    "guarentee": "guarantee", "handeling": "handling", "happend": "happened",
    "heirarchy": "hierarchy", "hierachy": "hierarchy", "howver": "however",
    "identifer": "identifier", "implemenation": "implementation",
    "implementaion": "implementation", "implmentation": "implementation",
    "independant": "independent", "indeces": "indices", "indexs": "indexes",
    "informations": "information", "inital": "initial", "initalize": "initialize",
    "initialise": "initialize", "instace": "instance", "instanciate": "instantiate",
    "intepreter": "interpreter", "interator": "iterator", "interupt": "interrupt",
    "invalidt": "invalid", "iterface": "interface", "lable": "label",
    "langauge": "language", "lenght": "length", "lengeth": "length", "libary": "library",
    "librarie": "library", "lisence": "license", "lsit": "list", "mantain": "maintain",
    "mesage": "message", "messge": "message", "mispelled": "misspelled",
    "mispell": "misspell", "modul": "module", "mroe": "more", "muliple": "multiple",
    "multipe": "multiple", "neccesary": "necessary", "neccessary": "necessary",
    "necesary": "necessary", "nessesary": "necessary", "noly": "only", "nubmer": "number",
    "occassion": "occasion", "occurance": "occurrence", "occurances": "occurrences",
    "occurrance": "occurrence", "occurrances": "occurrences", "occured": "occurred",
    "occurence": "occurrence", "occurences": "occurrences", "occuring": "occurring",
    "ocurrance": "occurrence", "ommitted": "omitted", "opimize": "optimize",
    "orginal": "original", "otherwize": "otherwise", "overriden": "overridden",
    "paramater": "parameter", "parameteres": "parameters", "paramter": "parameter",
    "parametes": "parameters", "parmeter": "parameter", "particulary": "particularly",
    "perfom": "perform", "performace": "performance", "permision": "permission",
    "persistant": "persistent", "poistion": "position", "posible": "possible",
    "positon": "position", "possibilty": "possibility", "prefered": "preferred",
    "prefrence": "preference", "prevert": "prevent", "priviledge": "privilege",
    "probaly": "probably", "procesing": "processing", "programing": "programming",
    "propery": "property", "propertly": "properly", "propeties": "properties",
    "provinding": "providing", "psuedo": "pseudo", "publically": "publicly",
    "quering": "querying", "questoin": "question", "recieve": "receive",
    "recieved": "received", "recomend": "recommend", "recomended": "recommended",
    "refered": "referred", "refering": "referring", "refernce": "reference",
    "reguar": "regular", "relevent": "relevant", "remebmer": "remember",
    "remove'": "remove", "repalce": "replace", "repeatly": "repeatedly",
    "represention": "representation", "requred": "required", "requries": "requires",
    "resposible": "responsible", "reproducable": "reproducible", "retreive": "retrieve",
    "retrive": "retrieve", "reult": "result", "sepcify": "specify",
    "seperate": "separate", "seperated": "separated", "seperately": "separately",
    "seperator": "separator", "sepcial": "special", "shoud": "should",
    "similiar": "similar", "simmilar": "similar", "sould": "should",
    "specifiy": "specify", "specifing": "specifying", "splited": "split",
    "sptring": "string", "strig": "string", "stirng": "string", "sucess": "success",
    "sucessful": "successful", "sucessfully": "successfully", "sufficent": "sufficient",
    "supress": "suppress", "supported'": "supported", "surpport": "support",
    "targetting": "targeting", "teh": "the", "tehn": "then", "thae": "the",
    "thats": "that's", "themselfs": "themselves", "thier": "their", "threshhold": "threshold",
    "throught": "through", "tiem": "time", "tmie": "time", "transfered": "transferred",
    "transformaton": "transformation", "trasform": "transform", "tuple'": "tuple",
    "unecessary": "unnecessary", "unfortunatly": "unfortunately", "unkown": "unknown",
    "unsuported": "unsupported", "untill": "until", "usefull": "useful",
    "usualy": "usually", "varaible": "variable", "variabel": "variable",
    "verison": "version", "wether": "whether", "wich": "which", "wierd": "weird",
    "wiht": "with", "wnat": "want", "wont": "won't", "wrapp": "wrap",
    "writen": "written", "yeild": "yield", "yorself": "yourself",
    "ect": "etc", "erturn": "return", "adn": "and", "nad": "and", "tot": "to",
    "th": "the", "fo": "of", "ot": "to", "si": "is", "od": "of",
    "prevet": "prevent", "conitnuos": "continuous", "continuos": "continuous",
    "contiguos": "contiguous", "obect": "object", "objet": "object",
    "arguments'": "arguments", "atleast": "at least", "inbetween": "in between",
}


def _dedupe(seq):
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# ---------------------------------------------------------------------------
# kind 0 : single character edits (typos, punctuation, off-by-one operators)
# ---------------------------------------------------------------------------

_CHARSET_SMALL = "abcdefghijklmnopqrstuvwxyz0123456789 _.,:;'\"()[]{}=+-*/%<>!\\"


def _act_char(line):
    out = []
    n = len(line)
    if n == 0 or n > 900:
        return out
    cs = _CHARSET if n <= 260 else _CHARSET_SMALL
    for i in range(n):
        out.append(line[:i] + line[i + 1:])
    for i in range(n - 1):
        if line[i] != line[i + 1]:
            out.append(line[:i] + line[i + 1] + line[i] + line[i + 2:])
    for i in range(n):
        pre = line[:i]
        post = line[i + 1:]
        orig = line[i]
        for ch in cs:
            if ch != orig:
                out.append(pre + ch + post)
    for i in range(n + 1):
        pre = line[:i]
        post = line[i:]
        for ch in cs:
            out.append(pre + ch + post)
    # doubling / undoubling a character
    for i in range(n):
        out.append(line[:i] + line[i] * 2 + line[i + 1:])
    return out


# ---------------------------------------------------------------------------
# kind 1 : word / prose level edits
# ---------------------------------------------------------------------------

def _corrections(w):
    res = []
    low = w.lower()
    for key in (low,):
        if key in _MISSPELL:
            res.append(_MISSPELL[key])
    if low.endswith("s") and low[:-1] in _MISSPELL:
        res.append(_MISSPELL[low[:-1]] + "s")
    if low.endswith("es") and low[:-2] in _MISSPELL:
        res.append(_MISSPELL[low[:-2]] + "es")
    if low.endswith("ing") and low[:-3] in _MISSPELL:
        res.append(_MISSPELL[low[:-3]] + "ing")
    if low.endswith("ed") and low[:-2] in _MISSPELL:
        res.append(_MISSPELL[low[:-2]] + "ed")
    fixed = []
    for r in res:
        if w[:1].isupper():
            fixed.append(r[:1].upper() + r[1:])
        else:
            fixed.append(r)
        fixed.append(r)
    return _dedupe(fixed)


def _act_word(line):
    out = []
    toks = [(m.start(), m.end()) for m in _TOKEN_RE.finditer(line)]
    if len(toks) > 60:
        toks = toks[:60]

    for m in _ALPHA_RE.finditer(line):
        for cand in _corrections(m.group(0)):
            out.append(line[:m.start()] + cand + line[m.end():])

    for (s, e) in toks:
        for w in _INSERT_WORDS:
            out.append(line[:s] + w + " " + line[s:])
    if toks:
        s, e = toks[-1]
        for w in _INSERT_WORDS:
            out.append(line[:e] + " " + w + line[e:])

    for (s, e) in toks:
        if e < len(line) and line[e] == " ":
            out.append(line[:s] + line[e + 1:])
        if s > 0 and line[s - 1] == " ":
            out.append(line[:s - 1] + line[e:])
        out.append(line[:s] + line[e:])

    for i in range(len(toks) - 1):
        a, b = toks[i], toks[i + 1]
        out.append(line[:a[0]] + line[b[0]:b[1]] + line[a[1]:b[0]] +
                   line[a[0]:a[1]] + line[b[1]:])

    # duplicated word removal
    for i in range(len(toks) - 1):
        a, b = toks[i], toks[i + 1]
        if line[a[0]:a[1]] == line[b[0]:b[1]]:
            out.append(line[:a[0]] + line[b[0]:])

    # a / an
    for m in re.finditer(r"\ba\b", line):
        out.append(line[:m.start()] + "an" + line[m.end():])
    for m in re.finditer(r"\ban\b", line):
        out.append(line[:m.start()] + "a" + line[m.end():])

    # replace a whole word with a common short word
    for (s, e) in toks:
        w = line[s:e]
        for r in _INSERT_WORDS:
            if r != w:
                out.append(line[:s] + r + line[e:])

    # morphological variants of each alphabetic word
    for m in _ALPHA_RE.finditer(line):
        w = m.group(0)
        s, e = m.start(), m.end()
        low = w.lower()
        vs = []
        for (a, b) in _SUFFIX_SWAPS:
            if low.endswith(a) and len(low) > len(a):
                vs.append(w[:len(w) - len(a)] + b)
        if len(w) > 2:
            vs.append(w + "s")
            vs.append(w + "es")
            vs.append(w + "d")
            vs.append(w + "ed")
            vs.append(w + "ing")
            vs.append(w + "ly")
            if w.endswith("s"):
                vs.append(w[:-1])
            if w.endswith("es"):
                vs.append(w[:-2])
            if w.endswith("ed"):
                vs.append(w[:-2])
                vs.append(w[:-1])
            if w.endswith("ing"):
                vs.append(w[:-3])
                vs.append(w[:-3] + "e")
            # doubled consonant before a suffix
            for suf in ("ed", "ing", "er", "es"):
                if low.endswith(suf) and len(low) > len(suf) + 1:
                    stem = w[:len(w) - len(suf)]
                    vs.append(stem + stem[-1] + suf)
                    if len(stem) > 2 and stem[-1] == stem[-2]:
                        vs.append(stem[:-1] + suf)
        vs.append(w.lower())
        vs.append(w.upper())
        vs.append(w[:1].upper() + w[1:])
        vs.append(w[:1].lower() + w[1:])
        for v in _dedupe(vs):
            if v != w:
                out.append(line[:s] + v + line[e:])

    return out


# ---------------------------------------------------------------------------
# kind 2 : import statement fixes
# ---------------------------------------------------------------------------

def _act_import(line):
    out = []
    st = line.lstrip()
    ind = line[:len(line) - len(st)]
    tail = ""
    body = st
    m = re.match(r"^(.*?)(\s*#.*)$", st)
    if m:
        body, tail = m.group(1), m.group(2)

    m = re.match(r"^from\s+(\.*)([\w\.]*)\s+import\s+(.*)$", body)
    if m:
        dots, mod, rest = m.group(1), m.group(2), m.group(3)
        for d in ("", ".", "..", "..."):
            if d != dots:
                out.append(ind + "from %s%s import %s" % (d, mod, rest) + tail)
        if mod:
            out.append(ind + "from . import %s" % mod + tail)
            out.append(ind + "from .. import %s" % mod + tail)
            out.append(ind + "import %s" % mod + tail)
        if "." in mod:
            head, _sep, last = mod.rpartition(".")
            out.append(ind + "from %s%s import %s" % (dots, head, last) + tail)
            out.append(ind + "from .%s import %s" % (head, rest) + tail)
        if "(" not in rest:
            out.append(ind + "from %s%s import (%s)" % (dots, mod, rest) + tail)
        for name in [n.strip() for n in rest.split(",")]:
            if name and name != rest.strip():
                out.append(ind + "from %s%s import %s" % (dots, mod, name) + tail)

    m2 = re.match(r"^import\s+([\w\.]+)(?:\s+as\s+(\w+))?$", body)
    if m2:
        mod, alias = m2.group(1), m2.group(2)
        out.append(ind + "from . import %s" % mod + tail)
        out.append(ind + "from .. import %s" % mod + tail)
        out.append(ind + "import %s" % mod + tail)
        if "." in mod:
            head, _sep, last = mod.rpartition(".")
            out.append(ind + "from %s import %s" % (head, last) + tail)
            out.append(ind + "from .%s import %s" % (head, last) + tail)
            out.append(ind + "import %s as %s" % (mod, last) + tail)
        if not alias:
            out.append(ind + "import %s as %s" % (mod, mod.rpartition(".")[2]) + tail)
    return out


# ---------------------------------------------------------------------------
# kind 3 : add a missing argument / element at every position of every call
# ---------------------------------------------------------------------------

def _act_add_arg(line):
    out = []
    spans = _callspans(line)
    if not spans:
        return out
    names = [n for n in _idents(line) if n not in _KEYWORDS]
    vocab = _dedupe(names + _ARG_VOCAB)
    kwargs = []
    _KWNAMES = ["default", "key", "value", "count", "months", "follow", "sep",
                "encoding", "reverse", "strict", "precision", "format", "gender",
                "plural", "number", "base", "size", "start", "end", "limit",
                "case", "flags", "name", "func", "num", "index", "word"]
    for kn in _KWNAMES:
        for kv in ("None", "True", "False", "0", "1", "''", '""'):
            kwargs.append(kn + "=" + kv)
    for kn in _KWNAMES + names:
        for kv in names:
            kwargs.append(kn + "=" + kv)
    for kv in names:
        kwargs.append(kv + "=" + kv)
    kwargs = _dedupe(kwargs)
    for (ns, o, c, op, name) in spans:
        content = line[o + 1:c]
        parts = _split_args(content)
        if not parts:
            for v in vocab + kwargs:
                out.append(line[:o + 1] + v + line[c:])
            continue
        # append after last argument
        for v in vocab:
            out.append(line[:c] + ", " + v + line[c:])
            out.append(line[:c] + "," + v + line[c:])
        for v in kwargs:
            out.append(line[:c] + ", " + v + line[c:])
        # insert before the first argument
        p0 = o + 1 + parts[0][0]
        for v in vocab:
            out.append(line[:p0] + v + ", " + line[p0:])
        # insert between arguments
        for idx in range(len(parts) - 1):
            pos = o + 1 + parts[idx][1]
            for v in vocab:
                out.append(line[:pos] + ", " + v + line[pos:])
        # duplicate an argument, possibly in a pluralised / negated form
        for (a, b) in parts:
            arg = content[a:b].strip()
            if not arg:
                continue
            out.append(line[:c] + ", " + arg + line[c:])
            variants = []
            m = re.match(r"^(['\"])(.*)\1$", arg)
            if m:
                q, body = m.group(1), m.group(2)
                variants += [q + body + "s" + q, q + body + "es" + q]
                if body.endswith("s"):
                    variants.append(q + body[:-1] + q)
            elif re.match(r"^[A-Za-z_][A-Za-z_0-9\.]*$", arg):
                variants += [arg + "s", "_" + arg, arg + "_"]
                if arg.endswith("s"):
                    variants.append(arg[:-1])
            for v in variants:
                out.append(line[:c] + ", " + v + line[c:])
                p0 = o + 1 + parts[0][0]
                out.append(line[:p0] + v + ", " + line[p0:])
    return out


# ---------------------------------------------------------------------------
# kind 4 : replace / remove / reorder arguments and identifiers
# ---------------------------------------------------------------------------

def _act_swap_names(line):
    out = []
    names = [n for n in _idents(line) if n not in _KEYWORDS]
    vocab = _dedupe(names + _NAME_VOCAB)

    for (s, e, w) in _ident_positions(line):
        local = ["_" + w, w + "_", w + "s", w.upper(), w.lower(),
                 w[:1].upper() + w[1:], "_" + w + "_", "self." + w, "cls." + w,
                 w + "()", "__" + w + "__"]
        if w.endswith("s"):
            local.append(w[:-1])
        if w.startswith("_") and len(w) > 1:
            local.append(w[1:])
        for v in vocab + local:
            if v != w:
                out.append(line[:s] + v + line[e:])

    # replace every occurrence at once
    for w in names:
        for v in vocab:
            if v != w:
                out.append(re.sub(r"\b" + re.escape(w) + r"\b", v, line))

    # argument level replace / remove / reorder
    for (ns, o, c, op, name) in _callspans(line):
        content = line[o + 1:c]
        parts = _split_args(content)
        if not parts:
            continue
        for (a, b) in parts:
            abs_a, abs_b = o + 1 + a, o + 1 + b
            s2, e2 = _trim_span(line, abs_a, abs_b)
            for v in vocab:
                out.append(line[:s2] + v + line[e2:])
        if len(parts) > 1:
            for idx in range(len(parts)):
                a, b = parts[idx]
                if idx == len(parts) - 1:
                    new = content[:parts[idx - 1][1]] + content[b:]
                else:
                    new = content[:a] + content[parts[idx + 1][0]:]
                out.append(line[:o + 1] + new + line[c:])
            for idx in range(len(parts) - 1):
                a1, b1 = parts[idx]
                a2, b2 = parts[idx + 1]
                new = (content[:a1] + content[a2:b2] + content[b1:a2] +
                       content[a1:b1] + content[b2:])
                out.append(line[:o + 1] + new + line[c:])
        else:
            out.append(line[:o + 1] + line[c:])
    return out


# ---------------------------------------------------------------------------
# kind 5 : wrap an expression in a call
# ---------------------------------------------------------------------------

def _act_wrap(line):
    out = []
    strs, groups, comment = _scan(line)
    end = comment if comment is not None else len(line)

    for (s, e) in _expr_targets(line):
        text = line[s:e]
        if not text:
            continue
        grouping = (text[0] == "(" and text[-1] == ")" and
                    (s == 0 or not (line[s - 1].isalnum() or line[s - 1] == "_")))
        inner = text[1:-1] if grouping else text
        for f in _WRAP_UNARY:
            if grouping:
                out.append(line[:s] + f + text + line[e:])
            else:
                out.append(line[:s] + f + "(" + text + ")" + line[e:])
        for (pre, post) in _WRAP_BINARY:
            out.append(line[:s] + pre + inner + post + line[e:])
        # parenthesise
        if not grouping:
            out.append(line[:s] + "(" + text + ")" + line[e:])
        else:
            out.append(line[:s] + inner + line[e:])
    return out


# ---------------------------------------------------------------------------
# kind 6 : open() / encoding fixes
# ---------------------------------------------------------------------------

def _act_open(line):
    out = []
    for (ns, o, c, op, name) in _callspans(line):
        if not name or name.split(".")[-1] != "open":
            continue
        content = line[o + 1:c]
        after = line[c + 1:]
        head = line[:ns]
        for mode in ("'rb'", '"rb"', "'r'", '"r"', "'rt'", '"rt"'):
            out.append(head + name + "(" + content + ", " + mode + ")" + after)
        for enc in ("encoding='utf-8'", 'encoding="utf-8"', "encoding='utf8'",
                    'encoding="utf8"', "encoding='UTF-8'", 'encoding="UTF-8"'):
            out.append(head + name + "(" + content + ", " + enc + ")" + after)
        for mode in ("'r'", '"r"', "'rb'", '"rb"'):
            for enc in ("encoding='utf-8'", 'encoding="utf-8"'):
                out.append(head + name + "(" + content + ", " + mode + ", " + enc + ")" + after)
        # open(...).read()  ->  open(..., 'rb').read().decode('utf-8')
        if after.startswith(".read()"):
            rest = after[len(".read()"):]
            for mq in ("'", '"'):
                for dq in ("'", '"'):
                    out.append(head + name + "(" + content + ", " + mq + "rb" + mq +
                               ").read().decode(" + dq + "utf-8" + dq + ")" + rest)
            for enc in ("encoding='utf-8'", 'encoding="utf-8"'):
                out.append(head + name + "(" + content + ", " + enc + ").read()" + rest)
            for dq in ("'", '"'):
                out.append(head + name + "(" + content + ").read().decode(" +
                           dq + "utf-8" + dq + ")" + rest)
        for mod in ("io.open", "codecs.open"):
            out.append(head + mod + "(" + content + ")" + after)
            out.append(head + mod + "(" + content + ", encoding='utf-8')" + after)
            out.append(head + mod + "(" + content + ', encoding="utf-8")' + after)
    return out


# ---------------------------------------------------------------------------
# kind 7 : append a method call / turn a literal into a call
# ---------------------------------------------------------------------------

def _act_method(line):
    out = []
    strs, groups, comment = _scan(line)

    for (s, e) in _expr_targets(line):
        text = line[s:e]
        if not text:
            continue
        for meth in _METHOD_APPEND:
            out.append(line[:e] + meth + line[e:])

    # literal -> constructor call
    for (s, e) in strs:
        lit = line[s:e]
        body = lit[1:-1] if len(lit) >= 2 else ""
        if body == "":
            for repl in ("cls()", "str()", "self.__class__()", "type(self)()",
                         "bytes()", "b''", 'b""', "u''", 'u""'):
                out.append(line[:s] + repl + line[e:])
        for pre in ("r", "f", "b", "u", "rb", "br"):
            out.append(line[:s] + pre + lit + line[e:])
        if lit[0] == "'":
            out.append(line[:s] + '"' + lit[1:-1] + '"' + line[e:])
        elif lit[0] == '"':
            out.append(line[:s] + "'" + lit[1:-1] + "'" + line[e:])

    for m in re.finditer(r"(?<![\w\]\)])\[\]", line):
        out.append(line[:m.start()] + "list()" + line[m.end():])
    for m in re.finditer(r"(?<![\w\]\)])\{\}", line):
        out.append(line[:m.start()] + "dict()" + line[m.end():])
        out.append(line[:m.start()] + "set()" + line[m.end():])
    return out


# ---------------------------------------------------------------------------
# kind 8 : operator and token swaps
# ---------------------------------------------------------------------------

def _act_tokens(line):
    out = []
    for (a, b) in _TOKEN_SWAPS:
        start = 0
        while True:
            i = line.find(a, start)
            if i < 0:
                break
            out.append(line[:i] + b + line[i + len(a):])
            start = i + 1
        if a in line:
            out.append(line.replace(a, b))
    for (a, b) in _WORD_SWAPS:
        pat = re.compile(r"\b" + re.escape(a) + r"\b")
        for m in pat.finditer(line):
            out.append(line[:m.start()] + b + line[m.end():])
        if pat.search(line):
            out.append(pat.sub(b, line))
    return out


# ---------------------------------------------------------------------------
# kind 9 : numeric literals and off by one
# ---------------------------------------------------------------------------

def _act_numbers(line):
    out = []
    for m in _NUM_RE.finditer(line):
        try:
            val = int(m.group(1))
        except ValueError:
            continue
        for nv in (val + 1, val - 1, 0, 1, 2, -val, val * 10, val // 10 if val >= 10 else val):
            if nv != val:
                out.append(line[:m.start(1)] + str(nv) + line[m.end(1):])
    for (s, e) in _expr_targets(line):
        text = line[s:e]
        if not text or len(text) > 60:
            continue
        for suf in (" + 1", " - 1", "+1", "-1", " * 2", " / 2", " // 2", " % 2"):
            out.append(line[:e] + suf + line[e:])
    # float / integer division
    for m in re.finditer(r"(?<![/])/(?![/=])", line):
        out.append(line[:m.start()] + "//" + line[m.end():])
    # subscript and slice edits
    for (ns, o, c, op, name) in _callspans(line):
        if op != "[":
            continue
        content = line[o + 1:c]
        news = [content + ":", ":" + content, content + " - 1", content + " + 1",
                content + "-1", content + "+1", "-" + content,
                "0", "1", "-1", "2", ":", ":-1", "1:", ":1", "::-1", "0:",
                content + ":" + content]
        if ":" in content:
            a, _s, b = content.partition(":")
            news += [b + ":" + a, a.strip() + ":", ":" + b.strip(), a, b]
        for nw in news:
            out.append(line[:o + 1] + nw + line[c:])
    return out


# ---------------------------------------------------------------------------
# kind 10 : string literal / format string edits
# ---------------------------------------------------------------------------

def _act_strings(line):
    out = []
    strs, groups, comment = _scan(line)
    for (s, e) in strs:
        lit = line[s:e]
        if len(lit) < 2:
            continue
        q = lit[0]
        body = lit[1:-1]
        for new in (body + " ", " " + body, body.strip(), body + "\\n", body + ".",
                    body + ":", body.rstrip("."), body + "s", body.rstrip("s")):
            if new != body:
                out.append(line[:s] + q + new + q + line[e:])
        for a, b in (("%s", "%d"), ("%d", "%s"), ("%s", "%r"), ("%i", "%d"),
                     ("%d", "%i"), ("{}", "{0}"), ("{0}", "{}")):
            if a in body:
                out.append(line[:s] + q + body.replace(a, b) + q + line[e:])
    # swap two string literals
    if len(strs) >= 2:
        for i in range(len(strs) - 1):
            (s1, e1), (s2, e2) = strs[i], strs[i + 1]
            out.append(line[:s1] + line[s2:e2] + line[e1:s2] + line[s1:e1] + line[e2:])
    # %s -> %d inside a call plus a .replace() to convert back
    for (ns, o, c, op, name) in _callspans(line):
        if not name:
            continue
        seg = line[ns:c + 1]
        for a, b in (("%s", "%d"), ("%d", "%s")):
            if a in seg:
                new = seg.replace(a, b)
                for q in ('"', "'"):
                    out.append(line[:ns] + new + ".replace(%s%s%s, %s%s%s)" %
                               (q, b, q, q, a, q) + line[c + 1:])
                out.append(line[:ns] + new + line[c + 1:])
    # whole line quote style flip
    if "'" in line and '"' not in line:
        out.append(line.replace("'", '"'))
    if '"' in line and "'" not in line:
        out.append(line.replace('"', "'"))
    return out


# ---------------------------------------------------------------------------
# kind 11 : negation and truth value fixes
# ---------------------------------------------------------------------------

def _act_negation(line):
    out = []
    for m in re.finditer(r"(?:(?<=^)|(?<=[\s(\[{:,=]))"
                         r"(if|elif|while|return|assert|and|or|not|in|is|yield|else)\s+", line):
        out.append(line[:m.end()] + "not " + line[m.end():])
    for m in re.finditer(r"[=(,]\s*", line):
        out.append(line[:m.end()] + "not " + line[m.end():])
    for m in re.finditer(r"\bnot\s+", line):
        out.append(line[:m.start()] + line[m.end():])
    for (s, e) in _expr_targets(line):
        text = line[s:e]
        if not text or len(text) > 80:
            continue
        out.append(line[:s] + "not " + text + line[e:])
        out.append(line[:s] + "not (" + text + ")" + line[e:])
        out.append(line[:s] + text + " is None" + line[e:])
        out.append(line[:s] + text + " is not None" + line[e:])
        out.append(line[:s] + "bool(" + text + ")" + line[e:])
        for tail in (" or None", " or 0", " or 1", " or ''", ' or ""', " or []",
                     " or {}", " or default", " or self", " and None", " and default",
                     " if x else y", " is None", " != None"):
            out.append(line[:e] + tail + line[e:])
    for a, b in (("is None", "is not None"), ("is not None", "is None"),
                 ("== None", "is None"), ("!= None", "is not None"),
                 (" is ", " == "), (" == ", " is ")):
        if a in line:
            out.append(line.replace(a, b, 1))
            out.append(line.replace(a, b))
    return out


# ---------------------------------------------------------------------------
# kind 12 : structural line edits
# ---------------------------------------------------------------------------

def _act_struct(line):
    out = []
    st = line.lstrip()
    ind = line[:len(line) - len(st)]

    # indentation
    for extra in ("    ", "        ", "\t"):
        out.append(extra + line)
    for n in (4, 8):
        if line.startswith(" " * n):
            out.append(line[n:])
    if line.startswith("\t"):
        out.append(line[1:])

    # self. / cls. prefixing
    for (s, e, w) in _ident_positions(line):
        if w in _KEYWORDS:
            continue
        if s >= 1 and line[s - 1] == ".":
            continue
        out.append(line[:s] + "self." + line[s:])
        out.append(line[:s] + "cls." + line[s:])
    for m in re.finditer(r"\bself\.", line):
        out.append(line[:m.start()] + line[m.end():])
    for m in re.finditer(r"\bcls\.", line):
        out.append(line[:m.start()] + line[m.end():])

    # subscript <-> .get()
    for (ns, o, c, op, name) in _callspans(line):
        content = line[o + 1:c]
        if op == "[" and name:
            out.append(line[:ns] + name + ".get(" + content + ")" + line[c + 1:])
            out.append(line[:ns] + name + ".get(" + content + ", None)" + line[c + 1:])
        if op == "(" and name.endswith(".get"):
            base = name[:-4]
            parts = _split_args(content)
            if parts:
                first = content[parts[0][0]:parts[0][1]].strip()
                out.append(line[:ns] + base + "[" + first + "]" + line[c + 1:])
        # trailing comma inside the bracket
        if content.strip() and not content.rstrip().endswith(","):
            out.append(line[:c] + "," + line[c:])

    # attribute <-> item access
    for m in re.finditer(r"\.([A-Za-z_][A-Za-z_0-9]*)", line):
        out.append(line[:m.start()] + '["' + m.group(1) + '"]' + line[m.end():])
        out.append(line[:m.start()] + "['" + m.group(1) + "']" + line[m.end():])

    # default values for parameters on a def line
    if st.startswith("def ") or st.startswith("async def ") or st.startswith("lambda"):
        for (ns, o, c, op, name) in _callspans(line):
            if op != "(":
                continue
            content = line[o + 1:c]
            parts = _split_args(content)
            for (a, b) in parts:
                arg = content[a:b].strip()
                if not arg or "=" in arg or arg.startswith("*"):
                    continue
                for dv in ("None", "False", "True", "0", "1", "''", '""', "()", "[]", "{}"):
                    new = content[:b] + "=" + dv + content[b:]
                    out.append(line[:o + 1] + new + line[c:])

    # trailing comma / colon on the statement
    code_end = _code_end(line)
    body = line[:code_end].rstrip()
    tail = line[len(body):]
    if body:
        if body.endswith(","):
            out.append(body[:-1] + tail)
        else:
            out.append(body + "," + tail)
        if body.endswith(":"):
            out.append(body[:-1] + tail)
        if body.endswith(")"):
            out.append(body + ":" + tail)
        out.append(body + tail.rstrip())
        out.append(body.rstrip() + tail)

    # strip / add outer parens on a return
    m = re.match(r"^(\s*)(return|yield)\s+\((.*)\)\s*$", line)
    if m:
        out.append("%s%s %s" % (m.group(1), m.group(2), m.group(3)))
    m = re.match(r"^(\s*)(return|yield)\s+(.*?)\s*$", line)
    if m:
        out.append("%s%s (%s)" % (m.group(1), m.group(2), m.group(3)))
        out.append("%s%s %s," % (m.group(1), m.group(2), m.group(3)))

    # comment marker fixes
    if st.startswith("#") and not st.startswith("# "):
        out.append(ind + "# " + st[1:])

    # whitespace normalisation
    out.append(line.rstrip())
    out.append(re.sub(r"[ ]{2,}", " ", line))
    out.append(re.sub(r"\s*,\s*", ", ", line))
    out.append(re.sub(r"(?<![=!<>+\-*/%&|^])=(?![=])", " = ", line))
    out.append(re.sub(r"\s+=\s+", "=", line))

    # python 2 -> 3 idioms
    m = re.match(r"^(\s*)except\s+([\w\.\(\), ]+?),\s*(\w+)\s*:(.*)$", line)
    if m:
        out.append("%sexcept %s as %s:%s" % (m.group(1), m.group(2), m.group(3), m.group(4)))
    m = re.match(r"^(\s*)print\s+(?!\()(.*?)\s*$", line)
    if m:
        out.append("%sprint(%s)" % (m.group(1), m.group(2)))
    m = re.match(r"^(\s*)raise\s+(\w+),\s*(.*?)\s*$", line)
    if m:
        out.append("%sraise %s(%s)" % (m.group(1), m.group(2), m.group(3)))
    for m in re.finditer(r"\.has_key\(", line):
        pass
    m = re.match(r"^(\s*)(.*?)\.has_key\((.*)\)(.*)$", line)
    if m:
        out.append("%s%s in %s%s" % (m.group(1), m.group(3), m.group(2), m.group(4)))
    for m in re.finditer(r"(?<![\w])[ubUB](['\"])", line):
        out.append(line[:m.start()] + line[m.start() + 1:])

    # swap the operands of a binary operator
    for m in re.finditer(r"([A-Za-z_][\w\.]*|\d+)\s*(\*\*|//|[-+*/%]|[<>=!]=|[<>]|\band\b|\bor\b|\bin\b)\s*"
                         r"([A-Za-z_][\w\.]*|\d+)", line):
        out.append(line[:m.start()] + "%s %s %s" % (m.group(3), m.group(2), m.group(1)) +
                   line[m.end():])
    return out


_ACTS = [
    _act_char,       # 0
    _act_word,       # 1
    _act_import,     # 2
    _act_add_arg,    # 3
    _act_swap_names, # 4
    _act_wrap,       # 5
    _act_open,       # 6
    _act_method,     # 7
    _act_tokens,     # 8
    _act_numbers,    # 9
    _act_strings,    # 10
    _act_negation,   # 11
    _act_struct,     # 12
]

N_KINDS = len(_ACTS)


# ---------------------------------------------------------------------------
# funcy specific knowledge: this project's own vocabulary and idioms.
#
# The recurring shapes in this repo's history are
#   * one funcy helper swapped for its sibling   (izip -> interleave,
#     make_pred -> make_func, map -> lmap, walk_keys -> walk_values, ...)
#   * a receiver / identifier replaced by another name already on the line
#     (timedelta.total_seconds() -> period.total_seconds(),  *key -> *args)
#   * a forgotten trailing argument               (iffy(bool, pred, default))
#   * a decorator used bare instead of called     (@wraps -> @wraps(func))
#   * a hardcoded type replaced by a type preserving one (''.join -> cls().join)
#   * py2/py3 iteration helpers, EMPTY sentinels, l-prefixed list variants
#   * prose typos in comments, docstrings and the readme
# ---------------------------------------------------------------------------

_FUNCY_VOCAB = _dedupe("""
identity constantly caller partial rpartial func_partial curry rcurry autocurry
compose rcompose complement juxt ljuxt iffy all_fn any_fn none_fn one_fn some_fn
empty iteritems itervalues iterkeys join merge join_with merge_with walk walk_keys
walk_values select select_keys select_values compact is_distinct all any none one
some zipdict flip project omit zip_values zip_dicts get_in get_lax set_in update_in
del_in has_path where lwhere pluck lpluck pluck_attr lpluck_attr invoke
count cycle repeat repeatedly iterate take drop first second nth last rest butlast
ilen map filter lmap lfilter remove lremove keep lkeep without lwithout concat
lconcat chain cat lcat flatten lflatten mapcat lmapcat interleave interpose distinct
ldistinct split lsplit split_at lsplit_at split_by lsplit_by group_by group_by_keys
group_values count_by count_reps partition lpartition chunks lchunks partition_by
lpartition_by with_prev with_next pairwise lzip reductions lreductions sums lsums
accumulate takewhile dropwhile ltakewhile ldropwhile izip imap ifilter ifilterfalse
izip_longest zip_longest xrange
isa is_mapping is_set is_list is_tuple is_seq is_iter is_seqcont is_seqcoll iterable
decorator wraps unwrap ContextDecorator Call get_argnames arggetter get_spec Spec
make_func make_pred
raiser ignore silent suppress nullcontext reraise retry fallback limit_error_rate
ErrorRateExceeded throttle post_processing collecting joining once once_per
once_per_arg wrap_with
re_iter re_all re_find re_finder re_test re_tester str_join cut_prefix cut_suffix
cached_property cached_readonly wrap_prop monkey LazyObject
tap log_calls print_calls log_enters print_enters log_exits print_exits log_errors
print_errors log_durations print_durations log_iter_durations print_iter_durations
memoize make_lookuper silent_lookuper cache SkipMemory CacheMemory
isnone notnone inc dec even odd
EMPTY PY2 PY3 str_types basestring unicode _factory _multi_dict_iter func_types
text_type string_types xmap xfilter xzip xsplit lsplit_at Iterator
Iterator Mapping Sequence Set defaultdict OrderedDict namedtuple deque islice
len list tuple set dict sorted reversed enumerate zip range next iter getattr
setattr hasattr isinstance issubclass callable type str int bool float object
""".split())

_FUNCY_GENERIC = [
    "func", "f", "g", "pred", "seq", "seqs", "coll", "colls", "args", "kwargs",
    "default", "key", "value", "n", "x", "self", "cls", "call", "EMPTY", "None",
    "True", "False", "obj", "attr", "name", "keys", "values", "mapping", "result",
    "item", "items", "sep", "d", "acc", "i", "k", "v", "step", "size", "start",
    "stop", "period", "timeout", "errors", "exceptions", "memory", "wrapper",
    "flags", "attr", "path", "prop", "spec", "tries", "count", "regex", "s",
    "deco", "callback", "memo", "text", "line", "node", "tree", "amount",
]

_FUNCY_WRAP = [
    "list", "iter", "tuple", "set", "dict", "lmap", "lfilter", "lkeep", "lcat",
    "make_func", "make_pred", "_factory", "empty", "identity", "constantly",
    "complement", "silent", "autocurry", "curry", "next", "first", "last", "len",
    "sorted", "str_join", "join", "merge", "cat", "flatten", "compact", "distinct",
    "ilen", "bool", "callable", "isa", "int", "str", "frozenset", "reversed",
    "iteritems", "itervalues", "iterkeys", "text_type", "xmap", "xfilter", "lzip",
    "repeat", "cycle", "unwrap", "get_spec", "arggetter", "type",
]

_DECORATOR_NAMES = [
    "wraps", "decorator", "memoize", "cache", "retry", "throttle", "once",
    "silent", "collecting", "joining", "post_processing", "log_calls",
    "print_calls", "monkey", "wrap_prop", "cached_property", "contextmanager",
]

_STAR_ARGS = ["*args", "**kwargs", "*seqs", "*colls", "*dicts", "*fs", "*preds"]


def _name_variants(w):
    """Sibling names this project would plausibly have meant instead of `w`."""
    vs = []
    if not w:
        return vs
    for p in ("l", "i", "r", "x", "_", "is_", "make_", "re_", "un", "not_", "__"):
        vs.append(p + w)
        if w.startswith(p) and len(w) > len(p):
            vs.append(w[len(p):])
    for suf in ("_by", "_with", "_keys", "_values", "_in", "_at", "_fn", "_attr",
                "s", "es", "_iter", "_seq", "_", "__"):
        vs.append(w + suf)
        if w.endswith(suf) and len(w) > len(suf):
            vs.append(w[:-len(suf)])
    for a, b in (("pred", "func"), ("func", "pred"), ("keys", "values"),
                 ("values", "keys"), ("key", "value"), ("value", "key"),
                 ("first", "last"), ("last", "first"), ("map", "filter"),
                 ("filter", "map"), ("left", "right"), ("right", "left"),
                 ("min", "max"), ("max", "min"), ("get", "set"), ("set", "get"),
                 ("log_", "print_"), ("print_", "log_"), ("join", "merge"),
                 ("merge", "join"), ("take", "drop"), ("drop", "take"),
                 ("select", "omit"), ("omit", "select"), ("_by", "_with"),
                 ("_with", "_by"), ("iter", ""), ("all", "any"), ("any", "all"),
                 ("seq", "coll"), ("coll", "seq"), ("args", "kwargs")):
        if a in w:
            vs.append(w.replace(a, b))
            vs.append(w.replace(a, b, 1))
    vs.append(w.replace("_", ""))
    vs.append(w.lower())
    vs.append(w.upper())
    vs.append(w[:1].upper() + w[1:])
    return _dedupe([v for v in vs if v and v != w])


# ---------------------------------------------------------------------------
# kind 13 : swap an identifier for a funcy sibling / another name on the line
# ---------------------------------------------------------------------------

def _act_funcy_names(line):
    out = []
    on_line = [n for n in _idents(line) if n not in _KEYWORDS]
    pos = _ident_positions(line)
    if not pos:
        return out
    near = _dedupe(on_line + _FUNCY_GENERIC)
    counts = {}
    for (s, e, w) in pos:
        counts[w] = counts.get(w, 0) + 1

    # pass 1 : names already present on the line (and the usual funcy spellings)
    for (s, e, w) in pos:
        for v in near:
            if v != w:
                out.append(line[:s] + v + line[e:])
    # pass 2 : sibling spellings of that very name
    for (s, e, w) in pos:
        for v in _name_variants(w):
            out.append(line[:s] + v + line[e:])
    # pass 3 : the whole funcy vocabulary
    for (s, e, w) in pos:
        for v in _FUNCY_VOCAB:
            if v != w:
                out.append(line[:s] + v + line[e:])
    # pass 4 : rename every occurrence of a repeated name at once
    for w in _dedupe([w for (s, e, w) in pos]):
        if counts.get(w, 0) < 2:
            continue
        pat = re.compile(r"\b" + re.escape(w) + r"\b")
        for v in near + _name_variants(w) + _FUNCY_VOCAB:
            if v != w:
                out.append(pat.sub(v, line))
    # pass 5 : dotted names -- change the receiver, drop / add an attribute
    for m in re.finditer(r"\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)", line):
        recv, attr = m.group(1), m.group(2)
        for v in near:
            if v != recv:
                out.append(line[:m.start()] + v + "." + attr + line[m.end():])
        out.append(line[:m.start()] + attr + line[m.end():])
        out.append(line[:m.start()] + recv + line[m.end():])
        for v in _name_variants(attr):
            out.append(line[:m.start()] + recv + "." + v + line[m.end():])
    return out


# ---------------------------------------------------------------------------
# kind 14 : funcy idioms -- decorators, star args, EMPTY, type preservation
# ---------------------------------------------------------------------------

def _act_funcy_struct(line):
    out = []
    code_end = _code_end(line)
    body = line[:code_end]
    tail = line[code_end:]
    st = line.strip()
    names = [n for n in _idents(line) if n not in _KEYWORDS]
    spans = _callspans(line)
    strs, groups, comment = _scan(line)

    # --- a list of quoted names (__all__ and friends) gains / renames a member
    quoted = [(s, e) for (s, e) in strs
              if re.match(r"^(['\"])[A-Za-z_]\w*\1$", line[s:e])]
    if quoted and (len(quoted) >= 2 or "__all__" in line):
        q = line[quoted[0][0]]
        for (s, e) in quoted[:6]:
            for nm in _FUNCY_VOCAB:
                out.append(line[:e] + ", " + q + nm + q + line[e:])
        s0 = quoted[0][0]
        for nm in _FUNCY_VOCAB:
            out.append(line[:s0] + q + nm + q + ", " + line[s0:])
        for (s, e) in quoted[:8]:
            w = line[s + 1:e - 1]
            for nm in _name_variants(w):
                out.append(line[:s] + q + nm + q + line[e:])

    # --- a bare decorator should have been called
    m = re.match(r"^(\s*)@([A-Za-z_][\w\.]*)\s*$", body.rstrip())
    if m:
        di, dn = m.group(1), m.group(2)
        for a in ("func", "f", "call", "cls", "self", "wrapper", "fn", "g",
                  "method", "", "*args", "**kwargs", "func, cls", "func, EMPTY"):
            out.append("%s@%s(%s)%s" % (di, dn, a, tail))
        if "." in dn:
            out.append("%s@%s%s" % (di, dn.rpartition(".")[2], tail))
        else:
            for pre in ("functools.", "self.", "cls."):
                out.append("%s@%s%s%s" % (di, pre, dn, tail))
        for nm in _DECORATOR_NAMES:
            out.append("%s@%s%s" % (di, nm, tail))
            out.append("%s@%s(func)%s" % (di, nm, tail))
    m = re.match(r"^(\s*)@([A-Za-z_][\w\.]*)\((.*)\)\s*$", body.rstrip())
    if m:
        out.append("%s@%s%s" % (m.group(1), m.group(2), tail))

    # --- star / double star on an argument
    for (ns, o, c, op, name) in spans:
        content = line[o + 1:c]
        for (a, b) in _split_args(content):
            s2, e2 = _trim_span(line, o + 1 + a, o + 1 + b)
            if e2 <= s2:
                continue
            arg = line[s2:e2]
            if arg.startswith("**"):
                out.append(line[:s2] + arg[1:] + line[e2:])
                out.append(line[:s2] + arg[2:] + line[e2:])
            elif arg.startswith("*"):
                out.append(line[:s2] + "*" + arg + line[e2:])
                out.append(line[:s2] + arg[1:] + line[e2:])
            else:
                out.append(line[:s2] + "*" + arg + line[e2:])
                out.append(line[:s2] + "**" + arg + line[e2:])

    # --- a funcy flavoured argument was forgotten
    extra = _dedupe(["default", "EMPTY", "func", "f", "pred", "seq", "seqs", "coll",
                     "colls", "call", "self", "cls", "n", "key", "value", "None",
                     "0", "1", "-1", "True", "False", "()", "[]", "{}",
                     "default=EMPTY", "default=None", "follow=False", "strict=False",
                     "key=None"] + _STAR_ARGS + names + _FUNCY_GENERIC)
    for (ns, o, c, op, name) in spans:
        content = line[o + 1:c]
        parts = _split_args(content)
        if content.strip() and parts:
            p0 = o + 1 + parts[0][0]
            for v in extra:
                out.append(line[:c] + ", " + v + line[c:])
                out.append(line[:p0] + v + ", " + line[p0:])
            for idx in range(len(parts) - 1):
                pos = o + 1 + parts[idx][1]
                for v in extra[:12]:
                    out.append(line[:pos] + ", " + v + line[pos:])
        else:
            for v in extra:
                out.append(line[:o + 1] + v + line[c:])

    # --- wrap in / unwrap a funcy call
    for (s, e) in _expr_targets(line)[:14]:
        text = line[s:e]
        if not text or len(text) > 120:
            continue
        for f in _FUNCY_WRAP:
            out.append(line[:s] + f + "(" + text + ")" + line[e:])
    for (ns, o, c, op, name) in spans:
        if name and op == "(":
            content = line[o + 1:c]
            out.append(line[:ns] + content + line[c + 1:])
            for f in _FUNCY_WRAP:
                if f != name:
                    out.append(line[:ns] + f + "(" + content + ")" + line[c + 1:])

    # --- python 2 / 3 iteration helpers
    for m in re.finditer(r"([A-Za-z_][\w\.]*)\."
                         r"(items|keys|values|iteritems|iterkeys|itervalues)\(\)", line):
        recv, meth = m.group(1), m.group(2)
        base = meth.replace("iter", "")
        for fn in ("iteritems", "itervalues", "iterkeys"):
            out.append(line[:m.start()] + fn + "(" + recv + ")" + line[m.end():])
        for mm in ("items", "keys", "values", "iteritems", "iterkeys", "itervalues"):
            if mm != meth:
                out.append(line[:m.start()] + recv + "." + mm + "()" + line[m.end():])
        out.append(line[:m.start()] + "list(" + recv + "." + base + "())" + line[m.end():])
    for m in re.finditer(r"\b(iteritems|itervalues|iterkeys)\(([^()]*)\)", line):
        fn, arg = m.group(1), m.group(2)
        base = fn.replace("iter", "")
        out.append(line[:m.start()] + arg + "." + base + "()" + line[m.end():])
        out.append(line[:m.start()] + arg + "." + fn + "()" + line[m.end():])

    # --- EMPTY sentinel
    for a, b in (("None", "EMPTY"), ("EMPTY", "None"), ("is None", "is EMPTY"),
                 ("is EMPTY", "is None"), ("== EMPTY", "is EMPTY"),
                 ("== None", "is None")):
        if a in line:
            out.append(line.replace(a, b, 1))
            out.append(line.replace(a, b))

    # --- parameter defaults on a def / lambda
    if re.match(r"^\s*(async\s+)?def\s", body) or "lambda" in body:
        for (ns, o, c, op, name) in spans:
            if op != "(":
                continue
            content = line[o + 1:c]
            for (a, b) in _split_args(content):
                s2, e2 = _trim_span(line, o + 1 + a, o + 1 + b)
                base = line[s2:e2]
                if not base or base.startswith("*"):
                    continue
                nm = base.split("=")[0].strip()
                for dv in ("EMPTY", "None", "False", "True", "0", "1", "()", "[]",
                           "{}", "''", '""', "identity", "bool", "1.0"):
                    out.append(line[:s2] + nm + "=" + dv + line[e2:])
                if "=" in base:
                    out.append(line[:s2] + nm + line[e2:])

    # --- type checks
    for (ns, o, c, op, name) in spans:
        if name.split(".")[-1] not in ("isinstance", "issubclass"):
            continue
        content = line[o + 1:c]
        parts = _split_args(content)
        if len(parts) < 2:
            continue
        s2, e2 = _trim_span(line, o + 1 + parts[-1][0], o + 1 + parts[-1][1])
        cur = line[s2:e2]
        for t in ("str_types", "basestring", "(list, tuple)", "Iterator", "Mapping",
                  "Set", "Sequence", "(int, float)", "dict", "list", "tuple", "set",
                  "type", "func_types", "(" + cur + ", tuple)", "(" + cur + ",)",
                  "(" + cur + ", list)", "(" + cur + ", str)"):
            if t != cur:
                out.append(line[:s2] + t + line[e2:])
        f0, f1 = _trim_span(line, o + 1 + parts[0][0], o + 1 + parts[0][1])
        first = line[f0:f1]
        for pn in ("is_mapping", "is_set", "is_list", "is_tuple", "is_seq", "is_iter",
                   "is_seqcont", "is_seqcoll", "iterable", "callable", "isnone",
                   "notnone", "isa(" + cur + ")"):
            out.append(line[:ns] + pn + "(" + first + ")" + line[c + 1:])

    # --- a nested pair of calls collapses into one helper (list(map()) -> lmap())
    for (ns, o, c, op, name) in spans:
        if op != "(" or not name:
            continue
        content = line[o + 1:c].strip()
        if len(_split_args(content)) != 1:
            continue
        m2 = re.match(r"^([A-Za-z_][\w\.]*)\((.*)\)$", content)
        if not m2:
            continue
        inner = m2.group(2)
        for v in _FUNCY_VOCAB:
            out.append(line[:ns] + v + "(" + inner + ")" + line[c + 1:])
        out.append(line[:ns] + m2.group(1) + "(" + inner + ")" + line[c + 1:])

    # --- version strings get bumped
    for m in re.finditer(r"(?<![\w.])(\d+)\.(\d+)(\.(\d+))?(?![\w.])", line):
        maj, mnr = int(m.group(1)), int(m.group(2))
        pat = m.group(4)
        news = ["%d.%d" % (maj, mnr + 1), "%d.%d" % (maj + 1, 0),
                "%d.%d.1" % (maj, mnr), "%d.%d.0" % (maj, mnr),
                "%d.%d" % (maj, mnr - 1 if mnr else 0)]
        if pat is not None:
            p = int(pat)
            news += ["%d.%d.%d" % (maj, mnr, p + 1), "%d.%d" % (maj, mnr),
                     "%d.%d.0" % (maj, mnr + 1)]
        for nv in news:
            if nv != m.group(0):
                out.append(line[:m.start()] + nv + line[m.end():])

    # --- type preserving constructions
    for (ns, o, c, op, name) in spans:
        if not name or not name.endswith(".join"):
            continue
        recv = name[:-len(".join")]
        content = line[o + 1:c]
        for r in ("cls()", "self.__class__()", "type(colls[0])()", "empty(colls[0])",
                  "_factory(colls[0])()", "''", '""', "text_type()", "str()",
                  "b''", "sep", "self.sep"):
            if r != recv:
                out.append(line[:ns] + r + ".join(" + content + ")" + line[c + 1:])
        out.append(line[:ns] + "str_join(" + content + ")" + line[c + 1:])
        out.append(line[:ns] + "str_join(" + recv + ", " + content + ")" + line[c + 1:])
    return out


# ---------------------------------------------------------------------------
# kind 15 : conditions gain a conjunct, brackets move, receivers change
# ---------------------------------------------------------------------------

def _act_cond_paren(line):
    out = []
    code_end = _code_end(line)
    body = line[:code_end]
    tail = line[code_end:]
    names = [n for n in _idents(line) if n not in _KEYWORDS]
    strs, groups, comment = _scan(line)

    atoms = ["None", "True", "False", "default", "EMPTY"]
    for n in names[:8]:
        atoms += [n, "not " + n, n + " is not None", n + " is None",
                  "callable(" + n + ")", n + " is not EMPTY", "len(" + n + ")"]
    atoms = _dedupe(atoms)

    # --- a condition was missing a conjunct
    m = re.match(r"^(\s*)(if|elif|while|assert)\s+(.*?)(\s*:)?\s*$", body)
    if m and m.group(3):
        ind, kw, cond = m.group(1), m.group(2), m.group(3)
        colon = m.group(4) or ""
        for a in atoms:
            out.append("%s%s %s and %s%s%s" % (ind, kw, cond, a, colon, tail))
            out.append("%s%s %s or %s%s%s" % (ind, kw, cond, a, colon, tail))
            out.append("%s%s %s and not %s%s%s" % (ind, kw, cond, a, colon, tail))
            out.append("%s%s %s and %s%s%s" % (ind, kw, a, cond, colon, tail))
            out.append("%s%s %s%s%s" % (ind, kw, a, colon, tail))
        out.append("%s%s (%s)%s%s" % (ind, kw, cond, colon, tail))
        out.append("%s%s not (%s)%s%s" % (ind, kw, cond, colon, tail))

    # --- a returned / assigned expression was missing a conjunct or a fallback
    for m in re.finditer(r"(?:(?<=^)|(?<=[\s(\[{,]))(return|yield)\s+", body):
        rest = body[m.end():].rstrip()
        if not rest:
            continue
        for a in atoms[:24]:
            out.append(body[:m.end()] + rest + " and " + a + tail)
            out.append(body[:m.end()] + rest + " or " + a + tail)
            out.append(body[:m.end()] + rest + " if " + a + " else None" + tail)
    m = re.search(r"(?<![=!<>+\-*/%&|^~])=(?!=)", body)
    if m:
        rhs = body[m.end():].strip()
        if rhs:
            for a in atoms[:24]:
                out.append(body[:m.end()] + " " + rhs + " or " + a + tail)
                out.append(body[:m.end()] + " " + rhs + " and " + a + tail)

    # --- a bracket sits in the wrong place
    for (o, c, op) in groups:
        if c >= code_end:
            continue
        cl = {"(": ")", "[": "]", "{": "}"}[op]
        # close it later
        for p in range(c + 1, code_end + 1):
            if p == code_end or line[p] in ",)]}":
                out.append(line[:c] + line[c + 1:p] + cl + line[p:])
        # close it earlier, at a top level comma of its own content
        content = line[o + 1:c]
        for (a, b) in _split_args(content):
            p = o + 1 + b
            if o < p < c:
                out.append(line[:p] + cl + line[p:c] + line[c + 1:])
        # open it earlier / later
        j = o
        while j > 0 and (line[j - 1].isalnum() or line[j - 1] in "_."):
            j -= 1
        for q in range(0, j):
            if line[q] in "(,[{ " and q + 1 < o:
                out.append(line[:q + 1] + op + line[q + 1:o] + line[o + 1:])
        for (a, b) in _split_args(content):
            p = o + 1 + a
            if o < p < c:
                out.append(line[:o] + line[o + 1:p] + op + line[p:])

    # --- the receiver of a method call is wrong
    for (ns, o, c, op, name) in _callspans(line):
        if op != "(" or "." not in name:
            continue
        recv, _sep, meth = name.rpartition(".")
        content = line[o + 1:c]
        parts = _split_args(content)
        if len(parts) == 1 and content.strip():
            out.append(line[:ns] + content.strip() + "." + meth + "(" + recv + ")" +
                       line[c + 1:])
        for r in _dedupe(names + ["self", "cls", "cls()", "self.__class__()",
                                  "type(self)()", "''", '""', "EMPTY", "func",
                                  "self." + meth.lstrip("_")]):
            if r != recv:
                out.append(line[:ns] + r + "." + meth + "(" + content + ")" +
                           line[c + 1:])
        for v in _name_variants(meth):
            out.append(line[:ns] + recv + "." + v + "(" + content + ")" + line[c + 1:])
        out.append(line[:ns] + meth + "(" + recv +
                   ((", " + content) if content.strip() else "") + ")" + line[c + 1:])

    # --- a bare name should have been called, or a call should not have been
    for (s, e, w) in _ident_positions(line):
        if w in _KEYWORDS:
            continue
        nxt = line[e:e + 1]
        if nxt not in ("(", "[", "."):
            for a in ("", "func", "self", "cls", "call", "*args", "**kwargs", "seq"):
                out.append(line[:e] + "(" + a + ")" + line[e:])
    for (ns, o, c, op, name) in _callspans(line):
        if name and op == "(" and not line[o + 1:c].strip():
            out.append(line[:o] + line[c + 1:])
    return out


_EXTRA_ACTS = [
    _act_funcy_names,   # 13
    _act_funcy_struct,  # 14
    _act_cond_paren,    # 15
]

_ALL_ACTS = _ACTS + _EXTRA_ACTS
_TOTAL_KINDS = len(_ALL_ACTS)


# ---------------------------------------------------------------------------
# kind 0 helper: single character edits, most plausible ones first
# ---------------------------------------------------------------------------

_LOWER = "abcdefghijklmnopqrstuvwxyz"


def _char_candidates(line):
    out = []
    n = len(line)
    if n == 0 or n > 900:
        return out
    for i in range(n):
        out.append(line[:i] + line[i + 1:])
    for i in range(n - 1):
        if line[i] != line[i + 1]:
            out.append(line[:i] + line[i + 1] + line[i] + line[i + 2:])
    for i in range(n):
        out.append(line[:i] + line[i] * 2 + line[i + 1:])
    for i in range(n):
        c = line[i]
        if c.isalpha():
            alpha = _LOWER if c.islower() else _LOWER.upper()
            for ch in alpha:
                if ch != c:
                    out.append(line[:i] + ch + line[i + 1:])
    for i in range(n):
        c = line[i]
        if c.isalpha():
            f = c.upper() if c.islower() else c.lower()
            out.append(line[:i] + f + line[i + 1:])
    for i in range(n + 1):
        for ch in _LOWER:
            out.append(line[:i] + ch + line[i:])
    for i in range(n + 1):
        for ch in " .,:;'\"()[]-_=*/#`|+<>!?%&":
            out.append(line[:i] + ch + line[i:])
    if n <= 200:
        out.extend(_act_char(line))
    return out


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

_CAPS = {0: 4200, 1: 2400, 3: 2800, 4: 2800, 5: 1800, 13: 3000, 14: 2600, 15: 1800}
_DEFAULT_CAP = 1500
_BUDGET = 10000

_STATE = {"line": None, "seen": set(), "left": _BUDGET}


def _reset(line):
    _STATE["line"] = line
    _STATE["seen"] = set([line])
    _STATE["left"] = _BUDGET
    try:
        strs, groups, comment = _scan(line)
        _STATE["prose"] = _is_prose(line, strs, comment)
    except Exception:
        _STATE["prose"] = False


def _kind_for_act(act):
    """Ask the router which kind this act number belongs to; never hardcoded."""
    for k in range(_TOTAL_KINDS):
        if router(WORKED_EXAMPLE[0], WORKED_EXAMPLE[1], k) == act:
            return k
    return None


def _is_prose(line, strs, comment):
    st = line.strip()
    if not st:
        return True
    if st.startswith("#"):
        return True
    if st.startswith("@") or st.startswith("from ") or st.startswith("import "):
        return False
    if " " not in st:
        return False
    code = line[:comment] if comment is not None else line
    outside = code
    for (s, e) in reversed(strs):
        if s < len(outside):
            outside = outside[:s] + " " * (min(e, len(outside)) - s) + outside[min(e, len(outside)):]
    if not re.search(r"[=()\[\]{}:;]|\b(def|class|return|import|from|if|for|while|lambda)\b",
                     outside):
        return True
    if re.match(r"^(\*|-|\d+\.|>|\||=+$|-+$|~+$)", st):
        return True
    return False


def observe(line):
    """Every fault kind this project makes, most plausible for `line` first."""
    if not isinstance(line, str):
        return list(range(_TOTAL_KINDS))
    _reset(line)
    strs, groups, comment = _scan(line)
    st = line.strip()
    prose = _is_prose(line, strs, comment)

    order = []

    def add(k, cond=True):
        if cond and k not in order:
            order.append(k)

    is_import = bool(re.match(r"^\s*(from|import)\s", line))
    is_decor = bool(re.match(r"^\s*@", st))
    is_def = bool(re.match(r"^\s*(async\s+)?(def|class)\s", line))
    is_cond = bool(re.match(r"^\s*(if|elif|while|assert)\b", st))
    has_open = "open(" in line
    has_str = bool(strs)
    has_call = any(True for (ns, o, c, op, nm) in _callspans(line) if nm)
    namelist = bool(re.search(r"['\"][A-Za-z_]\w*['\"]\s*,", line)) or "__all__" in line

    add(2, is_import)
    add(6, has_open)
    if is_decor:
        add(14)
        add(13)
        add(3)
    if prose:
        add(1)
        add(0)
        add(10, has_str)
        add(8)
        add(12)
    if namelist:
        add(14)
        add(10)
    if is_def:
        add(14)
        add(3)
        add(13)
        add(4)
    if is_cond:
        add(8)
        add(15)
        add(11)
        add(13)
    add(8)
    add(1, comment is not None)
    add(13)
    add(4)
    add(3)
    add(7, has_str or has_call)
    add(14)
    add(5)
    add(15)
    add(12)
    add(11)
    add(9)
    add(10, has_str)
    if comment is not None:
        add(1)
    for k in range(_TOTAL_KINDS):
        add(k)
    return order


def acts(line, act):
    out = []
    if not isinstance(line, str):
        return out
    kind = _kind_for_act(act)
    if kind is None:
        return out
    if _STATE["line"] != line:
        _reset(line)
    left = _STATE["left"]
    if left <= 0:
        return out
    cap = _CAPS.get(kind, _DEFAULT_CAP)
    if kind in (0, 1) and not _STATE.get("prose"):
        cap = 1300 if kind == 1 else 2600
    if cap > left:
        cap = left
    seen = _STATE["seen"]
    try:
        raw = _char_candidates(line) if kind == 0 else _ALL_ACTS[kind](line)
    except Exception:
        raw = []
    for c in raw:
        if type(c) is not str or c in seen:
            continue
        seen.add(c)
        out.append(c)
        if len(out) >= cap:
            break
    _STATE["left"] = left - len(out)
    return [c for c in out if c != line]

def candidates(line):
    for kind in observe(line):
        for c in acts(line, router(WORKED_EXAMPLE[0], WORKED_EXAMPLE[1], kind)):
            yield c
