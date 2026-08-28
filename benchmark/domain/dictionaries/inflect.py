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


# ===========================================================================
# PROJECT SPECIALISATION -- inflect
#
# What this codebase actually keeps getting wrong (from its own history):
#
#   * regex source text.  inflect is mostly one giant pile of hand written
#     regex constants, many of them bare fragments living inside triple
#     quoted VERBOSE strings.  Fixes there are anchor / group / quantifier
#     edits on a fragment that is not even a Python token
#     (`(?! FJO | ...`  ->  `^(?! FJO | ...`).
#   * word form data.  huge tuples/dicts of singular|plural spellings; a fix
#     is one suffix on one literal ("child" -> "children", stem+"es").
#   * missing str() coercion around a number that may be an int or a Word
#     (`match(r"\d", num)` -> `match(r"\d", str(num))`).
#   * mutating-method-returns-None misuse
#     (`return [sign].append(numchunks)` -> `numchunks = [sign] + numchunks`).
#   * type annotation churn, usually together with dropping a `# noqa`
#     (`num: Union[int, Word]) -> str:  # noqa: C901` -> `num: Word) -> str:`).
#   * setup.py file handling: open() mode / encoding / filename.
# ===========================================================================

_NAME_VOCAB = _dedupe(_NAME_VOCAB + [
    "word", "words", "wordlist", "word_list", "count", "num", "number", "text",
    "sign", "numchunks", "chunks", "chunk", "lowered", "mo", "classical",
    "andword", "zero", "one", "decimal", "threshold", "comma", "group",
    "gender", "person", "plural", "singular", "stem", "suffix", "prefix",
    "pre", "post", "orig", "inflected", "result", "wantlist", "dollars",
    "cents", "ordinal", "article", "lowerword", "firstword", "lastword",
    "root", "space", "sep", "level", "mod", "hundreds", "tens", "units",
    "self.classical_dict", "self.persistent_count", "self.thegender",
    "words.lowered", "words.last", "words.first", "words.split",
    "value", "elem", "entry", "spelling", "form", "forms", "known",
])

_ARG_VOCAB = _dedupe(_ARG_VOCAB + [
    "word", "words", "num", "count", "text", "str(num)", "str(word)",
    "str(text)", "str(value)", "word.lower()", "text.lower()", "num.lower()",
    "count=None", "count=count", "num=num", "word=word", "text=text",
    "wantlist=True", "wantlist=False", "threshold=None", "andword=''",
    'andword=""', "andword='and'", "comma=','", "group=0", "group=1",
    "group=2", "group=3", "decimal='point'", "zero='zero'", "one='one'",
    "sep=', '", "sep=' '", "classical=True", "classical=False",
    "re.VERBOSE", "re.IGNORECASE", "flags=re.VERBOSE",
    "re.IGNORECASE | re.VERBOSE", "re.VERBOSE | re.IGNORECASE",
    "self", "self.classical_dict", "self.thegender", "gender", "plural",
    "singular", "0", "1", "-1", "-2", "-3", "2", "3",
])

_WRAP_UNARY = _dedupe(_WRAP_UNARY + [
    "str", "int", "float", "list", "tuple", "len", "enclose", "joinstem",
    "unicode", "text_type", "self.plural", "self.plural_noun",
    "self.plural_verb", "self.plural_adj", "self.singular_noun",
    "self.postprocess", "self.partition_word", "self._plnoun", "self._plverb",
    "self._pladj", "self.a", "self.an", "self.no", "self.num",
    "self.ordinal", "self.number_to_words", "self.inflect", "self.join",
    "self.compare", "self.word_list", "self._sinoun", "self.get_count",
    "Words", "Word", "re.escape", "re.compile", "next", "abs", "bool",
])

_METHOD_APPEND = _dedupe(_METHOD_APPEND + [
    ".lower()", ".upper()", ".strip()", ".title()", ".capitalize()",
    ".rstrip('s')", '.rstrip("s")', ".split('|')", '.split("|")',
    ".split(' ')", '.split(" ")', ".group(0)", ".group(1)", ".group(2)",
    ".groups()", ".start()", ".end()", ".span()", ".pop(0)", ".pop()",
    ".replace(' ', '')", ".replace(',', '')", '.replace(",", "")',
    ".replace('|', '')", ".join(words)", ".join(result)", ".isdigit()",
    ".lstrip('0')", ".decode('utf-8')", '.decode("utf-8")', ".lower().strip()",
])

_WORD_SWAPS = _dedupe(_WORD_SWAPS + [
    ("plural", "plural_noun"), ("plural_noun", "plural"),
    ("plural", "singular_noun"), ("singular_noun", "plural_noun"),
    ("plural_noun", "plural_verb"), ("plural_verb", "plural_noun"),
    ("plural_verb", "plural_adj"), ("plural_adj", "plural_verb"),
    ("_plnoun", "_plverb"), ("_plverb", "_plnoun"), ("_plverb", "_pladj"),
    ("_pladj", "_plnoun"), ("_sinoun", "_plnoun"),
    ("a", "an"), ("an", "a"), ("word", "words"), ("words", "word"),
    ("word", "text"), ("text", "word"), ("num", "count"), ("count", "num"),
    ("num", "number"), ("number", "num"), ("lower", "lowered"),
    ("lowered", "lower"), ("last", "first"), ("first", "last"),
    ("VERBOSE", "IGNORECASE"), ("IGNORECASE", "VERBOSE"),
    ("match", "search"), ("search", "fullmatch"), ("fullmatch", "match"),
    ("sub", "subn"), ("subn", "sub"), ("split", "findall"),
    ("findall", "finditer"), ("enclose", "joinstem"), ("joinstem", "enclose"),
    ("singular", "plural"), ("plural", "singular"),
    ("classical", "modern"), ("stem", "root"), ("root", "stem"),
    ("suffix", "prefix"), ("prefix", "suffix"), ("pre", "post"),
    ("post", "pre"), ("ordinal", "ordinal_suff"), ("ordinal_suff", "ordinal"),
    ("Union", "Optional"), ("Optional", "Union"), ("Word", "str"),
    ("str", "Word"), ("Any", "str"), ("List", "Sequence"),
    ("sign", "signs"), ("chunk", "chunks"), ("chunks", "chunk"),
    ("numchunks", "chunks"), ("wantlist", "want_list"),
    ("endswith", "startswith"), ("isupper", "istitle"),
])


