# -*- coding: utf-8 -*-

import bs4
import requests
import requests.packages.urllib3
requests.packages.urllib3.disable_warnings()
import os
import time
import datetime
import json
import random
import math
import logging, logging.handlers
import argparse
import multiprocessing
import Queue
import threading
import select
import socket
import struct
import re
from jd_wrapper import JDWrapper
import sys
reload(sys)
sys.setdefaultencoding('utf-8')

# get function name
FuncName = lambda n=0: sys._getframe(n + 1).f_code.co_name

class JDCoupon(JDWrapper):
    '''
    This class used to click JD coupon
    '''
    wait_interval = 1
    wait_delay = 30
    duration = 1
    start_limit = 0.5
    def setup(self, key, role_id):
        base_urls = (
            "http://coupon.jd.com/ilink/couponSendFront/send_index.action",
            "http://coupon.jd.com/ilink/couponActiveFront/front_index.action",
        )
        for url in base_urls:
            time.sleep(1)
            test_url = url+"?key="+key+"&roleId="+role_id+"&to=www.jd.com"
            resp = self.sess.get(test_url, timeout=5)
            soup = bs4.BeautifulSoup(resp.text, "html.parser")
            tag1 = soup.select('title')
            tag2 = soup.select('div.content')
            if len(tag2):
                message = tag2[0].text.strip(' \t\r\n')
                if message.find(u'活动链接过期') == -1:
                    self.coupon_url = test_url
                    return True
        return False

    def my_click(self, level=None):
        try:
            res = self.socket_get(self.coupon_url)
            if res == None:
                logging.log(logging.ERROR, u'Can not get page')
                return
            if level != None:
                soup = bs4.BeautifulSoup(res, "html.parser")
                tag1 = soup.select('title')
                tag2 = soup.select('div.content')
                if len(tag2):
                    logging.log(level, u'{}'.format(tag2[0].text.strip(' \t\r\n')))
                else:
                    if len(tag1):
                        logging.log(level, u'{}'.format(tag1[0].text.strip(' \t\r\n')))
                    else:
                        logging.log(level, u'页面错误')
        except Exception, e:
            if level != None:
                logging.log(level, 'Exp {0} : {1}'.format(FuncName(), e))
            return 0
        else:
            return 1

    def click(self, level=None):
        try:
            resp = self.sess.get(self.coupon_url, timeout=5)
            if level != None:
                soup = bs4.BeautifulSoup(resp.text, "html.parser")
                tag1 = soup.select('title')
                tag2 = soup.select('div.content')
                if len(tag2):
                    logging.log(level, u'{}'.format(tag2[0].text.strip(' \t\r\n')))
                else:
                    if len(tag1):
                        logging.log(level, u'{}'.format(tag1[0].text.strip(' \t\r\n')))
                    else:
                        logging.log(level, u'页面错误')
        except Exception, e:
            if level != None:
                logging.log(level, 'Exp {0} : {1}'.format(FuncName(), e))
            return 0
        else:
            return 1

    def click_fast(self, count):
        try:
            return [self.sess.head(self.coupon_url, timeout=0.2) for i in range(count)]
        except Exception, e:
            return []

    def relax_wait(self, target):
        counter = 0
        self.set_local_time()
        while 1:
            if counter >= self.wait_delay:
                self.click(logging.INFO)
                #self.my_click(logging.INFO)
                counter = 0
            diff = self.compare_local_time(target)
            if (diff <= 60) and (diff >= -60):
                break;
            time.sleep(self.wait_interval)
            counter += self.wait_interval

    def busy_wait(self, target):
        self.set_local_time()
        while 1:
            diff = self.compare_local_time(target)
            if (diff <= self.start_limit):
                break;

