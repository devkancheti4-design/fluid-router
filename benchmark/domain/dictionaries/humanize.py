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
# humanize specific material
#
# The recurring faults in this project, read off its own history:
#   * prose typos in docstrings / comments (single char edit, or a word from a
#     misspelling table)                       -> kinds 0, 1, 15
#   * wrong type name written in a docstring
#     ``when (datetime.timedelta)``            -> kinds 4, 15
#   * boundary operator off by one in a time
#     bucket ``3600 < x`` -> ``3600 <= x``     -> kind 8
#   * missing parenthesis so an arithmetic
#     chain overflows / loses precision
#     ``base * b / u`` -> ``base * (b / u)``   -> kind 13
#   * a domain guard is missing, added as a
#     trailing conditional expression
#     ``... if value != 0 else 0``             -> kind 14
#   * absolute import that must become relative -> kind 2
#   * a wrong element in an os.path.join       -> kind 4
# ---------------------------------------------------------------------------

_TYPE_VOCAB = [
    "str", "int", "float", "bool", "bytes", "list", "dict", "tuple", "set",
    "None", "object", "callable", "iterable", "sequence", "optional",
    "datetime.datetime", "datetime.timedelta", "datetime.date", "datetime.time",
    "datetime", "timedelta", "date", "time", "Number", "NumberOrString",
    "Decimal", "Any", "float | str", "int | float", "str | None", "int | None",
    "float | None", "bool | None", "list[str]", "dict[str, str]",
    "datetime.datetime | None", "datetime.timedelta | None",
]

# words this project keeps interchanging; every ordered pair inside a group is
# offered as a swap
_PROSE_GROUPS = [
    ["second", "seconds", "minute", "minutes", "hour", "hours", "day", "days",
     "week", "weeks", "month", "months", "year", "years", "microsecond",
     "microseconds", "millisecond", "milliseconds", "decade", "decades",
     "century", "centuries", "millennium"],
    ["yesterday", "today", "tomorrow", "now", "moment"],
    ["ago", "later", "from now", "hence"],
    ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
     "nine", "ten", "eleven", "twelve"],
    ["thousand", "million", "billion", "trillion", "quadrillion", "quintillion",
     "sextillion", "septillion", "octillion", "nonillion", "decillion",
     "googol"],
    ["Byte", "Bytes", "kB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB",
     "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB"],
    ["greater", "less", "fewer", "more", "larger", "smaller", "bigger",
     "longer", "shorter", "higher", "lower"],
    ["before", "after", "above", "below", "prior", "following"],
    ["first", "last", "next", "previous", "second"],
    ["minimum", "maximum", "smallest", "largest"],
    ["singular", "plural"],
    ["positive", "negative"],
    ["upper", "lower", "left", "right"],
    ["start", "end", "begin", "finish", "stop"],
    ["round", "truncate", "floor", "ceil", "clamp"],
    ["binary", "decimal", "metric", "gnu", "scientific"],
    ["true", "false"],
    ["past", "future", "present"],
    ["number", "value", "integer", "float", "string", "amount", "quantity"],
    ["returns", "return", "yields", "gives", "produces"],
    ["timedelta", "datetime", "date", "duration", "delta", "interval"],
    ["locale", "language", "translation", "localization"],
    ["suffix", "prefix", "separator", "delimiter", "unit"],
    ["abbreviation", "abbreviated", "expanded", "full", "short", "long"],
    ["naturaldelta", "naturaltime", "naturalday", "naturaldate", "naturalsize",
     "precisedelta", "intcomma", "intword", "apnumber", "fractional",
     "scientific", "ordinal", "metric", "clamp"],
    ["and", "or", "but", "if", "when", "while", "than", "then"],
    ["a", "an", "the", "this", "that", "each", "every", "any", "some"],
    ["is", "are", "was", "were", "be", "been", "has", "have", "had"],
    ["to", "of", "in", "on", "for", "with", "from", "by", "at", "into", "as"],
]

