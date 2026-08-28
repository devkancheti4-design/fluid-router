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
# PROJECT LAYER — the mistakes THIS codebase actually keeps making
#
#   * a module qualifier where the local one was meant
#         logging.debug(...)                  -> log.debug(...)
#   * a freshly constructed object where the local variable was meant
#         Parser(fmt, extra_types=e).findall(..) -> p.findall(..)
#   * an option that is not threaded through the delegating wrapper
#         Parser(format, extra_types=extra_types)
#             -> Parser(format, extra_types=extra_types, case_sensitive=case_sensitive)
#   * a character-inspection condition missing its length guard
#         if string[0] == '0':  -> if string[0] == '0' and len(string) > 1:
#   * documentation prose that lost / gained a word
#         "indexes are supported" -> "indexes are not supported"
#   * the generated regular expression / format spec being one token off
# ===========================================================================

_RECEIVERS = [
    "log", "logging", "logger", "self", "cls", "p", "parser", "result", "m",
    "match", "re", "string", "format", "value", "self.log", "_log", "parse",
    "Parser", "os", "sys", "math", "datetime", "time", "d", "s", "obj", "l",
]

_LOG_METHODS = ["debug", "info", "warning", "warn", "error", "exception", "critical"]

_PROJ_ATTRS = [
    "_expression", "_match_re", "_search_re", "_fixed_fields", "_named_fields",
    "_name_types", "_group_index", "_type_conversions", "_format", "_case_sensitive",
    "_extra_types", "_group_to_name_map", "_name_to_group_map", "fixed", "named",
    "spans", "pattern", "base", "CHARS", "regex_group_count", "group_index",
    "evaluate_result", "case_sensitive", "extra_types", "groups", "groupdict",
]

_ATTR_SWAPS = [
    ("_match_re", "_search_re"), ("_search_re", "_match_re"),
    ("_fixed_fields", "_named_fields"), ("_named_fields", "_fixed_fields"),
    ("fixed", "named"), ("named", "fixed"),
    ("_name_types", "_type_conversions"), ("_type_conversions", "_name_types"),
    ("_expression", "_format"), ("_format", "_expression"),
    ("_group_index", "group_index"), ("group_index", "_group_index"),
]

_PROJ_KW = [
    "case_sensitive=case_sensitive", "case_sensitive=self._case_sensitive",
    "case_sensitive=False", "case_sensitive=True", "case_sensitive",
    "extra_types=extra_types", "extra_types=self._extra_types", "extra_types",
    "evaluate_result=evaluate_result", "evaluate_result=True",
    "evaluate_result=False", "evaluate_result",
    "pos", "endpos", "pos, endpos", "string", "format", "match", "self",
    "flags=re.IGNORECASE", "re.IGNORECASE", "re.DOTALL",
    "re.IGNORECASE | re.DOTALL", "0", "1", "-1", "None", "True", "False",
    "base", "self.base", "10", "16", "8", "2", "name", "value", "type",
]

_MICRO = [
    ("logging.", "log."), ("log.", "logging."), ("logger.", "log."),
    ("== None", "is None"), ("!= None", "is not None"),
    ("is None", "is not None"), ("is not None", "is None"),
    (".match(", ".search("), (".search(", ".match("),
    (".findall(", ".finditer("), (".finditer(", ".findall("),
    ("re.match(", "re.search("), ("re.search(", "re.match("),
    (".group(", ".groups("), (".groups(", ".group("),
    (".append(", ".extend("), (".extend(", ".append("),
    ("str(", "repr("), ("repr(", "str("), ("int(", "float("),
    ("%s", "%r"), ("%r", "%s"), ("%s", "%d"), ("%d", "%s"),
    ("{}", "{0}"), ("{0}", "{}"),
    (".format(", " % ("), ("' '", "''"), ("''", "' '"),
    ("self.", ""), ("if ", "elif "), ("elif ", "if "),
    (" == ", " is "), (" is ", " == "), (".strip()", ".rstrip()"),
    ("isdigit()", "isalnum()"), ("+", "+?"), ("*", "*?"),
]

