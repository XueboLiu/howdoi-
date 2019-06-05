#!/usr/bin/env python

#howdoi是把一个流程做成了python脚本。其流程如下：
#step1：利用site语法组装搜索语句(默认指定搜索stackoverflow网站)
#step2：利用google搜索接口获取搜索引擎的连接
#step3：访问该链接，根据排名从高倒下，提取代码块文本
#step4：提取到就显示到终端，没有提取到就提示未找到答案

#howdoi也作了一些其他的工作：
#代理设置
#既往问题进行缓存，提高下次查询的速度
#查询的目标网站可配置
#做成Python script脚本命令，方便快捷
#代码高亮（代码显示为彩色）格式化输出

######################################################
#
# howdoi - instant coding answers via the command line
# written by Benjamin Gleitzman (gleitz@mit.edu)
# inspired by Rich Jones (rich@anomos.info)
#
######################################################

import argparse #用于获取脚本命令行参数（命令行应用传参）
import glob #显示目录下所有jpg文件列表，并且以绝对路径打印
import os #处理文件和目录（程序与平台无关）
import random #帮助随机选择列表元素或打乱数据
import re #用于匹配处理字符串
import requests #用于发送http(s)请求（爬取页面）
import requests_cache #cache为requests库提供持久化缓存支持
import sys #显示python的版本
from . import __version__ #查看python版本
#用于控制台彩色高亮格式化输出,pygments为代码语法高亮库
#lexer词法分析器（输出包含空格、comments和正常tokens在内的所有字符）
#formatter格式器，把token流以HTML、LaTeX或RTF的格式输出到文件
from pygments import highlight #highlight对编程语言进行代码高亮
from pygments.lexers import guess_lexer, get_lexer_by_name #分析代码为哪种语言
from pygments.formatters.terminal import TerminalFormatter #所有代码进行命令行模式格式化
from pygments.util import ClassNotFound #无法找到指定类的异常
#用于网页解析
from pyquery import PyQuery as pq #一个非常强大又灵活的网页解析库
#字符串的初始化、打开html文件、打开某个网站、基于CSS选择器查找、查找标签、获取属性值、获取标签内容
from requests.exceptions import ConnectionError #爬取网页出现代理错误报错
from requests.exceptions import SSLError #未指定SSL证书报错

#兼容Python2.x和Python3.x的库
if sys.version < '3': #如果python的版本小于3
    import codecs #引入codecs模块（编码转换）
    from urllib import quote as url_quote #从urllib引入quote模块（屏蔽特殊字符、空格），作为url_quote
    from urllib import getproxies #从urllib引入getproxies模块（在某些版本中帮助抓取网页内容，无则不可）

    #处理unicode: http://stackoverflow.com/a/6633040/305414
    def u(x): #定义u(x)
        return codecs.unicode_escape_decode(x)[0] #返回“反编码”（将unicode码变为汉字）
else: #python的版本为3
    from urllib.request import getproxies #从urllib.request引入getproxies模块（在某些版本中帮助抓取网页内容，无则不可）
    from urllib.parse import quote as url_quote #从urllib.parse引入quote模块（屏蔽特殊字符、空格），作为url_quote

    def u(x): #定义u(x)
        return x #返回x

#设置google搜索url    (os.getenv返回进程的环境变量varname的值，若变量没有定义时3返回nil)
if os.getenv('HOWDOI_DISABLE_SSL'):  #使用系统环境变量中非SSL的http代替https，26行
    SEARCH_URL = 'http://www.google.com/search?q=site:{0}%20{1}' #搜索引擎网址
    VERIFY_SSL_CERTIFICATE = False
else:
    SEARCH_URL = 'https://www.google.com/search?q=site:{0}%20{1}' #搜索引擎网址
    VERIFY_SSL_CERTIFICATE = True
#设置目标问答网站
URL = os.getenv('HOWDOI_URL') or 'stackoverflow.com'  #26行，63行

#浏览器UA，用于伪造浏览器请求，防止网站对脚本请求进行屏蔽
USER_AGENTS = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10.7; rv:11.0) Gecko/20100101 Firefox/11.0',
               'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:22.0) Gecko/20100 101 Firefox/22.0',
               'Mozilla/5.0 (Windows NT 6.1; rv:11.0) Gecko/20100101 Firefox/11.0',
               ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_7_4) AppleWebKit/536.5 (KHTML, like Gecko) '
                'Chrome/19.0.1084.46 Safari/536.5'),
               ('Mozilla/5.0 (Windows; Windows NT 6.1) AppleWebKit/536.5 (KHTML, like Gecko) Chrome/19.0.1084.46'
                'Safari/536.5'), )
