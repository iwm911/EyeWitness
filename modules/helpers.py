import os
import platform
import random
import shutil
import sys
import time
import xml.sax
from distutils.util import strtobool
import glob
import socket
from netaddr import IPAddress
from netaddr.core import AddrFormatError
from urlparse import urlparse
from login_module import checkCreds
import OpenSSL
import ssl
from pyasn1.type import univ, constraint, char, namedtype, tag
from pyasn1.codec.der.decoder import decode
from pyasn1.error import PyAsn1Error

class XML_Parser(xml.sax.ContentHandler):

    def __init__(self, file_out, class_cli_obj):
        self.system_name = None
        self.port_number = None
        self.protocol = None
        self.masscan = False
        self.nmap = False
        self.nessus = False
        self.url_list = []
        self.port_open = False
        self.rdp_list = []
        self.vnc_list = []
        self.http_ports = ['80', '8080']
        self.https_ports = ['443', '8443']
        self.num_urls = 0
        self.get_fqdn = False
        self.get_ip = False
        self.service_detection = False
        self.out_file = file_out

        self.http_ports = self.http_ports + class_cli_obj.add_http_ports
        self.https_ports = self.https_ports + class_cli_obj.add_https_ports
        self.no_dns = class_cli_obj.no_dns
        self.only_ports = class_cli_obj.only_ports

    def startElement(self, tag, attributes):
        # Determine the Scanner being used
        if tag == "nmaprun" and attributes['scanner'] == "masscan":
            self.masscan = True
        elif tag == "nmaprun" and attributes['scanner'] == "nmap":
            self.nmap = True
        elif tag == "NessusClientData_v2":
            self.nessus = True

        if self.masscan or self.nmap:
            if tag == "address":
                if attributes['addrtype'].lower() == "mac":
                    pass
                else:
                    self.system_name = attributes['addr']
            elif tag == "hostname":
                if not self.no_dns:
                    if attributes['type'].lower() == "user":
                        self.system_name = attributes['name']
            elif tag == "port":
                self.port_number = attributes['portid']
            elif tag == "service":
                if "ssl" in attributes['name'] or self.port_number in self.https_ports:
                    self.protocol = "https"
                elif "http" == attributes['name'] or self.port_number in self.http_ports:
                    self.protocol = "http"
                elif "http-alt" == attributes['name']:
                    self.protocol = "http"
                elif "tunnel" in attributes:
                    if "ssl" in attributes['tunnel']:
                        self.protocol = "https"
                elif "vnc" in attributes['name']:
                    self.protocol = "vnc"
                elif "ms-wbt-server" in attributes['name']:
                    self.protocol = "rdp"
            elif tag == "state":
                if attributes['state'] == "open":
                    self.port_open = True

        elif self.nessus:
            if tag == "ReportHost":
                if 'name' in attributes:
                    self.system_name = attributes['name']

            elif tag == "ReportItem":
                if "port" in attributes and "svc_name" in attributes and "pluginName" in attributes:
                    self.port_number = attributes['port']

                    service_name = attributes['svc_name']
                    if service_name == 'https?' or self.port_number in self.https_ports:
                        self.protocol = "https"
                    elif service_name == "www" or service_name == "http?":
                        self.protocol = "http"
                    elif service_name == "msrdp":
                        self.protocol = "rdp"
                    elif service_name == "vnc":
                        self.protocol = "vnc"

                    self.service_detection = True
        return

    def endElement(self, tag):
        if self.masscan or self.nmap:
            if tag == "service":
                if not self.only_ports:
                    if (self.system_name is not None) and (self.port_number is not None) and self.port_open:
                        if self.protocol == "http" or self.protocol == "https":
                            built_url = self.protocol + "://" + self.system_name + ":" + self.port_number
                            if built_url not in self.url_list:
                                self.url_list.append(built_url)
                                self.num_urls += 1
                        elif self.protocol is None and self.port_number in self.http_ports:
                            built_url = "http://" + self.system_name + ":" + self.port_number
                            if built_url not in self.url_list:
                                self.url_list.append(built_url)
                                self.num_urls += 1
                        elif self.protocol is None and self.port_number in self.https_ports:
                            built_url = "https://" + self.system_name + ":" + self.port_number
                            if built_url not in self.url_list:
                                self.url_list.append(built_url)
                                self.num_urls += 1
                        elif self.protocol == "vnc":
                            if self.system_name not in self.vnc_list:
                                self.vnc_list.append(self.system_name)
                        elif self.port_number == "3389":
                            if self.system_name not in self.rdp_list:
                                self.rdp_list.append(self.system_name)
                else:
                    if (self.system_name is not None) and (self.port_number is not None) and self.port_open and int(self.port_number.encode('utf-8')) in self.only_ports:
                        if self.protocol == "http" or self.protocol == "https":
                            built_url = self.protocol + "://" + self.system_name
                            if built_url not in self.url_list:
                                self.url_list.append(built_url)
                                self.num_urls += 1
                        elif self.protocol is None and self.port_number in self.http_ports:
                            built_url = "http://" + self.system_name
                            if built_url not in self.url_list:
                                self.url_list.append(built_url)
                                self.num_urls += 1
                        elif self.protocol is None and self.port_number in self.https_ports:
                            built_url = "https://" + self.system_name
                            if built_url not in self.url_list:
                                self.url_list.append(built_url)
                                self.num_urls += 1
                        elif self.protocol == "vnc":
                            if self.system_name not in self.vnc_list:
                                self.vnc_list.append(self.system_name)
                        elif self.port_number == "3389":
                            if self.system_name not in self.rdp_list:
                                self.rdp_list.append(self.system_name)

                self.port_number = None
                self.protocol = None
                self.port_open = False

            elif tag == "host":
                self.system_name = None

            elif tag == "nmaprun":
                if len(self.url_list) > 0:
                    with open(self.out_file, 'a') as temp_web:
                        for url in self.url_list:
                            temp_web.write(url + '\n')
                if len(self.rdp_list) > 0:
                    with open(self.out_file, 'a') as temp_rdp:
                        for rdp in self.rdp_list:
                            temp_rdp.write(rdp + '\n')
                if len(self.vnc_list) > 0:
                    with open(self.out_file, 'a') as temp_vnc:
                        for vnc in self.vnc_list:
                            temp_vnc.write(vnc + '\n')

        elif self.nessus:
            if tag == "ReportItem":
                if not self.only_ports:
                    if (self.system_name is not None) and (self.protocol is not None) and self.service_detection:
                        if self.protocol == "http" or self.protocol == "https":
                            built_url = self.protocol + "://" + self.system_name + ":" + self.port_number
                            if built_url not in self.url_list:
                                self.url_list.append(built_url)
                        elif self.protocol == "vnc":
                            if self.system_name not in self.vnc_list:
                                self.vnc_list.append(self.system_name)
                        elif self.protocol == "rdp":
                            if self.system_name not in self.rdp_list:
                                self.rdp_list.append(self.system_name)
                else:
                    if (self.system_name is not None) and (self.protocol is not None) and self.service_detection and int(self.port_number.encode('utf-8')) in self.only_ports:
                        if self.protocol == "http" or self.protocol == "https":
                            built_url = self.protocol + "://" + self.system_name + ":" + self.port_number
                            if built_url not in self.url_list:
                                self.url_list.append(built_url)
                        elif self.protocol == "vnc":
                            if self.system_name not in self.vnc_list:
                                self.vnc_list.append(self.system_name)
                        elif self.protocol == "rdp":
                            if self.system_name not in self.rdp_list:
                                self.rdp_list.append(self.system_name)

                self.port_number = None
                self.protocol = None
                self.port_open = False
                self.service_detection = False

            elif tag == "ReportHost":
                self.system_name = None

            elif tag == "NessusClientData_v2":
                if len(self.url_list) > 0:
                    with open(self.out_file, 'a') as temp_web:
                        for url in self.url_list:
                            temp_web.write(url + '\n')
                if len(self.rdp_list) > 0:
                    with open(self.out_file, 'a') as temp_rdp:
                        for rdp in self.rdp_list:
                            temp_rdp.write(rdp + '\n')
                if len(self.vnc_list) > 0:
                    with open(self.out_file, 'a') as temp_vnc:
                        for vnc in self.vnc_list:
                            temp_vnc.write(vnc + '\n')

    def characters(self, content):
        return