_RX_SWAPS = [
    ("+", "*"), ("*", "+"), ("+", "+?"), ("*", "*?"), ("+", "{1,}"),
    ("?", ""), (")", ")?"), ("(", "(?:"), ("(?:", "("), ("(", "(?P<name>"),
    ("\\d", "\\w"), ("\\w", "\\d"), ("\\d", "\\d+"), ("\\w", "\\w+"),
    ("\\s", "\\s+"), ("[", "[^"), ("[^", "["), (".", "\\."), ("|", ""),
    ("\\", ""), ("{", "\\{"), ("}", "\\}"), ("*", "*?"), ("$", ""),
]

_CLASS_CHARS = ("<>=^!+-_,.:; %*?|/0123456789dnwsxXbBoOeEfFgGtrclmpuvhaikqjyz"
                "()[]{}#&@~\\'\"")

_PROJ_ONLY = [
    "group", "groups", "expression", "spec", "fill", "align", "zero", "sign",
    "wrap", "conv", "field", "fields", "extra_types", "case_sensitive",
    "evaluate_result", "endpos", "pos", "group_index", "base", "chars",
    "number_start", "precision", "width", "type", "name", "string", "format",
    "n", "m", "p", "s", "d", "e", "w", "i", "k", "log", "self", "cls",
]

_CONTRACTIONS = [
    ("there's", "there is"), ("it's", "it is"), ("that's", "that is"),
    ("doesn't", "does not"), ("don't", "do not"), ("isn't", "is not"),
    ("aren't", "are not"), ("can't", "cannot"), ("won't", "will not"),
    ("didn't", "did not"), ("wasn't", "was not"), ("hasn't", "has not"),
    ("haven't", "have not"), ("we're", "we are"), ("you're", "you are"),
    ("they're", "they are"), ("let's", "let us"), ("wouldn't", "would not"),
    ("shouldn't", "should not"), ("couldn't", "could not"), ("we'll", "we will"),
    ("you'll", "you will"), ("i'm", "I am"), ("what's", "what is"),
    ("there is", "there's"), ("it is", "it's"), ("does not", "doesn't"),
    ("do not", "don't"), ("is not", "isn't"), ("are not", "aren't"),
    ("cannot", "can't"), ("will not", "won't"), ("that is", "that's"),
]


def _nl_split(line):
    i = len(line)
    while i > 0 and line[i - 1] in "\r\n":
        i -= 1
    return line[:i], line[i:]


def _outside_strings(line):
    strs, groups, comment = _scan(line)
    end = comment if comment is not None else len(line)
    out = []
    for i, ch in enumerate(line[:end]):
        out.append(" " if _in_spans(i, strs) else ch)
    return "".join(out)


def _dotted_heads(line):
    """(head_start, head_end) for every dotted name written in code."""
    strs, groups, comment = _scan(line)
    end = comment if comment is not None else len(line)
    out = []
    for m in re.finditer(r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)+", line):
        s = m.start()
        if s >= end or _in_spans(s, strs):
            continue
        if s > 0 and (line[s - 1].isalnum() or line[s - 1] in "_."):
            continue
        hm = re.match(r"[A-Za-z_][A-Za-z_0-9]*", m.group(0))
        out.append((s, s + hm.end()))
    return out


def _dotted_names(line):
    strs, groups, comment = _scan(line)
    end = comment if comment is not None else len(line)
    out = []
    for m in re.finditer(r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)+", line):
        if m.start() >= end or _in_spans(m.start(), strs):
            continue
        out.append(m.group(0))
    return _dedupe(out)


def _receiver_spans(line):
    """Spans of a receiver expression that ends in a bracket and is followed by
    `.attr`, e.g. the `Parser(...)` of `Parser(...).findall(x)`."""
    strs, groups, comment = _scan(line)
    end = comment if comment is not None else len(line)
    closers = {}
    for (o, c, op) in groups:
        closers[c] = o
    out = []
    for m in re.finditer(r"\.\s*[A-Za-z_]", line):
        i = m.start()
        if i >= end or _in_spans(i, strs):
            continue
        j = i - 1
        while j >= 0 and line[j] in " \t":
            j -= 1
        if j < 0 or line[j] not in ")]}":
            continue
        o = closers.get(j)
        if o is None:
            continue
        k = o
        while k > 0 and (line[k - 1].isalnum() or line[k - 1] in "_."):
            k -= 1
        if (k, j + 1) not in out:
            out.append((k, j + 1))
        if k != o and (o, j + 1) not in out:
            out.append((o, j + 1))
    return out