# ---------------------------------------------------------------------------
# extra lexical helpers
# ---------------------------------------------------------------------------

_STMT_KW_RE = re.compile(
    r"^(def|class|import|from|return|if|elif|else|for|while|with|try|except|"
    r"finally|raise|assert|print|yield|del|global|nonlocal|pass|break|"
    r"continue|lambda|async|await|@)\b")


def _lit_spans(line):
    """[(prefix_start, quote_start, body_start, body_end, lit_end)] per literal."""
    strs, groups, comment = _scan(line)
    out = []
    for (s, e) in strs:
        if e - s < 2:
            continue
        q = line[s]
        ql = 3 if (line[s:s + 3] == q * 3 and e - s >= 6) else 1
        p = s
        while p > 0 and line[p - 1] in "rRbBuUfF" and s - p < 2:
            if p - 1 > 0 and (line[p - 2].isalnum() or line[p - 2] == "_"):
                break
            p -= 1
        out.append((p, s, s + ql, e - ql, e))
    return out


def _atom_spans(line):
    """Spans of bare atoms: dotted names, optionally with a trailing call
    or subscript group."""
    strs, groups, comment = _scan(line)
    end = comment if comment is not None else len(line)
    opens = {}
    for (o, c, op) in groups:
        opens[o] = c
    out = []
    for m in _DOTTED_RE.finditer(line):
        s, e = m.start(), m.end()
        if s >= end:
            break
        if _in_spans(s, strs):
            continue
        if s > 0 and (line[s - 1].isalnum() or line[s - 1] in "_."):
            continue
        head = m.group(0).split(".")[0]
        if head in _KEYWORDS and "." not in m.group(0):
            continue
        if (s, e) not in out:
            out.append((s, e))
        e2 = e
        for _ in range(3):
            if e2 < end and e2 in opens and line[e2] in "([":
                e2 = opens[e2] + 1
            else:
                break
        if e2 != e and (s, e2) not in out:
            out.append((s, e2))
    return out


def _split_alt(s):
    """Split a regex fragment on top level '|'."""
    parts = []
    depth = 0
    start = 0
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "\\":
            i += 2
            continue
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == "|" and depth <= 0:
            parts.append(s[start:i])
            start = i + 1
        i += 1
    parts.append(s[start:])
    return parts


def _split_param(core):
    """(name, annotation_or_None, default_or_None) for one parameter."""
    depth = 0
    q = None
    colon = -1
    eq = -1
    i = 0
    n = len(core)
    while i < n:
        ch = core[i]
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
        elif depth == 0 and ch == ":" and colon < 0 and eq < 0:
            colon = i
        elif depth == 0 and ch == "=" and eq < 0:
            if i + 1 < n and core[i + 1] == "=":
                i += 2
                continue
            if i > 0 and core[i - 1] in "=!<>":
                i += 1
                continue
            eq = i
        i += 1
    if colon < 0 and eq < 0:
        return core.strip(), None, None
    if colon < 0:
        return core[:eq].strip(), None, core[eq + 1:].strip()
    if eq < 0:
        return core[:colon].strip(), core[colon + 1:].strip(), None
    return (core[:colon].strip(), core[colon + 1:eq].strip(),
            core[eq + 1:].strip())


# ---------------------------------------------------------------------------
# KIND 0 : regex source text and word form literals  (the inflect bread and
#          butter -- anchors, groups, quantifiers, stems, suffixes)
# ---------------------------------------------------------------------------

