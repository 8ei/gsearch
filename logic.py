# -*- coding: utf-8 -*-
#########################################################
# python
import os
import re
import sys
import traceback
import subprocess
import json
import time
from datetime import datetime
import platform
import tarfile
import tempfile
import shutil
import ntpath
try:
    from urlparse import urlparse
    from urllib import urlretrieve
except ImportError:
    from urllib.parse import urlparse
    from urllib.request import urlretrieve

# third-party
import requests
from sqlitedict import SqliteDict

# sjva 공용
from framework import db, scheduler, app
from framework.util import Util

# 패키지
from .plugin import logger, package_name
from .model import ModelSetting, db_file
import google_oauth # 구글 드라이브 인증
        
sys.path.append('/usr/lib/python2.7/site-packages')

service = google_oauth.service # 구글 드라이브 인증
page_token = None # 구글 드라이브 인증

#########################################################


def pathscrub(dirty_path, os=None, filename=False):
    """
    Strips illegal characters for a given os from a path.
    :param dirty_path: Path to be scrubbed.
    :param os: Defines which os mode should be used, can be 'windows', 'mac', 'linux', or None to auto-detect
    :param filename: If this is True, path separators will be replaced with '-'
    :return: A valid path.
    """
    
    os_mode = 'windows'  # Can be 'windows', 'mac', 'linux' or None. None will auto-detect os.
    # Replacement order is important, don't use dicts to store
    platform_replaces = {
        'windows': [
            ['[:*?"<>| ]+', ' '],  # Turn illegal characters into a space
            [r'[\.\s]+([/\\]|$)', r'\1'],
        ],  # Dots cannot end file or directory names
        'mac': [['[: ]+', ' ']],  # Only colon is illegal here
        'linux': [],  # No illegal chars
    }

    # See if global os_mode has been defined by pathscrub plugin
    if os_mode and not os:
        os = os_mode

    if not os:
        # If os is not defined, try to detect appropriate
        drive, path = ntpath.splitdrive(dirty_path)
        if sys.platform.startswith('win') or drive:
            os = 'windows'
        elif sys.platform.startswith('darwin'):
            os = 'mac'
        else:
            os = 'linux'
    replaces = platform_replaces[os]

    # Make sure not to mess with windows drive specifications
    drive, path = ntpath.splitdrive(dirty_path)

    if filename:
        path = path.replace('/', ' ').replace('\\', ' ')
    # Remove spaces surrounding path components
    path = '/'.join(comp.strip() for comp in path.split('/'))
    if os == 'windows':
        path = '\\'.join(comp.strip() for comp in path.split('\\'))
    for search, replace in replaces:
        path = re.sub(search, replace, path)
    path = path.strip()
    # If we stripped everything from a filename, complain
    if filename and dirty_path and not path:
        raise ValueError(
            'Nothing was left after stripping invalid characters from path `%s`!' % dirty_path
        )
    return drive + path