# --- kind 13 : project idioms -------------------------------------------------

def _act_project(line):
    out = []
    strs, groups, comment = _scan(line)
    end = comment if comment is not None else len(line)
    names = [w for w in _idents(line) if w not in _KEYWORDS]
    positions = _ident_positions(line)
    dotted = _dotted_names(line)

    # 1. an identifier that should have been another identifier already present
    for (s, e, w) in positions:
        for v in names:
            if v != w:
                out.append(line[:s] + v + line[e:])
    for (s, e, w) in positions:
        for v in dotted:
            if v != w and not v.startswith(w + "."):
                out.append(line[:s] + v + line[e:])

    # 2. the receiver of a chained call is a fresh object, should be the local
    recv_vocab = _dedupe(["p", "self", "cls", "parser", "result", "m", "match",
                          "log", "re", "string", "format", "value", "obj", "d"]
                         + names + dotted)
    rspans = _receiver_spans(line)
    for (s, e) in rspans:
        cur = line[s:e]
        for v in recv_vocab:
            if v != cur:
                out.append(line[:s] + v + line[e:])
    # ... and the option the delegating wrapper still forgets to pass on
    if rspans:
        s, e = rspans[0]
        tail_calls = [(o, c) for (ns, o, c, op, nm) in _callspans(line)
                      if op == "(" and o > e and c < end]
        for v in ("p", "self", "parser"):
            base = line[:s] + v + line[e:]
            shift = len(v) - (e - s)
            for (o, c) in tail_calls:
                cc = c + shift
                inner = base[o + shift + 1:cc]
                for kw in ("evaluate_result=evaluate_result",
                           "case_sensitive=case_sensitive",
                           "extra_types=extra_types", "pos, endpos",
                           "pos", "endpos", "string", "format"):
                    if inner.strip():
                        out.append(base[:cc] + ", " + kw + base[cc:])
                    else:
                        out.append(base[:cc] + kw + base[cc:])

    # 3. the module qualifier of a dotted name (logging.debug -> log.debug)
    for (hs, he) in _dotted_heads(line):
        head = line[hs:he]
        for v in _RECEIVERS + names:
            if v != head:
                out.append(line[:hs] + v + line[he:])
        out.append(line[:hs] + line[he + 1:])
        out.append(line[:hs] + "self." + line[hs:])
        out.append(line[:hs] + "cls." + line[hs:])

    # 4. logging call spelled against the wrong logger / level
    for m in re.finditer(r"\b(?:log|logging|logger|LOG|self\.log)\s*\.\s*(\w+)\s*\(", line):
        for base in ("log", "logging", "logger", "self.log"):
            for meth in _LOG_METHODS:
                out.append(line[:m.start()] + base + "." + meth + "(" + line[m.end():])

    # 4b. eager % formatting where lazy / comma formatting was meant
    for m in re.finditer(r"(['\"])\s*%\s*", line):
        if _in_spans(m.start(1), strs) and not _in_spans(m.end(1) - 1, strs):
            pass
        out.append(line[:m.start(1) + 1] + ", " + line[m.end():])
        rest = line[m.end():]
        if rest.startswith("("):
            k = rest.find(")")
            if k > 0:
                out.append(line[:m.start(1) + 1] + ", " + rest[1:k] + rest[k + 1:])
    for m in re.finditer(r"(['\"])\s*,\s*", line):
        out.append(line[:m.start(1) + 1] + " % " + line[m.end():])

    # 5. the wrong attribute of self
    for (a, b) in _ATTR_SWAPS:
        for m in re.finditer(r"\b" + re.escape(a) + r"\b", line):
            out.append(line[:m.start()] + b + line[m.end():])
    for m in re.finditer(r"\.([A-Za-z_][A-Za-z_0-9]*)", line):
        if m.start() >= end or _in_spans(m.start(), strs):
            continue
        for v in _PROJ_ATTRS:
            if v != m.group(1):
                out.append(line[:m.start() + 1] + v + line[m.end():])

    # 6. an option that was never threaded through the call
    for (ns, o, c, op, name) in _callspans(line):
        if op != "(" or c >= end:
            continue
        content = line[o + 1:c]
        if content.strip():
            for kw in _PROJ_KW:
                out.append(line[:c] + ", " + kw + line[c:])
            parts = _split_args(content)
            if parts:
                p0 = o + 1 + parts[0][0]
                for kw in _PROJ_KW[:16]:
                    out.append(line[:p0] + kw + ", " + line[p0:])
        else:
            for kw in _PROJ_KW:
                out.append(line[:c] + kw + line[c:])

    # 6b. a positional argument that should be (or should stop being) a keyword
    _KWN = ["extra_types", "case_sensitive", "evaluate_result", "pos", "endpos",
            "base", "flags", "default", "name", "key", "value", "count",
            "precision", "width", "type", "string", "format", "sep", "maxsplit"]
    for (ns, o, c, op, name) in _callspans(line):
        if op != "(" or c >= end:
            continue
        content = line[o + 1:c]
        for (a, b) in _split_args(content):
            s2, e2 = _trim_span(line, o + 1 + a, o + 1 + b)
            arg = line[s2:e2]
            if not arg:
                continue
            if re.match(r"^[A-Za-z_][A-Za-z_0-9]*$", arg):
                out.append(line[:s2] + arg + "=" + arg + line[e2:])
                for kn in _KWN:
                    if kn != arg:
                        out.append(line[:s2] + kn + "=" + arg + line[e2:])
            m2 = re.match(r"^([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.+)$", arg)
            if m2:
                out.append(line[:s2] + m2.group(2) + line[e2:])
                for kn in _KWN:
                    if kn != m2.group(1):
                        out.append(line[:s2] + kn + "=" + m2.group(2) + line[e2:])

    # 6c. the exception that is raised
    for m in re.finditer(r"\b(\w*Error|\w*Exception|TooManyFields|RepeatedNameError|"
                         r"ValueError|TypeError|KeyError)\b", line):
        for v in ("ValueError", "TypeError", "KeyError", "IndexError",
                  "AttributeError", "NotImplementedError", "RuntimeError",
                  "TooManyFields", "RepeatedNameError", "ParseError"):
            if v != m.group(0):
                out.append(line[:m.start()] + v + line[m.end():])

    # 7. regex flags
    for m in re.finditer(r"re\.[A-Z]+(?:\s*\|\s*re\.[A-Z]+)*", line):
        cur = m.group(0)
        for v in ("re.IGNORECASE", "re.DOTALL", "re.MULTILINE", "re.UNICODE",
                  "re.VERBOSE", "re.IGNORECASE | re.DOTALL",
                  "re.DOTALL | re.IGNORECASE", cur + " | re.IGNORECASE",
                  cur + " | re.DOTALL", "re.IGNORECASE | " + cur,
                  "re.DOTALL | " + cur, "0"):
            if v != cur:
                out.append(line[:m.start()] + v + line[m.end():])

    # 8. curated one token fixes
    for (a, b) in _MICRO:
        start = 0
        while True:
            i = line.find(a, start)
            if i < 0:
                break
            out.append(line[:i] + b + line[i + len(a):])
            start = i + 1

    # 9. a bare name that should be self.<name> / the private spelling
    for (s, e, w) in positions:
        if s and line[s - 1] == ".":
            continue
        for v in ("self." + w, "self._" + w, "_" + w, w + "s", "self." + w + "s"):
            out.append(line[:s] + v + line[e:])
    return out