def _rx_variants(b, limit=300):
    out = []
    if not b or len(b) > 400:
        return out
    add = out.append
    add("^" + b)
    add(b + "$")
    add("^" + b + "$")
    add("\\b" + b)
    add(b + "\\b")
    add("\\b" + b + "\\b")
    add("(?:" + b + ")")
    add("(" + b + ")")
    add("(?:" + b + ")?")
    add("(" + b + ")?")
    add("(?:" + b + ")*")
    add("(?:" + b + ")+")
    add("(?!" + b + ")")
    add("(?=" + b + ")")
    add(b + "?")
    add(b + "*")
    add(b + "+")
    add(b + "s")
    add(b + "s?")
    add(b + "es")
    add(b + "es?")
    add(b + "e?s")
    add("(?i)" + b)
    add("(?x)" + b)
    add("\\s*" + b)
    add(b + "\\s*")
    add("^\\s*" + b)
    add(b + "\\s*$")
    add("\\A" + b)
    add(b + "\\Z")
    add("\\s" + b)
    add(b + "\\s")
    add(b + "|")
    add("|" + b)
    add(b + "\\.")
    add(b + "$?")
    if b.startswith("^"):
        add(b[1:])
        add("\\b" + b[1:])
        add(b[1:] + "$")
    if b.endswith("$"):
        add(b[:-1])
        add("^" + b[:-1])
    if b.startswith("\\b"):
        add(b[2:])
        add("^" + b[2:])
    if b.endswith("\\b"):
        add(b[:-2])
    if b.startswith("(") and b.endswith(")"):
        add(b[1:-1])
        add("^" + b + "$")
    for a, c in ((r"(?!", "(?="), ("(?=", "(?!"), (r"(?<!", "(?<="),
                 ("(?<=", "(?<!"), ("(?:", "("), (r"\d", r"\w"),
                 (r"\w", r"\d"), (r"\s", r"\s+"), (r"\b", ""),
                 ("*", "+"), ("+", "*"), ("?", ""), ("]", "]?"),
                 (r"\.", "."), ("|", "")):
        if a and a in b:
            add(b.replace(a, c))
            i = b.find(a)
            n = 0
            while i >= 0 and n < 24:
                add(b[:i] + c + b[i + len(a):])
                i = b.find(a, i + 1)
                n += 1
    for m in re.finditer(r"[*+]", b):
        add(b[:m.start() + 1] + "?" + b[m.start() + 1:])
    for m in re.finditer(r"(?<!\\)\.", b):
        add(b[:m.start()] + "\\." + b[m.start() + 1:])
    for m in re.finditer(r"(?<!\\)\(", b):
        add(b[:m.start()] + "(?:" + b[m.start() + 1:])
    for m in re.finditer(r"\(\?:", b):
        add(b[:m.start()] + "(" + b[m.start() + 3:])
    parts = _split_alt(b)
    if len(parts) > 1:
        for i in range(len(parts) - 1):
            np = list(parts)
            np[i], np[i + 1] = np[i + 1], np[i]
            add("|".join(np))
        for i in range(len(parts)):
            add("|".join(parts[:i] + parts[i + 1:]))
            add("|".join(parts[:i + 1] + [parts[i]] + parts[i + 1:]))
        # per branch edits: one alternative of an `enclose("a|b|c")` list is
        # what usually needs the extra letter / optional group
        for i, br in enumerate(parts[:14]):
            for suf in _BRANCH_SUFFIXES:
                np = list(parts)
                np[i] = br + suf
                add("|".join(np))
            np = list(parts)
            np[i] = "^" + br
            add("|".join(np))
            np = list(parts)
            np[i] = br.strip()
            add("|".join(np))
    return _dedupe([x for x in out if x and x != b])[:limit]


_BRANCH_SUFFIXES = (["s", "s?", "es", "es?", "e", "y", "?", "*", "+", "\\b",
                     "en", "ren", "ur", "[s]", "[ur]", "[aeiou]", "(?!i)",
                     ".*", "\\w*", "[a-z]"] +
                    [c for c in "aeiourstnlmydgh"] +
                    ["[%s]" % c for c in ("ur", "sz", "aeiou", "ao")])


_WORD_SUFFIXES = ["s", "es", "ies", "ves", "a", "ae", "i", "im", "en", "ices",
                  "ina", "ata", "eaux", "oes", "ys", "'s", "ed", "ing", "er",
                  "ren", "ia", "era", "ora", "ina", "ines", "ata", "es?"]

# the irregular pairs this library exists to tabulate; a data fix here is
# almost always one of these mappings being wrong in one direction.
_IRREGULAR = {
    "child": "children", "man": "men", "woman": "women", "person": "people",
    "foot": "feet", "tooth": "teeth", "goose": "geese", "mouse": "mice",
    "louse": "lice", "ox": "oxen", "die": "dice", "penny": "pence",
    "brother": "brethren", "cow": "kine", "sow": "swine", "genus": "genera",
    "corpus": "corpora", "opus": "opera", "octopus": "octopodes",
    "index": "indices", "matrix": "matrices", "vertex": "vertices",
    "axis": "axes", "basis": "bases", "crisis": "crises", "thesis": "theses",
    "datum": "data", "medium": "media", "criterion": "criteria",
    "phenomenon": "phenomena", "cactus": "cacti", "focus": "foci",
    "fungus": "fungi", "nucleus": "nuclei", "radius": "radii",
    "stimulus": "stimuli", "syllabus": "syllabi", "alumnus": "alumni",
    "alumna": "alumnae", "appendix": "appendices", "formula": "formulae",
    "larva": "larvae", "vita": "vitae", "life": "lives", "knife": "knives",
    "wife": "wives", "leaf": "leaves", "half": "halves", "self": "selves",
    "wolf": "wolves", "thief": "thieves", "loaf": "loaves",
    "shelf": "shelves", "calf": "calves", "elf": "elves", "hoof": "hooves",
    "aircraft": "aircraft", "series": "series", "species": "species",
    "sheep": "sheep", "deer": "deer", "fish": "fish", "bison": "bison",
    "seraph": "seraphim", "cherub": "cherubim", "schema": "schemata",
    "stigma": "stigmata", "dogma": "dogmata", "tempo": "tempi",
    "soliloquy": "soliloquies", "quiz": "quizzes", "bus": "buses",
}
_IRREGULAR_BACK = dict((v, k) for (k, v) in _IRREGULAR.items())


def _irregular_forms(b):
    out = []
    bases = [b]
    if b.endswith("s"):
        bases.append(b[:-1])
    if b.endswith("es"):
        bases.append(b[:-2])
    for base in bases:
        low = base.lower()
        for tbl in (_IRREGULAR, _IRREGULAR_BACK):
            if low in tbl:
                v = tbl[low]
                out.append(v)
                if base[:1].isupper():
                    out.append(v[:1].upper() + v[1:])
        out.append(base + "ren")
        out.append(base + "en")
        if "oo" in base:
            out.append(base.replace("oo", "ee"))
        if "ee" in base:
            out.append(base.replace("ee", "oo"))
        if base.endswith("ouse"):
            out.append(base[:-4] + "ice")
        if base.endswith("ice"):
            out.append(base[:-3] + "ouse")
    return out