#格式化答案输出
ANSWER_HEADER = u('--- Answer {0} ---\n{1}')
NO_ANSWER_MSG = '< no answer given >'

#设置缓存文件路径（26行）
XDG_CACHE_DIR = os.environ.get('XDG_CACHE_HOME',
                               os.path.join(os.path.expanduser('~'), '.cache'))
CACHE_DIR = os.path.join(XDG_CACHE_DIR, 'howdoi')
CACHE_FILE = os.path.join(CACHE_DIR, 'cache{0}'.format(
    sys.version_info[0] if sys.version_info[0] == 3 else ''))

#获取代理（中国）
def get_proxies():
    proxies = getproxies() #proxies为引入的getproxies（50行）
    filtered_proxies = {} #空字典
    for key, value in proxies.items(): #遍历字典
        if key.startswith('http'): #项的键以http开头
            if not value.startswith('http'): #值的开头不为http
                filtered_proxies[key] = 'http://%s' % value #将值置入字符串，生成新字符串
            else:
                filtered_proxies[key] = value #将值赋给键
    return filtered_proxies #返回字典
#可能出错的语句被放在try子句中。如果错误发生，程序执行就转到接下来的except子句开始处。
#可以将前面除数为零的代码放在一个try子句中，让except子句包含代码，来处理该错误发生时应该做的事。
def _get_result(url):
    try: #可能发生异常的代码
        return requests.get(url, headers={'User-Agent': random.choice(USER_AGENTS)}, proxies=get_proxies(),
                            verify=VERIFY_SSL_CERTIFICATE).text #（29行）
    except requests.exceptions.SSLError as e: #try中发生异常时，44行
        print('[ERROR] Encountered an SSL Error. Try using HTTP instead of '
              'HTTPS by setting the environment variable "HOWDOI_DISABLE_SSL".\n') #输出
        raise e #再执行except

#获取google搜索结果中的连接
def _get_links(query):
    result = _get_result(SEARCH_URL.format(URL, url_quote(query))) #104行函数
    html = pq(result) #用pyquery进行解析（41行）
    return [a.attrib['href'] for a in html('.l')] or \
        [a.attrib['href'] for a in html('.r')('a')] #提取html中.l、.r、.a这些标签中href属性的内容
#attrib修改文件属性（只读、存档、隐藏、系统）；href属性规定的超链接目标
#.l(.lnk)用于指向其他文件的一种文件；.r(rar)
def get_link_at_pos(links, position): #每个文档对象中都可以定义多个链接对象，链接对象都存储在links[]数组中
#链接对象以在页面中出现的顺序存储在links[]数组；position为CSS中指定元素位置（若为默认值则四个方向性质无效果）
    if not links: #判断有无链接对象
        return False #无则报错

    if len(links) >= position: #判断links与position的长度
        link = links[position - 1] #若>=把数组links中索引为(position-1)的值赋给link
    else:
        link = links[-1] #把数组links中最后一个值赋给link
    return link

#代码格式化输出函数
def _format_output(code, args): #args为传递给main函数的一个数组参数
    if not args['color']: #如果无color
        return code
    lexer = None #输出为空（34行）

    #尝试使用StackOverflow标记找到一个lexer
    #或查询参数
    for keyword in args['query'].split() + args['tags']: #遍历新数组
        try: #可能异常代码（102行）
            lexer = get_lexer_by_name(keyword) #函数返回值，37行
            break
        except ClassNotFound: #39行
            pass

    #上面没有找到lexer,则使用guesser
    if not lexer: #找不到lexer
        try: #可能异常代码（102行）
            lexer = guess_lexer(code) #函数返回值，37行
        except ClassNotFound: #39行
            return code #返回值为code

    return highlight(code,
                     lexer,
                     TerminalFormatter(bg='dark')) #返回函数值36行，38行

#利用政策匹配判断连接是否是问题
def _is_question(link):
    return re.search('questions/\d+/', link) #调用re(28行)，在link中找questions/\d+/并返回对象

#获取问题连接
def _get_questions(links):
    return [link for link in links if _is_question(link)] #158行