# --- kind 14 : a condition that needs one more conjunct -----------------------

def _guard_pool(line):
    strs, groups, comment = _scan(line)
    end = comment if comment is not None else len(line)
    names = [w for w in _idents(line) if w not in _KEYWORDS]
    subs = []
    for m in re.finditer(r"([A-Za-z_][A-Za-z_0-9\.]*)\s*\[", line[:end]):
        if not _in_spans(m.start(), strs):
            subs.append(m.group(1))
    pool = []
    tmpl = ["len(%s) > 1", "%s", "not %s", "len(%s) > 0", "%s is not None",
            "%s is None", "len(%s) > 2", "len(%s) >= 1", "len(%s) >= 2",
            "len(%s) == 1", "len(%s) != 1", "%s[0].isdigit()",
            "not %s[0].isdigit()", "%s.isdigit()", "%s[0] == '0'",
            "%s[0] in '<>=^'", "%s[1] in '<>=^'", "%s[0] not in '<>=^'",
            "%s != ''", "%s == ''"]
    who = _dedupe(subs + names)[:6]
    for t in tmpl:
        for nm in who:
            pool.append(t % nm)
    pool += ["len(string) > 1", "len(string) > 2", "len(format) > 1",
             "len(format) > 2", "len(value) > 1", "len(text) > 1",
             "self._case_sensitive", "not self._case_sensitive",
             "case_sensitive", "not case_sensitive", "format", "not format",
             "string", "not string", "value", "not value",
             "base is None", "base is not None", "self.base is None",
             "sign", "zero", "align", "fill", "width", "precision",
             "not width", "not precision"]
    return _dedupe(pool)