def _word_variants(b, limit=96):
    out = []
    if not b or len(b) > 60:
        return out
    add = out.append
    for v in _irregular_forms(b):
        add(v)
    for suf in _WORD_SUFFIXES:
        add(b + suf)
    if b.endswith("y"):
        add(b[:-1] + "ies")
        add(b[:-1] + "ie")
    if b.endswith("f"):
        add(b[:-1] + "ves")
    if b.endswith("fe"):
        add(b[:-2] + "ves")
    if b.endswith("s"):
        add(b[:-1])
        add(b[:-1] + "es")
        add(b + "es")
    if b.endswith("es"):
        add(b[:-2])
        add(b[:-2] + "is")
    if b.endswith("us"):
        add(b[:-2] + "i")
        add(b[:-2] + "era")
        add(b[:-2] + "ora")
    if b.endswith("um"):
        add(b[:-2] + "a")
    if b.endswith("on"):
        add(b[:-2] + "a")
    if b.endswith("a"):
        add(b + "e")
        add(b + "ta")
        add(b[:-1] + "ae")
    if b.endswith("is"):
        add(b[:-2] + "es")
    if b.endswith("ix") or b.endswith("ex"):
        add(b[:-2] + "ices")
    if b.endswith("o"):
        add(b + "es")
        add(b + "s")
    if b.endswith("man"):
        add(b[:-3] + "men")
    if b.endswith("men"):
        add(b[:-3] + "man")
    if b.endswith("ch") or b.endswith("sh") or b.endswith("x") or b.endswith("z"):
        add(b + "es")
    for n in (1, 2, 3):
        if len(b) > n:
            add(b[:-n])
            add(b[:-n] + "s")
            add(b[:-n] + "es")
    if "|" in b:
        a1, _s, a2 = b.partition("|")
        add(a1)
        add(a2)
        add(a2 + "|" + a1)
    else:
        add(b + "|" + b + "s")
        add(b + "|" + b)
    add(b.lower())
    add(b.upper())
    add(b[:1].upper() + b[1:])
    add(b[:1].lower() + b[1:])
    add(b.replace(" ", ""))
    add(b.replace(" ", "_"))
    add(b.replace("_", " "))
    add(b.strip())
    add(" " + b)
    add(b + " ")
    return _dedupe([x for x in out if x and x != b])[:limit]


_EXTS = ["txt", "rst", "md", "py", "cfg", "in", "json", "yml", "yaml", "html",
         "dat", "dic", "csv", "log", "ini", "toml", "tsv", "xml", "po", "sh",
         "rst.in", "txt.in", "old", "bak", "gz", "zip", "pyi"]

_PATH_STEMS = ["README", "CHANGES", "CHANGELOG", "HISTORY", "NEWS", "LICENSE",
               "LICENCE", "COPYING", "AUTHORS", "TODO", "MANIFEST", "setup",
               "conftest", "inflect", "__init__", "test_inflect", "index",
               "data", "words", "docs/index", "readme", "Readme"]


def _path_variants(b, limit=90):
    """filename / extension churn -- setup.py in this project renames its
    long_description source repeatedly."""
    out = []
    if not b or len(b) > 120 or "\n" in b:
        return out
    m = re.match(r"^(.*?)\.([A-Za-z0-9_]{1,6})$", b)
    if m:
        stem, ext = m.group(1), m.group(2)
        for e in _EXTS:
            out.append(stem + "." + e)
            out.append(stem + "." + e.upper())
        for s2 in _PATH_STEMS:
            out.append(s2 + "." + ext)
        out.append(stem)
        out.append(stem.upper() + "." + ext)
        out.append(stem.lower() + "." + ext)
        out.append(stem + "." + ext + ".in")
    else:
        for e in _EXTS:
            out.append(b + "." + e)
        for s2 in _PATH_STEMS:
            out.append(s2)
    if "/" in b:
        out.append(b.rsplit("/", 1)[1])
        out.append(b.split("/", 1)[1])
    for pre in ("./", "../", "docs/", "inflect/", "tests/"):
        out.append(pre + b)
    # component level replacement (dir/name.ext)
    for m2 in re.finditer(r"[A-Za-z_][A-Za-z_0-9]*", b):
        for s2 in _PATH_STEMS[:10] + _EXTS[:8]:
            out.append(b[:m2.start()] + s2 + b[m2.end():])
    return _dedupe([x for x in out if x and x != b])[:limit]


def _act_regex(line):
    out = []
    for (ps, qs, bs, be, qe) in _lit_spans(line):
        if bs > be:
            continue
        b = line[bs:be]
        for nb in _rx_variants(b):
            out.append(line[:bs] + nb + line[be:])
        for nb in _path_variants(b):
            out.append(line[:bs] + nb + line[be:])
        for nb in _word_variants(b):
            out.append(line[:bs] + nb + line[be:])
    ce = _code_end(line)
    code = line[:ce]
    st = code.strip()
    strs = _scan(line)[0]
    if st and not strs and not _STMT_KW_RE.match(st) and "=" not in st:
        ind = code[:len(code) - len(code.lstrip())]
        trail = line[len(code.rstrip()):]
        for nb in _rx_variants(st):
            out.append(ind + nb + trail)
        for nb in _word_variants(st):
            out.append(ind + nb + trail)
        for pre in ("^", "\\b", "(?:", "(", "|", " "):
            out.append(pre + line)
        for suf in ("$", "\\b", ")", "|", "?"):
            out.append(line.rstrip() + suf + trail)
    return out


# ---------------------------------------------------------------------------
# KIND 1 : signature / type annotation / trailing pragma comment
# ---------------------------------------------------------------------------