_EXTRA_MISSPELL = {
    "compatability": "compatibility", "compatabilty": "compatibility",
    "compatiblility": "compatibility", "compatabile": "compatible",
    "greather": "greater", "grater": "greater", "greatter": "greater",
    "transaltion": "translation", "trasnlation": "translation",
    "translaton": "translation", "tranlsation": "translation",
    "localiztion": "localization", "localisation": "localization",
    "internationalisation": "internationalization",
    "abbrevation": "abbreviation", "abreviation": "abbreviation",
    "aproximately": "approximately", "aproximate": "approximate",
    "approximatly": "approximately", "granuality": "granularity",
    "delimeter": "delimiter", "millenium": "millennium",
    "represenation": "representation", "representaion": "representation",
    "signficant": "significant", "signifcant": "significant",
    "precison": "precision", "presicion": "precision",
    "sepcified": "specified", "specifed": "specified",
    "specifiying": "specifying", "enviornment": "environment",
    "arbritrary": "arbitrary", "sucessive": "successive",
    "consequtive": "consecutive", "wheter": "whether", "wheather": "whether",
    "explicity": "explicitly", "implicity": "implicitly",
    "trucated": "truncated", "diffrence": "difference",
    "differance": "difference", "convertion": "conversion",
    "paramters": "parameters", "parmeters": "parameters",
    "arguemnts": "arguments", "retruns": "returns", "reutrns": "returns",
    "retrun": "return", "resturn": "return", "fucntion": "function",
    "fuction": "function", "fnuction": "function", "sting": "string",
    "stings": "strings", "vlaue": "value", "vaule": "value",
    "vaules": "values", "valeu": "value", "defualt": "default",
    "dfeault": "default", "singluar": "singular", "pural": "plural",
    "surpress": "suppress", "supressed": "suppressed",
    "supression": "suppression", "orderd": "ordered", "ordinial": "ordinal",
    "ordianl": "ordinal", "fromat": "format", "foramt": "format",
    "postion": "position", "postive": "positive", "posetive": "positive",
    "abosulte": "absolute", "aboslute": "absolute", "absoulte": "absolute",
    "timedetla": "timedelta", "timedleta": "timedelta", "datetiem": "datetime",
    "seonds": "seconds", "secons": "seconds", "sceonds": "seconds",
    "mintues": "minutes", "minuts": "minutes", "monthes": "months",
    "yeras": "years", "hous": "hours", "dyas": "days",
    "humanise": "humanize", "humanised": "humanized", "humanising": "humanizing",
    "seperator": "separator", "seperate": "separate", "seperated": "separated",
    "occurence": "occurrence", "occurences": "occurrences",
    "recieve": "receive", "recieves": "receives", "lenght": "length",
    "unkown": "unknown", "supress": "suppress", "wich": "which",
    "teh": "the", "hte": "the", "tha": "the", "taht": "that",
    "vs": "vs.", "ie": "i.e.", "eg": "e.g.", "etc": "etc.",
    "milisecond": "millisecond", "miliseconds": "milliseconds",
    "microsecods": "microseconds", "shold": "should", "wold": "would",
    "beacuse": "because", "diferent": "different", "verion": "version",
    "verions": "versions", "depricated": "deprecated",
    "depreciated": "deprecated", "backwrads": "backwards",
    "fallsback": "falls back", "fallback": "fall back",
    "iterrable": "iterable", "callabe": "callable", "keyowrd": "keyword",
    "keywrod": "keyword", "modle": "module", "packge": "package",
    "instal": "install", "usefull": "useful", "sucessfully": "successfully",
}

_SYM_OPS = ("**", "//", "<<", ">>", "==", "!=", "<=", ">=",
            "+", "-", "*", "/", "%", "<", ">", "&", "|", "^")

_CLOSER = {"(": ")", "[": "]", "{": "}"}


def _top_ops(s):
    """Top level binary operators of `s` as (start, end, text).

    Returns None when `s` is not a plain expression (contains a comma, a
    colon, an assignment, or a keyword we do not model).
    """
    out = []
    depth = 0
    q = None
    i = 0
    n = len(s)
    last_end = 0
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
            i += 1
            continue
        if ch in ")]}":
            depth -= 1
            if depth < 0:
                return None
            i += 1
            continue
        if depth == 0:
            if ch in ",;:":
                return None
            if ch == "#":
                break
            if ch == "=" and s[i:i + 2] != "==" and (
                    i == 0 or s[i - 1] not in "=!<>+-*/%&|^~"):
                return None
            matched = None
            for op in _SYM_OPS:
                if s.startswith(op, i):
                    matched = op
                    break
            if matched:
                if s[i + len(matched):i + len(matched) + 1] == "=":
                    return None
                prev = s[last_end:i].strip()
                if prev:
                    out.append((i, i + len(matched), matched))
                    last_end = i + len(matched)
                i += len(matched)
                continue
            m = re.match(r"(and|or|in|is|not|if|else|for|lambda|yield)\b", s[i:])
            if m and (i == 0 or not (s[i - 1].isalnum() or s[i - 1] == "_")):
                w = m.group(1)
                if w in ("and", "or"):
                    if s[last_end:i].strip():
                        out.append((i, i + len(w), w))
                        last_end = i + len(w)
                    i += len(w)
                    continue
                return None
        i += 1
    if depth != 0:
        return None
    return out