def click_task(coupon_url, id):    
    cnt = 0
    jd = JDCoupon()
    logging.warning(u'进程{}:开始运行'.format(id+1))
    if not jd.load_cookie(jd.pc_cookie_file):
        logging.warning(u'进程{}:无法加载cookie'.format(id+1))
        return 0
    jd.coupon_url = coupon_url
    while(wait_flag.value != 0):
        pass
    result = []
    while(run_flag.value != 0):
        result += jd.click_fast(8)
    for resp in result:
        if resp.ok:
            cnt += 1
    jd.click(logging.WARNING)
    return cnt

thread_flag = 1
thread_cnt = 0
thread_step = 16
def socket_producer(ip, msg_queue):
    global thread_flag
    global thread_step
    conn_dict = {}
    poll = select.poll()
    my_step = thread_step
    logging.warning('Producer enter {}'.format(msg_queue.qsize()))
    while thread_flag != 0:
        if msg_queue.qsize() >= 256:
            continue
        for i in range(my_step):
            se = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            se.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            se.setblocking(0)
            err = se.connect_ex((ip,80))
            se.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
            poll.register(se.fileno(), select.POLLOUT | select.POLLERR)
            conn_dict[se.fileno()] = se
        count = 0
        while True:
            if len(conn_dict) < (my_step / 4):
                break
            try:
                poll_list = poll.poll(10)
            except Exception, e:
                logging.error('Exp {0} : {1}'.format(FuncName(), e))
                print "queue {}, conn {}".format(msg_queue.qsize(), len(conn_dict))
                break
            if len(poll_list) == 0:
                count += 1
                if count >= 20:
                    for i in range(len(conn_dict)):
                        fd,se = conn_dict.popitem()
                        se.close()
                    break
            else:
                count = 0
            for fd, event in poll_list:
                if event & select.POLLOUT:
                    poll.unregister(fd)
                    se = conn_dict.pop(fd)
                    msg_queue.put(se)
                elif event & select.POLLERR:
                    poll.unregister(fd)
                    se = conn_dict.pop(fd)
                    se.close()
    for fd,se in conn_dict.items():
        se.close()
    logging.warning('Producer exit {}'.format(msg_queue.qsize()))
    return

def socket_consumer(text, msg_queue):
    global thread_flag
    global thread_cnt
    send_dict = {}
    poll = select.poll()
    logging.warning('Consumer enter {}'.format(msg_queue.qsize()))
    while thread_flag != 0:
        my_step = thread_step
        if my_step > msg_queue.qsize():
            my_step = msg_queue.qsize()
        try:
            for i in range(my_step):
                se = msg_queue.get(False)
                length = se.send(text)
                poll.register(se.fileno(), select.POLLIN | select.POLLERR)
                send_dict[se.fileno()] = se
        except Exception, e:
            pass
        count = 0
        while True:
            if len(send_dict) < (my_step / 4):
                break
            poll_list = poll.poll(10)
            if len(poll_list) == 0:
                count += 1
                if count >= 20:
                    for i in range(len(send_dict)):
                        fd,se = send_dict.popitem()
                        se.close()
                    break
            else:
                count = 0
            for fd, event in poll_list:
                if event & select.POLLIN:
                    poll.unregister(fd)
                    se = send_dict.pop(fd)
                    se.close()
                    thread_cnt += 1
                elif event & select.POLLERR:
                    poll.unregister(fd)
                    se = send_dict.pop(fd)
                    se.close()
    my_step = msg_queue.qsize()
    logging.warning('Consumer exit {}, click {}'.format(my_step, thread_cnt))
    for i in range(my_step):
        se = msg_queue.get(False)
        se.close()
    return