_TYPE_VOCAB = [
    "Word", "str", "int", "bool", "float", "Any", "None", "bytes",
    "Optional[str]", "Optional[int]", "Optional[Word]", "Optional[bool]",
    "Optional[Any]", "Union[int, Word]", "Union[str, int]", "Union[str, Word]",
    "Union[int, str]", "Optional[Union[str, int]]", "Union[str, int, Any]",
    "List[str]", "List[Word]", "Sequence[str]", "Iterable[str]",
    "Dict[str, str]", "Tuple[str, str]", "Tuple[str, str, str]",
    "Match", "Optional[Match]", "Callable", "Iterator[str]",
    "Union[str, List[str]]", "Optional[Union[int, str]]",
    # the shapes inflect's own signatures actually use
    "Optional[Union[int, str, Any]]", "Union[int, str, Any]",
    "Optional[Union[str, int, Any]]", "Union[str, int, Any]",
    "Optional[Union[int, Word]]", "Optional[Union[str, Word]]",
    "Union[int, Word, str]", "Optional[Union[Word, int]]",
    "Union[str, bool]", "Union[str, int, bool]", "Optional[Union[str, bool]]",
    "Word", '"Words"', "Words", "Optional[Words]", "Collection[str]",
]

_RET_VOCAB = [
    "str", "int", "bool", "None", "Word", "float", "bytes", "Any",
    "Optional[str]", "List[str]", "Union[str, List[str]]", "Iterator[str]",
    "Tuple[str, str, str]", "Optional[Word]", "Union[str, int]",
    '"Words"', "Words", "Optional[int]", "Set[str]", "Dict[str, str]",
]


def _type_variants(t, limit=34):
    if t is None:
        return []
    t = t.strip()
    out = []
    m = re.match(r"^([A-Za-z_][\w\.]*)\[(.*)\]$", t)
    if m:
        head, inner = m.group(1), m.group(2)
        parts = [inner[a:b].strip() for (a, b) in _split_args(inner)]
        for p in parts:
            out.append(p)
            out.append("Optional[%s]" % p)
            out.append("Union[str, %s]" % p)
            out.append("Union[int, %s]" % p)
            out.append("List[%s]" % p)
        if len(parts) > 1:
            for i in range(len(parts)):
                rest = parts[:i] + parts[i + 1:]
                out.append("%s[%s]" % (head, ", ".join(rest)))
                if len(rest) == 1:
                    out.append(rest[0])
            out.append("%s[%s]" % (head, ", ".join(reversed(parts))))
        out.append(inner)
        out.append("Optional[%s]" % t)
        out.append(head)
    else:
        out += ["Optional[%s]" % t, "Union[str, %s]" % t, "Union[int, %s]" % t,
                "List[%s]" % t, "Sequence[%s]" % t, "Union[%s, Word]" % t,
                "Union[%s, str]" % t, '"%s"' % t]
    out += _TYPE_VOCAB
    return _dedupe([x for x in out if x and x != t])[:limit]


def _with_comment(codes, line, ce):
    """For each rewritten code part, emit it with and without the trailing
    comment (inflect fixes routinely drop a `# noqa` alongside the edit)."""
    out = []
    cmt = line[ce:]
    ctext = cmt.strip()
    for c in codes:
        c = c.rstrip()
        out.append(c)
        if ctext:
            out.append(c + "  " + ctext)
            out.append(c + " " + ctext)
        else:
            out.append(c + "  # noqa")
            out.append(c + "  # noqa: C901")
    return out


def _act_signature(line):
    out = []
    ce = _code_end(line)
    code = line[:ce]
    cmt = line[ce:]
    st = code.strip()

    if cmt.strip():
        out.append(code.rstrip())
        out.append(code)
        out.append(re.sub(r"\s*#\s*noqa[^#]*$", "", line).rstrip())
        out.append(re.sub(r"\s*#.*$", "", line).rstrip())
    if not cmt.strip() and st:
        out.append(code.rstrip() + "  # noqa")
        out.append(code.rstrip() + "  # noqa: C901")
        out.append(code.rstrip() + "  # type: ignore")

    codes = []

    # --- return annotation -------------------------------------------------
    m = re.search(r"->\s*(.+?)\s*:\s*$", code)
    if m:
        rs, re_ = m.start(1), m.end(1)
        cur = m.group(1)
        for nv in _dedupe(_type_variants(cur, 24) + _RET_VOCAB)[:34]:
            codes.append(code[:rs] + nv + code[re_:])
        codes.append(re.sub(r"\s*->\s*[^:]+:\s*$", ":", code))
    elif re.search(r"\)\s*:\s*$", code) and re.match(r"^\s*(async\s+def|def)\s", st):
        for nv in _RET_VOCAB:
            codes.append(re.sub(r"\)\s*:\s*$", ") -> %s:" % nv, code))

    # --- parameter annotations / defaults ----------------------------------
    dm = re.match(r"^\s*(?:async\s+)?def\s+[A-Za-z_]\w*\s*\(", code)
    if dm:
        openidx = dm.end() - 1
        for (ns, o, c, op, name) in _callspans(line):
            if o != openidx or c >= ce:
                continue
            content = line[o + 1:c]
            parts = _split_args(content)
            for (a, b) in parts:
                arg = content[a:b]
                core = arg.strip()
                if not core or core in ("*", "self", "cls") or core.startswith("**"):
                    continue
                lead = arg[:len(arg) - len(arg.lstrip())]
                trail = arg[len(arg.rstrip()):]
                nm, ann, dflt = _split_param(core)
                news = []
                if ann is not None:
                    for nv in _dedupe(_type_variants(ann) + _TYPE_VOCAB):
                        news.append("%s: %s" % (nm, nv) +
                                    (" = %s" % dflt if dflt is not None else ""))
                    news.append(nm + ("=%s" % dflt if dflt is not None else ""))
                else:
                    for nv in _TYPE_VOCAB[:18]:
                        news.append("%s: %s" % (nm, nv) +
                                    (" = %s" % dflt if dflt is not None else ""))
                if dflt is None:
                    for dv in ("None", "False", "True", "0", "1", "''", '""',
                               "()", "[]", "{}"):
                        if ann is not None:
                            news.append("%s: %s = %s" % (nm, ann, dv))
                        else:
                            news.append("%s=%s" % (nm, dv))
                else:
                    news.append("%s: %s" % (nm, ann) if ann is not None else nm)
                    for dv in ("None", "False", "True", "0", "1", "''", '""'):
                        if dv == dflt:
                            continue
                        if ann is not None:
                            news.append("%s: %s = %s" % (nm, ann, dv))
                        else:
                            news.append("%s=%s" % (nm, dv))
                for nc in _dedupe(news):
                    if nc == core:
                        continue
                    newcontent = content[:a] + lead + nc + trail + content[b:]
                    codes.append(line[:o + 1] + newcontent + code[c:])

    # --- variable annotations ---------------------------------------------
    vm = re.match(r"^(\s*[A-Za-z_][\w\.\[\]\"']*)\s*:\s*([^=]+?)\s*(=\s*.*)?$", code)
    if vm and not dm and ":" in code and not st.endswith(":"):
        head, ann, rhs = vm.group(1), vm.group(2), vm.group(3) or ""
        for nv in _type_variants(ann):
            codes.append("%s: %s%s" % (head, nv, (" " + rhs) if rhs else ""))
        if rhs:
            codes.append("%s %s" % (head, rhs))

    out += _with_comment(_dedupe(codes), line, ce)
    return out