def _boundary_positions(line):
    """Positions where a bracket could plausibly begin or end."""
    strs, groups, comment = _scan(line)
    end = comment if comment is not None else len(line)
    body = line[:end]
    pos = set()
    for m in re.finditer(r"[A-Za-z_][A-Za-z_0-9\.]*|\d+(?:\.\d+)?|[)\]}]", body):
        if _in_spans(m.start(), strs):
            continue
        pos.add(m.start())
        pos.add(m.end())
    for (s, e) in strs:
        if s < end:
            pos.add(s)
            pos.add(e)
    pos.add(len(body.rstrip()))
    return sorted(p for p in pos if 0 <= p <= end)


def _top_spans(line):
    """The one or two spans a maintainer would treat as `the expression`."""
    end = _code_end(line)
    body = line[:end]
    out = []
    st = body.strip()
    if not st:
        return out
    ind = len(body) - len(body.lstrip())
    stop = len(body.rstrip())
    out.append((ind, stop))
    if body.rstrip().endswith(":"):
        out.append((ind, stop - 1))
    m = re.match(r"^(\s*[A-Za-z_][\w\.]*(?:\[[^\]]*\])?"
                 r"(?:\s*:\s*[^=]+?)?\s*=\s*)(\S.*?)\s*$", body)
    if m:
        out.append((m.end(1), m.end(2)))
    m = re.match(r"^(\s*(?:return|yield|assert|raise|del|await|elif|if|while|"
                 r"not|in)\s+)(\S.*?)\s*$", body)
    if m:
        s2, e2 = m.end(1), m.end(2)
        if body[:e2].rstrip().endswith(":"):
            out.append((s2, len(body[:e2].rstrip()) - 1))
        out.append((s2, e2))
    res = []
    for (s, e) in out:
        s, e = _trim_span(line, s, e)
        if e > s and (s, e) not in res:
            res.append((s, e))
    return res


def _guard_names(line):
    skip = set(_KEYWORDS) | {
        "int", "str", "float", "bool", "len", "abs", "round", "math", "re",
        "os", "sys", "format", "print", "min", "max", "sum", "list", "dict",
        "tuple", "set", "type", "isinstance", "datetime", "time",
    }
    names = []
    for n in _idents(line):
        if n in skip or n.isupper():
            continue
        names.append(n)
    if not names:
        names = [n for n in _idents(line) if n not in _KEYWORDS]
    return names[:6]


# ---------------------------------------------------------------------------
# kind 13 : operator precedence, parenthesisation, moving a bracket
# ---------------------------------------------------------------------------

def _act_precedence(line):
    out = []
    end = _code_end(line)
    if end == 0 or end > 400:
        return out

    seen = set()
    for (s, e) in _expr_targets(line)[:26]:
        text = line[s:e]
        if not text or len(text) > 200 or (s, e) in seen:
            continue
        seen.add((s, e))
        ops = _top_ops(text)
        if not ops:
            continue
        bounds = []
        prev = 0
        for (a, b, t) in ops:
            bounds.append((prev, a))
            prev = b
        bounds.append((prev, len(text)))
        tr = []
        for (a, b) in bounds:
            while a < b and text[a] in " \t":
                a += 1
            while b > a and text[b - 1] in " \t":
                b -= 1
            if b > a:
                tr.append((a, b))
        if len(tr) < 2:
            continue
        tr = tr[:7]
        for i in range(len(tr)):
            for j in range(i, len(tr)):
                a = tr[i][0]
                b = tr[j][1]
                seg = text[a:b]
                pre = line[:s] + text[:a]
                post = text[b:] + line[e:]
                out.append(pre + "(" + seg + ")" + post)
                for f in ("float", "int", "abs", "round"):
                    out.append(pre + f + "(" + seg + ")" + post)
        # drop a redundant pair of brackets around an operand
        for (a, b) in tr:
            seg = text[a:b]
            if len(seg) > 2 and seg[0] == "(" and seg[-1] == ")":
                out.append(line[:s] + text[:a] + seg[1:-1] + text[b:] + line[e:])

    # move an existing bracket
    strs, groups, comment = _scan(line)
    stops = _boundary_positions(line)
    if len(stops) <= 40:
        for (o, c, op) in groups[:8]:
            cl = _CLOSER.get(op, ")")
            if c >= end:
                continue
            for p in stops:
                if c < p <= end:
                    out.append(line[:c] + line[c + 1:p] + cl + line[p:])
                if o < p < c:
                    out.append(line[:p] + cl + line[p:c] + line[c + 1:])
                if p < o:
                    out.append(line[:p] + op + line[p:o] + line[o + 1:])
    return out


