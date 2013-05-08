#!/usr/bin/python
#   Copyright (C) 2013 Red Hat, Inc.
#   Copyright (C) 2013 Ian McLeod <imcleod@redhat.com>
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

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