def resolve_host(system):
    parsed = urlparse(system)
    system = parsed.path if parsed.netloc == '' else parsed.netloc
    try:
        toresolve = IPAddress(system)
        resolved = socket.gethostbyaddr(str(toresolve))[0]
        return resolved
    except AddrFormatError:
        pass
    except socket.herror:
        return 'Unknown'

    try:
        resolved = socket.gethostbyname(system)
        return resolved
    except socket.gaierror:
        return 'Unknown'


def find_file_name():
    file_not_found = True
    file_name = "parsed_xml"
    counter = 0
    first_time = True
    while file_not_found:
        if first_time:
            if not os.path.isfile(file_name + ".txt"):
                file_not_found = False
            else:
                counter += 1
                first_time = False
        else:
            if not os.path.isfile(file_name + str(counter) + ".txt"):
                file_not_found = False
            else:
                counter += 1
    if first_time:
        return file_name + ".txt"
    else:
        return file_name + str(counter) + ".txt"


def textfile_parser(file_to_parse, cli_obj):
    urls = []
    rdp = []
    vnc = []

    try:
        # Open the URL file and read all URLs, and reading again to catch
        # total number of websites
        with open(file_to_parse) as f:
            all_urls = [url for url in f if url.strip()]

        # else:
        for line in all_urls:
            line = line.strip()
            if not cli_obj.only_ports:
                if line.startswith('http://') or line.startswith('https://'):
                    urls.append(line)
                elif line.startswith('rdp://'):
                    rdp.append(line[6:])
                elif line.startswith('vnc://'):
                    vnc.append(line[6:])
                else:
                    if cli_obj.rdp:
                        rdp.append(line)
                    if cli_obj.vnc:
                        vnc.append(line)
                    if cli_obj.web or cli_obj.headless:
                        if cli_obj.prepend_https:
                            urls.append("http://" + line)
                            urls.append("https://" + line)
                        else:
                            urls.append(line)
            else:
                if line.startswith('http://') or line.startswith('https://'):
                    for port in cli_obj.only_ports:
                        urls.append(line + ':' + str(port))
                else:
                    if cli_obj.web or cli_obj.headless:
                        if cli_obj.prepend_https:
                            for port in cli_obj.only_ports:
                                urls.append("http://" + line + ':' + str(port))
                                urls.append("https://" + line + ':' + str(port))
                        else:
                            for port in cli_obj.only_ports:
                                urls.append(line + ':' + str(port))

        return urls, rdp, vnc

    except IOError:
        print "ERROR: You didn't give me a valid file name! I need a valid file containing URLs!"
        sys.exit()