def _act_guard(line):
    out = []
    code_end = _code_end(line)
    body = line[:code_end].rstrip()
    tail = line[len(body):]
    pool = _guard_pool(line)[:70]

    m = re.match(r"^(\s*)(if|elif|while)\s+(.+?)\s*:$", body)
    if m:
        ind, kw, cond = m.group(1), m.group(2), m.group(3)
        for g in pool:
            out.append("%s%s %s and %s:%s" % (ind, kw, cond, g, tail))
        for g in pool:
            out.append("%s%s %s or %s:%s" % (ind, kw, cond, g, tail))
        for g in pool:
            out.append("%s%s %s and %s:%s" % (ind, kw, g, cond, tail))
        for g in pool[:24]:
            out.append("%s%s (%s) and %s:%s" % (ind, kw, cond, g, tail))
            out.append("%s%s %s and (%s):%s" % (ind, kw, cond, g, tail))
        out.append("%s%s not (%s):%s" % (ind, kw, cond, tail))

    m = re.match(r"^(\s*)(return|assert|yield)\s+(.+?)$", body)
    if m:
        ind, kw, cond = m.group(1), m.group(2), m.group(3)
        for g in pool[:40]:
            out.append("%s%s %s and %s%s" % (ind, kw, cond, g, tail))
            out.append("%s%s %s or %s%s" % (ind, kw, cond, g, tail))

    # one more conjunct beside an existing and / or
    for m in re.finditer(r"\s+(and|or)\s+", body):
        for g in pool[:36]:
            out.append(body[:m.start()] + " %s %s" % (m.group(1), g) +
                       body[m.start():] + tail)
            out.append(body[:m.end()] + g + " %s " % m.group(1) +
                       body[m.end():] + tail)
    return out


# --- kind 15 : a parenthesis in the wrong place / regex text ------------------

_BRACKET_CLOSE = {"(": ")", "[": "]", "{": "}"}