# ---------------------------------------------------------------------------
# KIND 2 : mutating-method misuse, assignment restructure, conjuncts
# ---------------------------------------------------------------------------

_MUT_METHODS = ("append", "extend", "insert", "add", "update", "sort",
                "reverse", "remove", "discard")


def _base_name(expr):
    e = expr.strip()
    m = re.match(r"^\[?\s*([A-Za-z_][\w\.]*)\s*\]?$", e)
    if m:
        return m.group(1)
    m = re.match(r"^([A-Za-z_]\w*)", e)
    return m.group(1) if m else None


def _act_mutate(line):
    out = []
    ce = _code_end(line)
    code = line[:ce]
    tail = line[ce:]
    st = code.strip()
    if not st:
        return out
    ind = code[:len(code) - len(code.lstrip())]
    trail = code[len(code.rstrip()):]
    names = [n for n in _idents(line) if n not in _KEYWORDS]

    def emit(newst):
        out.append(ind + newst + trail + tail)

    # --- x.append(y) used as a value --------------------------------------
    m = re.match(r"^(return\s+|yield\s+)?(?:([A-Za-z_][\w\.\[\]]*)\s*=\s*)?"
                 r"(.+?)\.(\w+)\((.*)\)\s*$", st)
    if m and m.group(4) in _MUT_METHODS:
        kw = (m.group(1) or "").strip()
        lhs = m.group(2)
        recv = m.group(3).strip()
        meth = m.group(4)
        argtxt = m.group(5)
        args = [argtxt[a:b].strip() for (a, b) in _split_args(argtxt)]
        elem = args[-1] if args else ""
        first = args[0] if args else ""
        exprs = []
        if meth in ("append", "insert", "add"):
            exprs += ["%s + [%s]" % (recv, elem), "[%s] + %s" % (elem, recv),
                      "%s + %s" % (recv, elem), "%s + %s" % (elem, recv),
                      "list(%s) + [%s]" % (recv, elem)]
        elif meth in ("extend", "update"):
            exprs += ["%s + %s" % (recv, elem), "%s + %s" % (elem, recv),
                      "%s + list(%s)" % (recv, elem)]
        elif meth == "sort":
            exprs += ["sorted(%s)" % recv, "sorted(%s, %s)" % (recv, argtxt)
                      if argtxt else "sorted(%s)" % recv]
        elif meth == "reverse":
            exprs += ["list(reversed(%s))" % recv, "%s[::-1]" % recv]
        elif meth in ("remove", "discard"):
            exprs += ["[x for x in %s if x != %s]" % (recv, elem)]
        exprs = _dedupe([e for e in exprs if e])
        targets = _dedupe([t for t in
                           [_base_name(elem), _base_name(recv), _base_name(first), lhs]
                           + names if t])
        for e in exprs:
            for t in targets[:8]:
                emit("%s = %s" % (t, e))
            emit("return " + e)
            emit("yield " + e)
            emit(e)
        # simply drop the bad wrapper
        emit("%s.%s(%s)" % (recv, meth, argtxt))
        if kw:
            emit("%s.%s(%s)" % (recv, meth, argtxt))
        for alt in ("append", "extend", "insert"):
            if alt != meth:
                emit("%s.%s(%s)" % (recv, alt, argtxt))
        if lhs:
            emit("%s.%s(%s)" % (recv, meth, argtxt))

    # --- return <-> bare statement <-> assignment --------------------------
    m = re.match(r"^(return|yield)\s+(.*)$", st)
    if m:
        expr = m.group(2)
        emit(expr)
        emit("return " + expr if m.group(1) != "return" else "yield " + expr)
        for t in names[:8]:
            emit("%s = %s" % (t, expr))
        for t in names[:8]:
            emit("%s += %s" % (t, expr))
    elif not re.match(r"^(if|elif|else|for|while|with|try|except|finally|def|"
                      r"class|import|from|raise|assert|del|pass|break|continue|"
                      r"global|nonlocal|@)\b", st) and not st.endswith(":"):
        emit("return " + st)
        emit("yield " + st)
        for t in names[:8]:
            if not re.match(r"^%s\s*=" % re.escape(t), st):
                emit("%s = %s" % (t, st))

    # --- assignment target / operator -------------------------------------
    m = re.match(r"^([A-Za-z_][\w\.\[\]\"']*)\s*(\+?=)\s*(.*)$", st)
    if m and m.group(2) == "=":
        lhs, rhs = m.group(1), m.group(3)
        emit("%s += %s" % (lhs, rhs))
        emit("%s = %s + %s" % (lhs, lhs, rhs))
        emit("%s = %s + %s" % (lhs, rhs, lhs))
        emit("%s = [%s] + %s" % (lhs, rhs, lhs))
        emit("%s = %s + [%s]" % (lhs, lhs, rhs))
        emit("return %s" % rhs)
        for t in names:
            if t != lhs:
                emit("%s = %s" % (t, rhs))
    if m and m.group(2) == "+=":
        emit("%s = %s" % (m.group(1), m.group(3)))

    # --- adding a conjunct to a condition ---------------------------------
    m = re.match(r"^(if|elif|while|assert)\s+(.*?):?\s*$", st)
    cond_tail = ":" if st.endswith(":") else ""
    base = _dedupe(names + ["word", "words", "count", "num", "text", "value",
                            "self.classical_dict"])[:10]
    extra = ["None", "True", "False"]
    for nm in base:
        extra += [nm, "not " + nm, nm + " is None", nm + " is not None",
                  nm + " == 1", nm + " != 1", nm + " == 0", nm + " > 1",
                  nm + ' == ""', nm + " == '1'", "len(" + nm + ") > 1",
                  nm + ".lower()"]
    extra = _dedupe(extra)[:90]
    if m:
        kw, cond = m.group(1), m.group(2)
        for x in extra:
            emit("%s %s and %s%s" % (kw, cond, x, cond_tail))
            emit("%s %s or %s%s" % (kw, cond, x, cond_tail))
            emit("%s %s and not %s%s" % (kw, cond, x, cond_tail))
            emit("%s %s or not %s%s" % (kw, cond, x, cond_tail))
            emit("%s %s and %s%s" % (kw, x, cond, cond_tail))
            emit("%s %s or %s%s" % (kw, x, cond, cond_tail))
            emit("%s not %s and %s%s" % (kw, cond, x, cond_tail))
        emit("%s not %s%s" % (kw, cond, cond_tail))
        emit("%s not (%s)%s" % (kw, cond, cond_tail))
        emit("%s (%s)%s" % (kw, cond, cond_tail))
    m = re.match(r"^return\s+(.*)$", st)
    if m:
        cond = m.group(1)
        for x in extra[:40]:
            emit("return %s and %s" % (cond, x))
            emit("return %s or %s" % (cond, x))
            emit("return %s or %s" % (x, cond))
            emit("return %s and %s" % (x, cond))

    # --- an extraneous / missing trailing call ----------------------------
    m = re.match(r"^(.*?)\.(\w+)\(([^()]*)\)\s*$", st)
    if m and m.group(1).strip():
        emit(m.group(1))
        emit(m.group(1) + "()")
    return out