def target_creator(command_line_object):
    """Parses input files to create target lists

    Args:
        command_line_object (ArgumentParser): Command Line Arguments

    Returns:
        List: URLs detected for http
        List: Hosts detected for RDP
        List: Hosts detected for VNC
    """

    if command_line_object.x is not None:

        # Get a file name for the parsed results
        parsed_file_name = find_file_name()

        # Create parser
        parser = xml.sax.make_parser()

        # Turn off namespaces
        parser.setFeature(xml.sax.handler.feature_namespaces, 0)
        # Override the parser
        Handler = XML_Parser(parsed_file_name, command_line_object)
        parser.setContentHandler(Handler)
        # Parse the XML

        parser.parse(command_line_object.x)

        out_urls, out_rdp, out_vnc = textfile_parser(
            parsed_file_name, command_line_object)
        return out_urls, out_rdp, out_vnc

    elif command_line_object.f is not None:

        file_urls, file_rdp, file_vnc = textfile_parser(
            command_line_object.f, command_line_object)
        return file_urls, file_rdp, file_vnc


def get_ua_values(cycle_value):
    """Create the dicts which hold different user agents.
    Thanks to Chris John Riley for having an awesome tool which I
    could get this info from. His tool - UAtester.py -
    http://blog.c22.cc/toolsscripts/ua-tester/
    Additional user agent strings came from -
    http://www.useragentstring.com/pages/useragentstring.php

    Args:
        cycle_value (String): Which UA dict to retrieve

    Returns:
        Dict: Dictionary of user agents
    """

    # "Normal" desktop user agents
    desktop_uagents = {
        "MSIE9.0": ("Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1;"
                    " Trident/5.0)"),
        "MSIE8.0": ("Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 6.1; WOW64;"
                    "Trident/4.0)"),
        "MSIE7.0": "Mozilla/5.0 (Windows; U; MSIE 7.0; Windows NT 6.0; en-US)",
        "MSIE6.0": ("Mozilla/5.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1;"
                    " .NET CLR 2.0.50727)"),
        "Chrome32.0.1667.0": ("Mozilla/5.0 (Windows NT 6.2; Win64; x64)"
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/32.0.1667.0"
                              "Safari/537.36"),
        "Chrome31.0.1650.16": ("Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36"
                               " (KHTML, like Gecko) Chrome/31.0.1650.16 Safari/537.36"),
        "Firefox25": ("Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:25.0)"
                      " Gecko/20100101 Firefox/25.0"),
        "Firefox24": ("Mozilla/5.0 (Windows NT 6.0; WOW64; rv:24.0)"
                      " Gecko/20100101 Firefox/24.0,"),
        "Opera12.14": ("Opera/9.80 (Windows NT 6.0) Presto/2.12.388"
                       " Version/12.14"),
        "Opera12": ("Opera/12.0(Windows NT 5.1;U;en)Presto/22.9.168"
                    " Version/12.00"),
        "Safari5.1.7": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_6_8)"
                        " AppleWebKit/537.13+ (KHTML, like Gecko) Version/5.1.7 Safari/534.57.2"),
        "Safari5.0": ("Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US)"
                      " AppleWebKit/533.18.1 (KHTML, like Gecko) Version/5.0 Safari/533.16")
    }

    # Miscellaneous user agents
    misc_uagents = {
        "wget1.9.1": "Wget/1.9.1",
        "curl7.9.8": ("curl/7.9.8 (i686-pc-linux-gnu) libcurl 7.9.8"
                      " (OpenSSL 0.9.6b) (ipv6 enabled)"),
        "PyCurl7.23.1": "PycURL/7.23.1",
        "Pythonurllib3.1": "Python-urllib/3.1"
    }

    # Bot crawler user agents
    crawler_uagents = {
        "Baiduspider": "Baiduspider+(+http://www.baidu.com/search/spider.htm)",
        "Bingbot": ("Mozilla/5.0 (compatible;"
                    " bingbot/2.0 +http://www.bing.com/bingbot.htm)"),
        "Googlebot2.1": "Googlebot/2.1 (+http://www.googlebot.com/bot.html)",
        "MSNBot2.1": "msnbot/2.1",
        "YahooSlurp!": ("Mozilla/5.0 (compatible; Yahoo! Slurp;"
                        " http://help.yahoo.com/help/us/ysearch/slurp)")
    }

    # Random mobile User agents
    mobile_uagents = {
        "BlackBerry": ("Mozilla/5.0 (BlackBerry; U; BlackBerry 9900; en)"
                       " AppleWebKit/534.11+ (KHTML, like Gecko) Version/7.1.0.346 Mobile"
                       " Safari/534.11+"),
        "Android": ("Mozilla/5.0 (Linux; U; Android 2.3.5; en-us; HTC Vision"
                    " Build/GRI40) AppleWebKit/533.1 (KHTML, like Gecko) Version/4.0"
                    " Mobile Safari/533.1"),
        "IEMobile9.0": ("Mozilla/5.0 (compatible; MSIE 9.0; Windows Phone OS"
                        " 7.5; Trident/5.0; IEMobile/9.0)"),
        "OperaMobile12.02": ("Opera/12.02 (Android 4.1; Linux; Opera"
                             " Mobi/ADR-1111101157; U; en-US) Presto/2.9.201 Version/12.02"),
        "iPadSafari6.0": ("Mozilla/5.0 (iPad; CPU OS 6_0 like Mac OS X)"
                          " AppleWebKit/536.26 (KHTML, like Gecko) Version/6.0 Mobile/10A5355d"
                          " Safari/8536.25"),
        "iPhoneSafari7.0.6": ("Mozilla/5.0 (iPhone; CPU iPhone OS 7_0_6 like"
                              " Mac OS X) AppleWebKit/537.51.1 (KHTML, like Gecko) Version/7.0"
                              " Mobile/11B651 Safari/9537.53")
    }

    # Web App Vuln Scanning user agents (give me more if you have any)
    scanner_uagents = {
        "w3af": "w3af.org",
        "skipfish": "Mozilla/5.0 SF/2.10b",
        "HTTrack": "Mozilla/4.5 (compatible; HTTrack 3.0x; Windows 98)",
        "nikto": "Mozilla/5.00 (Nikto/2.1.5) (Evasions:None) (Test:map_codes)"
    }

    # Combine all user agents into a single dictionary
    all_combined_uagents = dict(desktop_uagents.items() + misc_uagents.items()
                                + crawler_uagents.items() +
                                mobile_uagents.items())

    cycle_value = cycle_value.lower()

    if cycle_value == "browser":
        return desktop_uagents
    elif cycle_value == "misc":
        return misc_uagents
    elif cycle_value == "crawler":
        return crawler_uagents
    elif cycle_value == "mobile":
        return mobile_uagents
    elif cycle_value == "scanner":
        return scanner_uagents
    elif cycle_value == "all":
        return all_combined_uagents
    else:
        print "[*] Error: You did not provide the type of user agents\
         to cycle through!".replace('    ', '')
        print "[*] Error: Defaulting to desktop browser user agents."
        return desktop_uagents