class Logic(object):
    # 디폴트 세팅값
    db_default = {
        'sjva_driveId': '0APysWOqmhluvUk9PVA,0AKsuG07ZgpERUk9PVA,0AFDcdQuiZjpSUk9PVA,0AKgSZgnJ4FyTUk9PVA',
        'path_count': '50',
        'plex_path': '',
        'win_path': '',
        'path1': '',
        'path2': '',
        'path3': '',
        'use_dht': 'True',
        'scrape': 'False',
        'timeout': '15',
        'trackers': '',
        'n_try': '3',
        'tracker_last_update': '1970-01-01',
        'tracker_update_every': '30',
        'tracker_update_from': 'best',
        'libtorrent_build': '191217',
        'http_proxy': '',
        'list_pagesize': '20'
    }

    torrent_cache = None

    tracker_update_from_list = ['best', 'all', 'all_udp', 'all_http', 'all_https', 'all_ws', 'best_ip', 'all_ip']

    @staticmethod
    def db_init():
        try:
            for key, value in Logic.db_default.items():
                if db.session.query(ModelSetting).filter_by(key=key).count() == 0:
                    db.session.add(ModelSetting(key, value))
            db.session.commit()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def plugin_load():
        try:
            # DB 초기화
            Logic.db_init()

            # 편의를 위해 json 파일 생성
            from .plugin import plugin_info
            Util.save_from_dict_to_json(plugin_info, os.path.join(os.path.dirname(__file__), 'info.json'))

            #
            # 자동시작 옵션이 있으면 보통 여기서
            #
            # 토렌트 캐쉬 초기화
            Logic.cache_init()

            # tracker 자동 업데이트
            # tracker_update_every = ModelSetting.get_int('tracker_update_every')
            # tracker_last_update = ModelSetting.get('tracker_last_update')
            # if tracker_update_every > 0:
            #     if (datetime.now() - datetime.strptime(tracker_last_update, '%Y-%m-%d')).days >= tracker_update_every:
            #         Logic.update_tracker()
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def plugin_unload():
        try:
            logger.debug('%s plugin_unload', package_name)
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    @staticmethod
    def setting_save(req):
        try:
            for key, value in req.form.items():
                logger.debug('Key:%s Value:%s', key, value)
                entity = db.session.query(ModelSetting).filter_by(key=key).with_for_update().first()
                entity.value = value
            db.session.commit()
            return True
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())
            return False

    # 기본 구조 End
    ##################################################################

    @staticmethod
    def cache_init():
        if Logic.torrent_cache is None:
            Logic.torrent_cache = SqliteDict(
                db_file, tablename='plugin_{}_cache'.format(package_name), encode=json.dumps, decode=json.loads, autocommit=True
            )

    @staticmethod
    def tracker_save(req):
        for key, value in req.form.items():
            logger.debug({'key': key, 'value': value})
            if key == 'trackers':
                value = json.dumps(value.split('\n'))
            logger.debug('Key:%s Value:%s', key, value)
            entity = db.session.query(ModelSetting).filter_by(key=key).with_for_update().first()
            entity.value = value
        db.session.commit()

    @staticmethod
    def update_tracker():
        # https://github.com/ngosang/trackerslist
        src_url = 'https://ngosang.github.io/trackerslist/trackers_%s.txt' % ModelSetting.get('tracker_update_from')
        new_trackers = requests.get(src_url).content.decode('utf8').split('\n\n')[:-1]
        ModelSetting.set('trackers', json.dumps(new_trackers))
        ModelSetting.set('tracker_last_update', datetime.now().strftime('%Y-%m-%d'))

    @staticmethod
    def size_fmt(num, suffix='B'):
        # Windows에서 쓰는 단위로 가자 https://superuser.com/a/938259
        for unit in ['','K','M','G','T','P','E','Z']:
            if abs(num) < 1000.0:
                return "%3.1f %s%s" % (num, unit, suffix)
            num /= 1024.0
        return "%.1f %s%s" % (num, 'Y', suffix)

    # gsearch 추가 - 구글드라이브 검색 기능 ######################################
    @staticmethod
    def gpath2(fileId):
        tree2 = ""
        print(fileId)
        file = service.files().get(fileId=fileId, 
                                        fields='name, parents, teamDriveId',
                                        supportsAllDrives='true',
                                        supportsTeamDrives='true').execute()
        print(file)
        parent = file['parents']
        print(parent)
        if parent:
            while True:
                folder = service.files().get(fileId=parent[0], 
                                                fields='name, parents, teamDriveId',
                                                supportsAllDrives='true',
                                                supportsTeamDrives='true').execute()
                # parent = folder.get('parents') #팀드라이브, 내드라이브 구분을 위해 위치 변경
                parent = folder.get('parents')

                if parent is None:
                    if folder.get('name') == u"내 드라이브":
                        tree2 = folder.get('name') + "/" + tree2
                    elif folder.get('name') == "드라이브":
                        drive_name = service.drives().get(driveId=folder.get('teamDriveId')).execute()
                        tree2 = drive_name.get('name') + "/" + tree2
                        break
                    break
                # tree.append({'id': parent[0], 'name': folder.get('name')})
                parent = folder.get('parents')
                tree2 = folder.get('name') + "/" + tree2
        file['fullPath'] = tree2
        print(tree2)
        return(tree2)


    @staticmethod
    def gsearch(words, path_option, order1, order2, order3, pageSize):
        start_time = time.time()  # 작업 소요시간 측정을 위한 시작 시간 저장
        words = words.strip()
        query = ""
        path_count = int(ModelSetting.get('path_count')) - 1
        sjva_driveId = ModelSetting.get('sjva_driveId')

        for word in words.split(): # 확장자 검색이 가능하게 만들고 검색 정확도 향상을 위해 api 쿼리에 and 연산자 추가
            if word == words.split()[0] and query == "": # 첫 단어일 때
                query = "name contains \'" + word + "\'"
                continue
            query = query + " and " + "name contains \'" + word + "\'"

        while True:
            # response = service.files().list(q="name contains \'" + words + "\'",
            response = service.files().list(q=query,
                                                spaces='drive',
                                                fields='nextPageToken, files(id, name, mimeType, parents, driveId, md5Checksum, size, owners, thumbnailLink, modifiedTime, sharingUser, iconLink)',
                                                supportsAllDrives='true',
                                                supportsTeamDrives='true',
                                                includeTeamDriveItems='true',
                                                includeItemsFromAllDrives='true',
                                                corpora='allDrives',
                                                # driveId='0AByHal5RqyziUk9PVA',
                                                orderBy=order3 + ',' + order1 + "," + order2,
                                                pageSize=pageSize,
                                                pageToken=page_token).execute()
            
            i = -1
            folder_name_cache = {} #googld api에 같은 쿼리를 하지 않기 위해서 쿼리 결과를 캐쉬로 저장함
            for file in response.get('files', []):
                i = i + 1
                response['files'][i]['fullPath'] = "" # 이 키가 없으면 make_list 에러남
                response['files'][i]['dupe'] = False
                ii = 0
                
                for file2 in response.get('files', []): # MD5 중복 체크
                    if file.get('md5Checksum') is not None and file2.get('md5Checksum') is not None:
                        
                        if file['md5Checksum'] == file2['md5Checksum']:
                            ii = ii + 1
                            if ii > 1:                
                                response['files'][i]['dupe'] = True
                                break
                            # else:
                            #     response['files'][i]['dupe'] = False

                for sjva_drive in sjva_driveId.split(','): # SJVA 임시저장소 회피
                    if file.get('driveId') == sjva_drive: 
                        response['files'][i]['sjva'] = True
                        break
                if response['files'][i].get('sjva') is True or i > path_count or i > 100: # 경로 파싱 최대 100개 까지 또는 설정값을 따름
                    continue
                
                tree2 = "" #패스 파싱 함수에서 실행
                fileId = file.get('id')
                if file.get('parents'): #공유된 파일중에 parents 가 없는 경우 예외처리
                    parent = file['parents'] #패스 파싱 함수에서 사용할 변수
                else:
                    continue

                if parent and path_option == "fullPath" :
                    plex_path = ModelSetting.get('plex_path')
                    win_path = ModelSetting.get('win_path')

                    if file.get('mimeType') == 'application/vnd.google-apps.folder': #대상이 폴더인 경우 자신의 이름을 경로 끝에 입력
                        tree2 = file.get('name')

                    # logger.debug(parent[0])
                    # logger.debug(folder_name_cache)
                    # logger.debug(folder_name_cache.get(parent[0]))

                    while True:

                        if folder_name_cache.get(parent[0]): # api 쿼리 보내기전 캐쉬에서 먼저 검색
                            tree2 = folder_name_cache[parent[0]]['name'] + "/" + tree2
                            parent = folder_name_cache[parent[0]].get('parents')

                            if parent is None:
                                # logger.debug("=================== parent is none")
                                break

                        else:
                            folder = service.files().get(fileId=parent[0],
                                                            fields='name, parents, teamDriveId, id',
                                                            supportsAllDrives='true',
                                                            supportsTeamDrives='true').execute()
                            
                            folder_name_cache[folder.get('id')] = folder #같은 쿼리를 보내지 않기 위해 캐쉬에 저장
                            parent = folder.get('parents')
                            # logger.debug(parent)

                            if parent is None:
                                
                                if folder.get('name') == "내 드라이브":
                                    tree2 = folder.get('name') + "/" + tree2
                                elif folder.get('name') == "드라이브":
                                    drive_name = service.drives().get(driveId=folder.get('teamDriveId')).execute()
                                    tree2 = drive_name.get('name') + "/" + tree2                                    
                                    folder['name'] = drive_name.get('name')

                                folder_name_cache[folder.get('id')] = folder ######## 최상위 까지 캐시하기 위해서 추가
                                break
                            
                            tree2 = folder.get('name') + "/" + tree2

                    response['files'][i]['plex_path'] = tree2
                    response['files'][i]['win_path'] = tree2
                    if plex_path:
                        for sub in plex_path.split(','):
                            path_match = sub.split('=')
                            response['files'][i]['plex_path'] = response['files'][i]['plex_path'].replace(path_match[0], path_match[1], 1)

                    if win_path:
                        for sub in win_path.split(','):
                            path_match = sub.split('=')
                            response['files'][i]['win_path'] = response['files'][i]['win_path'].replace(path_match[0], path_match[1], 1)
                        response['files'][i]['win_path'] = response['files'][i]['win_path'].replace('/','\\')
                        response['files'][i]['win_path2'] = response['files'][i]['win_path'].replace("(","zzzzzxxxxxzzzzzxxxxx")
                        response['files'][i]['win_path2'] = response['files'][i]['win_path2'].replace(")","xxxxxzzzzzxxxxxzzzzz")
                        response['files'][i]['win_path2'] = response['files'][i]['win_path2'].replace("+","xxxxxzzzzzxxxxxccccc")
                                
                response['files'][i]['fullPath'] = tree2

            if page_token is None:
                break
        gsearch_result = response.get('files', []) #원래 구글 레퍼런스에 있던 원본
        # logger.debug(response)
        # logger.debug(type(gsearch_result))
        # logger.debug(gsearch_result)
        # logger.debug(folder_name_cache)
        logger.debug("=================== 작업 소요 시간 : " +  str(time.time() - start_time))  # 현재시각 - 시작시간 = 실행 시간
        return gsearch_result

    @staticmethod
    def gdelete(fileId):
        fileId = fileId.strip()
        fileId = fileId.replace(",", " ")

        i = 0
        for target in fileId.split(): 
            try:
                gdelete_result = service.files().delete(fileId=target, supportsTeamDrives='true').execute()
                # gdelete_result = service.files().delete(fileId=fileId, supportsTeamDrives='true').execute()
                i = i + 1
            except:
                err = service.files().get(fileId=target,
                                            fields='name, parents, teamDriveId, id',
                                            supportsAllDrives='true',
                                            supportsTeamDrives='true').execute()
                logger.debug(err)
                continue
        return(gdelete_result, i)

    @staticmethod
    def gmove(fileId, dest_folderId):
        service.files().update
