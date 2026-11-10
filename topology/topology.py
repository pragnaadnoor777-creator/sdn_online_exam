#!/usr/bin/env python


"""
star_topo.py

Mininet topology for the "SDN‑enabled online‑exam" project.

- 1 switch (Open vSwitch, OpenFlow 1.3)   named s1
- 5 exam‑taker hosts   h1 … h5   (IPs 10.0.0.1 … 10.0.0.5)
- 1 server host        srv      (IP 10.0.0.2, holds the exam page)
- Links are created with TCLink:
      * bandwidth = 5 Mbps
      * delay     = 30 ms
  This emulates a constrained capacity that makes the switch’s output
  queue grow when many hosts send traffic at once.
- A tiny Python HTTP server on the server host replies “Exam page OK”
  to a GET /exam request.
- Each exam host repeatedly fetches that URL (≈ 60 requests per host,
  150 ms between requests) – the background load that the Ryu controller
  will watch for congestion.
"""
import os
import time
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink # traffic‑capable links
from mininet.cli import CLI
from mininet.log import setLogLevel,info, error


def star_topo():
    net = Mininet(controller=RemoteController, link=TCLink, switch=OVSSwitch)

    info("*** Adding switch s1 (OpenFlow13) ***\n")
    s1 = net.addSwitch('s1', protocols='OpenFlow13')

    info("*** Adding exam hosts h1‑h5 ***\n") # just added the three asterisks to tell that its more like a statement
    hosts = [] #stores all the ips of hosts
    for i in range(1, 6):                     # h1 … h5
        h = net.addHost('h%s' % i,ip='10.0.0.%i' % i)# generating ip for each host
        hosts.append(h)
        net.addLink(h, s1,bw=10,delay='30ms')                     # each host connects to the switch

    info("*** Adding server host srv ***\n")
    srv = net.addHost('srv', ip='10.0.0.100')   # exam‑paper server ,we'll keep that on 100 , since hosts are on .1 to .5
    net.addLink(srv, s1,bw=10,delay='30ms')                      # server also attaches to s1

    info("*** Adding a default controller (c0) ***\n")
    net.addController('c0',controller=RemoteController,ip='127.0.0.1',port=6653)   # Ryu will bind to the default port 6633
    # baseline controller type thing added
    info("*** Building and starting the network ***\n")
    net.build()
    net.start()


    base=os.path.dirname(os.path.abspath(__file__))
    # -----------------------------------------------------------------
    # Very small HTTP server on the server host (port 8080)
    # -----------------------------------------------------------------
    info("*** Starting HTTP server on srv (port 8080) ***\n")

    srv.cmd('python3 %s/server.py > /tmp/srv.log 2>&1 &' % base)
    time.sleep(1) 
    # -----------------------------------------------------------------
    # Generate background traffic from every exam host.
    # -----------------------------------------------------------------
    info("*** Starting exam traffic from all hosts ***\n")
    for h in hosts:
        # The “&” runs the loop in the background so all hosts start at once.
        h.cmd('python3 %s/exam_client.py > /tmp/%s.log 2>&1 &' %(base,h.name))   # background & so all hosts begin instantly

    info("*** Mininet CLI is now available – type help for commands ***\n")
    CLI(net)          # you can ping, iperf, or just let the traffic run

    info("*** Stopping network ***\n")
    net.stop()


if __name__ == '__main__':
    setLogLevel('info')   # makes the Mininet info() lines appear
    star_topo()