def title_screen():
    """Prints the title screen for EyeWitness
    """
    if platform.system() == "Windows":
        os.system('cls')
    else:
        os.system('clear')
    print "#" * 80
    print "#" + " " * 34 + "EyeWitness" + " " * 34 + "#"
    print "#" * 80 + "\n"

    python_info = sys.version_info
    if python_info[0] is not 2 or python_info[1] < 7:
        print "[*] Error: Your version of python is not supported!"
        print "[*] Error: Please install Python 2.7.X"
        sys.exit()
    else:
        pass
    return


def strip_nonalphanum(string):
    """Strips any non-alphanumeric characters in the ascii range from a string

    Args:
        string (String): String to strip

    Returns:
        String: String stripped of all non-alphanumeric characters
    """
    todel = ''.join(c for c in map(chr, range(256)) if not c.isalnum())
    return string.translate(None, todel)


def do_jitter(cli_parsed):
    """Jitters between URLs to add delay/randomness

    Args:
        cli_parsed (ArgumentParser): CLI Object

    Returns:
        TYPE: Description
    """
    if cli_parsed.jitter is not 0:
        sleep_value = random.randint(0, 30)
        sleep_value = sleep_value * .01
        sleep_value = 1 - sleep_value
        sleep_value = sleep_value * cli_parsed.jitter
        print "[*] Sleeping for " + str(sleep_value) + " seconds.."
        try:
            time.sleep(sleep_value)
        except KeyboardInterrupt:
            pass


