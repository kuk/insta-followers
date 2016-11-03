# encoding: utf8

import re
import os.path
import cjson
import math
from hashlib import sha1
from collections import namedtuple, Counter, defaultdict
from datetime import datetime

import requests as requests_
requests_.packages.urllib3.disable_warnings()

import pandas as pd
import numpy as np
import networkx as nx

import seaborn as sns
from matplotlib import pyplot as plt

from IPython.display import HTML, display


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/37.0.2049.0 Safari/537.36'
}

DATA_DIR = 'data'
JSON_DIR = os.path.join(DATA_DIR, 'json')
JSON_LIST = os.path.join(JSON_DIR, 'list.txt')

GRAPH = 'graph.gexf'
USERS_CHECK = os.path.join(DATA_DIR, 'users_check.xlsx')


InstaUser = namedtuple(
    'InstaUser',
    ['id', 'username', 'name', 'bio', 'image',
     'follows', 'followers']
)
InstaRelatedRecord = namedtuple(
    'InstaRelatedRecord',
    ['id', 'username']
)
InstaMediaRecord = namedtuple(
    'InstaMediaRecord',
    ['id', 'code', 'type', 'user_id', 'username', 'created',
     'comments', 'likes', 'thumb', 'image']
)


def log_progress(sequence, every=None, size=None):
    from ipywidgets import IntProgress, HTML, VBox
    from IPython.display import display

    is_iterator = False
    if size is None:
        try:
            size = len(sequence)
        except TypeError:
            is_iterator = True
    if size is not None:
        if every is None:
            if size <= 200:
                every = 1
            else:
                every = size / 200     # every 0.5%
    else:
        assert every is not None, 'sequence is iterator, set every'

    if is_iterator:
        progress = IntProgress(min=0, max=1, value=1)
        progress.bar_style = 'info'
    else:
        progress = IntProgress(min=0, max=size, value=0)
    label = HTML()
    box = VBox(children=[label, progress])
    display(box)

    index = 0
    try:
        for index, record in enumerate(sequence, 1):
            if index == 1 or index % every == 0:
                if is_iterator:
                    label.value = '{index} / ?'.format(index=index)
                else:
                    progress.value = index
                    label.value = u'{index} / {size}'.format(
                        index=index,
                        size=size
                    )
            yield record
    except:
        progress.bar_style = 'danger'
        raise
    else:
        progress.bar_style = 'success'
        progress.value = index
        label.value = str(index or '?')


def hash_item(item):
    return sha1(item.encode('utf8')).hexdigest()


hash_url = hash_item


def get_json_filename(url):
    return '{hash}.json'.format(
        hash=hash_url(url)
    )


def get_json_path(url):
    return os.path.join(
        JSON_DIR,
        get_json_filename(url)
    )


def load_items_cache(path):
    with open(path) as file:
        for line in file:
            line = line.decode('utf8').rstrip('\n')
            if '\t' in line:
                # several lines in cache got currepted
                hash, item = line.split('\t', 1)
                yield item


def list_json_cache():
    return load_items_cache(JSON_LIST)


def update_items_cache(item, path):
    with open(path, 'a') as file:
        hash = hash_item(item)
        file.write('{hash}\t{item}\n'.format(
            hash=hash,
            item=item.encode('utf8')
        ))
        

def update_json_cache(url):
    update_items_cache(url, JSON_LIST)


def dump_json(path, data):
    with open(path, 'w') as file:
        file.write(cjson.encode(data))


def load_raw_json(path):
    with open(path) as file:
        return cjson.decode(file.read())


def download_json(url):
    response = requests_.get(
        url,
        headers=HEADERS
    )
    try:
        return response.json()
    except ValueError:
        return


def fetch_json(url):
    path = get_json_path(url)
    data = download_json(url)
    dump_json(path, data)
    update_json_cache(url)


def fetch_jsons(urls):
    for url in urls:
        fetch_json(url)


def load_json(url):
    path = get_json_path(url)
    return load_raw_json(path)


def get_insta_url(username):
    return 'https://www.instagram.com/{username}/'.format(
        username=username
    )


def get_insta_query_url(query):
    query = re.sub('\s+', '', query)
    return 'https://www.instagram.com/query/?q={q}'.format(q=query)


def get_insta_related_url(id):
    query = '''
ig_user(%s) {
  chaining {
    nodes {
      blocked_by_viewer,
      followed_by_viewer,
      follows_viewer,
      full_name,
      has_blocked_viewer,
      has_requested_viewer,
      id,
      is_private,
      is_verified,
      profile_pic_url,
      requested_by_viewer,
      username
    }
  }
}
''' % id
    return get_insta_query_url(query)


def get_insta_user_by_username_url(username):
    return 'https://www.instagram.com/{username}/?__a=1'.format(
        username=username
    )