# ---------------------------------------------------------------------------
# kind 14 : guards -- trailing conditional expressions and extra conjuncts
# ---------------------------------------------------------------------------

_COND_TMPL = [
    "%s", "not %s", "%s is None", "%s is not None", "%s != 0", "%s == 0",
    "%s > 0", "%s < 0", "%s >= 0", "%s <= 0", "%s != 1", "%s == 1",
    "abs(%s) > 0", "%s is not False", "isinstance(%s, str)",
    "isinstance(%s, int)",
]

_TERN_TMPL = [
    "%s != 0", "%s", "%s is not None", "%s > 0", "%s == 0", "%s is None",
    "not %s", "%s != 0.0",
]

_TERN_DEFAULT = ["0", "1", "None", "''", '""', "-1", "0.0", "value"]


def _act_condition(line):
    out = []
    end = _code_end(line)
    if end == 0 or end > 300:
        return out
    spans = _top_spans(line)
    if not spans:
        return out
    names = _guard_names(line)
    conds = []
    for v in names:
        for t in _COND_TMPL:
            conds.append(t % v)
    conds += ["True", "False", "None"]

    st = line[:end].strip()
    is_cond = bool(re.match(r"^(if|elif|while|assert)\b", st))

    for (s, e) in spans[:3]:
        text = line[s:e]
        if not text or len(text) > 160:
            continue
        for c in conds:
            out.append(line[:e] + " and " + c + line[e:])
            out.append(line[:e] + " or " + c + line[e:])
            out.append(line[:s] + c + " and " + line[s:])
            out.append(line[:s] + c + " or " + line[s:])
        if is_cond:
            out.append(line[:s] + "not (" + text + ")" + line[s + len(text):])
        # trailing conditional expression -- the humanize `metric(0)` shape
        for v in names:
            for t in _TERN_TMPL:
                cond = t % v
                for d in _TERN_DEFAULT:
                    out.append(line[:e] + " if " + cond + " else " + d + line[e:])
                out.append(line[:e] + " if " + cond + " else " + v + line[e:])
                out.append(line[:s] + "0 if " + cond + " else " + text + line[e:])
                out.append(line[:s] + "None if " + cond + " else " + text + line[e:])
    return out


# ---------------------------------------------------------------------------
# kind 15 : prose, docstring types and markup
# ---------------------------------------------------------------------------

