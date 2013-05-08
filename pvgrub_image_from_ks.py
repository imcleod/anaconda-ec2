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


import sys
from pvgrub_utils import generate_install_image

if len(sys.argv) != 3:
    print
    print "Create a pvgrub bootable image file for EC2"
    print
    print "usage: %s <ks_file> <image_file>" % sys.argv[0]
    print
    sys.exit(1)

generate_install_image(sys.argv[1], sys.argv[2])

