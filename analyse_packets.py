import environment
import db
import pyshark
import socket
import os
import argparse
import csv_saver


# Analyse a pkt to save it in the good key of our date structure
def analyse_packets(pkt):
    if (('TCP' in pkt or 'UDP' in pkt) and ('IP' in pkt or 'IPV6' in pkt)):
        # time when the packet was received
        timestamp = float(pkt.sniff_timestamp)
        
        # A stream index is an id for stream between ipA:portA and ipB:portB
        streamIndex = -1
        protocol = ''
        if 'TCP' in pkt:
            streamIndex = str(pkt.tcp.stream)
            protocol = 'tcp'
        else:
            streamIndex = pkt.udp.stream
            protocol = 'udp'
        
        # If we already have the stream in the dict or not
        if (streamIndex not in packet_dict):
            # Get the remote ip of the stream
            ipSrc = pkt.ipv6.src if 'IPV6' in pkt else pkt.ip.src
            ipDst = pkt.ipv6.dst if 'IPV6' in pkt else pkt.ip.dst
            save_new_stream(streamIndex, timestamp, ipSrc, ipDst, pkt, protocol)
        else:
            time_delta = float(pkt[protocol].time_delta)
            average_delta = packet_dict[streamIndex]['averageDelta']

            # Based on the average delta time we split the packets
            if (average_delta != 0 and time_delta > average_delta * 3):
                push_data(streamIndex)
                del packet_dict[streamIndex]
            else:
                # Update the delta average
                sum_delta = packet_dict[streamIndex]['sumDelta'] + time_delta
                number_of_packets = packet_dict[streamIndex]['numberOfPackets'] + 1
                average_delta = sum_delta / number_of_packets

                # Save the new data of the stream
                packet_dict[streamIndex]['endTime'] = timestamp
                packet_dict[streamIndex]['sumDelta'] = sum_delta
                packet_dict[streamIndex]['numberOfPackets'] = number_of_packets
                packet_dict[streamIndex]['averageDelta'] = average_delta
                packet_dict[streamIndex]['totalMbSize'] += get_packet_size(
                    pkt)


# Get the size in MB of a packet
def get_packet_size(pkt):
    return int(pkt.length.raw_value, 16) * 0.000001


# Save a new stream and its first packet in the dict
def save_new_stream(stream_id, timestamp, ipSrc, ipDst, pkt, protocol):
    domainSrc = reverse_dns(ipSrc)
    domainDst = reverse_dns(ipDst)
    packet_dict[stream_id] = {
        'sumDelta': 0,
        'averageDelta': 0,
        'ipSrc': ipSrc,
        'ipDst': ipDst,
        'domainSrc': domainSrc,
        'domainDst': domainDst,
        'numberOfPackets': 1,
        'totalMbSize': get_packet_size(pkt),
        'startTime': timestamp,
        'endTime': timestamp,
        'protocol': protocol
    }


# Send a group of packets that seems to be together to the DB
def push_data(key):
    print('Push data: ' + str(packet_dict[key]))
    del packet_dict[key]['sumDelta']
    del packet_dict[key]['averageDelta']
    if (args.export == "mongo"):
        db.save_element(packet_dict[key], captureFileName.replace('.pcap', ''))
    else:
        csv_saver.save_element(packet_dict[key])


# Reverse DNS a remote IP
def reverse_dns(ip):
    try:
        reversed_dns = socket.gethostbyaddr(ip)
        return reversed_dns[0]
    except:
        return ""


# Arguments available
parser = argparse.ArgumentParser()
parser.add_argument('--captureFileName', '-cfn', default='capture.pcap',
                    help='The name of the pcap file to analyse, default: capture.pcap')
parser.add_argument('--export', '-e', default='csv',
                    help="The export mode you want to use: mongo or csv, default: csv")
args = parser.parse_args()

captureFileName = args.captureFileName
# Check if capture file exists
if not os.path.exists(captureFileName):
    raise Exception("File {} doesn't exist".format(captureFileName))

# Data structure
""" packet_dict = {
  stream_index: {
    'sumDelta': 0,
    'averageDelta': 0,
    'ip': ip,
    'domain': string,
    'numberOfPackets': 1,
    'totalMbSize': size in MB,
    'startTime': timestamp,
    'endTime': timestamp,
    'protocol': string
  }
} """
packet_dict = {}

# Connect to db if we are in the mongo export mode
if (args.export == "mongo"):
    environment.check_mongo_env()
    db.connect_to_db()

# Open the capture file
cap = pyshark.FileCapture(captureFileName)

# Launch capture file analysis
cap.apply_on_packets(analyse_packets)

# We push_data all the remaining streams in packet_dict
for key in packet_dict:
    push_data(key)

print('Analyse done')
