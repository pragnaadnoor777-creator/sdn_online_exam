#!/usr/bin/env python


"""
star_topo.py

Mininet topology for the "SDN‑enabled online‑exam" project.

-srv --10 mbps , 30ms -->s1 switch port 1
 bg --100 mbps----> s1
 h1....hN --100 mbps , 30 ms-> s1 , switch ports 3... (one student per host as of now)

 
 srv 10.0.0.100 exam server(tcp , port 5000) and iperf udp sink(port 5001)
bg    10.0.0.200   sends background traffic to srv to create congestion
h1..hN   10.0.0.1..N  student hosts (N set with --students, default 10, max 99)
Switch ports are numbered in addLink order, 
so keep srv first and bg second: the controller relies on srv being port 1.
"""

import os
import json
import argparse
import os
import time
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink # traffic‑capable links
from mininet.cli import CLI
from mininet.log import setLogLevel,info, error


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
with open(os.path.join(ROOT, "config.json")) as f:
    CFG = json.load(f)

STUDENT_LINK_MBPS = 100
BG_LINK_MBPS = 100
LINK_DELAY = "30ms"
MAX_STUDENTS = 99
# all this to just avoid hardcoding ips

def star_topo(n_students):
    net = Mininet(controller=RemoteController, link=TCLink, switch=OVSSwitch)

    info("*** Adding switch s1 (OpenFlow13) ***\n")
    s1 = net.addSwitch('s1', protocols='OpenFlow13')

    info("*** Adding server host srv and bg***\n")
    srv = net.addHost('srv', ip=CFG['server_ip'] + '/24')
    bg=net.addHost('bg',ip=CFG['bg_host_ip'] + '/24')
    net.addLink(srv, s1,bw=CFG['bottleneck_mbps'],delay=LINK_DELAY)                      # server also attaches to s1
    net.addLink(bg,s1,bw=BG_LINK_MBPS)



    info("*** Adding exam hosts h1‑hN ***\n") # just added the three asterisks to tell that its more like a statement
    hosts = [] #stores all the ips of hosts
    for i in range(1, n_students+1):                     
        h = net.addHost('h%s' % i,ip='10.0.0.%d/24' % i)# generating ip for each host
        hosts.append(h) # /24 keeps 10.0.0.x together
        net.addLink(h, s1,bw=STUDENT_LINK_MBPS,delay=LINK_DELAY)                     # each host connects to the switch

    

    info("*** Adding a default controller (c0) ***\n")
    net.addController('c0',controller=RemoteController,ip='127.0.0.1',port=6653) 

    # baseline controller type thing added
    info("*** Building and starting the network ***\n")
    net.build()
    net.start()


    base=os.path.dirname(os.path.abspath(__file__))
    
    info("*** Starting exam server and iperf sink on srv ***\n")
    srv.cmd('python3 %s/server/server.py --port %d > /tmp/exam_server.log 2>&1 &'
        % (ROOT, CFG['server_port']))
    srv.cmd('iperf -s -u -p %d > /tmp/iperf_srv.log 2>&1 &' % CFG['iperf_port'])
    
    time.sleep(1)
    
    info("*** Mininet CLI is now available – type help for commands ***\n")
    CLI(net)          # you can ping, iperf, or just let the traffic run

    info("*** Stopping network ***\n")
    net.stop()


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--students', type=int, default=10)
    parser.add_argument('--mode', help='accepted and ignored')
    args = parser.parse_args()
    if not 1 <= args.students <= MAX_STUDENTS:
        parser.error('--students must be between 1 and %d' % MAX_STUDENTS)
    setLogLevel('info')
    star_topo(args.students)

    