if __name__ == '__main__':
    # help message
    parser = argparse.ArgumentParser(description='Simulate to login Jing Dong, and click coupon')
    parser.add_argument('-k', '--key', 
                        help='Coupon key', required=True)
    parser.add_argument('-r', '--role_id', 
                        help='Coupon role id', required=True)
    parser.add_argument('-hh', '--hour', 
                        type=int, help='Target hour', default=10)
    parser.add_argument('-m', '--minute', 
                        type=int, help='Target minute', default=0)
    parser.add_argument('-p', '--process', 
                        type=int, help='Number of processes', default=1)
    parser.add_argument('-l', '--log', 
                        help='Log file', default=None)

    options = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - (%(levelname)s) %(message)s', datefmt='%H:%M:%S')  
    if (options.log != None):
        log_hdl = logging.FileHandler(options.log,"w")  
        log_hdl.setLevel(logging.WARNING)
        log_fmt = logging.Formatter("%(asctime)s - %(message)s", '%H:%M:%S')  
        log_hdl.setFormatter(log_fmt)  
        logging.getLogger('').addHandler(log_hdl)
    jd = JDCoupon()
    if not jd.pc_login():
        sys.exit(1)
    if not jd.setup(options.key, options.role_id):
        sys.exit(1)
    if options.process <= 1:
        ip, text = jd.url_to_request(jd.coupon_url)
        if None == ip:
            logging.warning("socket_get_fast failed")
        else:
            target = (options.hour * 3600) + (options.minute * 60)
            run_time = jd.duration
            jd.relax_wait(target)
            send_dict = jd.socket_prepare(ip, 10)
            jd.busy_wait(target)
            cnt = jd.socket_run(send_dict, ip, text, run_time)
            h, m, s = jd.format_local_time()
            logging.warning(u'#结束时间 {:0>2}:{:0>2}:{:0>2} #目标时间 {:0>2}:{:0>2}:{:0>2}'.format(h, m, s, options.hour, options.minute, 0))
            logging.warning(u'运行{}秒，点击{}次'.format(run_time, cnt))
            jd.my_click(logging.WARNING)
    elif options.process == 2:
        ip, text = jd.url_to_request(jd.coupon_url)
        if None == ip:
            logging.warning("socket_get_fast failed")
        else:
            thread_flag = 1
            thread_cnt = 0
            msg_queue = Queue.Queue(2048)
            t1 = threading.Thread(target=socket_producer, args=(ip, msg_queue,))
            t2 = threading.Thread(target=socket_consumer, args=(text, msg_queue,))
            target = (options.hour * 3600) + (options.minute * 60)
            run_time = jd.duration
            jd.relax_wait(target)
            t1.start()
            jd.busy_wait(target)
            t2.start()
            time.sleep(run_time)
            thread_flag = 0
            h, m, s = jd.format_local_time()
            logging.warning(u'#结束时间 {:0>2}:{:0>2}:{:0>2} #目标时间 {:0>2}:{:0>2}:{:0>2}'.format(h, m, s, options.hour, options.minute, 0))
            logging.warning(u'运行{}秒，点击{}次'.format(run_time, thread_cnt))
            jd.my_click(logging.WARNING)
            t1.join()
            t2.join()
    else:
        jd.click(logging.WARNING)
        target = (options.hour * 3600) + (options.minute * 60)
        jd.relax_wait(target)
        jd.click(logging.WARNING)
        wait_flag = multiprocessing.Value('i', 0)
        run_flag = multiprocessing.Value('i', 0)
        pool = multiprocessing.Pool(processes=options.process+1)
        result = []
        h, m, s = jd.format_local_time()
        logging.warning(u'#开始时间 {:0>2}:{:0>2}:{:0>2} #目标时间 {:0>2}:{:0>2}:{:0>2}'.format(h, m, s, options.hour, options.minute, 0))
        wait_flag.value = 1
        run_flag.value = 1
        for i in range(options.process):
            result.append(pool.apply_async(click_task, args=(jd.coupon_url, i,)))
        jd.busy_wait(target)
        wait_flag.value = 0
        run_time = jd.duration
        time.sleep(run_time)
        h, m, s = jd.format_local_time()
        logging.warning(u'#结束时间 {:0>2}:{:0>2}:{:0>2} #目标时间 {:0>2}:{:0>2}:{:0>2}'.format(h, m, s, options.hour, options.minute, 0))
        run_flag.value = 0
        pool.close()
        pool.join()
        cnt = 0
        for res in result:
            cnt += res.get()
        logging.warning(u'运行{}秒，点击{}次'.format(run_time, cnt))