def parse_insta_user_by_username(data):
    if not data:
        return
    data = data['user']
    id = data['id']
    username = data['username']
    name = data['full_name']
    bio = data['biography']
    image = data['profile_pic_url']
    follows = data['follows']['count']
    followers = data['followed_by']['count']
    return InstaUser(
        id, username, name, bio, image,
        follows, followers
    )


def load_insta_user_by_username(username):
    url = get_insta_user_by_username_url(username)
    data = load_json(url)
    return parse_insta_user_by_username(data)


def parse_insta_related(data):
    if 'chaining' not in data:
        return
    for record in data['chaining']['nodes']:
        id = record['id']
        username = record['username']
        yield InstaRelatedRecord(id, username)
        
        
def load_insta_related(id):
    url = get_insta_related_url(id)
    data = load_json(url)
    return parse_insta_related(data)


def make_graph(users):
    graph = nx.DiGraph()
    for user in users:
        source = user.username
        for related in load_insta_related(user.id):
            target = related.username
            graph.add_edge(source, target)
    return graph


def save_graph(graph):
    nx.write_gexf(graph, GRAPH)


def dump_users_check(users, user_indegrees):
    username_indegrees = {}
    for user in user_indegrees:
        username_indegrees[user.username] = user_indegrees[user]
    data = []
    for user in users:
        username = user.username
        url = get_insta_url(username)
        degree = username_indegrees[username]
        data.append([username, url, degree, '+', user.name, user.bio])
    table = pd.DataFrame(
        data,
        columns=['username', 'url', 'degree', 'correct', 'name', 'bio']
    )
    table.to_excel(USERS_CHECK, index=False)


def load_users_check(all=False):
    table = pd.read_excel(USERS_CHECK)
    for _, row in table.iterrows():
        if row.correct in ('+', '\\') or all:
            yield row.username


def get_insta_media_url(username, max_id=None):
    url = 'https://www.instagram.com/{username}/media/'.format(
        username=username
    )
    if max_id is not None:
        url += '?max_id={max_id}'.format(max_id=max_id)
    return url


def parse_timestamp(timestamp):
    return datetime.fromtimestamp(timestamp)


def parse_insta_media(data):
    if not data or 'items' not in data:
        return
    for item in data['items']:
        id = item['id']
        code = item['code']
        type = item['type']

        user = item['user']
        user_id = user['id']
        username = user['username']
        created = parse_timestamp(int(item['created_time']))

        comments = item['comments']['count']
        likes = item['likes']['count']
        
        images = item['images']
        thumb = images['thumbnail']['url']
        image = None
        if 'standard_resolution' in images:
            image = images['standard_resolution']['url']

        yield InstaMediaRecord(
            id, code, type, user_id, username, created,
            comments, likes, thumb, image
        )

        
def load_insta_media(username):
    url = get_insta_media_url(username)
    data = load_json(url)
    return parse_insta_media(data)


def show_insta_user(user):
    html = u'''
<table style="border:none">
  <tr style="border:none">
    <td style="border:none">
      <a href="{url}">
        <img src="{image}" style="min-width:100px;max-width:100px"/>
      </a>
    </td>
    <td style="border:none;vertical-align:top;width:400px">
      <div>
        <b>{name}</b>
      </div>
      <div>
        {bio}
      </div>
      <div style="color:silver">
        follows: {follows}, followed by: {followers}
      </div>
    </td>
  </tr>
<table>
    '''.format(
        image=user.image,
        url=get_insta_url(user.username),
        name=user.name or '',
        bio=user.bio or '',
        follows=user.follows,
        followers=user.followers
    )
    display(HTML(html))


def wrap_sequence(sequence, size=5):
    count = int(math.ceil(len(sequence) / float(size)))
    for index in xrange(count):
        yield sequence[index * size:(index + 1) * size]

        
def format_insta_media(media, size=5):
    yield '<table style="border:none">'
    for chunk in wrap_sequence(media, size):
        yield '<tr style="border:none">'
        for record in chunk:
            yield '<td style="border:none">'
            yield '<img src="{image}" style="min-width:150px;max-width:150px"/>'.format(
                image=record.thumb
            )
            yield '<div style="color:silver">'
            yield u'{date} 💬&nbsp;{comments} ❤&nbsp;{likes}'.format(
                date=record.created.strftime('%Y-%m-%d'),
                comments=record.comments,
                likes=record.likes
            )
            yield '</div>'
            yield '</td>'
        yield '</tr>'
    yield '</table>'

    
def show_insta_media(media):
    html = '\n'.join(format_insta_media(media))
    display(HTML(html))


def show_likes_comments(media):
    xs = []
    ys = []
    for record in media:
        likes = record.likes
        comments = record.comments
        if likes and comments:
            xs.append(likes)
            ys.append(comments)
    fig, ax = plt.subplots()
    ax.scatter(xs, ys, lw=0, s=1, alpha=0.3)
    ax.set_yscale('log')
    ax.set_xscale('log')
    ax.set_xlabel('likes')
    ax.set_ylabel('comments')