#获取答案（主要是解析stackoverflow的问答页面）（52行）
def _get_answer(args, links):
    links = _get_questions(links) #163行
    link = get_link_at_pos(links, args['pos']) #121行
    if not link: #判断是否存在link
        return False
    if args.get('link'): #寻找link
        return link
    page = _get_result(link + '?answertab=votes') #104行，将拼接后的函数返回值赋给page
    html = pq(page) #41行，解析网页
    
    first_answer = html('.answer').eq(0) #第一个答案
    instructions = first_answer.find('pre') or first_answer.find('code') #pre和code标签为目标代码块
    args['tags'] = [t.text for t in html('.post-tag')] #匹配标签，并显示文章标签

    if not instructions and not args['all']: #如果找不到目标代码块和文件
        text = first_answer.find('.post-text').eq(0).text() #寻找目标代码块中第一个并赋给text
    elif args['all']: #若找到目标文件
        texts = [] #令text为空列表
        for html_tag in first_answer.items('.post-text > *'): #匹配字符串
            current_text = html_tag.text() #读取文本
            if current_text: 
                if html_tag[0].tag in ['pre', 'code']: #判断第一个是否为目标代码块
                    texts.append(_format_output(current_text, args)) #格式化输出的内容加到列表texts末尾
                else:
                    texts.append(current_text) #直接加到末尾
        texts.append('\n---\nAnswer from {0}'.format(link)) #将格式化输出的链接加到末尾，参考81行
        text = '\n'.join(texts) #合并两个列表，中间加一个换行作为分隔符
    else:
        text = _format_output(instructions.eq(0).text(), args) #调用132行代码格式化输出函数，赋给text
    if text is None: #若为空
        text = NO_ANSWER_MSG #格式化输出为< no answer given >，82行
    text = text.strip() #对text进行strip操作（把头和尾的空格以及位于头尾的\n和\t删掉）
    return text


def _get_instructions(args):
    links = _get_links(args['query']) #调用114行函数，获取搜索结果中的链接

    if not links:
        return False #无链接则报错
    answers = [] #创建新列表
    append_header = args['num_answers'] > 1 #如果表达式的值为真，则为1，否则，为0
    initial_position = args['pos']
    for answer_number in range(args['num_answers']): #遍历从0到args['num_answers']
        current_position = answer_number + initial_position #拼接字符串
        args['pos'] = current_position
        answer = _get_answer(args, links)
        if not answer:
            continue
        if append_header:
            answer = ANSWER_HEADER.format(current_position, answer) #格式化答案输出，81行
        answer += '\n' #末尾加换行
        answers.append(answer) #末尾加answer
    return '\n'.join(answers) #拼接分隔符与answers

#启动缓存
def _enable_cache():
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
    requests_cache.install_cache(CACHE_FILE)

#清除缓存
def _clear_cache():
    for cache in glob.glob('{0}*'.format(CACHE_FILE)):
        os.remove(cache)

#脚本主函数
def howdoi(args):
    #构造查询（主要是把问号删除）
    args['query'] = ' '.join(args['query']).replace('?', '')
    try:
        return _get_instructions(args) or 'Sorry, couldn\'t find any help with that topic\n'
    except (ConnectionError, SSLError):
        return 'Failed to establish network connection\n'

#获取用户输入的命令行参数
def get_parser():
    parser = argparse.ArgumentParser(description='instant coding answers via the command line')
    parser.add_argument('query', metavar='QUERY', type=str, nargs='*',
                        help='the question to answer')
    parser.add_argument('-p', '--pos', help='select answer in specified position (default: 1)', default=1, type=int)
    parser.add_argument('-a', '--all', help='display the full text of the answer',
                        action='store_true')
    parser.add_argument('-l', '--link', help='display only the answer link',
                        action='store_true')
    parser.add_argument('-c', '--color', help='enable colorized output',
                        action='store_true')
    parser.add_argument('-n', '--num-answers', help='number of answers to return', default=1, type=int)
    parser.add_argument('-C', '--clear-cache', help='clear the cache',
                        action='store_true')
    parser.add_argument('-v', '--version', help='displays the current version of howdoi',
                        action='store_true')
    return parser

#启动函数
def command_line_runner():
    parser = get_parser()
    args = vars(parser.parse_args())

    #输出脚本版本
    if args['version']:
        print(__version__)
        return
    #清除缓存
    if args['clear_cache']:
        _clear_cache()
        print('Cache cleared successfully')
        return
    #如果没有query，就输出帮助信息
    if not args['query']:
        parser.print_help()
        return

    #如果环境变量设置了禁止缓存，就清除缓存
    if not os.getenv('HOWDOI_DISABLE_CACHE'):
        _enable_cache()
    #彩色输出
    if os.getenv('HOWDOI_COLORIZE'):
        args['color'] = True
    #如果用户Python版本小于3就进行utf-8编码，如否，就正常启动
    if sys.version < '3':
        print(howdoi(args).encode('utf-8', 'ignore'))
    else:
        print(howdoi(args))


if __name__ == '__main__':
    command_line_runner()