def _act_paren(line):
    out = []
    strs, groups, comment = _scan(line)
    end = comment if comment is not None else len(line)

    for (o, c, op) in groups[:8]:
        if c >= end:
            continue
        closer = _BRACKET_CLOSE.get(op, ")")
        clen = c - o - 1
        combined = line[o + 1:c] + line[c + 1:]
        limit = len(combined)
        depth = 0
        q = None
        i = clen
        while i < len(combined):
            ch = combined[i]
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
            elif ch in "([{":
                depth += 1
            elif ch in ")]}":
                if depth == 0:
                    limit = i
                    break
                depth -= 1
            elif ch == "#":
                limit = i
                break
            i += 1
        posset = []
        for m in re.finditer(r"\S+", combined):
            posset.append(m.start())
            posset.append(m.end())
        for m in re.finditer(r"[\w\]\)\'\"]+", combined):
            posset.append(m.end())
        good = [p for p in _dedupe(posset) if 0 < p <= limit and p != clen]
        for p in good[:26]:
            out.append(line[:o + 1] + combined[:p] + closer + combined[p:])

    # regular expression / format-spec text
    for (s, e) in strs:
        if s >= end:
            continue
        lit = line[s:e]
        if len(lit) < 2:
            continue
        if lit[:3] in ('"""', "'''") and len(lit) >= 6:
            q, body = lit[:3], lit[3:-3]
        else:
            q, body = lit[0], lit[1:-1]

        def emit(nb):
            if nb != body:
                out.append(line[:s] + q + nb + q + line[e:])

        for (a, b) in _RX_SWAPS:
            start = 0
            while True:
                i = body.find(a, start)
                if i < 0:
                    break
                emit(body[:i] + b + body[i + len(a):])
                start = i + 1
        emit("^" + body)
        emit(body + "$")
        emit("(" + body + ")")
        emit("(?:" + body + ")")
        emit(body + "?")
        emit(body + "+")
        emit(body + "*")
        emit("\\" + body)
        for i in range(len(body)):
            if body[i] in ".*+?()[]{}|^$":
                emit(body[:i] + "\\" + body[i:])
            if body[i] == "\\":
                emit(body[:i] + body[i + 1:])
        if len(body) <= 14:
            for ch in _CLASS_CHARS:
                if ch not in body:
                    emit(body + ch)
                    emit(ch + body)
        if len(body) <= 4:
            for i in range(len(body)):
                for ch in _CLASS_CHARS:
                    emit(body[:i] + ch + body[i + 1:])
        for i in range(len(body)):
            emit(body[:i] + body[i + 1:])
        for m in re.finditer(r"\d+", body):
            v = int(m.group(0))
            for nv in (v + 1, v - 1, 0, 1):
                if nv != v and nv >= 0:
                    emit(body[:m.start()] + str(nv) + body[m.end():])
    return out


# --- ranked variants of the two very large generic acts -----------------------