# ---------------------------------------------------------------------------
# extra: wrap / method-append on bare atoms (str(num), word.lower(), ...)
# ---------------------------------------------------------------------------

_ATOM_WRAP = ["str", "int", "float", "list", "len", "bool", "tuple", "set",
              "sorted", "reversed", "repr", "enclose", "joinstem", "re.escape",
              "self.plural", "self.plural_noun", "self.singular_noun",
              "self.postprocess", "self.number_to_words", "self.ordinal",
              "self.a", "self.no", "self.num", "unicode", "text_type", "next"]

_ATOM_METHODS = [".lower()", ".upper()", ".strip()", ".title()", ".capitalize()",
                 ".split()", ".split(' ')", ".group()", ".group(0)", ".group(1)",
                 ".groups()", ".items()", ".keys()", ".values()", ".copy()",
                 ".pop()", ".pop(0)", ".rstrip()", ".lstrip()", ".read()",
                 ".decode('utf-8')", ".encode('utf-8')", ".lower().strip()",
                 ".rstrip('s')", ".isdigit()", ".__name__"]


def _act_atom_wrap(line):
    out = []
    spans = _atom_spans(line)
    for (s, e) in spans[:14]:
        text = line[s:e]
        for f in _ATOM_WRAP:
            out.append(line[:s] + f + "(" + text + ")" + line[e:])
        out.append(line[:s] + "(" + text + ")" + line[e:])
        out.append(line[:s] + "[" + text + "]" + line[e:])
    return out


def _act_atom_method(line):
    out = []
    spans = _atom_spans(line)
    for (s, e) in spans[:14]:
        for meth in _ATOM_METHODS:
            out.append(line[:e] + meth + line[e:])
    return out


# ---------------------------------------------------------------------------
# extra: moving a bracket
# ---------------------------------------------------------------------------

_CLOSER = {"(": ")", "[": "]", "{": "}"}


def _act_paren(line):
    out = []
    ce = _code_end(line)
    code = line[:ce]
    tail = line[ce:]
    strs, groups, comment = _scan(line)
    body_end = len(code.rstrip())
    for (o, c, op) in groups:
        if c >= ce:
            continue
        closer = _CLOSER.get(op, ")")
        # move the closer to the right, swallowing following text
        stops = []
        for p in range(c + 1, body_end + 1):
            if p == body_end:
                stops.append(p)
                continue
            if code[p - 1] in " \t":
                continue
            if p < len(code) and (code[p].isalnum() or code[p] == "_"):
                continue
            stops.append(p)
        for p in stops[:25]:
            out.append(code[:c] + code[c + 1:p] + closer + code[p:] + tail)
        # move the closer to the left, spilling the rest outside
        content = line[o + 1:c]
        for (a, b) in _split_args(content):
            p = o + 1 + b
            if o < p < c:
                out.append(code[:p] + closer + code[p:c] + code[c + 1:] + tail)
        # drop / duplicate the pair
        out.append(code[:o] + code[o + 1:c] + code[c + 1:] + tail)
        out.append(code[:o] + op + code[o:c + 1] + closer + code[c + 1:] + tail)
    return out


