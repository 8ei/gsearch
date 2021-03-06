# -*- coding: utf-8 -*-
#########################################################
# 고정영역
#########################################################
# python
import os
import traceback
import json
try:
    from urllib import quote  # Python 2.X
except ImportError:
    from urllib.parse import quote  # Python 3+

# third-party
from flask import Blueprint, request, render_template, redirect, jsonify, Response
from flask_login import login_required

# sjva 공용
from framework.logger import get_logger
from framework import app, db, scheduler, check_api

# 패키지
package_name = __name__.split('.')[0]
logger = get_logger(package_name)

from .logic import Logic
from .model import ModelSetting

blueprint = Blueprint(
    package_name, package_name,
    url_prefix='/%s' % package_name,
    template_folder=os.path.join(os.path.dirname(__file__), 'templates')
)


def plugin_load():
    Logic.plugin_load()


def plugin_unload():
    Logic.plugin_unload()


plugin_info = {
    "category_name": "service",
    "version": "0.1",
    "name": "gsearch",
    "home": "https://github.com/8ei/gsearch",
    "more": "https://github.com/8ei/gsearch",
    "description": "토렌트 마그넷/파일 정보를 보여주는 플러그인",
    "developer": "summer",
    "zip": "https://github.com/8ei/gsearch/archive/master.zip"
}
#########################################################


# 메뉴 구성.
menu = {
    'main': [package_name, '구글드라이브 검색'],
    'sub': [
        ['setting', '설정'], ['gsearch', '구글드라이브 검색'], ['log', '로그']
    ],
    'category': 'service',
}


#########################################################
# WEB Menu
#########################################################
@blueprint.route('/')
def home():
    return redirect('/%s/gsearch' % package_name)


@blueprint.route('/<sub>')
@login_required
def detail(sub):
    if sub == 'setting':
        arg = ModelSetting.to_dict()
        arg['package_name'] = package_name
        # arg['trackers'] = '\n'.join(json.loads(arg['trackers']))
        arg['tracker_update_from_list'] = [[x, 'https://ngosang.github.io/trackerslist/trackers_%s.txt' % x] for x in Logic.tracker_update_from_list]
        arg['plugin_ver'] = plugin_info['version']
        from system.model import ModelSetting as SystemModelSetting
        ddns = SystemModelSetting.get('ddns')
        arg['json_api'] = '%s/%s/api/json' % (ddns, package_name)
        arg['m2t_api'] = '%s/%s/api/m2t' % (ddns, package_name)
        arg['ps1_down_url'] = ddns + "/file/data/custom/gsearch/summer.ps1"
        arg['reg_down_url'] = ddns + "/file/data/custom/gsearch/gsearch.reg"
        if SystemModelSetting.get_bool('auth_use_apikey'):
            arg['json_api'] += '?apikey=%s' % SystemModelSetting.get('auth_apikey')
            arg['m2t_api'] += '?apikey=%s' % SystemModelSetting.get('auth_apikey')
        return render_template('%s_setting.html' % package_name, sub=sub, arg=arg)
    elif sub == 'search':
        arg = ModelSetting.to_dict()
        arg['package_name'] = package_name
        arg['cache_size'] = len(Logic.torrent_cache)
        return render_template('%s_search.html' % package_name, arg=arg)
    elif sub == 'gsearch':
        arg = ModelSetting.to_dict()
        arg['package_name'] = package_name
        arg['cache_size'] = len(Logic.torrent_cache)
        return render_template('%s_gsearch.html' % package_name, arg=arg)
    elif sub == 'log':
        return render_template('log.html', package=package_name)
    return render_template('sample.html', title='%s - %s' % (package_name, sub))


#########################################################
# For UI                                                          
#########################################################
@blueprint.route('/ajax/<sub>', methods=['GET', 'POST'])
@login_required
def ajax(sub):
    # 설정 저장
    if sub == 'setting_save':
        try:
            ret = Logic.setting_save(request)
            return jsonify(ret)
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
    elif sub == 'creds_save':
        try:
            ret = Logic.creds_save(request)
            return jsonify(ret)
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())            
    elif sub == 'oauth':
        try:
            ret = Logic.oauth()
            return jsonify(ret)
        except Exception as e: 
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())     
    elif sub == 'gsearch':        
        # for local use - default arguments from user db
        try:            
            logger.debug("=================== gsearch 검색 - 검색어: " + request.form['words'] + "  경로검색 옵션: " + request.form['path'])
            words = request.form['words']
            path = request.form['path']
            order1 = request.form['order1']
            order2 = request.form['order2']
            order3 = request.form['order3']
            pageSize = request.form['pageSize']
            # option2 = Logic.gsearch(request.form['option2'])
            # order = Logic.gsearch(request.form['order'])
            gsearch_result = Logic.gsearch(words, path, order1, order2, order3, pageSize) #결과 받아서 전달
            # return torrent_info
            return jsonify({'success': True, 'list': gsearch_result})
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return jsonify({'success': False, 'log': str(e)})
    elif sub == 'gdelete':
        logger.debug(request)
        # for local use - default arguments from user db
        try:
            gdelete_result = Logic.gdelete(request.form['fileId'])
            # return torrent_info
            return jsonify({'success': True, 'list': gdelete_result})
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return jsonify({'success': False, 'log': str(e)})    


#########################################################
# API
#########################################################
@blueprint.route('/api/<sub>', methods=['GET', 'POST'])
@check_api
def api(sub):
    try:
        if sub == 'json':
            data = request.form.to_dict() if request.method == 'POST' else request.args.to_dict()
            if data.get('uri', ''):
                magnet_uri = data.get('uri')
                if not magnet_uri.startswith('magnet'):
                    magnet_uri = 'magnet:?xt=urn:btih:' + magnet_uri

                # override db default by api input
                func_args = {}
                for k in ['scrape', 'use_dht', 'no_cache']:
                    if k in data:
                        func_args[k] = data.get(k).lower() == 'true'
                for k in ['timeout', 'n_try']:
                    if k in data:
                        func_args[k] = int(data.get(k))

                torrent_info = Logic.parse_magnet_uri(magnet_uri, **func_args)
            elif data.get('url', ''):
                torrent_info = Logic.parse_torrent_url(data.get('url'))
            else:
                return jsonify({'success': False, 'log': 'At least one of "uri" or "url" parameter required'})
            return jsonify({'success': True, 'info': torrent_info})

        elif sub == 'm2t':
            if request.method == 'POST':
                return jsonify({'success': False, 'log': 'POST method not allowed'})
            data = request.args.to_dict()
            magnet_uri = data.get('uri', '')
            if not magnet_uri.startswith('magnet'):
                magnet_uri = 'magnet:?xt=urn:btih:' + magnet_uri

            # override db default by api input
            func_args = {}
            for k in ['scrape', 'use_dht']:
                if k in data:
                    func_args[k] = data.get(k).lower() == 'true'
            for k in ['timeout', 'n_try']:
                if k in data:
                    func_args[k] = int(data.get(k))
            func_args.update({'no_cache': True, 'to_torrent': True})
            torrent_file, torrent_name = Logic.parse_magnet_uri(magnet_uri, **func_args)
            resp = Response(torrent_file)
            resp.headers['Content-Type'] = 'application/x-bittorrent'
            resp.headers['Content-Disposition'] = "attachment; filename*=UTF-8''{}".format(quote(torrent_name + '.torrent'))
            return resp
    except Exception as e:
        logger.error('Exception:%s', e)
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'log': str(e)})
