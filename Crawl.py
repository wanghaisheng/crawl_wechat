#!/usr/bin/env python3
import ctypes
import json
import logging
import re
import threading
from collections import defaultdict
import rumps
import signal
import psutil
import os
import random
from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.keys import Keys
import time
from urllib.parse import urlparse, parse_qs, unquote
import datetime
from loguru import logger
import shutil
import string
import redis
from redis import StrictRedis

process_name = os.path.basename(__file__).split('.')[0]
for proc in psutil.process_iter():
    try:
        if proc.name() == process_name and proc.pid() != os.getpid():
            print("pid-%d,name:%s" % (proc.pid, proc.name()))
            os.kill(int(proc.pid), signal.SIGKILL)
    except:
        pass

LOG_FORMAT = '<level>{level: <8}</level>  <green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> - <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>'
LIMIT_ERROR_MESSAGE = '您已被限号'


class PomodoroAppWeiXinSite(object):

    def __init__(self):
        self.link_set = set()
        self.icon = "./logo.ico"
        self.home_path = os.path.join(os.path.expanduser('~'), 'weixin')
        self.account_db = os.path.join(self.home_path, '.account.json')
        self.error_db = os.path.join(self.home_path, '.error.json')
        self.ack_db = os.path.join(self.home_path, '.ack.json')
        self.history_db = os.path.join(self.home_path, '.history.json')
        self.log = os.path.join(self.home_path, f'crawl.log')
        self.raw_get = None
        shutil.rmtree(self.log, ignore_errors=True)
        if not os.path.exists(self.home_path):
            os.makedirs(self.home_path, exist_ok=True)
        logger.add(
            self.log, encoding='utf-8', rotation="100 MB", serialize=False, enqueue=True,
            level=logging.DEBUG, compression='zip', format=LOG_FORMAT,
        )
        logger.debug('日志系统已加载')
        self.driver: WebDriver = None
        self.index: str = ''
        self.config = {
            "app_name": "Crawl",
            "crawl": "crawl",
            "down": "down",
            "terminate": "terminate",
            "add": "add",
        }
        self._ack_dict = dict()
        self.search_account_set = set()
        self.crawl_history_url_dict = defaultdict(dict)
        """
        {
            account:{
                title:url
            }
        }
        """

        self.app = rumps.App(self.config["app_name"], icon=self.icon)
        # self.app.title = self.config['app_name']
        self.crawl_button = rumps.MenuItem(title=self.config["crawl"], callback=self.crawl)
        self.down_button = rumps.MenuItem(title=self.config["down"], callback=self.down_article)
        self.terminate_button = rumps.MenuItem(title=self.config["terminate"], callback=self.terminate)
        self.add_pause_button = rumps.MenuItem(title=self.config["add"], callback=self.add)
        self.app.menu = [
            self.crawl_button,
            self.down_button,
            self.terminate_button,
            self.add_pause_button
        ]
        self.t: threading.Thread = None
        rumps.notification(
            icon=self.icon,
            title='', subtitle='START', message=''
        )
        logger.info('START')
        # os.system("ps -ef |grep chromedriver |grep -v grep |awk '{print $2}'|xargs kill -9")
        self.quit()
        self.limit = None
        self._error_dict = dict()
        self.redis: StrictRedis = None
        self.crawl_redis: StrictRedis = None
        self.last_page_context = set()
        self._load_data()

    def init_redis(self):
        if self.redis:
            return
        self.redis = redis.Redis(
            connection_pool=redis.ConnectionPool(host='127.0.0.1', port=46379, decode_responses=True))

        self.crawl_redis = redis.Redis(
            connection_pool=redis.ConnectionPool(host='127.0.0.1', port=46379, decode_responses=True, db=1)
        )

    def _load_data(self):
        self.init_redis()
        self._error_dict = dict()
        self._ack_dict = dict()
        self.search_account_set = set()
        self.crawl_history_url_dict = defaultdict(dict)
        try:
            with open(self.ack_db, 'r', encoding='utf8') as f:
                for item in json.loads(f.read()):
                    self._ack_dict[item] = 1
        except Exception:
            pass
        try:
            with open(self.account_db, 'r', encoding='utf8') as f:
                for item in json.loads(f.read()):
                    if item:
                        self.search_account_set.add(item)
        except Exception:
            pass
        try:

            with open(self.history_db, 'r', encoding='utf8') as f:
                for account, v_map in json.loads(f.read()).items():
                    for href, [title, article_date] in v_map.items():
                        self.redis.hset(account, key=href, value=json.dumps([title, article_date], ensure_ascii=False))
            # for account in self.get_account():
            #     for file in self._account_files(os.path.join(self.home_path, account)):
            #
            #         self.driver.get(f"file://{file}", log=False)
            #         url = self.driver.find_elements_by_xpath('//*[@id="raw_link"]').get_attribute('href')
            #         if self.redis.hget(account, url):
            #             continue
            #
            #         article_date = ''
            #         title = ''
            #         self.redis.hset(
            #             account, key=url, value=json.dumps([title, article_date], ensure_ascii=False)
            #         )

            for account in self.redis.keys(pattern='*'):
                for href, title_date in self.redis.hgetall(account).items():
                    title, article_date = json.loads(title_date)

                    self.crawl_history_url_dict[account][href] = [title, article_date]
            for account, v_map in self.crawl_history_url_dict.items():
                for href, [title, article_date] in v_map.items():
                    try:
                        datetime.datetime.strptime(article_date, '%Y-%m-%d')
                    except Exception as e:
                        logger.error(account)
                        logger.error(href)
                        logger.error(title)
                        logger.error(article_date)
                        logger.exception(e)
                        return
        except Exception as e:
            logger.error(e)
        with open(self.history_db, 'w', encoding='utf8') as f:
            f.write(json.dumps(self.crawl_history_url_dict, ensure_ascii=False, indent=4))

        try:
            with open(self.error_db, 'r', encoding='utf8') as f:
                self._error_dict = json.loads(f.read())
        except Exception as e:
            logger.error(e)

        flag = False
        for account in self.crawl_history_url_dict.keys():
            for url, [title, article_date] in self.crawl_history_url_dict[account].items():
                path = self._get_file_name(public_account=account, title=title, url=url)
                if not os.path.exists(path):
                    # 文件不存在，但是在确认表里 [刨除在err中的]
                    if path in self._ack_dict:
                        if url in self._error_dict:
                            pass
                        else:
                            self._ack_dict.pop(path)
                            flag = True
        if flag:
            with open(self.ack_db, 'w', encoding='utf8') as f:
                f.write(json.dumps(self._ack_dict, ensure_ascii=False, indent=4))
            self._load_data()
        logger.info('data load over')

    def _validate(self, public_account):
        # 清除本不应该存在的文件
        self._empty_invalid_file(public_account)
        # 现在存在的文件
        for url, [title, article_date] in self.crawl_history_url_dict[public_account].items():
            start = time.time()
            file = self._get_file_name(public_account=public_account, title=title, url=url)
            if not os.path.exists(file):
                continue
            # for file in self._account_files(os.path.join(self.home_path, public_account)):
            # 将所有未加载完的文件删除,会打开文件
            if self.validate_file_load_over(public_account, file):
                if self._check_raw_link(public_account) is False:
                    # 插入
                    self._insert_a(file, _open=True, url=url, title=title, _date=article_date)
                else:
                    if file in self._ack_dict:
                        continue
                    self._ack_dict[file] = 1
                    with open(self.ack_db, 'w', encoding='utf8') as f:
                        f.write(json.dumps(self._ack_dict, ensure_ascii=False, indent=4))
                self.redis.hset(public_account, key=url, value=json.dumps([title, article_date], ensure_ascii=False))
                if time.time() - start > 1:
                    logger.info(file)

    def validate_file_load_over(self, public_account, file=None):
        if file in self._ack_dict:
            return True
        if '关于粉丝迁移至本公众号的说明' in file:
            return True
        self.driver.get(f"file://{file}", log=False)
        page_source = self.driver.page_source
        if '该文件可能已被移至别' in page_source:
            logger.info(f'无法访问您的文件 {file}')
            os.remove(file)
            return False
        if '该内容已被发布者删除' in page_source:
            return True
        if '未连接到互联网' in page_source:
            logger.info(f'未连接到互联网 {file}')
            os.remove(file)
            return False
        delete_flag = False
        loading_img = 0
        div_flags = self.driver.find_elements_by_tag_name('div')
        if not div_flags:
            logger.info(f'delete {file}')
            os.remove(file)
            return False
        account_desc = self.driver.find_elements_by_xpath('//*[@id="js_name"]')
        if account_desc:
            if account_desc[0].text.strip() != public_account:
                logger.info(f"{file} 与公众号不符,因此删除")
                os.remove(file)
                return False
        for item in self.driver.find_elements_by_tag_name('img'):
            if 'img_loading' in item.get_attribute('class'):
                if item.size.get('width', 0) > 30:
                    loading_img += 1
                    delete_flag = True
        if delete_flag:
            logger.info(f"{loading_img} {file} 存在未加载完毕的图片,因此删除")
            # open -a "/Applications/Google Chrome.app" http://10.10.10.121:3000/?orgId=1&search=open
            os.remove(file)
            return False
        return True

    def _insert_a(self, file_path, _open=False, url=None, title=None, _date=None):
        if not _open:
            self.driver.get(f"file://{file_path}", log=False, _down=True)
        if url:
            js = f"html=document.getElementsByTagName('html');a = document.createElement('a');a.setAttribute('_date','{_date}');a.setAttribute('title','{title}');a.style='z-index: 9999;height: 50px;display: block;position: fixed;top: 240px;right: 77px;';a.id='raw_link';a.href='{url}';a.text='原文链接';html[0].appendChild(a);"
        else:
            js = f"html=document.getElementsByTagName('html');a = document.createElement('a');a.setAttribute('_date','{_date}');a.setAttribute('title','{title}');a.style='z-index: 9999;height: 50px;display: block;position: fixed;top: 240px;right: 77px;';a.id='raw_link';a.href=document.documentURI;a.text='原文链接';html[0].appendChild(a);"
        try:
            self.driver.set_script_timeout(0.1)
            self.driver.execute_async_script(js)
            time.sleep(0.1)
        except Exception:
            pass
        self._save_page(file_path + 'bak')
        if os.path.exists(file_path):
            os.remove(file_path)
        os.rename(file_path + 'bak', file_path)

    # 简单一些，直接从文件里检查
    def _check_raw_link(self, file_path):
        if file_path in self._ack_dict:
            return
        if not os.path.exists(file_path):
            return
        with open(file_path, 'r', encoding='utf8') as f:
            data = f.read()
            if 'id="raw_link"' in data and 'z-index: 9999' in data and '原文链接' in data:
                return True
        return False

    def _save_page(self, file_path):
        res = self.driver.execute_cdp_cmd('Page.captureSnapshot', {})
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', newline='') as f:
            f.write(res['data'])

    def add(self, sender):
        window = rumps.Window(
            message="格式: search,公众号 \neg: aohoBlog,aoho求索 ", title="录入要爬取的公众号",
            dimensions=(320, 100)
        )
        window.icon = self.icon
        response = window.run()
        for line in response.text.split('\n'):
            for account in line.strip().split(','):  # type str,str
                logger.info(f'add account {account}')
                if account.strip():
                    self.search_account_set.add(account.strip())

        with open(self.account_db, 'w', encoding='utf8') as f:
            f.write(json.dumps(list(self.search_account_set), ensure_ascii=False, indent=4))
        rumps.notification(
            icon=self.icon,
            title='', subtitle=f'add', message=''
        )

    def _empty_invalid_file(self, public_account):
        # 清除本不应该存在的文件
        os.makedirs(os.path.join(self.home_path, public_account), exist_ok=True)
        local_account_files: list = self._account_files(os.path.join(self.home_path, public_account))
        local_account_dict = {
        }
        for item in local_account_files:
            local_account_dict[item] = 1

        for url, [title, article_date] in self.crawl_history_url_dict[public_account].items():
            path = self._get_file_name(public_account, title, url)
            if path in local_account_dict:
                local_account_dict.pop(path)

        for file in local_account_dict.keys():
            if os.path.exists(file):
                logger.info(f'delete {file}')
                os.remove(file)
        logger.info(
            f"----> {public_account}:[{self._file_count(os.path.join(self.home_path, public_account))}/{len(self.crawl_history_url_dict[public_account])}]"
        )

    def _init_driver(self, down=False):
        self.quit()
        self.driver = webdriver.Chrome(executable_path='/Users/liushuo/software/chromedriver')
        self.driver.implicitly_wait(10)
        if self.raw_get:
            func = self.raw_get
        else:
            func = self.driver.get
            self.raw_get = func

        def _get(url: str, retry=False, log=True, _down=down):
            i = 0
            while i < 3 and self.driver:
                try:
                    func(url)
                    if '公众号' in self.driver.title:
                        time.sleep(20)
                    while self.driver.execute_script("return document.readyState;") != 'complete':
                        if _down:
                            time.sleep(random.random() + 1)
                        else:
                            time.sleep(random.random() * 30 + 30)
                    if not retry:
                        if log:
                            logger.info(url[:-2])
                    return True
                except Exception as e:
                    if 'HTTPConnectionPool' in str(e) and self.driver is None:
                        return False
                i += 1
                if i >= 3 and url.startswith('http'):
                    self._update_error(url, '')
                retry = True
            if self.driver is None:
                return False
            return True

        self.driver.get = _get

    def crawl(self, sender):
        # self._load_data()
        self.terminate(sender)
        self._init_driver()
        self.t = threading.Thread(target=self._exec)
        self.t.start()

    def _down_article(self, public_account):
        self._validate(public_account)
        logger.info(f"开始下载{public_account}")
        # public_account_count=self.file_account(os.path.join(self.home_path, public_account))
        for url in self.crawl_history_url_dict[public_account].keys():
            title, article_date = self.crawl_history_url_dict[public_account][url]
            start_crawl_article_time = time.time()
            if url in self._error_dict:
                continue

            file_path = self._get_file_name(public_account, title, url)
            if file_path in self._ack_dict:
                continue
            if os.path.exists(file_path):
                if os.stat(file_path).st_size < 100:
                    pass
                else:
                    # logger.info(f"已存在{url}")
                    continue
            err_count = 0
            _exec_flag = True
            while err_count < 3 and _exec_flag:
                try:
                    if err_count != 0:
                        res = self.driver.get(url, retry=True)
                    else:
                        res = self.driver.get(url)
                    if res is False:
                        return
                    # total_height = self.driver.execute_script("return document.body.scrollHeight")
                    # page_height = self.driver.execute_script("return window.screen.availHeight")
                    # i = 0
                    # while page_height * (i + 1) < total_height:
                    #     self.driver.execute_script(
                    #         f'window.scrollTo({page_height * i},{page_height * (i + 1)})'
                    #     )
                    #     i += 1
                    #     time.sleep(1)
                    self.driver.execute_script(f'window.scrollTo(0,document.body.scrollHeight);')
                    if self._wait_img() is False:
                        err_count += 1
                        logger.info('图片未加载完毕')
                        continue
                    self.driver.execute_script(f'window.scrollTo(0,document.body.scrollHeight);')
                    self._insert_a(file_path, _open=True, title=title, _date=article_date)
                    self._print_state(public_account)
                    if self.validate_file_load_over(public_account, file_path):
                        rumps.notification(
                            icon=self.icon,
                            title=f"{public_account}👌🏻",
                            subtitle=f'{title}', message=''
                        )
                        logger.info(f"cost:{time.time() - start_crawl_article_time} ---- '{file_path}'")
                        _exec_flag = False
                        err_count = 0
                    else:
                        err_count += 1
                except Exception as e:
                    err_count += 1
                    logger.error(f"\n\n\n{str(e)}\n{title}\n{url}\n\n")
            if err_count >= 3:
                self._update_error(url, title)
                logger.info(f"没成功======>{url}")
        logger.info(f'OVER {public_account}')

    @staticmethod
    def is_chinese(ch):
        if '\u4e00' <= ch <= '\u9fff':
            return True
        return False

    def down_article(self, sender):
        # self._load_data()
        self.terminate(sender)

        def inner(_self: PomodoroAppWeiXinSite):
            _self._init_driver(down=True)
            for public_account in _self.get_account():
                if public_account in _self.crawl_history_url_dict:
                    try:
                        _self._down_article(public_account)
                    except Exception as e:
                        logger.exception(e)
            logger.info('already download exists file')
            _self.quit()

        self.t = threading.Thread(target=inner, args=(self,))
        self.t.start()

    def run(self):
        self.app.run()

    def terminate(self, sender=None):
        # self._load_data()
        rumps.notification(
            icon=self.icon,
            title='', subtitle=f'STOP', message=''
        )
        if not self.t:
            return
        """raises the exception, performs cleanup if needed"""
        tid = ctypes.c_long(self.t.ident)
        # if not inspect.isclass(SystemExit):
        #     exctype = type(SystemExit)
        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
            tid, ctypes.py_object(SystemExit))
        if res == 0:
            logger.info("invalid thread id")
            # raise ValueError("invalid thread id")
        elif res != 1:
            # """if it returns a number greater than one, you're in trouble,
            # and you should call it again with exc=NULL to revert the effect"""
            ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, None)
            # raise SystemError("PyThreadState_SetAsyncExc failed")
            logger.info("PyThreadState_SetAsyncExc failed")
        self.t = None
        self.quit()

    def _min(self):
        pass
        # self.driver.minimize_window()

    def get_account(self):
        demo = [
            "网管叨bi叨",
            "Golang梦工厂",
            "码农桃花源",
            "HHFCodeRv",
            "TechPaper",
            "小白debug",
            "polarisxu",
            "TonyBai",
            'Go招聘',
            '幽鬼',
            'GoCN',
            'Golang语言开发栈',
            'Golang技术分享',
        ]
        for item in self.search_account_set:
            if item not in demo:
                demo.append(item)
        return demo

    def _exec(self):
        self.driver.get('https://mp.weixin.qq.com/')
        # 图文
        _bt = self.driver.find_elements_by_xpath(
            '//*[@id="app"]/div[2]/div[3]/div[2]/div/div[1]')
        while not _bt:
            time.sleep(3)
            logger.info('sleep')
            _bt = self.driver.find_elements_by_xpath('//*[@id="app"]/div[2]/div[3]/div[2]/div/div[1]')
        self.index = self.driver.current_url
        logger.info(self.index)
        self._min()

        for account in self.get_account():
            os.makedirs(os.path.join(self.home_path, account), exist_ok=True)
            num = 0
            while num < 3:
                try:
                    if account:
                        if self.get_account_latest_article(account) == datetime.datetime.now().strftime('%Y-%m-%d'):
                            logger.info(f'{account} 数据已是最新的')
                            num = 4
                            continue
                        res = self.crawl_redis.get(account)
                        if res:
                            logger.info(f'{account} 今天已经爬取了')
                            num = 4
                            continue
                        if self.validate_limit():
                            self._down_article(public_account=account)
                            num = 4
                            now = datetime.datetime.now()
                            self.crawl_redis.expireat(account, datetime.datetime(
                                year=now.year, month=now.month, day=now.day,
                                hour=23,
                            ))
                            continue
                        crawl_count_before = len(self.crawl_history_url_dict[account])
                        self._get_news(account)
                        crawl_count_after = len(self.crawl_history_url_dict[account])
                        if crawl_count_after > crawl_count_before:
                            time.sleep(160)
                        else:
                            time.sleep(random.random() * 10 + 40)
                        self.crawl_redis.set(account, value=1)
                        now = datetime.datetime.now()
                        self.crawl_redis.expireat(account, datetime.datetime(
                            year=now.year, month=now.month, day=now.day,
                            hour=23,
                        ))

                except Exception as e:
                    num += 1
                    with open(self.history_db, 'w', encoding='utf8') as f:
                        f.write(json.dumps(dict(self.crawl_history_url_dict), ensure_ascii=False, indent=4))
                    if LIMIT_ERROR_MESSAGE == str(e):
                        pass
                    else:
                        self.last_page_context.add(LIMIT_ERROR_MESSAGE)
                        logger.exception(e)

                num = 4
        logger.info('crawl over')
        self.down_article(sender=None)

    def _print_state(self, public_account):
        _file_count = self._file_count(os.path.join(self.home_path, public_account))
        logger.info(
            f"{public_account}:[{_file_count}/{len(self.crawl_history_url_dict[public_account])}]"
        )

    def _have_next_page(self):
        page_btns = self.driver.find_elements_by_xpath(
            # '//*[@id="vue_app"]/div[2]/div[1]/div/div[2]/div[2]/form[1]/div[4]/div/div/div[3]',
            '/html/body/div[2]/div/div/div/div/div[6]/div[2]/div[1]/div/div[2]/div[2]/form[1]/div[5]/div/div/div[3]'
        )
        if page_btns:
            text = page_btns[0].text
            if text:
                start, end = re.findall(r'\d+', text)
                have_page = True
                return start, end, have_page
        return 1, 1, False

    def _get_one_page_count(self) -> int:
        js = 'document.querySelectorAll("#vue_app > div.weui-desktop-link-dialog > div.weui-desktop-dialog__wrp > div > div.weui-desktop-dialog__bd > div.link_dialog_panel > form:nth-child(1) > div:nth-child(5) > div > div > div.weui-desktop-media__list-wrp > div > div > label").length'
        value = self.driver.execute_script(f'return {js};')
        return int(value)

    def judge_current_date_le_xx(self, _latest_new_datetime: str):
        _latest_new_datetime = datetime.datetime.strptime(_latest_new_datetime, '%Y-%m-%d')
        dates = []
        for link in self.driver.find_elements_by_xpath(
                '/html/body/div[2]/div/div/div/div/div[6]/div[2]/div[1]/div/div[2]/div[2]/form[1]/div[5]/div/div/div[2]/div/div/label'
        ):
            title, article_date = self.empty_link_text(link.text)
            dates.append(datetime.datetime.strptime(article_date, '%Y-%m-%d'))

        return all([item <= _latest_new_datetime for item in dates])

    def empty_link_text(self, text):
        logger.info(text)
        if '付费' in text:
            res = text.split('\n')
            title = res[1]

            article_date = res[2]
        else:
            if '\n' in text:
                res = text.split('\n')
                article_date = res[1]
                title = res[0]

            else:
                title = ''
                article_date = '1000-01-01'
        return title, article_date

    def get_articles(self, public_account, new_count, save=True):
        try:
            # 用于和上一页数据进行判断，被官网封账号
            # todo 找不到文章
            for link in self.driver.find_elements_by_xpath(
                    '/html/body/div[2]/div/div/div/div/div[6]/div[2]/div[1]/div/div[2]/div[2]/form[1]/div[5]/div/div/div[2]/div/div/label'
            ):
                title, article_date = self.empty_link_text(link.text)
                href = link.find_element_by_tag_name('a').get_attribute('href')

                if self.crawl_history_url_dict[public_account].get(href):
                    pass
                else:
                    new_count += 1
                    if save:
                        self.update_record(public_account, url=href, title=title.strip(), _date=article_date)
                        a, _, _ = self._have_next_page()
                        logger.info([f"page:{a} new:{new_count}", title.strip(), article_date.strip(), href])

        except Exception as e:
            logger.exception(e)
        return new_count

    def get_account_latest_article(self, public_account) -> str:
        latest_new_datetime = datetime.datetime(year=1999, day=1, month=1)
        for [title, article_date] in self.crawl_history_url_dict[public_account].values():
            xxx = datetime.datetime.strptime(article_date, '%Y-%m-%d')
            if xxx > latest_new_datetime:
                latest_new_datetime = xxx
        return latest_new_datetime.strftime('%Y-%m-%d')

    def _get_news(self, public_account, _iter=1):
        # public_account = '网管叨bi叨'
        try:
            latest_new_datetime = self.get_account_latest_article(public_account)
        except Exception as e:
            logger.error(e)
            return
        logger.info(f"{public_account} {latest_new_datetime}")
        if _iter > 3:
            return
        self.driver.get(self.index)
        # 图文
        bt = self.driver.find_elements_by_xpath('//*[@id="app"]/div[2]/div[3]/div[2]/div/div[1]')
        while not bt:
            time.sleep(3)
            logger.info('图文 sleep')
            bt = self.driver.find_elements_by_xpath('//*[@id="app"]/div[2]/div[3]/div[2]/div/div[1]')
        logger.info('图文 click')
        bt[0].click()
        xx = self.driver.current_window_handle
        self._min()
        for item in self.driver.window_handles:
            if xx != item:
                xx = item
                break
        for item in self.driver.window_handles:
            if item != xx:
                # close
                logger.info(f'close window {item}')
                self.driver.switch_to.window(item)
                self.driver.close()
        self.driver.switch_to.window(xx)
        self._min()
        while len(self.driver.find_elements_by_tag_name('li')) > 6 and \
                self.driver.find_elements_by_tag_name('li')[5].text != '超链接':
            logger.info('超链接 sleep')
            time.sleep(3)
        self.driver.find_elements_by_tag_name('li')[5].click()
        time.sleep(3)
        logger.info('超链接 ok')
        # find
        # self.driver.find_element_by_xpath(
        #     '//*[@id="vue_app"]/div[2]/div[1]/div/div[2]/div[2]/form[1]/div[3]/div/div/p/div/button').click()
        self.driver.execute_script(
            'document.querySelector("#vue_app > div.weui-desktop-link-dialog > div.weui-desktop-dialog__wrp > div > div.weui-desktop-dialog__bd > div.link_dialog_panel > form:nth-child(1) > div:nth-child(4) > div > div > p > div > button").click()'
        )

        # input
        time.sleep(3)
        logger.info(f'send {public_account}')
        # _input = self.driver.find_element_by_xpath('//*[@id="vue_app"]/div[2]/div[1]/div/div[2]/div[2]/form[1]/div[3]/div/div/div/div/div[1]/span/input')
        _input = self.driver.find_element_by_xpath(
            '/html/body/div[2]/div/div/div/div/div[6]/div[2]/div[1]/div/div[2]/div[2]/form[1]/div[4]/div/div/div/div/div[1]/span/input')
        time.sleep(1)
        _input.clear()
        time.sleep(1)
        _input.send_keys(public_account)
        _input.send_keys(Keys.ENTER)
        # document.querySelector("#vue_app > div.weui-desktop-link-dialog > div.weui-desktop-dialog__wrp > div > div.weui-desktop-dialog__bd > div.link_dialog_panel > form:nth-child(1) > div:nth-child(4) > div > div > div > div > div.weui-desktop-form__input-area > span > input").value=1
        time.sleep(3)
        public_account_list = self.driver.find_elements_by_xpath(
            # '//*[@id="vue_app"]/div[2]/div[1]/div/div[2]/div[2]/form[1]/div[3]/div/div/div/div[2]/ul/li/div[1]/strong',
            '/html/body/div[2]/div/div/div/div/div[6]/div[2]/div[1]/div/div[2]/div[2]/form[1]/div[4]/div/div/div/div[2]/ul/li/div[1]/strong'
        )
        time.sleep(10)
        if public_account_list:
            click = False
            for item in public_account_list:
                if item.text == public_account:
                    logger.info(f'change {item.text}')
                    item.click()
                    click = True
                    break
            if click:
                pass
            else:
                return
        else:
            return
        time.sleep(3)
        last_btn = True
        new_count = 0
        # 1、获取页码
        while 1:
            try:
                crawl_start, end, have_page = self._have_next_page()
                articles_count = self._get_one_page_count()
                if articles_count < 5 and crawl_start == end:
                    logger.info(f"{public_account} len < 5")
                    break
                else:
                    new_count_2 = self.get_articles(public_account, new_count, save=False)
                    if new_count_2 - new_count < self._get_one_page_count():
                        self.get_articles(public_account, new_count, save=True)
                        # 说明有存在,即不用再往下一页了
                        return
                    else:
                        new_count = new_count_2
                    break

            except Exception as e:
                logger.error(e)
                time.sleep(3)
                self._get_news(public_account, _iter + 1)
                return
        new_count = 0
        logger.info(have_page)
        if have_page:

            # 3、根据现有数据量
            now_count = len(self.crawl_history_url_dict[public_account])
            page_count = 5
            if eval(end) > 2:
                # 2、调到倒数第二页
                self._skip_page(str(eval(end) - 1))
                page_count = self._get_one_page_count()

            # 2、调到最后一页
            self._skip_page(end)
            if now_count - 1 > 0:
                # todo 应该根据倒数第二页进行数据量获取
                _crawl_start = max(eval(end) - (max(0, now_count - 1)) // max(page_count, now_count // int(end)), 1)
                # 4、跳到对应该爬取的页面
                if _crawl_start + 2 < eval(end):
                    if _crawl_start > 1:
                        self._skip_page(str(_crawl_start + 2))
                    else:
                        self._skip_page('1')
                else:
                    self._skip_page(str(_crawl_start))
                while not self.judge_current_date_le_xx(latest_new_datetime):
                    new_count = self.get_articles(public_account, new_count, save=False)
                    a, _, _ = self._have_next_page()
                    self._skip_page(str(int(a) + 1))

                time.sleep(30)
        last_counter = 0
        current_crawl_num = 1
        new_count = 0
        # 5、上一页,直到没有上一页
        while last_btn:
            # if last_counter > 30:
            #     同一账号，只能一次性爬取30页
            # break
            time.sleep(random.random() * 130 + 20)

            new_count = self.get_articles(public_account, new_count)
            # if self._get_one_page_count() < 5:
            #     rumps.notification(
            #         icon=self.icon,
            #         title='', subtitle=LIMIT_ERROR_MESSAGE, message=''
            #     )
            #     raise Exception(LIMIT_ERROR_MESSAGE)
            if current_crawl_num % 10 == 0 and self.validate_limit():
                return
            try:
                footer_a = self.driver.find_elements_by_xpath(
                    '/html/body/div[2]/div/div/div/div/div[6]/div[2]/div[1]/div/div[2]/div[2]/form[1]/div[5]/div/div/div[3]/span[1]/a'
                    # '//*[@id="vue_app"]/div[2]/div[1]/div/div[2]/div[2]/form[1]/div[4]/div/div/div[3]'
                )
                if footer_a:
                    if '上一页' not in ''.join([a.text for a in footer_a]):
                        last_btn = False
                        logger.info('无上一页')
                        break
                    else:
                        a, _, _ = self._have_next_page()
                        logger.info(f'{public_account} 上一页 current page:{a}')
                        for a in footer_a:
                            if '上一页' in a.text:
                                last_btn = True
                                a.click()
                                current_crawl_num += 1
                                last_counter += 1
                                break
                else:
                    a, _, _ = self._have_next_page()
                    logger.info(f'no last btn page:{a}')
                    break

            except Exception as e:
                logger.exception(e)
            with open(self.history_db, 'w', encoding='utf8') as f:
                f.write(json.dumps(dict(self.crawl_history_url_dict), ensure_ascii=False, indent=4))
        with open(self.history_db, 'w', encoding='utf8') as f:
            f.write(json.dumps(dict(self.crawl_history_url_dict), ensure_ascii=False, indent=4))

    def validate_limit(self):
        if self.limit:
            return True
        # 如果不等于空，就是被限号了

        # current_url = 'https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1&type=77&createType=0&token=2046417052&lang=zh_CN'
        urldata = unquote(self.index, encoding='gbk', errors='replace')
        result = urlparse(urldata)
        token = parse_qs(result.query)['token'][0]
        # cookies = self.driver.get_cookies()
        # # 把cookies设置到session中
        # for cookie in cookies:
        #     s.cookies.set(cookie['name'], cookie['value'])
        request_url = f'https://mp.weixin.qq.com/cgi-bin/appmsg?action=list_ex&begin=0&count=5&fakeid=MjM5ODYxMDA5OQ==&type=9&query=&token={token}&lang=zh_CN&f=json&ajax=1'
        current = self.driver.current_window_handle
        new = ''
        logger.info(f'window.open("{request_url}")')
        while 1:
            try:
                self.driver.execute_script(f'window.open("{request_url}")')
                break
            except TimeoutException as e:
                logger.error(e)
        for item in self.driver.window_handles:
            if current != item:
                new = item
                break
        self.driver.switch_to.window(new)
        # 获取text
        text = self.driver.find_elements_by_xpath('/html/body/pre')[0].text
        res = json.loads(text)

        delete_windows = []
        for item in self.driver.window_handles:
            if current != item:
                delete_windows.append(item)
        for item in delete_windows:
            self.driver.switch_to.window(item)
            self.driver.close()
        self.driver.switch_to.window(current)
        limit = res['base_resp'].get('err_msg') == "freq control"
        if limit:
            logger.info('已经限流了')
            self.limit = True
        return self.limit

    def _update_page(self, page: str):
        flag = True
        js = 'document.querySelector("#vue_app > div.weui-desktop-link-dialog > div.weui-desktop-dialog__wrp > div > div.weui-desktop-dialog__bd > div.link_dialog_panel > form:nth-child(1) > div:nth-child(5) > div > div > div.weui-desktop-pagination > span.weui-desktop-pagination__form > input").value'

        while flag:
            self.driver.execute_script(f'{js}="";')
            _input = self.driver.find_element_by_xpath(
                '/html/body/div[2]/div/div/div/div/div[6]/div[2]/div[1]/div/div[2]/div[2]/form[1]/div[5]/div/div/div[3]/span[2]/input'
            )
            _input.send_keys(page)
            value = self.driver.execute_script(f'return {js};')
            if value != page:
                time.sleep(1)
                continue
            else:
                flag = False

    def _skip_page(self, updated_value: str):
        repeat_num = 0
        self._update_page(updated_value)
        time.sleep(1)
        _input = self.driver.find_element_by_xpath(
            '/html/body/div[2]/div/div/div/div/div[6]/div[2]/div[1]/div/div[2]/div[2]/form[1]/div[5]/div/div/div[3]/span[2]/input'
        )
        # todo 不生效
        while repeat_num < 10:
            self._update_page(updated_value)
            _input.send_keys(Keys.ENTER)
            current, total, _ = self._have_next_page()
            if current == updated_value:
                return
            else:
                repeat_num += 1
                time.sleep(1)
        if repeat_num > 10:
            raise Exception('跳转失败')

    def _file_count(self, root_path, file_account=0):
        # 获取该目录下所有的文件名称和目录名称
        dir_or_files = os.listdir(root_path)
        for dir_file in dir_or_files:
            # 获取目录或者文件的路径
            dir_file_path = os.path.join(root_path, dir_file)
            # 判断该路径为文件还是路径
            if os.path.isdir(dir_file_path):
                file_account += self._file_count(dir_file_path)
            else:
                file_account += 1
        return file_account

    def _account_files(self, root_path):
        res = []
        # 获取该目录下所有的文件名称和目录名称
        dir_or_files = os.listdir(root_path)
        for dir_file in dir_or_files:
            # 获取目录或者文件的路径
            dir_file_path = os.path.join(root_path, dir_file)
            # 判断该路径为文件还是路径
            if os.path.isdir(dir_file_path):
                for item in self._account_files(dir_file_path):
                    res.append(item)
            else:
                res.append(dir_file_path)
        return res

    def _get_file_name_old(self, public_account, title, url):
        title = title.strip('.')  # type: str
        for item in ['(', ")", "）", "（"]:
            title = title.replace(item, '')
        title = title.replace(os.sep, '_') + url[-7:-3]
        return os.path.join(self.home_path, public_account, f"{title}.mhtml")

    def _get_file_name(self, public_account, title, url):
        temp = []
        for ch in title:
            if self.is_chinese(ch):
                temp.append(ch)
            else:
                if ch in string.ascii_letters + string.digits:
                    temp.append(ch)

        title = ''.join(temp) + url[-7:-3]
        return os.path.join(self.home_path, public_account, f"{title}.mhtml")

    def _wait_img(self, count=0):
        #                    # document.body.clientWidth ==> BODY对象宽度
        #                     #  document.body.clientHeight ==> BODY对象高度
        #                     #  document.documentElement.clientWidth ==> 可见区域宽度
        #                     #  document.documentElement.clientHeight ==> 可见区域高度
        self.driver.execute_script(f'window.scrollTo(0,0);')
        time.sleep(1)
        total_height = self.driver.execute_script("return document.body.scrollHeight;")
        page_height = self.driver.execute_script("return window.screen.availHeight;")
        offset_height = 0
        while offset_height < total_height - page_height:
            try:
                self.driver.set_script_timeout(1)
                start = time.time()
                try:
                    self.driver.execute_async_script(
                        f'window.scrollTo({offset_height},{offset_height + page_height / 2})'
                    )
                    time.sleep(1)
                except Exception:
                    pass
                offset_height += page_height / 2
            except StaleElementReferenceException as e:
                logger.error(e)
        over_flag = True

        for item in self.driver.find_elements_by_tag_name('img'):
            if 'img_loading' in item.get_attribute('class'):
                if item.size.get('width', 0) > 30:
                    over_flag = False
                    break
        if not over_flag:
            if count < 2:
                return self._wait_img(count + 1)
            else:
                return False
        else:
            return True

    def update_record(self, account, url, title, _date):
        self.init_redis()
        try:
            datetime.datetime.strptime(_date, '%Y-%m-%d')
        except Exception as e:
            logger.error(account)
            logger.error(url)
            logger.error(title)
            logger.error(_date)
            logger.exception(e)
            return
        self.crawl_history_url_dict[account][url] = [title, _date]

        self.redis.hset(account, key=url, value=json.dumps([title, _date], ensure_ascii=False))
        with open(self.history_db, 'w', encoding='utf8') as f:
            f.write(json.dumps(dict(self.crawl_history_url_dict), ensure_ascii=False, indent=4))

    def quit(self):
        try:
            if not self.driver:
                return
            self.driver.quit()
            self.driver = None
            logger.info('quit')
        except Exception as e:
            logger.error(e)

    def _update_error(self, url, title=''):
        if url in self._error_dict:
            return
        self._error_dict[url] = title
        with open(self.error_db, 'w', encoding='utf8') as f:
            f.write(json.dumps(self._error_dict, ensure_ascii=False, indent=4))


if __name__ == '__main__':
    app = PomodoroAppWeiXinSite()
    app.run()