def create_folders_css(cli_parsed):
    """Writes out the CSS file and generates folders for output

    Args:
        cli_parsed (ArgumentParser): CLI Object
    """
    css_page = """img {
    max-width:100%;
    height:auto;
    }
    #screenshot{
    max-width: 850px;
    max-height: 550px;
    display: inline-block;
    width: 850px;
    overflow:scroll;
    }
    .hide{
    display:none;
    }
    .uabold{
    font-weight:bold;
    cursor:pointer;
    background-color:green;
    }
    .uared{
    font-weight:bold;
    cursor:pointer;
    background-color:red;
    }
    table.toc_table{
    border-collapse: collapse;
    border: 1px solid black;
    }
    table.toc_table td{
    border: 1px solid black;
    padding: 3px 8px 3px 8px;
    }
    table.toc_table th{
    border: 1px solid black;
    text-align: left;
    padding: 3px 8px 3px 8px;
    }
    """

    # Create output directories
    os.makedirs(cli_parsed.d)
    os.makedirs(os.path.join(cli_parsed.d, 'screens'))
    os.makedirs(os.path.join(cli_parsed.d, 'source'))
    local_path = os.path.dirname(os.path.realpath(__file__))
    # Move our jquery file to the local directory
    shutil.copy2(
        os.path.join(local_path, '..', 'bin', 'jquery-1.11.3.min.js'), cli_parsed.d)

    # Write our stylesheet to disk
    with open(os.path.join(cli_parsed.d, 'style.css'), 'w') as f:
        f.write(css_page)


