from __future__ import annotations

import hashlib
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parents[1]
MIN_SCORE = 0.08
WORD_WEIGHT = 0.7
ALIASES = {
    'رسوم':'fees fee', 'استرداد':'refund', 'مرفوض':'rejected', 'رفض':'reject',
    'سحب':'withdrawal', 'مراجعة':'review', 'هوية':'identity', 'جوال':'mobile',
    'تحقق':'verification', 'التحقق':'verification', 'لوحة':'sign', 'اللوحة':'sign',
    'مضيئة':'illuminated', 'المضيئة':'illuminated', 'بناء':'building',
    'عطلة':'weekend', 'التصعيد':'escalation', 'تصعيد':'escalation',
}


def normalise(text):
    text = unicodedata.normalize('NFKC', text).lower()
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.sub(r'\s+',' ',text).strip()


def expand_query(query):
    query = normalise(query)
    words = set(re.findall(r'\w+',query))
    additions = [value for key,value in ALIASES.items() if key in words]
    return query + (' ' + ' '.join(additions) if additions else '')


class PolicyIndex:
    def __init__(self, documents):
        self.documents = documents
        if not documents: raise ValueError('No policy documents available')
        text = [normalise(d['text']) for d in documents]
        self.words = TfidfVectorizer(ngram_range=(1,2),sublinear_tf=True,stop_words='english')
        self.characters = TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5),sublinear_tf=True)
        self.word_matrix = self.words.fit_transform(text)
        self.character_matrix = self.characters.fit_transform(text)

    def search(self, query, mode='B', limit=2):
        if mode not in {'A','B'}: raise ValueError('Search mode must be A or B')
        if not query.strip() or len(query)>1000: raise ValueError('Query must contain 1–1000 characters')
        if not 1<=limit<=5: raise ValueError('Invalid result limit')
        expanded = expand_query(query)
        word_scores = (self.word_matrix @ self.words.transform([expanded]).T).toarray().ravel()
        scores = word_scores
        if mode=='B':
            char_scores = (self.character_matrix @ self.characters.transform([expanded]).T).toarray().ravel()
            scores = WORD_WEIGHT*word_scores+(1-WORD_WEIGHT)*char_scores
        ordered = sorted(range(len(scores)),key=lambda i:(-scores[i],self.documents[i]['id']))
        results = []
        terms = set(re.findall(r'\w+',expanded))
        for i in ordered[:limit]:
            if scores[i]<MIN_SCORE: continue
            document = self.documents[i]
            paragraphs = [p.strip() for p in document['text'].split('\n\n') if len(p.strip())>40]
            snippet = max(paragraphs,key=lambda p:sum(t in normalise(p) for t in terms)) if paragraphs else document['text']
            title = next((line.lstrip('# ').strip() for line in document['text'].splitlines() if line.startswith('# ')),document['id'])
            results.append({'id':document['id'],'title':title,'text':document['text'][:4500],
                            'snippet':snippet[:600],'score':round(float(scores[i]),6)})
        return results


def documents():
    return [{'id':p.stem,'text':p.read_text(encoding='utf-8')} for p in sorted((ROOT/'data/policies').glob('*.md'))]


def corpus_signature():
    return tuple((str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in sorted((ROOT/'data/policies').glob('*.md')))


@lru_cache(maxsize=2)
def _cached_index(signature):
    return PolicyIndex(documents())


def policy_search(query, mode='B', limit=2):
    return _cached_index(corpus_signature()).search(query,mode,limit)
