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