def _act_char_ranked(line):
    """Same edits as `_act_char` but ordered so that a truncated prefix still
    covers the whole line rather than only its first few columns."""
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
    letters = len(re.findall(r"[A-Za-z]", line))
    if letters * 2 > n:
        cs = ("aeiousrtnlcdmpghbfwyvkxjqz .,'\"-_)(:;0123456789"
              "ETASIOCPRDFMNLWBHG=+*/%<>[]{}!")
    else:
        cs = ("_.,:'\"()[]{}=+-*/%<>0123456789 |?\\!&^~"
              "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
    for ch in cs:
        for i in range(n):
            if line[i] != ch:
                out.append(line[:i] + ch + line[i + 1:])
        for i in range(n + 1):
            out.append(line[:i] + ch + line[i:])
    return out


_PROSE_INSERTS = ["not", "no", "only", "also", "a", "an", "the", "is", "are",
                  "be", "to", "of", "in", "on", "and", "or", "if", "as", "for",
                  "with", "that", "than", "then", "must", "should", "can",
                  "will", "may", "does", "do", "always", "never", "now"]


def _act_word_ranked(line):
    out = []
    toks = [(m.start(), m.end()) for m in _TOKEN_RE.finditer(line)]
    for w in _PROSE_INSERTS:
        for (s, e) in toks:
            out.append(line[:s] + w + " " + line[s:])
        if toks:
            s, e = toks[-1]
            out.append(line[:e] + " " + w + line[e:])
    for m in re.finditer(r"\bnot\s+", line):
        out.append(line[:m.start()] + line[m.end():])
    for m in re.finditer(r"\s+not\b", line):
        out.append(line[:m.start()] + line[m.end():])
    for m in _ALPHA_RE.finditer(line):
        for cand in _corrections(m.group(0)):
            out.append(line[:m.start()] + cand + line[m.end():])
    out.extend(_act_word(line))
    return out


_ALL_ACTS = ([_act_char_ranked, _act_word_ranked] + _ACTS[2:] +
             [_act_project, _act_guard, _act_paren])

_N_KINDS = len(_ALL_ACTS)          # 16 — the router carries kinds 0..15

_CAP = 2000
_QUOTA = {
    0: 640, 1: 700, 2: 320, 3: 420, 4: 430, 5: 340, 6: 260, 7: 280,
    8: 320, 9: 300, 10: 330, 11: 320, 12: 360, 13: 520, 14: 380, 15: 360,
}

_STATE = {"line": None, "used": 0, "seen": None}


def _budget_reset(line):
    _STATE["line"] = line
    _STATE["used"] = 0
    _STATE["seen"] = set()


def _kind_of(act):
    """Invert the router without ever writing the mapping down."""
    for k in range(_N_KINDS):
        if router(WORKED_EXAMPLE[0], WORKED_EXAMPLE[1], k) == act:
            return k
    return None


def observe(line):
    line, _nl = _nl_split(line)
    _budget_reset(line)

    code_end = _code_end(line)
    code = line[:code_end]
    st = line.strip()
    strs, groups, comment = _scan(line)
    outside = _outside_strings(line)
    has_code = bool(code.strip())
    is_comment = st.startswith("#")
    words = re.findall(r"[A-Za-z][A-Za-z']+", line)

    score = 0
    if re.match(r"^(def|class|import|from|return|if|elif|else|for|while|try|"
                r"except|finally|with|raise|assert|yield|del|global|nonlocal|"
                r"lambda|print|pass|break|continue|@)\b", st):
        score += 1
    if "=" in outside:
        score += 1
    if re.search(r"[\w\)\]\'\"]\(", outside):
        score += 1
    if re.search(r"[\w\)\]\'\"]\[", outside):
        score += 1
    if re.search(r"[A-Za-z_]\w*\.[A-Za-z_]\w*", outside):
        score += 1
    if re.search(r"[{}]|::|\bself\b|\bcls\b|\*\*|\+\+|->|%[sdri]\b", outside):
        score += 1
    if st.endswith(":") or st.endswith(",") or st.endswith("\\"):
        score += 1
    if re.search(r"\w_\w|_\w*\(", outside):
        score += 1

    prose = ((not has_code) or is_comment or (len(words) >= 4 and score == 0))
    mixed = (not prose) and len(words) >= 5 and score <= 1
    is_import = bool(re.match(r"^(from|import)\b", st))
    is_cond = bool(re.match(r"^(if|elif|while|assert)\b", st)) or bool(
        re.search(r"(==|!=|<=|>=|[^<>=!]<[^<]|[^<>=!]>[^>]|\bin\b|\bis\b|\band\b|"
                  r"\bor\b|\bnot\b|\breturn\b)", outside))
    str_words = 0
    for (s, e) in strs:
        str_words += len(re.findall(r"[A-Za-z][A-Za-z']+", line[s:e]))
    wordy = (is_comment or comment is not None or str_words >= 3 or
             len(words) >= 5)

    if prose:
        order = [1, 0, 15, 12, 10, 8, 13, 4]
    elif is_import:
        order = [2, 13, 8, 4, 12, 1, 0]
    elif mixed:
        order = [1, 13, 8, 15, 10, 12, 4, 11, 14, 0]
    else:
        order = [13]
        if is_cond:
            order.append(14)
        order += [8, 4, 15, 11, 9, 10, 3, 5, 12, 7]
        if not is_cond:
            order.append(14)
        if "open(" in code:
            order.append(6)
        if wordy:
            order.append(1)
        order.append(0)
    return [k for k in order if 0 <= k < _N_KINDS]


def acts(line, act):
    line, nl = _nl_split(line)
    out = []
    if _STATE["line"] != line or _STATE["seen"] is None:
        _budget_reset(line)
    kind = _kind_of(act)
    if kind is None:
        return []
    try:
        raw = _ALL_ACTS[kind](line)
    except Exception:
        raw = []
    seen = _STATE["seen"]
    room = min(_QUOTA.get(kind, 300), _CAP - _STATE["used"])
    used = 0
    for c in raw:
        if used >= room:
            break
        if not c or c == line or c in seen:
            continue
        seen.add(c)
        out.append(c + nl if nl else c)
        used += 1
    _STATE["used"] += used
    return [c for c in out if c != line]

def candidates(line):
    for kind in observe(line):
        for c in acts(line, router(WORKED_EXAMPLE[0], WORKED_EXAMPLE[1], kind)):
            yield c