def _act_docs(line):
    out = []
    if not line.strip() or len(line) > 600:
        return out

    words = [(m.start(), m.end(), m.group(0))
             for m in re.finditer(r"[A-Za-z_][A-Za-z_0-9']*", line)][:45]

    # project misspellings (including multi edit ones)
    for (s, e, w) in words:
        low = w.lower()
        cands = []
        if low in _EXTRA_MISSPELL:
            cands.append(_EXTRA_MISSPELL[low])
        if low in _MISSPELL:
            cands.append(_MISSPELL[low])
        for suf in ("s", "es", "d", "ed", "ing", "ly"):
            if low.endswith(suf) and low[:-len(suf)] in _EXTRA_MISSPELL:
                cands.append(_EXTRA_MISSPELL[low[:-len(suf)]] + suf)
        for c in cands:
            out.append(line[:s] + c + line[e:])
            if w[:1].isupper():
                out.append(line[:s] + c[:1].upper() + c[1:] + line[e:])

    # words this project interchanges
    for (s, e, w) in words:
        low = w.lower()
        for grp in _PROSE_GROUPS:
            if low in grp:
                for other in grp:
                    if other == low:
                        continue
                    out.append(line[:s] + other + line[e:])
                    if w[:1].isupper():
                        out.append(line[:s] + other[:1].upper() + other[1:] +
                                   line[e:])

    # replace a word with another word already on the line
    vocab = _dedupe([w for (_a, _b, w) in words])
    if len(vocab) <= 40:
        for (s, e, w) in words:
            for v in vocab:
                if v != w:
                    out.append(line[:s] + v + line[e:])

    # documented types:  ``when (datetime.timedelta):``  /  ``x: int``
    for m in re.finditer(r"\(([A-Za-z_][\w\.\[\], |]*)\)", line):
        cur = m.group(1)
        for t in _TYPE_VOCAB:
            if t != cur:
                out.append(line[:m.start()] + "(" + t + ")" + line[m.end():])
    for m in re.finditer(r"(->\s*|:\s*)([A-Za-z_][\w\.]*(?:\s*\|\s*[A-Za-z_][\w\.]*)*)",
                         line):
        cur = m.group(2)
        for t in _TYPE_VOCAB:
            if t != cur:
                out.append(line[:m.start(2)] + t + line[m.end(2):])
        out.append(line[:m.end(2)] + " | None" + line[m.end(2):])
        out.append(line[:m.start(2)] + "Optional[" + cur + "]" + line[m.end(2):])

    # docstring section headers
    for a in ("Args", "Returns", "Raises", "Yields", "Examples", "Example",
              "Note", "Notes", "Attributes", "Parameters"):
        if a + ":" in line:
            for b in ("Args", "Returns", "Raises", "Yields", "Examples",
                      "Note", "Attributes", "Parameters"):
                if b != a:
                    out.append(line.replace(a + ":", b + ":", 1))

    # markup
    if "`" in line:
        out.append(re.sub(r"(?<!`)`([^`\n]+)`(?!`)", r"``\1``", line))
        out.append(re.sub(r"``([^`\n]+)``", r"`\1`", line))
        for m in re.finditer(r"(?<!`)`([^`\n]+)`(?!`)", line):
            out.append(line[:m.start()] + "``" + m.group(1) + "``" + line[m.end():])
        for m in re.finditer(r"``([^`\n]+)``", line):
            out.append(line[:m.start()] + "`" + m.group(1) + "`" + line[m.end():])
            out.append(line[:m.start()] + "**" + m.group(1) + "**" + line[m.end():])
    for m in re.finditer(r"\*\*([^*\n]+)\*\*", line):
        out.append(line[:m.start()] + "*" + m.group(1) + "*" + line[m.end():])
        out.append(line[:m.start()] + "``" + m.group(1) + "``" + line[m.end():])
    for m in re.finditer(r"(?<![\*\w])\*([^*\s][^*\n]*)\*(?![\*\w])", line):
        out.append(line[:m.start()] + "**" + m.group(1) + "**" + line[m.end():])
        out.append(line[:m.start()] + "``" + m.group(1) + "``" + line[m.end():])
    for (s, e, w) in words[:30]:
        for (a, b) in (("`", "`"), ("``", "``"), ("*", "*"), ("**", "**"),
                       ("_", "_"), ('"', '"'), ("'", "'")):
            out.append(line[:s] + a + w + b + line[e:])

    # sentence level punctuation / capitalisation
    body = line.rstrip()
    tail = line[len(body):]
    if body:
        st = body.lstrip()
        ind = body[:len(body) - len(st)]
        for p in (".", ":", ",", "?", "!", ";"):
            if body.endswith(p):
                out.append(body[:-1] + tail)
                out.append(body[:-1] + "." + tail)
            else:
                out.append(body + p + tail)
        if st:
            out.append(ind + st[:1].upper() + st[1:] + tail)
            out.append(ind + st[:1].lower() + st[1:] + tail)
    return out


# --- extras folded into the kind they belong to ----------------------------

# the constants this library is made of: unit bases and calendar arithmetic
_NUM_VOCAB = [
    "0", "1", "2", "3", "4", "5", "6", "7", "9", "10", "11", "12", "13", "20",
    "24", "28", "29", "30", "31", "52", "59", "60", "61", "90", "99", "100",
    "128", "180", "300", "360", "365", "366", "500", "999", "1000", "1024",
    "3600", "3599", "3601", "7200", "86400", "1000000", "1048576",
    "10 ** 3", "10 ** 6", "1024 ** 2", "1e3", "1e6",
]

