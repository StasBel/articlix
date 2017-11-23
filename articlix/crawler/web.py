import logging
import time
from collections import namedtuple
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from contexttimer import Timer
from dateutil import parser as date_parser
from lazy_property import LazyProperty as lazy_property

from articlix.crawler import USER_AGENT
from articlix.crawler.article import Article
from articlix.crawler.exception import FetchError
from articlix.crawler.url import Url

logger = logging.getLogger(__name__)


class Page:
    def __init__(self, url, headers, text):
        self.url = url
        self.head = headers
        self.text = text

    @lazy_property
    def date(self):
        date = self.head.get('Date', None)
        if date is not None:
            date = date_parser.parse(date)
        return date

    @lazy_property
    def last_modified(self):
        last_modified = self.head.get('Last-Modified', None)
        if last_modified is not None:
            last_modified = date_parser.parse(last_modified)
        return last_modified

    @lazy_property
    def allow_cache(self):
        return not self._have_perm('NOCACHE')

    @lazy_property
    def allow_follow(self):
        return not self._have_perm('NOFOLLOW')

    def links_gen(self):
        if not self.allow_follow:
            return

        for link_node in self.soup.find_all('a'):
            url_str = link_node.get('href')
            if url_str is None: continue
            url = Url(url_str)
            url = url if url.is_absolute else self.url + url
            if url.is_valid: yield url

    @lazy_property
    def soup(self):
        return BeautifulSoup(self.text, 'html.parser')

    def read(self):
        return Article(self)

    def _have_perm(self, perm):
        for tag in self.soup.find_all('ROBOTS', 'meta'):
            if perm in tag['content'].split(', '):
                return True
        return False


Response = namedtuple('Response', 'headers text elapsed ended')


def fetch_raw(url, method='GET', strict=True, timeout=3):
    try:
        with Timer() as t:
            r = requests.request(method, str(url),
                                 headers={'User-Agent': USER_AGENT},
                                 timeout=timeout)
            r.raise_for_status()
        return Response(r.headers, r.text, t.elapsed, t.end)
    except Exception as e:
        if strict:
            raise FetchError("Failed to get data") from e
    return None


class Fetcher:
    def __init__(self, delay=None, use_adaptive=True,
                 adaptive_scale=5, upper_bound=3):
        self.delay = delay
        self.use_adaptive = use_adaptive
        self.adaptive_scale = adaptive_scale
        self.upper_bound = upper_bound

        self._t = None
        self._last_fetched = None

    def __call__(self, url):
        self._cool_down()
        headers, text, self._t, self._last_fetched = fetch_raw(url)
        logging.info("Last fetched time is `%s`.", self._last_fetched)
        return Page(url, headers, text)

    def _cool_down(self):
        if self._last_fetched is None:
            return

        def cutb(t):
            return max(0, min(t, self.upper_bound))

        time_passed = time.time() - self._last_fetched

        if self.delay is not None:
            time.sleep(cutb(self.delay - time_passed))

        if self.delay is None and self.use_adaptive:
            time.sleep(cutb(self.adaptive_scale * self._t - time_passed))


class Site:
    DEFAULT_ROBOTS = 'User-Agent: *\nAllow: /\n'

    def __init__(self, url):
        self.url = url

    def allow_crawl(self, url):
        return self._robots.can_fetch(USER_AGENT, str(url))

    def fetch(self, url):
        return self._fetcher(url)

    @lazy_property
    def _robots(self):
        robots = RobotFileParser()
        r = fetch_raw(self.url.site + 'robots.txt', strict=False)
        if r is None:
            robots.parse(self.DEFAULT_ROBOTS.splitlines())
        else:
            robots.parse(r.text.splitlines())
        return robots

    @lazy_property
    def _fetcher(self):
        crawl_delay = self._crawl_delay
        if crawl_delay is None:
            request_rate = self._request_rate
            if request_rate is not None:
                crawl_delay = request_rate[1] / request_rate[0]
        return Fetcher(crawl_delay)

    @lazy_property
    def _crawl_delay(self):
        try:
            return self._robots.crawl_delay(USER_AGENT)
        except:
            return None

    @lazy_property
    def _request_rate(self):
        try:
            return self._robots.request_rate(USER_AGENT)
        except:
            return None
