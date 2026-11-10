import time

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import (CONFIG_DISPATCHER, MAIN_DISPATCHER,
                                    DEAD_DISPATCHER, set_ev_cls)
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types
from ryu.lib import hub

# ---------------- settings ----------------
LINK_MBPS        = 10            # matches bw=10 in topology.py
SERVER_PORT      = 6             # srv is the 6th link added -> port 6 on s1
SERVER_IP        = '10.0.0.100'
POLL_INTERVAL    = 2             # seconds between stats requests
THRESHOLD_PCT    = 80            # congestion above 80% of the srv link

LIMIT_KBPS       = 2000          # a limited host may send 2 Mbps toward srv
LIMIT_SECONDS    = 30            # the limit removes itself after this long
MIN_SENDER_MBPS  = 1.0           # ignore hosts sending less than this
METER_ID         = 1
LIMIT_PRIORITY   = 10            # above learned flows (priority 1)
# ------------------------------------------


class ExamCongestionApp(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(ExamCongestionApp, self).__init__(*args, **kwargs)
        self.mac_to_port = {}     # {dpid: {mac: port}}
        self.datapaths = {}       # {dpid: datapath}
        self.prev_bytes = {}      # {(dpid, port, 'rx'/'tx'): bytes}
        self.prev_time = {}       # {dpid: time of last stats reply}
        self.limited = {}         # {port: time when its limit expires}
        self.congested = False
        self.monitor_thread = hub.spawn(self._monitor)

    # ---------- switch connects ----------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def _switch_features(self, ev):
        dp = ev.msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser

        # table-miss: send unknown packets to the controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER,
                                          ofp.OFPCML_NO_BUFFER)]
        self._add_flow(dp, 0, match, actions)

        # meter used by the rate limit (delete first in case it exists)
        dp.send_msg(parser.OFPMeterMod(
            datapath=dp, command=ofp.OFPMC_DELETE,
            flags=ofp.OFPMF_KBPS, meter_id=METER_ID))
        band = parser.OFPMeterBandDrop(rate=LIMIT_KBPS, burst_size=0)
        dp.send_msg(parser.OFPMeterMod(
            datapath=dp, command=ofp.OFPMC_ADD,
            flags=ofp.OFPMF_KBPS, meter_id=METER_ID, bands=[band]))

        self.logger.info("Switch %016x connected", dp.id)

    def _add_flow(self, dp, priority, match, actions, idle=0):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        dp.send_msg(parser.OFPFlowMod(datapath=dp, priority=priority,
                                      match=match, instructions=inst,
                                      idle_timeout=idle))

    # ---------- learning switch ----------
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in(self, ev):
        msg = ev.msg
        dp = msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        in_port = msg.match['in_port']

        eth = packet.Packet(msg.data).get_protocol(ethernet.ethernet)
        if eth is None or eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        src, dst = eth.src, eth.dst
        table = self.mac_to_port.setdefault(dp.id, {})
        table[src] = in_port

        out_port = table.get(dst, ofp.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out_port)]

        if out_port != ofp.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            self._add_flow(dp, 1, match, actions, idle=30)

        data = msg.data if msg.buffer_id == ofp.OFP_NO_BUFFER else None
        dp.send_msg(parser.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id,
                                        in_port=in_port, actions=actions,
                                        data=data))

    # ---------- track connected switches ----------
    @set_ev_cls(ofp_event.EventOFPStateChange,
                [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change(self, ev):
        dp = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            self.datapaths[dp.id] = dp
        else:
            self.datapaths.pop(dp.id, None)

    # ---------- show switch errors (e.g. meters unsupported) ----------
    @set_ev_cls(ofp_event.EventOFPErrorMsg, [CONFIG_DISPATCHER, MAIN_DISPATCHER])
    def _error(self, ev):
        msg = ev.msg
        self.logger.error("OpenFlow error from switch: type=%s code=%s",
                          msg.type, msg.code)

    # ---------- monitoring ----------
    def _monitor(self):
        while True:
            for dp in list(self.datapaths.values()):
                dp.send_msg(dp.ofproto_parser.OFPPortStatsRequest(
                    dp, 0, dp.ofproto.OFPP_ANY))
            hub.sleep(POLL_INTERVAL)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply(self, ev):
        dp = ev.msg.datapath
        now = time.time()
        last = self.prev_time.get(dp.id)
        self.prev_time[dp.id] = now

        # work out Mbps for every port, both directions
        rates = {}
        for stat in ev.msg.body:
            port = stat.port_no
            if port > dp.ofproto.OFPP_MAX:
                continue
            for kind, val in (('tx', stat.tx_bytes), ('rx', stat.rx_bytes)):
                key = (dp.id, port, kind)
                prev = self.prev_bytes.get(key)
                self.prev_bytes[key] = val
                if prev is not None and last is not None and now > last:
                    rates[(port, kind)] = (val - prev) * 8 / (now - last) / 1e6

        srv_mbps = rates.get((SERVER_PORT, 'tx'))
        if srv_mbps is None:
            return                       # first reply: no baseline yet

        # forget limits that have expired on the switch
        for port in [p for p, t in self.limited.items() if t <= now]:
            del self.limited[port]
            self.logger.info("Limit on port %s expired", port)

        pct = srv_mbps / LINK_MBPS * 100
        self.logger.info("srv link: %.2f Mbps (%.0f%%)  limited ports: %s",
                         srv_mbps, pct, sorted(self.limited) or "none")

        if pct >= THRESHOLD_PCT:
            if not self.congested:
                self.congested = True
                self.logger.warning("CONGESTION on srv link: %.2f Mbps",
                                    srv_mbps)
            self._limit_heaviest(dp, rates, now)
        elif self.congested:
            self.congested = False
            self.logger.info("srv link recovered")

    # ---------- reaction ----------
    def _limit_heaviest(self, dp, rates, now):
        """Rate-limit the host sending the most toward srv (one per poll)."""
        candidates = [(mbps, port) for (port, kind), mbps in rates.items()
                      if kind == 'rx' and port != SERVER_PORT
                      and port not in self.limited
                      and mbps >= MIN_SENDER_MBPS]
        if not candidates:
            return
        mbps, port = max(candidates)

        ofp, parser = dp.ofproto, dp.ofproto_parser
        match = parser.OFPMatch(in_port=port, eth_type=0x0800,
                                ipv4_dst=SERVER_IP)
        inst = [parser.OFPInstructionMeter(METER_ID),
                parser.OFPInstructionActions(
                    ofp.OFPIT_APPLY_ACTIONS,
                    [parser.OFPActionOutput(SERVER_PORT)])]
        dp.send_msg(parser.OFPFlowMod(datapath=dp, priority=LIMIT_PRIORITY,
                                      match=match, instructions=inst,
                                      hard_timeout=LIMIT_SECONDS))
        self.limited[port] = now + LIMIT_SECONDS
        self.logger.warning(
            "REACTION: port %s was sending %.2f Mbps -> limited to %.1f Mbps "
            "for %ds", port, mbps, LIMIT_KBPS / 1000.0, LIMIT_SECONDS)