_STR_VOCAB = [
    '"%.1f"', "'%.1f'", '"%.2f"', "'%.2f'", '"%.0f"', '"%d"', "'%d'",
    '"%s"', "'%s'", '"%.3f"', '"%0.1f"', '"{:,}"', '"{}"',
    '""', "''", '" "', "' '", '", "', "', '", '"."', "'.'", '"-"', "'-'",
    '"a moment"', "'a moment'", '"now"', "'now'", '"ago"', "'ago'",
    '"from now"', "'from now'", '"Byte"', '"Bytes"', '"B"', '"kB"', '"KiB"',
    '"%d Byte"', '"%d Bytes"', '"%.1f %s"', "'%.1f %s'", '"%d %s"',
    '"yesterday"', '"today"', '"tomorrow"', '"and"', "'and'", '"or"',
]


# this library's own parameter and local names
_HZ_NAMES = [
    "value", "value_", "bytes_", "base", "unit", "units", "suffix", "suffixes",
    "exponent", "ret", "format", "binary", "gnu", "ndigits", "precision",
    "minimum_unit", "suppress", "months", "use_months", "when", "now", "tz",
    "future", "gender", "floor", "ceil", "floor_token", "ceil_token",
    "delta", "date", "dt", "seconds", "minutes", "hours", "days", "weeks",
    "years", "powers", "human_powers", "ordinal", "fraction", "numerator",
    "denominator", "whole_number", "locale", "path", "translation",
    "_translations", "items", "word", "sep", "prefix", "abbrev", "number",
    "num", "index", "text", "result", "parts", "total", "count",
]

_HZ_KWARGS = [
    "months=True", "months=False", 'minimum_unit="seconds"',
    "minimum_unit='seconds'", "when=None", "when=when", "now=now", "now=None",
    'format="%.1f"', "format='%.1f'", 'format="%.2f"', 'format="%0.2f"',
    "binary=False", "binary=True", "gnu=False", "gnu=True", "precision=3",
    "precision=2", "ndigits=None", "ndigits=0", "suppress=()", "suppress=[]",
    'gender="male"', "future=False", "future=True", "tz=None",
    "tz=datetime.timezone.utc", "locale=None", "path=None", "value=value",
    "use_months=True", "use_months=False", "abbrev=False",
    "floor=None", "ceil=None", "strict=False", "sep=', '",
]


def _extra_numbers(line):
    out = []
    if _code_end(line) == 0:
        return out
    for m in _NUM_RE.finditer(line):
        cur = m.group(1)
        for v in _NUM_VOCAB:
            if v != cur:
                out.append(line[:m.start(1)] + v + line[m.end(1):])
        # integer -> float, the shape that fixes this project's overflow and
        # truncation bugs
        for v in (cur + ".0", cur + ".", "float(" + cur + ")", cur + "_000"):
            out.append(line[:m.start(1)] + v + line[m.end(1):])
    for m in re.finditer(r"(?<![\w.])(\d+)\.(\d+)(?![\w.])", line):
        for v in _NUM_VOCAB:
            out.append(line[:m.start()] + v + line[m.end():])
        out.append(line[:m.start()] + m.group(1) + line[m.end():])
        out.append(line[:m.start()] + m.group(1) + ".0" + line[m.end():])
    return out


def _extra_names(line):
    """Replace an identifier with one of this project's own names."""
    out = []
    for (s, e, w) in _ident_positions(line)[:24]:
        for v in _HZ_NAMES:
            if v != w:
                out.append(line[:s] + v + line[e:])
    return out


def _extra_args(line):
    """Add one of this project's own keyword arguments to a call."""
    out = []
    for (ns, o, c, op, name) in _callspans(line)[:5]:
        if op != "(":
            continue
        content = line[o + 1:c]
        vocab = _HZ_KWARGS + _HZ_NAMES
        if not content.strip():
            for v in vocab:
                out.append(line[:o + 1] + v + line[c:])
            continue
        for v in vocab:
            out.append(line[:c] + ", " + v + line[c:])
        p0 = o + 1 + _split_args(content)[0][0]
        for v in vocab:
            out.append(line[:p0] + v + ", " + line[p0:])
    return out


