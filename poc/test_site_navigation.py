"""Static site-organization gates; no wallet/API calls or extra dependencies."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
EXPECTED = {'Home': '/', 'Scan': '/#scan', 'NFT': '/nft/', 'Experimental': '/experimental/'}

class Page(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.ids=[]; self.links=[]; self.navs=[]; self.nav=None; self.anchor=None
        self.scripts=[]; self.script=None
        self.feed(text)
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if tag=='nav':self.nav=[];self.navs.append(self.nav)
        if tag=='a':
            self.anchor=[a,'']
            if self.nav is not None:self.nav.append(self.anchor)
        if tag in ('a','link') and a.get('href'):self.links.append(a['href'])
        if tag in ('img','script') and a.get('src'):self.links.append(a['src'])
        if tag=='script':self.script=[a.get('src'), ''];self.scripts.append(self.script)
    def handle_data(self,data):
        if self.anchor is not None:self.anchor[1]+=data
        if self.script is not None:self.script[1]+=data
    def handle_endtag(self,tag):
        if tag=='nav':self.nav=None
        if tag=='a':self.anchor=None
        if tag=='script':self.script=None

def pages():return sorted(DOCS.rglob('*.html'))
def parse(p):return Page(p.read_text(encoding='utf-8'))
def local_target(page,url):
    u=urlsplit(url)
    if u.scheme or u.netloc:return None
    path=(DOCS/unquote(u.path.lstrip('/'))) if u.path.startswith('/') else (page.parent/unquote(u.path)) if u.path else page
    if path.is_dir():path=path/'index.html'
    return path,u.fragment

class Navigation(unittest.TestCase):
    def test_all_pages_have_same_primary_tabs(self):
        for p in pages():
            with self.subTest(page=str(p.relative_to(DOCS))):
                found=[]
                for nav in parse(p).navs:
                    links={text.strip():attrs.get('href') for attrs,text in nav}
                    if all(links.get(k)==v for k,v in EXPECTED.items()):found.append(nav)
                self.assertEqual(len(found),1,'Exactly one shared primary nav is required')
                active=[(a,t.strip()) for a,t in found[0] if a.get('aria-current') not in (None,'false')]
                self.assertEqual(len(active),1)
                expected='NFT' if 'nft'==p.relative_to(DOCS).parts[0] else 'Home' if p==DOCS/'index.html' else 'Experimental'
                self.assertEqual(active[0][1],expected)
    def test_local_links_and_fragments(self):
        for p in pages():
            for link in parse(p).links:
                target=local_target(p,link)
                if target is None:continue
                path,fragment=target
                with self.subTest(page=str(p.relative_to(DOCS)),link=link):
                    self.assertTrue(path.exists(),str(path))
                    if fragment and path.suffix=='.html':self.assertIn(unquote(fragment),parse(path).ids)
    def test_unique_ids(self):
        for p in pages():
            ids=parse(p).ids
            with self.subTest(page=str(p.relative_to(DOCS))):self.assertEqual(len(ids),len(set(ids)))
    def test_existing_functional_scripts_unchanged(self):
        # Compare against the preceding deployed navigation baseline, not future HEAD.
        for p in pages():
            relative=p.relative_to(ROOT).as_posix()
            r=subprocess.run(['git','show','de580f2:'+relative],cwd=ROOT,capture_output=True)
            if r.returncode:continue # new hub page
            before=Page(r.stdout.decode('utf-8')).scripts
            after=parse(p).scripts
            with self.subTest(page=relative):self.assertEqual(before,after,'Navigation must not change functional script bodies or sources')
    def test_hubs_cover_existing_destinations(self):
        nft=set(parse(DOCS/'nft/index.html').links)
        experiments=set(parse(DOCS/'experimental/index.html').links)
        def paths(page,links):
            return {t[0].resolve() for u in links if (t:=local_target(page,u)) is not None}
        np=paths(DOCS/'nft/index.html',nft); ep=paths(DOCS/'experimental/index.html',experiments)
        for name in ['genesis','genesis/mint','emberlong','bonsai','facade','rooftop']:
            self.assertIn((DOCS/'nft'/name/'index.html').resolve(),np)
        for name in ['market-preview/index.html','market-preview/wallet.html','market-preview/chain.html','ble/index.html','verify/index.html','j/index.html']:
            self.assertIn((DOCS/name).resolve(),ep)

if __name__=='__main__':unittest.main(verbosity=2)
