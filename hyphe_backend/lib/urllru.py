#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
URL/LRU library to manage, build and clean original URLs and corresponding LRUs
"""

import re, urllib
from urlparse import urljoin, urlparse

lruPattern = re.compile("^s:[^|]+(\|t:[^|]+)?(\|h:[^|]+)+")
lruFullPattern = re.compile("^([^:/?#]+):(?://([^/?#]*))?([^?#]*)(?:\?([^#]*))?(?:#(.*))?$")
lruSchemePattern = re.compile("https?")
lruAuthorityPattern = re.compile("^(?:([^:]+)(?::([^@]+))?\@)?(\[[\da-f]*:[\da-f:]*\]|[^\s:]+)(?::(\d+))?$", re.I)
lruStems = re.compile(r'(?:^|\|)([shtpqf]):')
queryStems = re.compile(r'(?:^|&)([^=]+)=([^&]+)')
special_hosts = re.compile(r'localhost|(\d{1,3}\.){3}\d{1,3}|\[[\da-f]*:[\da-f:]*\]', re.I)

def uri_decode(text):
    try:
        return urllib.unquote(text.encode('utf-8')).decode('utf-8')
    except:
        return urllib.unquote(text)

def uri_encode(text, safechars=''):
    try:
        return urllib.quote(text.encode('utf-8'), safechars).decode('utf-8')
    except:
        return urllib.quote(text, safechars)

def uri_recode(text, safechars='', query=False):
    if query:
        return uri_recode_query(text)
    return uri_encode(uri_decode(text), safechars)

def uri_recode_query(query):
    elements = queryStems.split(query)
    if len(elements) == 1:
        return uri_recode(query)
    return "&".join(["%s=%s" % (uri_recode(elements[1+3*i]), uri_recode(elements[2+3*i])) for i in range(int(len(elements[1:])/3))])

def lru_parent_prefixes(lru):
    res = []
    lru_arr = [k for _,_,k in split_lru_in_stems(lru)]
    lru_arr.pop()
    while lru_arr:
        res.append("|".join(lru_arr)+"|")
        lru_arr.pop()
    return res

def split_lru_in_stems(lru, check=True):
    elements = lruStems.split(lru.rstrip("|"))
    if not check and len(elements) < 2:
        return []
    if len(elements) < 2 or elements[0] != '' or (check and (len(elements) < 6 or elements[1] != 's' or elements[5] != 'h') and not special_hosts.match(elements[4])):
        raise ValueError("ERROR: %s is not a proper LRU." % lru)
    return [(elements[1+2*i], elements[2+2*i], "%s:%s" % (elements[1+2*i], elements[2+2*i])) for i in range(int(len(elements[1:])/2))]

def url_clean(url):
    if not url or url.strip() == "":
        return None
    # Fix missing http
    if not url.startswith('http'):
        url = "http://%s" % url.lstrip('/')
    # Lowerize host since some servers answer badly when querying upcase hosts
    host = urlparse(url)[1]
    return url.replace("://"+host, "://"+host.lower())

titlize_url_regexp = re.compile(r'(https?://|[./#])', re.I)
def url_shorten(url):
    return titlize_url_regexp.sub(' ', uri_decode(url)).strip().title().encode('utf-8')

def name_url(url):
    host = []
    path = ""
    name = ""
    lasthost = ""
    pathdone = False
    for (k,v,_) in split_lru_in_stems(url_to_lru_clean(url)):
        if k == "h" and v != "www":
            lasthost = v.title()
            if host or len(lasthost) > 3:
                host.insert(0, lasthost)
        elif k == "p" and v:
            path = " %s/%s" % ("/..." if pathdone else "", v)
            pathdone = True
        elif k == "q" and v:
            name += ' ?%s' % v
        elif k == "f" and v:
            name += ' #%s' % v
    if not host and lasthost:
        host = [lasthost]
    return ".".join(host) + path + name

def url_to_lru(url, encode_utf8=True):
    """
    Convert a URL to a LRU
    >>> url_to_lru("http://www.google.com/search?q=text&p=2")
    's:http|t:80|h:com|h:google|h:www|p:search|q:q=text&p=2|'
    """
    try:
        lru = lruFullPattern.match(url)
    except:
        raise ValueError("Not an url: %s" % url)
    if lru:
        scheme, authority, path, query, fragment = lru.groups()
        if lruSchemePattern.match(scheme) and authority:
            hostAndPort = lruAuthorityPattern.match(authority)
            if hostAndPort:
                _, _, host, port = hostAndPort.groups()
                if special_hosts.match(host):
                    host = [host]
                else:
                    host = host.lower().split(".")
                host.reverse()
                tokens = ["s:" + scheme.lower(), "t:"+ (port if port else (str(443) if scheme == "https" else str(80)))]
                if host:
                    tokens += ["h:"+stem for stem in host if stem]
                if path:
                    path = uri_recode(path, '/+')
                    if len(path) and path.startswith("/"):
                        path = path[1:]
                    tokens += ["p:"+stem for stem in path.split("/")]
                if query is not None:
                    tokens.append("q:"+uri_recode_query(query))
                if fragment is not None:
                    fragment = uri_recode(fragment)
                    tokens.append("f:"+fragment)
                res_lru = "|".join(tokens)
                if encode_utf8:
                    try:
                        return add_trailing_pipe(res_lru).encode('utf-8')
                    except:
                        pass
                return add_trailing_pipe(res_lru)
    raise ValueError("Not an url: %s" % url)

def url_to_lru_clean(url, encode_utf8=True):
    return lru_clean(url_to_lru(url, encode_utf8))

def lru_to_url(lru, encode_utf8=True, nocheck=False):
    """
    Convert a LRU to a URL
    >>> lru_to_url('s:http|t:80|h:com|h:google|h:www|p:search|')
    'http://www.google.com/search'
    >>> lru_to_url('s:http|t:80|h:com|h:google|h:www|p:search|q:q=text&p=2|')
    #'http://www.google.com/search?q=text&p=2'
    """

    if not lruPattern.match(lru) and not nocheck:
        raise ValueError("Not an lru: %s" % lru)

    stem_types = []
    lru = lru.rstrip("|")
    lru_list = [[k, t] for k, t, _ in split_lru_in_stems(lru, not nocheck)]
    for stem in lru_list:
        if stem[0] not in stem_types:
            stem_types.append(stem[0])
    url = [x[1] for x in filter(lambda (k, stem): k == "s", lru_list)][0] + "://"
    h = [x[1] for x in filter(lambda (k, stem): k == "h", lru_list)]
    h.reverse()
    url += ".".join(h)
    if "t" in stem_types:
        port = [x[1] for x in filter(lambda (k, stem): k == "t", lru_list)][0]
        if port and port != '80' and port != '443':
            url += ":" + port
    if "p" in stem_types:
        path = "/".join([x[1] for x in filter(lambda (k, stem): k=="p", lru_list)])
        if path:
            url += "/" + uri_recode(path, '/+')
        if not path and ['p', ''] in lru_list:
            url += "/"
    if "q" in stem_types:
        query = [x[1] for x in filter(lambda (k, stem): k == "q", lru_list)][0]
        if query or ['q', ''] in lru_list:
            url += "?" + uri_recode_query(query)
    if "f" in stem_types:
        fragment = [x[1] for x in filter(lambda (k, stem): k == "f", lru_list)][0]
        if fragment or ['f', ''] in lru_list:
            url += "#" + uri_recode(fragment)
    if encode_utf8:
        try:
            return url.encode('utf-8')
        except:
            pass
    return url

def url_clean_and_convert(url, lru_encode_utf8=True):
    url = url_clean(url)
    lru = url_to_lru_clean(url, lru_encode_utf8)
    return url, lru

def lru_clean_and_convert(lru, url_encode_utf8=True):
    lru = lru_clean(lru)
    url = lru_to_url(lru, url_encode_utf8)
    return url, lru

# Removing port if 80 (http) or 443 (https):
def lru_strip_standard_ports(lru):
    return add_trailing_pipe("|".join([stem for _, _, stem in split_lru_in_stems(lru, False) if not stem in ['t:80', 't:443']]))

def lru_lowerize_host(lru):
    return add_trailing_pipe("|".join([stem.lower() if k in ['s', 'h'] else stem for k,_, stem in split_lru_in_stems(lru)]))

# Removing subdomain if www:
def lru_strip_www(lru):
    return add_trailing_pipe("|".join([stem for k, t, stem in split_lru_in_stems(lru) if k != 'h' or t != "www" ]))

# Removing slash at the end if ending with path or host stem:
re_host_trailing_slash = re.compile(r'(h:[^\|]*)\|p:\|?$')
def lru_strip_host_trailing_slash(lru):
    return re_host_trailing_slash.sub(r'\1', lru)

# Remove slash at the end of path for webentity defining lru prefixes:
re_path_trailing_slash = re.compile(r'(p:\|?)+$')
def lru_strip_path_trailing_slash(lru):
    return re_path_trailing_slash.sub(r'\1', lru)

# Removing anchors:
def lru_strip_anchors(lru) :
    return add_trailing_pipe("|".join([stem for k, _, stem in split_lru_in_stems(lru) if k != "f"]))

# Order query parameters alphabetically:
queryRegexp = re.compile(r"\|q:([^|]*)")
def lru_reorder_query(lru) :
    match = queryRegexp.search(lru)
    if match is not None and match.group(1) is not None :
        res = match.group(1).split("&")
        res.sort()
        lru = lru.replace(match.group(1), "&".join(res))
    return add_trailing_pipe(lru)

def lru_uriencode(lru):
    return add_trailing_pipe("|".join(["%s:%s" % (k, uri_recode(t, safechars=('/+' if k == 'p' else ''), query=(k=='q'))) if k in ['p', 'q', 'f'] else stem for k, t, stem in split_lru_in_stems(lru)]))

def add_trailing_pipe(lru):
    if not lru.endswith("|"):
        lru += "|"
    return lru

#Clean LRU by applying selection of previous filters
def lru_clean(lru):
    lru = lru_strip_standard_ports(lru)
    lru = lru_lowerize_host(lru)
#    lru = lru_strip_www(lru)
    lru = lru_strip_host_trailing_slash(lru)
#    lru = lru_strip_anchors(lru)
#    lru = lru_reorder_query(lru)
    lru = lru_uriencode(lru)
    lru = add_trailing_pipe(lru)
    return lru

def lru_is_full_precision(lru, precision_exceptions = []):
    return (lru in precision_exceptions)

re_host_lru = re.compile(r'(([sth]:[^|]*(\||$))+)', re.I)
def lru_get_host_url(lru):
    return lru_to_url(re_host_lru.match(lru).group(1), False)

re_path_lru = re.compile(r'(([sthp]:[^|]*(\||$))+)', re.I)
def lru_get_path_url(lru):
    return lru_to_url(re_path_lru.match(lru).group(1), False)

def lru_get_head(lru, precision_exceptions = []):
    possible_result = ""
    for precision_exception in precision_exceptions:
        if lru.startswith(precision_exception) and len(precision_exception) > len(possible_result):
            possible_result = precision_exception
    if possible_result:
        return possible_result
    return add_trailing_pipe(re_host_lru.match(lru).group(1))

# Identify links which are nodes
def lru_is_node(lru, precision_limit = 1, precision_exceptions = [], lru_head = None):
    if not lru_head:
        lru_head = lru_get_head(lru, precision_exceptions)
    return (len(split_lru_in_stems(lru.replace(lru_head, ''), False)) <= precision_limit)

# Get a LRU's node
def lru_get_node(lru, precision_limit = 1, precision_exceptions = [], lru_head = None) :
# need to add check for exceptions
    if not lru_head:
        lru_head = lru_get_head(lru, precision_exceptions)
    stems = [stem for _, _, stem in split_lru_in_stems(lru.replace(lru_head, ''), False)[:precision_limit]]
    stems.insert(0, lru_head.strip("|"))
    return add_trailing_pipe("|".join(stems))

def lru_variations(lru, https=True, www=True, encode_utf8=False):
    listLRUs = [lru]
    url = lru_to_url(lru, encode_utf8)
    url2 = None
    if "s:http|" in lru:
        lru2 = lru.replace("s:http|", "s:https|", 1)
    elif "s:https|" in lru:
        lru2 = lru.replace("s:https|", "s:http|", 1)
    if lru2:
        listLRUs.append(lru2)
        url2 = lru_to_url(lru2, encode_utf8)
    if lru.count("|h:") == 1:
        return listLRUs
    if "//www." in url:
        listLRUs.append(url_to_lru_clean(url.replace("//www.", "//", 1), encode_utf8))
        if url2:
            listLRUs.append(url_to_lru_clean(url2.replace("//www.", "//", 1), encode_utf8))
    else:
        listLRUs.append(url_to_lru_clean(url.replace("//", "//www.", 1), encode_utf8))
        if url2:
            listLRUs.append(url_to_lru_clean(url2.replace("//", "//www.", 1), encode_utf8))
    return listLRUs

def has_prefix(lru, prefixes):
    if prefixes:
        return any((lru.startswith(p) for p in prefixes))
    return False


# TESTS
#url = "http://medialab.sciences-po.fr/hci"
#lru = urlTokenizer(url)
#print lru
#print lru.split("|")[0:5]
#print lruRebuild(lru)

#print getUrl("s:http|h:fr|h:sciences-po|h:www")
#print getUrl("s:http|h:fr|h:sciences-po|h:medialab")
#print getUrl("s:http|h:fr|h:sciences-po|h:www|p:dans|p:ton|p:cul.html")

#    testlru = "s:http|t:80|h:org|h:mongodb|h:www|p:display|p:DOCS|p:Verifying+Propagation+of+Writes+with+getLastError|q:f=1&sg=3&a=3&b=34&_675=5&loiyy=hdsjk|f:HGYT"
#    print "TEST : " + testlru + "\nTEST : " + lru_clean(testlru)