def _extra_strings(line):
    out = []
    strs, groups, comment = _scan(line)
    for (s, e) in strs[:6]:
        cur = line[s:e]
        for v in _STR_VOCAB:
            if v != cur:
                out.append(line[:s] + v + line[e:])
    return out


_EXTRA = {
    3: _extra_args,
    4: _extra_names,
    9: _extra_numbers,
    10: _extra_strings,
}


_ALL_ACTS = _ACTS + [
    _act_precedence,  # 13
    _act_condition,   # 14
    _act_docs,        # 15
]


# ---------------------------------------------------------------------------
# observation: every kind is in play, ordered by how often this project makes
# that particular mistake on a line that looks like this one.
# ---------------------------------------------------------------------------

def _priority(line):
    end = _code_end(line)
    body = line[:end]
    st = line.strip()
    stc = body.strip()
    words = re.findall(r"[A-Za-z][A-Za-z']+", line)
    prose = len(words)
    code_marks = len(re.findall(r"[=(){}\[\]%<>+*/]|->", body))
    is_comment = st.startswith("#")
    is_import = bool(re.match(r"^\s*(from|import)\s", body))
    is_def = bool(re.match(r"^\s*(async\s+def|def|class)\b", stc))
    is_cond = bool(re.match(r"^\s*(if|elif|while|assert)\b", stc))
    is_stringy = ('"' in line or "'" in line)
    has_num = bool(_NUM_RE.search(body))
    has_call = "(" in body
    doclike = is_comment or (prose >= 4 and code_marks <= 2)

    p = {}
    # targeted kinds first: they are small and carry most of the hits
    p[1] = 92 if doclike else 70     # word level prose edits
    p[15] = 90 if doclike else 62    # docstring types, markup, project words
    p[8] = 88 if not doclike else 54  # operator / token swaps
    p[4] = 80 if not doclike else 58  # identifier and argument replacement
    p[9] = 74 if has_num else 50     # numeric literals, slices
    p[13] = 72 if code_marks >= 3 else 44   # precedence / parentheses
    p[12] = 68                       # structural line edits
    p[5] = 64 if not doclike else 34  # wrap an expression in a call
    p[10] = 62 if is_stringy else 30  # string / format literal edits
    p[11] = 58 if not doclike else 28  # negation and truth values
    p[14] = 56 if (is_cond or code_marks >= 2) else 26   # guards
    p[3] = 52 if has_call else 24    # add a missing argument
    p[7] = 46 if not doclike else 20  # append a method call
    p[2] = 96 if is_import else 8    # import fixes
    p[6] = 94 if "open(" in body else 6
    if is_def:
        p[3] += 12
        p[15] += 8
    if is_cond:
        p[8] += 6
    # the exhaustive single character sweep is emitted last: it is by far the
    # bulkiest kind, and most of what it finds (the project's docstring typos)
    # the targeted kinds above already name explicitly.
    p[0] = 1
    return p


def observe(line):
    """Fault kinds in play for `line`, most likely first.

    The kind space is contiguous from 0; every kind is offered because a
    surplus candidate is free while a missing one cannot be recovered.  The
    order is what carries the diagnosis.
    """
    if line is None:
        return []
    p = _priority(line)
    return sorted(range(len(_ALL_ACTS)), key=lambda k: (-p.get(k, 0), k))


def _kind_of(act):
    """Which kind does `act` serve?  Asked of the router, never written down."""
    for k in range(len(_ALL_ACTS)):
        if router(WORKED_EXAMPLE[0], WORKED_EXAMPLE[1], k) == act:
            return k
    return -1


def acts(line, act):
    """Every replacement line the act numbered `act` offers for `line`."""
    out = []
    try:
        kind = _kind_of(int(act))
    except Exception:
        return []
    if 0 <= kind < len(_ALL_ACTS):
        try:
            out = _ALL_ACTS[kind](line) or []
        except Exception:
            out = []
        extra = _EXTRA.get(kind)
        if extra is not None:
            try:
                out = out + (extra(line) or [])
            except Exception:
                pass
    return _dedupe([c for c in out if isinstance(c, str) and c != line])

def candidates(line):
    for kind in observe(line):
        for c in acts(line, router(WORKED_EXAMPLE[0], WORKED_EXAMPLE[1], kind)):
            yield c