def _act_call_shape(line):
    """unwrap / empty / retarget a call -- the inverse of wrapping, and the
    `text.split(" ")` -> `text.split()` shape."""
    out = []
    ce = _code_end(line)
    for (ns, o, c, op, name) in _callspans(line):
        if c >= ce:
            continue
        content = line[o + 1:c]
        if not name:
            continue
        if content.strip():
            out.append(line[:o + 1] + line[c:])                   # f()
            out.append(line[:ns] + content + line[c + 1:])        # unwrap
            out.append(line[:ns] + content.strip() + line[c + 1:])
        out.append(line[:ns] + name + line[c + 1:])               # drop call
        if "." in name:
            recv, _d, meth = name.rpartition(".")
            out.append(line[:ns] + recv + line[c + 1:])           # drop .m(...)
            out.append(line[:ns] + recv + "." + meth + "()" + line[c + 1:])
            for alt in ("lower", "upper", "strip", "group", "split", "join",
                        "get", "pop", "append", "extend", "search", "match",
                        "sub", "findall", "replace", "startswith", "endswith"):
                if alt != meth:
                    out.append(line[:ns] + recv + "." + alt + "(" + content +
                               ")" + line[c + 1:])
    return out


def _act_struct_plus(line):
    return _act_struct(line) + _act_paren(line)


def _act_wrap_plus(line):
    return _act_wrap(line) + _act_atom_wrap(line) + _act_call_shape(line)


def _act_method_plus(line):
    return _act_method(line) + _act_atom_method(line)


# ---------------------------------------------------------------------------
# KIND 11 : single character edits, ordered by how often they are the fix
# ---------------------------------------------------------------------------

_HOT_CHARS = "^$()[]{}|\\.,'\"*+?:=-_ /!<>%&sey0123456789"
_LOWER = "abcdefghijklmnopqrstuvwxyz"
_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_REST = "#@~`;"

_CHAR_CAP = 6200


def _act_char2(line):
    out = []
    n = len(line)
    if n == 0 or n > 1200:
        return out
    for i in range(n):
        out.append(line[:i] + line[i + 1:])
    for i in range(n - 1):
        if line[i] != line[i + 1]:
            out.append(line[:i] + line[i + 1] + line[i] + line[i + 2:])
    for i in range(n):
        out.append(line[:i] + line[i] * 2 + line[i + 1:])
    for grp in (_HOT_CHARS, _LOWER, _UPPER, _REST):
        for i in range(n + 1):
            pre, post = line[:i], line[i:]
            for ch in grp:
                out.append(pre + ch + post)
        for i in range(n):
            pre, post, orig = line[:i], line[i + 1:], line[i]
            for ch in grp:
                if ch != orig:
                    out.append(pre + ch + post)
        if len(out) >= _CHAR_CAP:
            break
    return out[:_CHAR_CAP]


# ---------------------------------------------------------------------------
# the ordered act table.  kind k -> act number (k + 5) mod 16, so exactly
# sixteen kinds are addressable; they are listed most-likely-fix first so a
# truncated candidate stream still carries the good ones.
# ---------------------------------------------------------------------------

_ORDERED = [
    _act_regex,        # 0  regex / word-form literal surgery
    _act_signature,    # 1  annotations, defaults, trailing pragma comments
    _act_mutate,       # 2  mutating-method misuse, restructure, conjuncts
    _act_open,         # 3  open() mode / encoding / filename
    _act_wrap_plus,    # 4  wrap a subexpression in a call  (str(num), ...)
    _act_tokens,       # 5  operator / word token swaps
    _act_strings,      # 6  generic string literal edits
    _act_method_plus,  # 7  append a method call
    _act_negation,     # 8  negation and truth value fixes
    _act_numbers,      # 9  numeric literals, slices, off-by-one
    _act_add_arg,      # 10 add a missing argument (count=, classical=, ...)
    _act_struct_plus,  # 11 structural edits + bracket moves
    _act_char2,        # 12 single character edits
    _act_import,       # 13 import statement fixes
    _act_swap_names,   # 14 replace / remove / reorder names and arguments
    _act_word,         # 15 prose / docstring / comment wording
]

_N = len(_ORDERED)

_BUDGET_TOTAL = 16000

_STATE = {"line": None, "left": 0, "seen": None}


def _reset(line):
    _STATE["line"] = line
    _STATE["left"] = _BUDGET_TOTAL
    _STATE["seen"] = set([line])


def observe(line):
    _reset(line)
    return list(range(_N))


def acts(line, act):
    kind = (act - 5) % 16
    if kind < 0 or kind >= _N:
        return []
    if _STATE["line"] != line or _STATE["seen"] is None:
        _reset(line)
    if _STATE["left"] <= 0:
        return []
    try:
        raw = _ORDERED[kind](line) or []
    except Exception:
        raw = []
    seen = _STATE["seen"]
    left = _STATE["left"]
    out = []
    for c in raw:
        if left <= 0:
            break
        if not isinstance(c, str) or c == line or c in seen:
            continue
        seen.add(c)
        out.append(c)
        left -= 1
    _STATE["left"] = left
    return out

def candidates(line):
    for kind in observe(line):
        for c in acts(line, router(WORKED_EXAMPLE[0], WORKED_EXAMPLE[1], kind)):
            yield c
