#!/usr/bin/python
import logging
import sys
from aws_utils import EBSHelper, AMIHelper

if len(sys.argv) != 5:
    print
    print "Create an AMI on EC2 from a bootable image file"
    print
    print "usage: %s <ec2_region> <ec2_key> <ec2_secret> <image_file>" % sys.argv[0]
    print
    sys.exit(1)

region = sys.argv[1]
key = sys.argv[2]
secret = sys.argv[3]
image_file = sys.argv[4]

logging.basicConfig(level=logging.DEBUG, format='%(message)s')

ebs_helper = EBSHelper(region, key, secret)
snapshot = ebs_helper.safe_upload_and_shutdown(image_file)

ami_helper = AMIHelper(region, key, secret)
ami = ami_helper.register_ebs_ami(snapshot)

print "Got AMI: %s" % ami
