#!/usr/bin/python
import logging
import sys
from aws_utils import EBSHelper, AMIHelper
from pvgrub_utils import do_pw_sub

if len(sys.argv) != 7:
    print
    print "Create an AMI on EC2 by running a native installer contained in a pre-existing AMI"
    print
    print "usage: %s <ec2_region> <ec2_key> <ec2_secret> <install_ami> <install_script> <root_pw>" % sys.argv[0]
    print
    sys.exit(1)

region = sys.argv[1]
key = sys.argv[2]
secret = sys.argv[3]
install_ami = sys.argv[4]
install_script = sys.argv[5]
root_pw = sys.argv[6]

logging.basicConfig(level=logging.DEBUG, format='%(message)s')

ami_helper = AMIHelper(region, key, secret)

user_data = do_pw_sub(install_script, root_pw)
install_ami = ami_helper.launch_wait_snapshot(install_ami, user_data, 10)

print "Got AMI: %s" % install_ami