def default_creds_category(http_object):
    """Adds default credentials or categories to a http_object if either exist

    Args:
        http_object (HTTPTableObject): Object representing a URL

    Returns:
        HTTPTableObject: Object with creds/category added
    """
    http_object.default_creds = None
    http_object.category = None
    try:
        sigpath = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               '..', 'signatures.txt')
        catpath = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               '..', 'categories.txt')
        with open(sigpath) as sig_file:
            signatures = sig_file.readlines()

        with open(catpath) as cat_file:
            categories = cat_file.readlines()

        # Loop through and see if there are any matches from the source code
        # EyeWitness obtained
        if http_object.source_code is not None:
            for sig in signatures:
                # Find the signature(s), split them into their own list if needed
                # Assign default creds to its own variable
                sig_cred = sig.split('|')
                page_sig = sig_cred[0].split(";")
                cred_info = sig_cred[1].strip()

                # Set our variable to 1 if the signature was not identified.  If it is
                # identified, it will be added later on.  Find total number of
                # "signatures" needed to uniquely identify the web app
                # signature_range = len(page_sig)

                # This is used if there is more than one "part" of the
                # web page needed to make a signature Delimete the "signature"
                # by ";" before the "|", and then have the creds after the "|"
                if all([x.lower() in http_object.source_code.lower() for x in page_sig]):
                    if http_object.default_creds is None:
                        http_object.default_creds = cred_info
                    else:
                        http_object.default_creds += '\n' + cred_info

            for cat in categories:
                # Find the signature(s), split them into their own list if needed
                # Assign default creds to its own variable
                cat_split = cat.split('|')
                cat_sig = cat_split[0].split(";")
                cat_name = cat_split[1]

                # Set our variable to 1 if the signature was not identified.  If it is
                # identified, it will be added later on.  Find total number of
                # "signatures" needed to uniquely identify the web app
                # signature_range = len(page_sig)

                # This is used if there is more than one "part" of the
                # web page needed to make a signature Delimete the "signature"
                # by ";" before the "|", and then have the creds after the "|"
                if all([x.lower() in http_object.source_code.lower() for x in cat_sig]):
                    http_object.category = cat_name.strip()
                    break

        if http_object.page_title is not None:
            if '403 Forbidden' in http_object.page_title or '401 Unauthorized' in http_object.page_title:
                http_object.category = 'unauth'
            if ('Index of /' in http_object.page_title or
                    'Directory Listing For /' in http_object.page_title or
                    'Directory of /' in http_object.page_title):
                http_object.category = 'dirlist'
            if '404 Not Found' in http_object.page_title:
                http_object.category = 'notfound'        

        #Performs login against host to see if it is a valid login
        if http_object._active_scan:            
            http_object = checkCreds(http_object)

        return http_object
    except IOError:
        print("[*] WARNING: Credentials file not in the same directory"
              " as EyeWitness")
        print '[*] Skipping credential check'
        return http_object


def open_file_input(cli_parsed):
    files = glob.glob(os.path.join(cli_parsed.d, '*report.html'))
    if len(files) > 0:
        print('\n[*] Done! Report written in the {0} folder!').format(
            cli_parsed.d)
        print 'Would you like to open the report now? [Y/n]',
        while True:
            try:
                response = raw_input().lower()
                if response is "":
                    return True
                else:
                    return strtobool(response)
            except ValueError:
                print "Please respond with y or n",
    else:
        print '[*] No report files found to open, perhaps no hosts were successful'
        return False


class _GeneralName(univ.Choice):
    # Copied from https://github.com/theprincy/sslchecker
    # We are only interested in dNSNames. We use a default handler to ignore
    # other types.
    # TODO: We should also handle iPAddresses.
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('dNSName', char.IA5String().subtype(
            implicitTag=tag.Tag(tag.tagClassContext, tag.tagFormatSimple, 2)
        )
        ),
    )


class _GeneralNames(univ.SequenceOf):
    # Copied from https://github.com/theprincy/sslchecker
    componentType = _GeneralName()
    sizeSpec = univ.SequenceOf.sizeSpec + \
        constraint.ValueSizeConstraint(1, 1024)


class Certificate(object):
    # Based on https://github.com/theprincy/sslchecker
    def __init__(self,ip,port=443):
        cert = ssl.get_server_certificate((ip, port))
        self.x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, cert)

    def subject(self):
        return self.x509.get_subject().get_components()

    def cn(self):
        c = None
        for i in self.subject():
            if i[0] == b"CN":
                c = i[1]
        if type(c) == bytes:
            c = c.decode('utf-8')
        return c


    def altnames(self):
        altnames = []
        for i in range(self.x509.get_extension_count()):
            ext = self.x509.get_extension(i)
            if ext.get_short_name() == b"subjectAltName":
                try:
                    dec = decode(ext.get_data(), asn1Spec=_GeneralNames())
                except PyAsn1Error:
                    continue
                for i in dec[0]:
                    altnames.append(i[0].asOctets())
        if type(altnames) == bytes:
            altnames = altnames.decode('utf-8')
        return altnames
